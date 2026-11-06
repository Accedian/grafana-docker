#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
test_directory="$(mktemp -d)"
trap 'rm -rf "$test_directory"' EXIT

mkdir -p "$test_directory/bin"

cat > "$test_directory/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

for expected_argument in \
    --proto '=https' \
    "$DISCOVERY_EXPECTED_URL" \
    "Host: performance.example.test" \
    "X-Forwarded-Server: performance.example.test"; do
    found=false
    for argument in "$@"; do
        if [ "$argument" = "$expected_argument" ]; then
            found=true
            break
        fi
    done
    if [ "$found" != true ]; then
        echo "Missing AAA discovery argument: $expected_argument" >&2
        exit 2
    fi
done

if [ -n "${DISCOVERY_EXPECTED_CONNECT_TO:-}" ]; then
    for expected in --noproxy '*' --connect-to "$DISCOVERY_EXPECTED_CONNECT_TO" \
        --cacert "$GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE"; do
        found=false
        for argument in "$@"; do
            if [ "$argument" = "$expected" ]; then found=true; fi
        done
        [ "$found" = true ] || exit 2
    done
fi

call_count=0
if [ -s "$DISCOVERY_CALL_COUNT_FILE" ]; then
    read -r call_count < "$DISCOVERY_CALL_COUNT_FILE"
fi
call_count=$((call_count + 1))
printf '%s\n' "$call_count" > "$DISCOVERY_CALL_COUNT_FILE"

case "$DISCOVERY_TEST_SCENARIO" in
    unready-then-valid)
        if [ "$call_count" -eq 1 ]; then
            printf '%s\n' "$DISCOVERY_INVALID_BODY"
        else
            printf '%s\n' "$DISCOVERY_VALID_BODY"
        fi
        ;;
    invalid-then-valid)
        case "$call_count" in
            1) exit 0 ;;
            2) printf '%s\n' 'not a valid client ID' ;;
            *) printf '%s\n' '{"data":{"type":"tenant-info","attributes":{"tenantId":"AAA_ROOT","zitadelAuth":true,"zitadelConfig":{"clients":[{"name":"pca-grafana-pkce","appId":"app-id","clientId":"public-client-id"}]}}}}' ;;
        esac
        ;;
    http-error-then-valid)
        if [ "$call_count" -eq 1 ]; then
            exit 22
        fi
        printf '%s\n' '{"data":{"type":"tenant-info","attributes":{"tenantId":"AAA_ROOT","zitadelAuth":true,"zitadelConfig":{"clients":[{"name":"pca-grafana-pkce","appId":"app-id","clientId":"public-client-id"}]}}}}'
        ;;
    oversized-then-valid)
        if [ "$call_count" -eq 1 ]; then
            printf '%131072s' ''
        else
            printf '%s\n' '{"data":{"type":"tenant-info","attributes":{"tenantId":"AAA_ROOT","zitadelAuth":true,"zitadelConfig":{"clients":[{"name":"pca-grafana-pkce","appId":"app-id","clientId":"public-client-id"}]}}}}'
        fi
        ;;
    always-invalid)
        printf '%s\n' 'not a valid client ID'
        ;;
    *)
        echo "Unknown discovery test scenario" >&2
        exit 2
        ;;
esac
EOF

cat > "$test_directory/bin/sleep" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

chmod +x "$test_directory/bin/curl" "$test_directory/bin/sleep"

# shellcheck source=../oauth-client-discovery.sh
. "$repository_root/oauth-client-discovery.sh"

export PATH="$test_directory/bin:$PATH"
export DISCOVERY_CALL_COUNT_FILE="$test_directory/call-count"
export GF_AUTH_GENERIC_OAUTH_ENABLED=true
export DISCOVERY_EXPECTED_URL=https://performance.example.test/api/v1/onboarding/tenant-info
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL="$DISCOVERY_EXPECTED_URL"
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST=performance.example.test
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION=pca-grafana-pkce
export DISCOVERY_VALID_BODY='{"data":{"type":"tenant-info","attributes":{"tenantId":"AAA_ROOT","zitadelAuth":true,"zitadelConfig":{"clients":[{"name":"pca-grafana-pkce","appId":"app-id","clientId":"public-client-id"}]}}}}'
export GRAFANA_OAUTH_END_SESSION_URL=https://auth.example.test/oidc/v1/end_session
export GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL=https://performance.example.test/grafana/

for change in \
    '.data.attributes.tenantId = "child-tenant"' \
    '.data.attributes.zitadelAuth = false' \
    '.data.attributes.zitadelConfig.clients = []' \
    '.data.attributes.zitadelConfig.clients |= . + .' \
    '.data.attributes.zitadelConfig.clients[0].appId = ""' \
    '.data.attributes.zitadelConfig.clients[0].clientId = ""'; do
    DISCOVERY_INVALID_BODY="$(jq "$change" <<< "$DISCOVERY_VALID_BODY")"
    export DISCOVERY_INVALID_BODY
    export DISCOVERY_TEST_SCENARIO=unready-then-valid
    : > "$DISCOVERY_CALL_COUNT_FILE"
    unset GF_AUTH_GENERIC_OAUTH_CLIENT_ID
    resolve_generic_oauth_client_id
    [ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = public-client-id ]
    [ "$(< "$DISCOVERY_CALL_COUNT_FILE")" = 2 ]
done

# OAuth off leaves the legacy CAS/local path untouched, with no discovery call.
export GF_AUTH_GENERIC_OAUTH_ENABLED=false
: > "$DISCOVERY_CALL_COUNT_FILE"
unset GF_AUTH_GENERIC_OAUTH_CLIENT_ID
resolve_generic_oauth_client_id
[ ! -s "$DISCOVERY_CALL_COUNT_FILE" ]
export GF_AUTH_GENERIC_OAUTH_ENABLED=true

# Standalone Generic OAuth must not require managed discovery or logout settings.
for signout in '' 'https://other-idp.example.test/logout?return=home'; do
    (
        for setting in ${!GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_@} \
            GRAFANA_OAUTH_END_SESSION_URL GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL; do
            unset "$setting"
        done
        export GF_AUTH_GENERIC_OAUTH_CLIENT_ID='standalone/client'
        if [ -n "$signout" ]; then
            export GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL="$signout"
        else
            unset GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL
        fi
        : > "$DISCOVERY_CALL_COUNT_FILE"
        configure_generic_oauth
        [ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = 'standalone/client' ]
        [ "${GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL:-}" = "$signout" ]
        [ ! -s "$DISCOVERY_CALL_COUNT_FILE" ]
    )
done

# A partially supplied managed configuration must not become standalone OAuth.
for marker in GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL \
    GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_HOST \
    GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION \
    GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS \
    GRAFANA_OAUTH_END_SESSION_URL GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL; do
    (
        for setting in ${!GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_@} \
            GRAFANA_OAUTH_END_SESSION_URL GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL; do
            unset "$setting"
        done
        export GF_AUTH_GENERIC_OAUTH_CLIENT_ID=static-client
        unset GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL
        export "$marker=partial"
        if configure_generic_oauth; then
            echo "Partial managed OAuth configuration unexpectedly succeeded" >&2
            exit 1
        fi
        [ -z "${GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL:-}" ]
    )
done

expected_signout_redirect_url='https://auth.example.test/oidc/v1/end_session?client_id=public-client-id&post_logout_redirect_uri=https%3A%2F%2Fperformance.example.test%2Fgrafana%2F'

reset_discovery_test() {
    : > "$DISCOVERY_CALL_COUNT_FILE"
    unset GF_AUTH_GENERIC_OAUTH_CLIENT_ID
    unset GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL
    SECONDS=0
}

# Route canonical HTTPS discovery without changing trusted tenant headers.
export DISCOVERY_EXPECTED_URL=https://performance.example.test:9443/api/v1/onboarding/tenant-info
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL="$DISCOVERY_EXPECTED_URL"
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT=8443
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE="$test_directory/discovery-ca.crt"
printf '%s\n' 'fixture CA bundle' > "$GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE"
export DISCOVERY_EXPECTED_CONNECT_TO=performance.example.test:9443:nginx-service:8443
export DISCOVERY_TEST_SCENARIO=http-error-then-valid
reset_discovery_test
resolve_generic_oauth_client_id
[ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = public-client-id ]

for port in 0 65536 invalid '443;echo'; do
    reset_discovery_test
    export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT="$port"
    if resolve_generic_oauth_client_id; then exit 1; fi
    [ ! -s "$DISCOVERY_CALL_COUNT_FILE" ]
done
unset DISCOVERY_EXPECTED_CONNECT_TO GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT
unset GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_CA_FILE
for nginx_port in '' 8443; do
    for discovery_url in \
        http://performance.example.test/api/v1/onboarding/tenant-info \
        ftp://performance.example.test/tenant-info file:///tmp/tenant-info \
        https://user@performance.example.test/tenant-info \
        'https://performance.example.test/tenant-info?x=1' \
        'https://performance.example.test/tenant-info#fragment' \
        https://performance.example.test:0/tenant-info \
        https://performance.example.test:65536/tenant-info; do
        reset_discovery_test
        export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT="$nginx_port"
        export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL="$discovery_url"
        if resolve_generic_oauth_client_id; then
            echo "Invalid discovery URL unexpectedly succeeded" >&2
            exit 1
        fi
        [ ! -s "$DISCOVERY_CALL_COUNT_FILE" ]
        [ -z "${GF_AUTH_GENERIC_OAUTH_CLIENT_ID:-}" ]
    done
done
unset GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_NGINX_HTTPS_PORT
export DISCOVERY_EXPECTED_URL=https://performance.example.test/api/v1/onboarding/tenant-info
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL="$DISCOVERY_EXPECTED_URL"

reset_discovery_test
export DISCOVERY_TEST_SCENARIO=invalid-then-valid
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS=30
configure_generic_oauth
[ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = "public-client-id" ]
[ "$GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL" = "$expected_signout_redirect_url" ]
[ "$(< "$DISCOVERY_CALL_COUNT_FILE")" -eq 3 ]

reset_discovery_test
export DISCOVERY_TEST_SCENARIO=http-error-then-valid
configure_generic_oauth
[ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = "public-client-id" ]
[ "$GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL" = "$expected_signout_redirect_url" ]
[ "$(< "$DISCOVERY_CALL_COUNT_FILE")" -eq 2 ]

reset_discovery_test
export DISCOVERY_TEST_SCENARIO=oversized-then-valid
configure_generic_oauth
[ "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID" = "public-client-id" ]
[ "$GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL" = "$expected_signout_redirect_url" ]
[ "$(< "$DISCOVERY_CALL_COUNT_FILE")" -eq 2 ]

reset_discovery_test
export GF_AUTH_GENERIC_OAUTH_CLIENT_ID='static:client'
configure_generic_oauth
[ "$GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL" = 'https://auth.example.test/oidc/v1/end_session?client_id=static%3Aclient&post_logout_redirect_uri=https%3A%2F%2Fperformance.example.test%2Fgrafana%2F' ]
[ ! -s "$DISCOVERY_CALL_COUNT_FILE" ]

reset_discovery_test
export GF_AUTH_GENERIC_OAUTH_CLIENT_ID=static-client
export GRAFANA_OAUTH_END_SESSION_URL=http://auth.example.test/oidc/v1/end_session
if configure_generic_oauth; then
    echo "Insecure Grafana OAuth end-session URL unexpectedly succeeded" >&2
    exit 1
fi
[ -z "${GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL:-}" ]
export GRAFANA_OAUTH_END_SESSION_URL=https://auth.example.test/oidc/v1/end_session

reset_discovery_test
export DISCOVERY_TEST_SCENARIO=always-invalid
export GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS=30
# Advance the caller's clock after the first rejected response. A one-second
# wall-clock deadline can expire during mktemp before curl is ever invoked.
sleep() {
    SECONDS=$((SECONDS + GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS))
}
if configure_generic_oauth; then
    echo "Permanently invalid discovery response unexpectedly succeeded" >&2
    exit 1
fi
[ -z "${GF_AUTH_GENERIC_OAUTH_CLIENT_ID:-}" ]
[ -z "${GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL:-}" ]
[ "$(< "$DISCOVERY_CALL_COUNT_FILE")" -eq 1 ]
