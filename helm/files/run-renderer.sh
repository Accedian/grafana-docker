#!/bin/sh
set -eu

# A missing/empty Secret must never enable the upstream default authentication.
if [ -z "${AUTH_TOKEN:-}" ] || [ "${#AUTH_TOKEN}" -lt 32 ]; then
    echo "Renderer requires a non-default token of at least 32 characters." >&2
    exit 1
fi

# AUTH_TOKEN is parsed as a list upstream. Require one token, never a list
# containing the upstream default "-" alongside a longer value.
case "$AUTH_TOKEN" in
    *[!a-zA-Z0-9_+/=-]*)
        echo "Renderer requires a single alphanumeric or base64 token." >&2
        exit 1
        ;;
esac

exec /usr/bin/tini -- /usr/bin/grafana-image-renderer server
