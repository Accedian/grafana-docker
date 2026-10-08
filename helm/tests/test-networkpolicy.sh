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
    '[]' 'null' '{}' '""' 'true' '1' \
    '[{}]' '[null]' '[true]' '[1]' '["nginx"]' \
    '[{"unknown":{}}]' '[{"podSelector":null}]' \
    '[{"namespaceSelector":true}]' '[{"podSelector":[]}]' \
    '[{"ipBlock":null}]' '[{"ipBlock":{}}]' \
    '[{"ipBlock":{"cidr":""}}]' '[{"ipBlock":{"cidr":1}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":null}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":"192.0.2.1/32"}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":{}}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":[null]}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":[1]}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"},"podSelector":{}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"},"namespaceSelector":{}}]' \
    '[{"podSelector":{}},{}]' \
    '[{"podSelector":{}},null]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":["192.0.2.1/32",null]}}]'; do
    if helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=$peers" \
        > /dev/null 2> "$rendered_chart"; then
        echo "Grafana NetworkPolicy accepted invalid peers: $peers" >&2
        exit 1
    fi
    grep -Fq 'grafana.networkPolicy.trustedIngress' "$rendered_chart"
done

# Kubernetes, not Helm, validates CIDR syntax. These invalid examples must
# survive rendering unchanged so API admission rejects them, not a chart parser.
# In particular, never silently remove an invalid restriction or later exception.
for cidr in not-a-cidr 192.0.2.0 192.0.2.0/33 256.0.2.0/24 \
            2001:db8::/129 2001:db8:::1/64 'fe80::1%eth0/64'; do
    for peers in \
        "[{\"ipBlock\":{\"cidr\":\"$cidr\"}}]" \
        "[{\"ipBlock\":{\"cidr\":\"0.0.0.0/0\",\"except\":[\"192.0.2.1/32\",\"$cidr\"]}}]"; do
        helm template grafana helm \
            --set grafana.networkPolicy.enabled=true \
            --set-json "grafana.networkPolicy.trustedIngress=$peers" \
            > "$rendered_chart"
        grep -Fq 'kind: NetworkPolicy' "$rendered_chart"
        grep -Fq -- "$cidr" "$rendered_chart"
        if [[ "$peers" == *'"except"'* ]]; then
            grep -Fq 'cidr: 0.0.0.0/0' "$rendered_chart"
            grep -Fq -- '- 192.0.2.1/32' "$rendered_chart"
        fi
    done
done

# Preserve IPv4/IPv6 boundary prefixes, compressed IPv6 and embedded IPv4.
for cidr in 0.0.0.0/0 192.0.2.0/24 255.255.255.255/32 \
            ::/0 ::1/128 2001:db8::/32 2001:DB8:0:1::/64 \
            1:2:3:4:5:6:7:8/128 ::1:2:3:4:5:6:7/128 \
            1:2:3:4:5:6:7::/128 ::192.0.2.1/128 ::ffff:192.0.2.1/128 \
            1:2:3:4:5:6:192.0.2.1/128; do
    helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-string "grafana.networkPolicy.trustedIngress[0].ipBlock.cidr=$cidr" \
        > "$rendered_chart"
    grep -Fq "cidr: $cidr" "$rendered_chart"
done

# Empty selectors are valid explicit Kubernetes peers, not missing selectors.
for peers in \
    '[{"podSelector":{}}]' '[{"namespaceSelector":{}}]' \
    '[{"podSelector":{},"namespaceSelector":{}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24"}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":[]}}]' \
    '[{"ipBlock":{"cidr":"192.0.2.0/24","except":["192.0.2.1/32","192.0.2.128/25"]}}]' \
    '[{"ipBlock":{"cidr":"2001:db8::/32","except":["2001:db8::/64","2001:db8::1/128"]}}]' \
    '[{"podSelector":{}},{"ipBlock":{"cidr":"192.0.2.0/24"}}]'; do
    helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=$peers" \
        > "$rendered_chart"
    grep -Fq 'kind: NetworkPolicy' "$rendered_chart"
    grep -Fq 'port: http' "$rendered_chart"
done

# Kubernetes also validates exception containment and address families. Preserve
# these invalid pairs for API validation rather than maintaining a Helm parser.
for pair in \
    '192.0.2.0/24|198.51.100.0/24' \
    '192.0.2.0/24|198.51.100.1/32' \
    '192.0.2.0/24|2001:db8::1/128' \
    '192.0.2.0/24|::ffff:192.0.2.1/128' \
    '192.0.2.0/24|192.0.2.0/24' \
    '192.0.2.0/24|192.0.2.128/24' \
    '192.0.2.0/24|192.0.0.0/16' \
    '192.0.2.128/25|192.0.2.127/32' \
    '192.0.2.0/25|192.0.2.128/32' \
    '192.0.2.1/32|192.0.2.1/32' \
    '0.0.0.0/0|0.0.0.0/0' \
    '2001:db8::/32|2001:db9::/64' \
    '2001:db8::/32|192.0.2.1/32' \
    '::ffff:192.0.2.0/120|192.0.2.1/32' \
    '2001:db8::/32|2001:0DB8:0:0:0:0:0:0/32' \
    '2001:db8::/32|2001:db8::/31' \
    '2001:db8:8000::/33|2001:db8:7fff::/128' \
    '2001:db8::/33|2001:db8:8000::/128' \
    '2001:db8::/127|2001:db8::2/128' \
    '2001:db8::1/128|2001:db8::1/128' \
    '::/0|::/0'; do
    IFS='|' read -r parent exception <<< "$pair"
    helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=[{\"ipBlock\":{\"cidr\":\"$parent\",\"except\":[\"$exception\"]}}]" \
        > "$rendered_chart"
    grep -Fq "cidr: $parent" "$rendered_chart"
    grep -Fq -- "- $exception" "$rendered_chart"
done

# Preserve a later exception and peer, not only the first valid subnet.
helm template grafana helm \
    --set grafana.networkPolicy.enabled=true \
    --set-json 'grafana.networkPolicy.trustedIngress=[{"podSelector":{}},{"ipBlock":{"cidr":"192.0.2.0/24","except":["192.0.2.1/32","198.51.100.1/32"]}}]' \
    > "$rendered_chart"
grep -Fq 'podSelector: {}' "$rendered_chart"
grep -Fq 'cidr: 192.0.2.0/24' "$rendered_chart"
grep -Fq -- '- 192.0.2.1/32' "$rendered_chart"
grep -Fq -- '- 198.51.100.1/32' "$rendered_chart"

# Preserve valid exception spellings, including partial octets and hextets.
for pair in \
    '0.0.0.0/0|255.255.255.255/32' \
    '192.0.2.128/25|192.0.2.128/26' \
    '192.0.2.128/25|192.0.2.255/32' \
    '192.0.2.0/25|192.0.2.127/32' \
    '192.0.2.0/31|192.0.2.1/32' \
    '192.0.2.129/25|192.0.2.255/32' \
    '::/0|ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff/128' \
    '::/0|::1/128' \
    '::/0|::192.0.2.1/128' \
    '2001:db8::/32|2001:0DB8:0000:0000:0000:0000:0000:0001/128' \
    '2001:0DB8:0:0:0:0:0:0/32|2001:db8::1/128' \
    '2001:db8:8000::/33|2001:db8:ffff::/48' \
    '2001:db8::/33|2001:db8:7fff::/128' \
    '2001:db8::/127|2001:db8::1/128' \
    '2001:db8::1/127|2001:db8::/128' \
    '::ffff:192.0.2.0/120|::ffff:c000:2ff/128' \
    '::ffff:c000:200/120|::ffff:192.0.2.255/128'; do
    IFS='|' read -r parent exception <<< "$pair"
    helm template grafana helm \
        --set grafana.networkPolicy.enabled=true \
        --set-json "grafana.networkPolicy.trustedIngress=[{\"ipBlock\":{\"cidr\":\"$parent\",\"except\":[\"$exception\"]}}]" \
        > "$rendered_chart"
    grep -Fq "cidr: $parent" "$rendered_chart"
    grep -Fq -- "- $exception" "$rendered_chart"
done

# Invalid unused peer settings must not alter the disabled deployment path.
helm template grafana helm \
    --set-json 'grafana.networkPolicy.trustedIngress=[{}, {"ipBlock":{"cidr":"not-a-cidr"}}, {"ipBlock":{"cidr":"192.0.2.0/24","except":["198.51.100.1/32"]}}]' \
    > "$rendered_chart"
if grep -Fq 'kind: NetworkPolicy' "$rendered_chart"; then
    echo "Disabled Grafana NetworkPolicy rendered with unused peers" >&2
    exit 1
fi
