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

# ConfigMap names use Kubernetes DNS-subdomain validation: 253 characters
# overall, with nonempty dot-separated segments bounded by alphanumerics.
# Unlike DNS-label resource names, these do not have a 63-character limit.
printf -v label64 '%064d' 0
printf -v name253 '%0253d' 0
printf -v segment63 '%063d' 0
dotted253="$segment63.$segment63.$segment63.${segment63:0:61}"
for profile in a 0 profile.prod profile-1.prod-2 "$label64" "$name253" "$dotted253"; do
    helm template grafana helm "${staged_values[@]}" \
        --set-string "grafana.auth.genericOAuth.activationConfigMap=$profile" \
        >/dev/null
done

for profile in invalid/name Profile profile_name .profile profile. \
               -profile profile- profile..prod profile.-prod profile-.prod \
               "${name253}0" "${dotted253}0"; do
    if helm template grafana helm "${staged_values[@]}" \
        --set-string "grafana.auth.genericOAuth.activationConfigMap=$profile" \
        > /dev/null 2> "$test_dir/invalid-profile.log"; then
        echo "invalid activation ConfigMap name accepted: $profile" >&2
        exit 1
    fi
    grep -Fq 'activationConfigMap must be a Kubernetes ConfigMap name' \
        "$test_dir/invalid-profile.log"
done

# Internal discovery must keep the public URL and mount only the selected CA.
for secret in nginx-tls-secret-cm nginx-tls-secret-hm; do
    for mode in full lite disabled; do
        extra_values=()
        if [ "$mode" = lite ]; then extra_values=(--set global.skylight_full_version=false); fi
        if [ "$mode" = disabled ]; then extra_values=(--set grafana.auth.genericOAuth.enabled=false); fi
        helm template grafana "$test_dir/chart" "${staged_values[@]}" \
            --set global.clusterIPPort=8443 \
            --set grafana.auth.genericOAuth.clientIdDiscovery.internalNginx=true \
            --set grafana.auth.genericOAuth.internalProvider.enabled=true \
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
    assert data["GF_AUTH_GENERIC_OAUTH_TOKEN_URL"] == (
        "https://grafana-oidc-provider.default.svc.cluster.local/oauth/v2/token"
    )
    assert data["GF_AUTH_GENERIC_OAUTH_API_URL"] == (
        "https://grafana-oidc-provider.default.svc.cluster.local/oidc/v1/userinfo"
    )
    assert data["GF_AUTH_GENERIC_OAUTH_AUTH_URL"] == "https://auth.accedian.local/oauth/v2/authorize"
    assert data["GRAFANA_OAUTH_END_SESSION_URL"] == "https://auth.accedian.local/oidc/v1/end_session"
    assert data["GF_AUTH_GENERIC_OAUTH_TLS_SKIP_VERIFY_INSECURE"] == "false"
    assert data["GF_AUTH_GENERIC_OAUTH_TLS_CLIENT_CA"] == "/etc/grafana-provider-ca/ca.crt"
    provider, = [v for v in pod["volumes"] if v["name"] == "grafana-provider-ca"]
    assert provider["secret"] == {"secretName": "grafana-oidc-provider-tls",
                                  "items": [{"key": "ca.crt", "path": "ca.crt"}]}
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
    assert "GF_AUTH_GENERIC_OAUTH_TLS_CLIENT_CA" not in data
    assert not [v for v in pod["volumes"] if v["name"] == "grafana-provider-ca"]
    assert not volumes and not mounts
    assert "GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT" not in data
    assert "GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE" not in data
PY
    done
done
