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

for peers in \
    '{}' '[{}]' '[null]' '[true]' '[1]' '["nginx"]' \
    '[{"unknown":{}}]' '[{"podSelector":null}]' \
    '[{"namespaceSelector":true}]' '[{"podSelector":[]}]' \
    '[{"ipBlock":null}]' '[{"ipBlock":{}}]' \
    '[{"ipBlock":{"cidr":""}}]' '[{"ipBlock":{"cidr":1}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"},"podSelector":{}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"},"namespaceSelector":{}}]' \
    '[{"podSelector":{}},{}]'; do
    if helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=$peers" \
        > /dev/null 2> "$rendered_chart"; then
        echo "Grafana NetworkPolicy accepted invalid peers: $peers" >&2
        exit 1
    fi
    grep -Fq 'grafana.networkPolicy.trustedIngress' "$rendered_chart"
done

# Empty selectors are valid explicit Kubernetes peers, not missing selectors.
for peers in \
    '[{"podSelector":{}}]' '[{"namespaceSelector":{}}]' \
    '[{"podSelector":{},"namespaceSelector":{}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"}}]' \
    '[{"podSelector":{}},{"ipBlock":{"cidr":"192.0.2.0/24"}}]'; do
    helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=$peers" \
        > "$rendered_chart"
    grep -Fq 'kind: NetworkPolicy' "$rendered_chart"
    grep -Fq 'port: http' "$rendered_chart"
done

# Invalid unused peer settings must not alter the disabled deployment path.
helm template grafana helm --set-json 'grafana.networkPolicy.trustedIngress=[{}]' \
    > "$rendered_chart"
if grep -Fq 'kind: NetworkPolicy' "$rendered_chart"; then
    echo "Disabled Grafana NetworkPolicy rendered with unused peers" >&2
    exit 1
fi
