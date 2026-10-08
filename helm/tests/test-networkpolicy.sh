#!/usr/bin/env bash

set -euo pipefail

rendered_chart="$(mktemp)"
trap 'rm -f "$rendered_chart"' EXIT

helm template grafana helm > "$rendered_chart"
if grep -Fq 'kind: NetworkPolicy' "$rendered_chart"; then
    echo "Grafana NetworkPolicy rendered while disabled" >&2
    exit 1
fi

if helm template grafana helm \
    --set grafana.networkPolicy.enabled=true \
    >/dev/null 2>&1; then
    echo "Grafana NetworkPolicy accepted an empty ingress allowlist" >&2
    exit 1
fi

helm template grafana helm \
    --set grafana.networkPolicy.enabled=true \
    --set-string 'grafana.networkPolicy.trustedIngress[0].podSelector.matchLabels.app=nginx' \
    > "$rendered_chart"

grep -Fq 'kind: NetworkPolicy' "$rendered_chart"
grep -Fq 'app: nginx' "$rendered_chart"
grep -Fq 'port: http' "$rendered_chart"
