#!/usr/bin/env bash

set -euo pipefail

rendered_chart="$(mktemp)"
trap 'rm -f "$rendered_chart"' EXIT

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
