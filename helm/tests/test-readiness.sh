#!/usr/bin/env bash

set -euo pipefail

rendered_chart="$(mktemp)"
trap 'rm -f "$rendered_chart"' EXIT

check_readiness() {
    helm template grafana helm --show-only templates/statefulset.yaml \
        "$@" > "$rendered_chart"

    local probe
    probe="$(awk '
        /^          readinessProbe:/ { reading = 1; next }
        reading && /^          [^ ]/ { exit }
        reading { print }
    ' "$rendered_chart")"

    grep -Fxq '            tcpSocket:' <<< "$probe"
    grep -Fxq '              port: http' <<< "$probe"
    grep -Fxq '            periodSeconds: 5' <<< "$probe"
    grep -Fxq '            timeoutSeconds: 1' <<< "$probe"
    grep -Fxq '            failureThreshold: 1' <<< "$probe"
    grep -Fq 'name: http' "$rendered_chart"
    grep -Fq 'containerPort: 3000' "$rendered_chart"

    # Readiness must not restart Grafana during the bounded discovery wait.
    if grep -Eq 'livenessProbe:|startupProbe:' "$rendered_chart"; then
        echo "Grafana discovery can be interrupted by a restart probe" >&2
        exit 1
    fi
}

check_readiness
check_readiness \
    --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.auth.genericOAuth.clientId=test-public-client
check_readiness \
    --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.auth.genericOAuth.clientIdDiscovery.url=http://skylight-aaa:12001/api/v1/onboarding/tenant-info \
    --set-string grafana.auth.genericOAuth.clientIdDiscovery.application=pca-grafana-pkce \
    --set grafana.auth.genericOAuth.clientIdDiscovery.timeoutSeconds=900
check_readiness \
    --set grafana.auth.genericOAuth.enabled=true \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=false
