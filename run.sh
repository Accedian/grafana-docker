#!/bin/bash -e

export GF_USERS_DEFAULT_THEME=light

: "${GF_PATHS_DATA:=/var/lib/grafana}"
: "${GF_PATHS_LOGS:=${GF_PATHS_DATA}/logs}"
: "${GF_PATHS_PLUGINS:=${GF_PATHS_DATA}/plugins}"
: "${GF_PATHS_PROVISIONING:=${GF_PATHS_DATA}/provisioning}"
: "${GF_PATHS_CONFIG:=${GF_PATHS_DATA}/grafana.ini}"
: "${DS_PROMETHEUS:=http://localhost:9090}"

mkdir -p "$GF_PATHS_DATA" "$GF_PATHS_LOGS" "$GF_PATHS_PLUGINS" "$GF_PATHS_PROVISIONING" "$GF_PATHS_DATA/dashboards" "$GF_PATHS_DATA/dashboards-ops" || true

# Prefer a writable config file on data volume for restricted OpenShift UIDs.
if [ ! -f "$GF_PATHS_CONFIG" ]; then
    if [ -r /etc/grafana/grafana.ini ]; then
        cp /etc/grafana/grafana.ini "$GF_PATHS_CONFIG"
    else
        : > "$GF_PATHS_CONFIG"
    fi
fi

if [ "$(id -u)" = "0" ]; then
    chown -R grafana:root "$GF_PATHS_DATA" "$GF_PATHS_LOGS" || true
fi

if [ -f /var/run/secrets/gce_oauth_key ]; then
 export GF_AUTH_GOOGLE_CLIENT_ID=$(cat /var/run/secrets/gce_oauth_key)
fi

if [ -f /var/run/secrets/gce_oauth_secret ]; then
 export GF_AUTH_GOOGLE_CLIENT_SECRET=$(cat /var/run/secrets/gce_oauth_secret)
fi

if [ ! -z ${GF_AWS_PROFILES+x} ]; then
    mkdir -p ~grafana/.aws/
    > ~grafana/.aws/credentials

    for profile in ${GF_AWS_PROFILES}; do
        access_key_varname="GF_AWS_${profile}_ACCESS_KEY_ID"
        secret_key_varname="GF_AWS_${profile}_SECRET_ACCESS_KEY"
        region_varname="GF_AWS_${profile}_REGION"

        if [ ! -z "${!access_key_varname}" -a ! -z "${!secret_key_varname}" ]; then
            echo "[${profile}]" >> ~grafana/.aws/credentials
            echo "aws_access_key_id = ${!access_key_varname}" >> ~grafana/.aws/credentials
            echo "aws_secret_access_key = ${!secret_key_varname}" >> ~grafana/.aws/credentials
            if [ ! -z "${!region_varname}" ]; then
                echo "region = ${!region_varname}" >> ~grafana/.aws/credentials
            fi
        fi
    done

    chmod 600 ~grafana/.aws/credentials
fi

if [ "z$DONT_COPY_STOCK_DASHBOARDS"  = "z" ]; then
  echo "Deleting existing provisioning"
    rm -rf "$GF_PATHS_PROVISIONING"/* || true

  echo "Deleting existing dashboards"
    rm -rf "$GF_PATHS_DATA/dashboards"/* || true

  echo "Restoring plugins from image"
    cp -Rn /data/grafana/plugins/. "$GF_PATHS_PLUGINS/" 2>/dev/null || true

  echo "Copying stock provisioning"
    cp -R /tmp/provisioning/. "$GF_PATHS_PROVISIONING/"

  # Alerts are seeded via API (not file-provisioned) so customers can edit them.
  # Factory defaults remain at /tmp/provisioning/alerting/ for the seed script.
  echo "Clearing file-provisioned alerts (will be API-seeded instead)"
    rm -f "$GF_PATHS_PROVISIONING"/alerting/*.yaml || true

  echo "Copying stock dashboards"
    # Resolve Docker COPY nesting (/tmp/dashboards/ may contain a dashboards/ subdir)
    _DASH_SRC=/tmp/dashboards
    [ -d "$_DASH_SRC/dashboards" ] && _DASH_SRC="$_DASH_SRC/dashboards"
    # Copy non-ops dashboards
    find "$_DASH_SRC" -maxdepth 1 -name '*.json' -exec cp {} "$GF_PATHS_DATA/dashboards/" \;
    # Copy ops dashboards to dedicated directory (avoids overlap with system-provider)
    if [ -d "$_DASH_SRC/ops" ]; then
      cp "$_DASH_SRC/ops/"*.json "$GF_PATHS_DATA/dashboards-ops/"
    fi
fi

# Seed alert rules via API in the background once Grafana is ready.
# Uses X-Disable-Provenance so customers can freely edit rules in the UI.
/usr/local/bin/seed-alerts.py &

# Root: drop to grafana user via gosu. $@ omitted — nothing provides args.
# Non-root (OpenShift): keeps $@ for optional pod-spec arg overrides.
if [ "$(id -u)" = "0" ]; then
    exec gosu grafana grafana-server \
        --homepath=/usr/share/grafana \
        --config="$GF_PATHS_CONFIG" \
        cfg:default.log.mode=console \
        cfg:default.paths.data="$GF_PATHS_DATA" \
        cfg:default.paths.logs="$GF_PATHS_LOGS" \
        cfg:default.paths.plugins="$GF_PATHS_PLUGINS" \
        cfg:default.paths.provisioning="$GF_PATHS_PROVISIONING"
else
    exec grafana-server "$@" \
        --homepath=/usr/share/grafana \
        --config="$GF_PATHS_CONFIG" \
        cfg:default.log.mode=console \
        cfg:default.paths.data="$GF_PATHS_DATA" \
        cfg:default.paths.logs="$GF_PATHS_LOGS" \
        cfg:default.paths.plugins="$GF_PATHS_PLUGINS" \
        cfg:default.paths.provisioning="$GF_PATHS_PROVISIONING"
fi
