#!/usr/bin/env bash
# Container smoke test for Kubernetes customer alerting.
# Requires a built grafana-docker image. CI runs this after `make build`.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
IMAGE="${DOCKER_REPO_NAME:-gcr.io/npav-172917/}grafana:${DOCKER_VER:-$(whoami)-dev}"

if ! command -v docker >/dev/null 2>&1; then
  if [ "${REQUIRE_SMOKE:-0}" = "1" ]; then
    echo "docker is required for the Grafana alerting smoke test" >&2
    exit 1
  fi
  echo "Skipping Grafana alerting smoke test: docker is not available"
  exit 0
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  if [ "${REQUIRE_SMOKE:-0}" = "1" ]; then
    echo "image $IMAGE is required for the Grafana alerting smoke test" >&2
    exit 1
  fi
  echo "Skipping Grafana alerting smoke test: image $IMAGE is not present"
  exit 0
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"; docker rm -f grafana-alerting-smoke grafana-alerting-smoke-swarm >/dev/null 2>&1 || true' EXIT

mkdir -p "$workdir/secrets/smtp" "$workdir/secrets/security" "$workdir/data" "$workdir/swarm-data"
printf 'smtp-test-password\n' > "$workdir/secrets/smtp/password"
printf 'security-test-key\n' > "$workdir/secrets/security/secret-key"
chmod 0440 "$workdir/secrets/smtp/password" "$workdir/secrets/security/secret-key"
chown 472:472 "$workdir/secrets/smtp/password" "$workdir/secrets/security/secret-key" 2>/dev/null || \
  chown 0:472 "$workdir/secrets/smtp/password" "$workdir/secrets/security/secret-key" 2>/dev/null || true

cat > "$workdir/customer-contact-points.yaml" <<'EOF'
apiVersion: 1
contactPoints:
  - orgId: 1
    name: pca-customer-webhook
    receivers:
      - uid: pca-customer-webhook
        type: webhook
        settings:
          url: https://example.com/alert
          httpMethod: POST
          authorization_scheme: Bearer
          authorization_credentials: $PCA_GRAFANA_WEBHOOK_AUTH_SECRET
EOF

wait_healthy() {
  local name="$1"
  local i
  for i in $(seq 1 60); do
    if docker exec "$name" curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done
  echo "Grafana container $name did not become healthy" >&2
  docker logs "$name" >&2 || true
  return 1
}

docker run -d --name grafana-alerting-smoke \
  -e PCA_ENABLE_K8S_CUSTOMER_ALERTS=true \
  -e PCA_GRAFANA_WEBHOOK_AUTH_SECRET=hunter2-token \
  -e 'GF_SMTP_PASSWORD=$__file{/var/run/secrets/grafana-smtp/password}' \
  -e 'GF_SECURITY_SECRET_KEY=$__file{/var/run/secrets/grafana-security/secret-key}' \
  -v "$workdir/secrets/smtp:/var/run/secrets/grafana-smtp:ro" \
  -v "$workdir/secrets/security:/var/run/secrets/grafana-security:ro" \
  -v "$workdir/customer-contact-points.yaml:/tmp/provisioning/alerting/customer-contact-points.yaml:ro" \
  -v "$workdir/data:/var/lib/grafana" \
  "$IMAGE" >/dev/null

wait_healthy grafana-alerting-smoke

docker exec grafana-alerting-smoke test -f /var/lib/grafana/provisioning/alerting/customer-k8s-alerts.yaml
docker exec grafana-alerting-smoke grep -F 'folder: Customer Alerts (k8s)' \
  /var/lib/grafana/provisioning/alerting/customer-k8s-alerts.yaml
if docker exec grafana-alerting-smoke grep -F 'folder: Customer (k8s)' \
  /var/lib/grafana/provisioning/alerting/customer-k8s-alerts.yaml; then
  echo "K8s customer alerts used the dashboard folder name" >&2
  exit 1
fi

logs="$(docker logs grafana-alerting-smoke 2>&1)"
if grep -Fq 'hunter2-token' <<<"$logs"; then
  echo "Webhook secret leaked into Grafana logs" >&2
  exit 1
fi
if grep -Fq 'smtp-test-password' <<<"$logs"; then
  echo "SMTP password leaked into Grafana logs" >&2
  exit 1
fi
if grep -Fq 'security-test-key' <<<"$logs"; then
  echo "Grafana secret key leaked into Grafana logs" >&2
  exit 1
fi

docker run -d --name grafana-alerting-smoke-swarm \
  -v "$workdir/swarm-data:/var/lib/grafana" \
  "$IMAGE" >/dev/null

wait_healthy grafana-alerting-smoke-swarm

if docker exec grafana-alerting-smoke-swarm test -f /var/lib/grafana/provisioning/alerting/customer-k8s-alerts.yaml; then
  echo "Swarm-style start loaded Kubernetes customer alerts" >&2
  exit 1
fi

echo "Grafana alerting smoke test passed against $IMAGE"
