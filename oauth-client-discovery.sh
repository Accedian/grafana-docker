#!/usr/bin/env bash

valid_oidc_client_id() {
    local client_id="$1"
    [[ "$client_id" =~ ^[A-Za-z0-9._:@-]{1,512}$ ]]
}

valid_https_url_without_query_or_fragment() {
    local url="$1"
    [[ "$url" =~ ^https://[^/?#[:space:]]+(/[^?#[:space:]]*)?$ ]]
}

percent_encode_uri_component() {
    local value="$1"
    local encoded=""
    local character
    local escaped
    local i
    local LC_ALL=C

    for ((i = 0; i < ${#value}; i++)); do
        character="${value:i:1}"
        case "$character" in
            [A-Za-z0-9.~_-]) encoded+="$character" ;;
            *)
                printf -v escaped '%%%02X' "'$character"
                encoded+="$escaped"
                ;;
        esac
    done

    printf '%s' "$encoded"
}

oidc_discovery_response_max_bytes=1024

fetch_bounded_oidc_discovery_response() {
    local output_file="$1"
    shift
    local -a pipeline_status

    curl "$@" |
        head -c "$((oidc_discovery_response_max_bytes + 1))" > "$output_file"
    pipeline_status=("${PIPESTATUS[@]}")
    (( pipeline_status[0] == 0 && pipeline_status[1] == 0 ))
}

resolve_generic_oauth_client_id() {
    if [ "${GF_AUTH_GENERIC_OAUTH_ENABLED,,}" != "true" ]; then
        return
    fi

    if [ -n "${GF_AUTH_GENERIC_OAUTH_CLIENT_ID:-}" ]; then
        if ! valid_oidc_client_id "$GF_AUTH_GENERIC_OAUTH_CLIENT_ID"; then
            echo "Configured Grafana OAuth client ID has an invalid format" >&2
            return 1
        fi
        return
    fi

    local discovery_url="${GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_URL:-}"
    local organization="${GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_ORGANIZATION:-}"
    local project="${GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_PROJECT:-}"
    local application="${GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_APPLICATION:-}"
    local timeout_seconds="${GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_TIMEOUT_SECONDS:-900}"
    local retry_seconds=5

    if [ -z "$discovery_url" ] || [ -z "$organization" ] || [ -z "$project" ] || [ -z "$application" ]; then
        echo "Grafana OAuth requires a client ID or complete client ID discovery configuration" >&2
        return 1
    fi
    if [[ ! "$timeout_seconds" =~ ^[1-9][0-9]{0,4}$ ]]; then
        echo "Grafana OAuth client ID discovery timeout must be between 1 and 99999 seconds" >&2
        return 1
    fi

    local deadline=$((SECONDS + timeout_seconds))
    local remaining_seconds
    local request_timeout_seconds
    local resolved_client_id=""
    local response_file
    local response_size
    local response_complete

    if ! response_file="$(mktemp)"; then
        echo "Unable to create a temporary file for Grafana OAuth client discovery" >&2
        return 1
    fi

    echo "Waiting for the Grafana public OAuth client to be provisioned"
    while (( SECONDS < deadline )); do
        remaining_seconds=$((deadline - SECONDS))
        request_timeout_seconds=10
        if (( remaining_seconds < request_timeout_seconds )); then
            request_timeout_seconds=$remaining_seconds
        fi

        response_complete=false
        if fetch_bounded_oidc_discovery_response "$response_file" \
            --fail \
            --silent \
            --connect-timeout 5 \
            --max-time "$request_timeout_seconds" \
            --max-filesize "$oidc_discovery_response_max_bytes" \
            --get \
            --data-urlencode "organization=$organization" \
            --data-urlencode "project=$project" \
            --data-urlencode "application=$application" \
            "$discovery_url"; then
            response_complete=true
        fi

        response_size="$(wc -c < "$response_file")"
        if (( response_size > oidc_discovery_response_max_bytes )); then
            echo "Grafana OAuth client discovery response exceeds" \
                "${oidc_discovery_response_max_bytes} bytes; retrying" >&2
        elif [ "$response_complete" = true ]; then
            resolved_client_id="$(< "$response_file")"
            if valid_oidc_client_id "$resolved_client_id"; then
                rm -f "$response_file"
                export GF_AUTH_GENERIC_OAUTH_CLIENT_ID="$resolved_client_id"
                echo "Grafana public OAuth client ID resolved"
                return
            fi
            echo "Grafana OAuth client discovery has not returned a valid client ID; retrying" >&2
        fi

        remaining_seconds=$((deadline - SECONDS))
        if (( remaining_seconds <= 0 )); then
            break
        fi
        if (( remaining_seconds < retry_seconds )); then
            sleep "$remaining_seconds"
        else
            sleep "$retry_seconds"
        fi
    done

    rm -f "$response_file"
    echo "Timed out waiting for the Grafana public OAuth client" >&2
    return 1
}

configure_generic_oauth_signout_redirect() {
    if [ "${GF_AUTH_GENERIC_OAUTH_ENABLED,,}" != "true" ]; then
        return
    fi

    local client_id="${GF_AUTH_GENERIC_OAUTH_CLIENT_ID:-}"
    local end_session_url="${GRAFANA_OAUTH_END_SESSION_URL:-}"
    local post_logout_redirect_url="${GRAFANA_OAUTH_POST_LOGOUT_REDIRECT_URL:-}"

    if ! valid_oidc_client_id "$client_id"; then
        echo "Grafana OAuth sign-out requires a valid public client ID" >&2
        return 1
    fi
    if ! valid_https_url_without_query_or_fragment "$end_session_url"; then
        echo "Grafana OAuth end-session URL must be an HTTPS URL without a query or fragment" >&2
        return 1
    fi
    if ! valid_https_url_without_query_or_fragment "$post_logout_redirect_url"; then
        echo "Grafana OAuth post-logout redirect URL must be an HTTPS URL without a query or fragment" >&2
        return 1
    fi

    export GF_AUTH_GENERIC_OAUTH_SIGNOUT_REDIRECT_URL="${end_session_url}?client_id=$(percent_encode_uri_component "$client_id")&post_logout_redirect_uri=$(percent_encode_uri_component "$post_logout_redirect_url")"
}

configure_generic_oauth() {
    resolve_generic_oauth_client_id || return
    configure_generic_oauth_signout_redirect
}
