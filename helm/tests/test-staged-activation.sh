#!/usr/bin/env bash
set -euo pipefail

test_dir=$(mktemp -d)
trap 'rm -rf -- "$test_dir"' EXIT
rendered_chart="$test_dir/rendered.json"
# Keep the inspector outside the shipped templates; test a disposable copy.
cp -R helm "$test_dir/chart"
cp helm/tests/staged-activation-probe.yaml "$test_dir/chart/templates/"
staged_values=(
    --set grafana.auth.genericOAuth.enabled=true
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true
    --set global.skylight_full_version=true
    --set-string grafana.auth.genericOAuth.activationConfigMap=grafana-oidc-activation
    --set-string grafana.publicOriginConfigMap=grafana-public-origin
)
for mode in defaults placeholders; do
    extra_values=()
    if [ "$mode" = placeholders ]; then
        extra_values=(
            --set-string global.analytics.deployment.name=from_env_file_TF_VAR_deployment_name
            --set-string global.analytics.deployment.domain=from_env_file_DOMAIN_NAME
            --set global.dns.support=false
            --set-string global.external_ip=
        )
    fi
    helm template grafana "$test_dir/chart" "${staged_values[@]}" "${extra_values[@]}" \
        --show-only templates/staged-activation-probe.yaml > "$rendered_chart"
python3 -S - "$rendered_chart" <<'PY'
import json
import sys

# Helm adds document/source headers before the compact JSON probe.
with open(sys.argv[1]) as rendered:
    resources = json.loads(next(line for line in rendered if line.startswith("{")))
config = resources["config"]
assert config["kind"] == "ConfigMap"
assert config["metadata"]["name"] == "grafana-config"
assert config["data"]["GF_AUTH_GENERIC_OAUTH_ENABLED"] == "false"
assert config["data"]["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
assert config["data"]["GF_AUTH_PROXY_ENABLED"] == "false"
assert config["data"]["GF_AUTH_BASIC_ENABLED"] == "true"
statefulset = resources["statefulset"]
assert statefulset["kind"] == "StatefulSet"
sources = statefulset["spec"]["template"]["spec"]["containers"][0]["envFrom"]
assert sources == [
    {"configMapRef": {"name": "grafana-config"}},
    {"configMapRef": {"name": "grafana-oidc-activation", "optional": True}},
]
assert statefulset["metadata"]["annotations"]["reloader.stakater.com/auto"] == "true"
PY
done

# Even on a staged baseline, an explicitly configured origin is not a placeholder.
for origin in http://example.test https://example.test/path https://example.test:0; do
    if helm template grafana helm "${staged_values[@]}" \
        --set-string "grafana.publicOrigin=$origin" >/dev/null 2>&1; then
        echo "staged OAuth accepted invalid explicit origin: $origin" >&2
        exit 1
    fi
done

# Neither disabled OAuth nor analytics-lite may consume an activation profile.
for disabled in '--set grafana.auth.genericOAuth.enabled=false' \
                '--set global.skylight_full_version=false'; do
    # Intentional shell splitting of the two fixed test arguments.
    helm template grafana helm \
        --set grafana.auth.genericOAuth.enabled=true \
        --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
        --set global.skylight_full_version=true \
        --set-string grafana.auth.genericOAuth.activationConfigMap=grafana-oidc-activation \
        $disabled > "$rendered_chart"
    if grep -Fq 'name: "grafana-oidc-activation"' "$rendered_chart"; then
        echo 'disabled OAuth consumed an activation profile' >&2
        exit 1
    fi
done

if helm template grafana helm --set grafana.auth.genericOAuth.enabled=true \
    --set-string 'grafana.auth.genericOAuth.activationConfigMap=invalid/name' \
    >/dev/null 2>&1; then
    echo 'invalid activation ConfigMap name accepted' >&2
    exit 1
fi

# Internal discovery must keep the public URL and mount only the selected CA.
for secret in nginx-tls-secret-cm nginx-tls-secret-hm; do
    for mode in full lite disabled; do
        extra_values=()
        if [ "$mode" = lite ]; then extra_values=(--set global.skylight_full_version=false); fi
        if [ "$mode" = disabled ]; then extra_values=(--set grafana.auth.genericOAuth.enabled=false); fi
        helm template grafana "$test_dir/chart" "${staged_values[@]}" \
            --set global.clusterIPPort=8443 \
            --set grafana.auth.genericOAuth.clientIdDiscovery.internalNginx=true \
            --set-string "grafana.auth.genericOAuth.clientIdDiscovery.tlsCASecretName=$secret" \
            "${extra_values[@]}" --show-only templates/staged-activation-probe.yaml > "$rendered_chart"
        python3 -S - "$rendered_chart" "$secret" "$mode" <<'PY'
import json
import sys

with open(sys.argv[1]) as rendered:
    resources = json.loads(next(line for line in rendered if line.startswith("{")))
data = resources["config"]["data"]
pod = resources["statefulset"]["spec"]["template"]["spec"]
volumes = [v for v in pod["volumes"] if v["name"] == "grafana-discovery-ca"]
mounts = [v for v in pod["containers"][0]["volumeMounts"] if v["name"] == "grafana-discovery-ca"]
if sys.argv[3] == "full":
    assert data["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT"] == "8443"
    assert data["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL"] == (
        "https://deployment.accedian.local/api/v1/onboarding/tenant-info"
    )
    assert data["GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE"] == "/etc/grafana-discovery-ca/ca.crt"
    assert volumes == [{"name": "grafana-discovery-ca", "secret": {
        "secretName": sys.argv[2], "items": [{"key": "ca.crt", "path": "ca.crt"}]}}]
    assert mounts == [{"name": "grafana-discovery-ca",
        "mountPath": "/etc/grafana-discovery-ca", "readOnly": True}]
else:
    assert not volumes and not mounts
    assert "GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT" not in data
    assert "GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE" not in data
PY
    done
done
