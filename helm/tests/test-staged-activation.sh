#!/usr/bin/env bash
set -euo pipefail

rendered_chart=$(mktemp)
trap 'rm -f "$rendered_chart"' EXIT
helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=true \
    --set-string grafana.auth.genericOAuth.activationConfigMap=grafana-oidc-activation \
    > "$rendered_chart"
python3 - "$rendered_chart" <<'PY'
import sys
import yaml

resources = list(yaml.safe_load_all(open(sys.argv[1])))
config = next(r for r in resources if r.get("kind") == "ConfigMap"
              and r["metadata"]["name"] == "grafana-config")
assert config["data"]["GF_AUTH_GENERIC_OAUTH_ENABLED"] == "false"
assert config["data"]["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
assert config["data"]["GF_AUTH_PROXY_ENABLED"] == "false"
assert config["data"]["GF_AUTH_BASIC_ENABLED"] == "true"
statefulset = next(r for r in resources if r.get("kind") == "StatefulSet")
sources = statefulset["spec"]["template"]["spec"]["containers"][0]["envFrom"]
assert sources == [
    {"configMapRef": {"name": "grafana-config"}},
    {"configMapRef": {"name": "grafana-oidc-activation", "optional": True}},
]
assert statefulset["metadata"]["annotations"]["reloader.stakater.com/auto"] == "true"
PY

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
