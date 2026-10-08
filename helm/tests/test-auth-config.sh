#!/usr/bin/env bash

set -euo pipefail

rendered_chart="$(mktemp)"
trap 'rm -f "$rendered_chart"' EXIT

# Umbrella build defaults are unresolved placeholders, not browser origins.
placeholder_values=(
    --set-string global.analytics.deployment.name=from_env_file_TF_VAR_deployment_name
    --set-string global.analytics.deployment.domain=from_env_file_DOMAIN_NAME
    --set global.dns.support=false
    --set-string global.external_ip=
)
for mode in disabled lite; do
    mode_values=(--set grafana.auth.genericOAuth.enabled=false)
    if [ "$mode" = lite ]; then
        mode_values=(
            --set grafana.auth.genericOAuth.enabled=true
            --set grafana.auth.genericOAuth.fullDeploymentOnly=true
            --set global.skylight_full_version=false
        )
    fi
    helm template grafana helm "${placeholder_values[@]}" "${mode_values[@]}" \
        > "$rendered_chart"
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "false"' "$rendered_chart"
    grep -Fq 'GF_SERVER_ROOT_URL: "https://from_env_file_TF_VAR_deployment_name.from_env_file_DOMAIN_NAME/grafana"' "$rendered_chart"
done
if helm template grafana helm "${placeholder_values[@]}" \
    --set grafana.auth.genericOAuth.enabled=true >/dev/null 2>&1; then
    echo 'active OAuth accepted an invalid derived browser origin' >&2
    exit 1
fi

# The parent ConfigMap overrides browser settings, not discovery or issuer URLs.
helm template grafana helm "${placeholder_values[@]}" \
    --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.publicOriginConfigMap=parent-grafana-origin > "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "true"' "$rendered_chart"
grep -Fq 'name: "parent-grafana-origin"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST: "from_env_file_TF_VAR_deployment_name.from_env_file_DOMAIN_NAME"' "$rendered_chart"

printf -v max_label '%63s' ''
max_label="${max_label// /a}"
max_host="$max_label.$max_label.$max_label.${max_label:0:61}"

# Browser origin overrides must not select a different AAA tenant or issuer.
for origin in https://Grafana.example.test:8443 https://192.0.2.20:9443 \
    https://localhost https://xn--bcher-kva.example https://123.example \
    https://grafana.example. https://0.0.0.0:1 https://255.255.255.255:65535 \
    "https://$max_label.example" "https://$max_host" "https://$max_host."; do
    helm template grafana helm \
        --set grafana.auth.genericOAuth.enabled=true \
        --set-string "grafana.publicOrigin=$origin" > "$rendered_chart"
    grep -Fq "GF_SERVER_ROOT_URL: \"$origin/grafana\"" "$rendered_chart"
    grep -Fq "GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL: \"$origin/grafana/\"" "$rendered_chart"
    hostname="${origin#https://}"
    hostname="${hostname%%:*}"
    grep -Fq "GF_SERVER_DOMAIN: \"$hostname\"" "$rendered_chart"
    grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST: "deployment.accedian.local"' "$rendered_chart"
    grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL: "https://deployment.accedian.local/api/v1/onboarding/tenant-info"' "$rendered_chart"
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_AUTH_URL: "https://auth.accedian.local/oauth/v2/authorize"' "$rendered_chart"
done

# Character allow-lists alone do not establish a DNS name or IPv4 address.
invalid_hosts=(
    -grafana.example grafana-.example example..test .example.test example.test..
    . - bad_host.example "$max_label"a.example "$max_host"a
    999.999.999.999 192.0.2.256 256.0.2.1 192.256.2.1 192.0.256.1
    192.0.2 192.0.2.1.5 192.00.2.1 123 '[2001:db8::1]'
)
for host in "${invalid_hosts[@]}"; do
    for enabled in true false; do
        for override in '' parent-grafana-origin; do
            if helm template grafana helm \
                --set "grafana.auth.genericOAuth.enabled=$enabled" \
                --set-string "grafana.publicOriginConfigMap=$override" \
                --set-string "grafana.publicOrigin=https://$host:8443" \
                > /dev/null 2>&1; then
                echo "accepted invalid Grafana public hostname: $host" >&2
                exit 1
            fi
        done
    done
    # Active OAuth must also reject malformed deployment-derived origins.
    if helm template grafana helm --set grafana.auth.genericOAuth.enabled=true \
        --set global.dns.support=false --set-string "global.external_ip=$host" \
        > /dev/null 2>&1; then
        echo "accepted invalid derived Grafana public hostname: $host" >&2
        exit 1
    fi
done
for origin in http://example.test https://example.test/ https://example.test/path \
    https://user@example.test 'https://example.test?x=1' 'https://example.test#x' \
    https://example.test: https://example.test:0 https://example.test:65536 \
    'https://example.test;return 200'; do
    if helm template grafana helm --set-string "grafana.publicOrigin=$origin" \
        >/dev/null 2>&1; then
        echo "accepted invalid Grafana public origin: $origin" >&2
        exit 1
    fi
done

# An external override must never suppress validation of an explicit origin.
for enabled in true false; do
    for origin in http://example.test https://example.test/path https://example.test:0; do
        if helm template grafana helm "${placeholder_values[@]}" \
            --set "grafana.auth.genericOAuth.enabled=$enabled" \
            --set-string grafana.publicOriginConfigMap=parent-grafana-origin \
            --set-string "grafana.publicOrigin=$origin" >/dev/null 2>&1; then
            echo 'parent ConfigMap bypassed explicit browser-origin validation' >&2
            exit 1
        fi
    done
done

helm template grafana helm --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.publicOriginConfigMap=parent-grafana-origin > "$rendered_chart"
grep -Fq 'name: "parent-grafana-origin"' "$rendered_chart"
helm template grafana helm --set grafana.auth.genericOAuth.enabled=false \
    --set-string grafana.publicOriginConfigMap=parent-grafana-origin > "$rendered_chart"
if grep -Fq 'name: "parent-grafana-origin"' "$rendered_chart"; then
    echo "inactive OAuth consumed the parent origin override" >&2
    exit 1
fi

oauth_values=(
    --set grafana.auth.genericOAuth.enabled=true
    --set-string grafana.auth.genericOAuth.clientId=test-public-client
    --set-string grafana.auth.genericOAuth.authUrl=https://auth.example.test/oauth/v2/authorize
    --set-string grafana.auth.genericOAuth.tokenUrl=https://auth.example.test/oauth/v2/token
    --set-string grafana.auth.genericOAuth.apiUrl=https://auth.example.test/oidc/v1/userinfo
    --set-string grafana.auth.genericOAuth.endSessionUrl=https://auth.example.test/oidc/v1/end_session
    --set-string grafana.auth.genericOAuth.postLogoutRedirectUrl=https://performance.example.test/grafana/
)

helm template grafana helm "${oauth_values[@]}" > "$rendered_chart"

grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "true"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_ID_TOKEN_ATTRIBUTE_NAME: "__disabled_id_token"' "$rendered_chart"
grep -Fq 'GF_AUTH_PROXY_ENABLED: "false"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_END_SESSION_URL: "https://auth.example.test/oidc/v1/end_session"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL: "https://performance.example.test/grafana/"' "$rendered_chart"

if grep -Fq 'GF_AUTH_GENERIC_OAUTH_VALIDATE_ID_TOKEN' "$rendered_chart" ||
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_JWK_SET_URL' "$rendered_chart"; then
    echo "unsupported Grafana 12.1 Generic OAuth settings were rendered" >&2
    exit 1
fi

# Active OAuth must forbid anonymous access even when explicitly requested.
# Inactive OAuth must preserve both anonymous settings, including lite mode.
for anonymous_enabled in true false; do
    for full_deployment_only in true false; do
        helm template grafana helm "${oauth_values[@]}" \
            --set "grafana.auth.anonymous.enabled=${anonymous_enabled}" \
            --set "grafana.auth.genericOAuth.fullDeploymentOnly=${full_deployment_only}" \
            --set global.skylight_full_version=true > "$rendered_chart"
        grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "true"' "$rendered_chart"
        grep -Fq 'GF_AUTH_ANONYMOUS_ENABLED: "false"' "$rendered_chart"
    done

    helm template grafana helm \
        --set grafana.auth.genericOAuth.enabled=false \
        --set "grafana.auth.anonymous.enabled=${anonymous_enabled}" > "$rendered_chart"
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "false"' "$rendered_chart"
    grep -Fq "GF_AUTH_ANONYMOUS_ENABLED: \"${anonymous_enabled}\"" "$rendered_chart"

    helm template grafana helm \
        --set grafana.auth.genericOAuth.enabled=true \
        --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
        --set global.skylight_full_version=false \
        --set "grafana.auth.anonymous.enabled=${anonymous_enabled}" > "$rendered_chart"
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "false"' "$rendered_chart"
    grep -Fq "GF_AUTH_ANONYMOUS_ENABLED: \"${anonymous_enabled}\"" "$rendered_chart"
done

for endpoint in authUrl tokenUrl apiUrl; do
    if helm template grafana helm "${oauth_values[@]}" \
        --set-string "grafana.auth.genericOAuth.${endpoint}=http://auth.example.test/insecure" \
        >/dev/null 2>&1; then
        echo "generic OAuth accepted insecure ${endpoint}" >&2
        exit 1
    fi
done

for endpoint in endSessionUrl postLogoutRedirectUrl; do
    if helm template grafana helm "${oauth_values[@]}" \
        --set-string "grafana.auth.genericOAuth.${endpoint}=http://auth.example.test/insecure" \
        >/dev/null 2>&1; then
        echo "generic OAuth accepted insecure ${endpoint}" >&2
        exit 1
    fi
done

helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.auth.genericOAuth.clientId=test-public-client \
    --set-string global.analytics.deployment.name=performance \
    --set-string global.analytics.deployment.domain=example.test \
    > "$rendered_chart"

grep -Fq 'GF_SERVER_ROOT_URL: "https://performance.example.test/grafana"' "$rendered_chart"
grep -Fq 'GF_SERVER_DOMAIN: "performance.example.test"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_AUTH_URL: "https://auth.example.test/oauth/v2/authorize"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_TOKEN_URL: "https://auth.example.test/oauth/v2/token"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_API_URL: "https://auth.example.test/oidc/v1/userinfo"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_END_SESSION_URL: "https://auth.example.test/oidc/v1/end_session"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL: "https://performance.example.test/grafana/"' "$rendered_chart"

helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set-string grafana.auth.genericOAuth.clientId=test-public-client \
    --set global.dns.support=false \
    --set-string global.external_ip=192.0.2.10 \
    --set global.clusterIPPortZitadelAuth=3443 \
    > "$rendered_chart"

grep -Fq 'GF_SERVER_ROOT_URL: "https://192.0.2.10/grafana"' "$rendered_chart"
grep -Fq 'GF_SERVER_DOMAIN: "192.0.2.10"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_AUTH_URL: "https://192.0.2.10:3443/oauth/v2/authorize"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_TOKEN_URL: "https://192.0.2.10:3443/oauth/v2/token"' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_API_URL: "https://192.0.2.10:3443/oidc/v1/userinfo"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_END_SESSION_URL: "https://192.0.2.10:3443/oidc/v1/end_session"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL: "https://192.0.2.10/grafana/"' "$rendered_chart"

discovery_values=(
    --set grafana.auth.genericOAuth.enabled=true
    --set-string grafana.auth.genericOAuth.clientIdDiscovery.url=http://skylight-aaa:12001/api/v1/onboarding/tenant-info
)

helm template grafana helm --set grafana.auth.genericOAuth.enabled=true \
    --set-string global.analytics.deployment.name=Tenant-Blue > "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL: "https://Tenant-Blue.accedian.local/api/v1/onboarding/tenant-info"' "$rendered_chart"

helm template grafana helm --set grafana.auth.genericOAuth.enabled=true \
    --set global.dns.support=false --set-string global.external_ip=192.0.2.10 \
    > "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL: "https://192.0.2.10/api/v1/onboarding/tenant-info"' "$rendered_chart"

helm template grafana helm "${discovery_values[@]}" \
    --set-string global.analytics.deployment.name=Tenant-Blue \
    > "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST: "Tenant-Blue.accedian.local"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL: "http://skylight-aaa:12001/api/v1/onboarding/tenant-info"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION: "pca-grafana-pkce"' "$rendered_chart"

helm template grafana helm "${discovery_values[@]}" \
    --set-string global.analytics.deployment.name=Tenant-Blue \
    --set-string grafana.auth.genericOAuth.clientIdDiscovery.host=canonical.example \
    > "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST: "canonical.example"' "$rendered_chart"


# Analytics-lite has no Zitadel gateway. It must keep local Grafana login
# without rendering any OAuth discovery or auto-login settings.
helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=false \
    > "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "false"' "$rendered_chart"
grep -Fq 'GF_AUTH_BASIC_ENABLED: "true"' "$rendered_chart"
grep -Fq 'GF_AUTH_ANONYMOUS_ENABLED: "false"' "$rendered_chart"
if grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL:' "$rendered_chart" ||
    grep -Fq 'GF_AUTH_GENERIC_OAUTH_AUTO_LOGIN:' "$rendered_chart"; then
    echo "analytics-lite rendered Zitadel OAuth configuration" >&2
    exit 1
fi

helm template grafana helm "${discovery_values[@]}" \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=true \
    > "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_ENABLED: "true"' "$rendered_chart"
grep -Fq 'GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL:' "$rendered_chart"
grep -Fq 'GF_AUTH_GENERIC_OAUTH_AUTO_LOGIN: "true"' "$rendered_chart"

helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=false \
    --show-only templates/statefulset.yaml > "$rendered_chart"
lite_checksum="$(awk '/checksum\/config:/ {print $2}' "$rendered_chart")"

helm template grafana helm \
    --set grafana.auth.genericOAuth.enabled=true \
    --set grafana.auth.genericOAuth.fullDeploymentOnly=true \
    --set global.skylight_full_version=true \
    --set-string grafana.auth.genericOAuth.clientId=test-public-client \
    --show-only templates/statefulset.yaml > "$rendered_chart"
full_checksum="$(awk '/checksum\/config:/ {print $2}' "$rendered_chart")"
if [ -z "$lite_checksum" ] || [ -z "$full_checksum" ] ||
    [ "$lite_checksum" = "$full_checksum" ]; then
    echo "Grafana OAuth mode changes do not trigger a pod rollout" >&2
    exit 1
fi
