#!/bin/bash -e

export GF_USERS_DEFAULT_THEME=light

: "${GF_PATHS_DATA:=/var/lib/grafana}"
: "${GF_PATHS_LOGS:=${GF_PATHS_DATA}/logs}"
: "${GF_PATHS_PLUGINS:=${GF_PATHS_DATA}/plugins}"
: "${GF_PATHS_PROVISIONING:=${GF_PATHS_DATA}/provisioning}"
: "${GF_PATHS_CONFIG:=${GF_PATHS_DATA}/grafana.ini}"
: "${DS_PROMETHEUS:=http://localhost:9090}"

mkdir -p "$GF_PATHS_DATA" "$GF_PATHS_LOGS" "$GF_PATHS_PLUGINS" "$GF_PATHS_PROVISIONING" "$GF_PATHS_DATA/dashboards" || true

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

  echo "Copying stock provisioning"
    cp -R /tmp/provisioning/. "$GF_PATHS_PROVISIONING/"

  echo "Copying stock dashboars"
    cp -R /tmp/dashboards/. "$GF_PATHS_DATA/dashboards/"
fi

if [ "$(id -u)" = "0" ]; then
    exec gosu grafana "$@"
else
    exec grafana "$@" \
        --homepath=/usr/share/grafana \
        --config="$GF_PATHS_CONFIG" \
        cfg:default.log.mode=console \
        cfg:default.paths.data="$GF_PATHS_DATA" \
        cfg:default.paths.logs="$GF_PATHS_LOGS" \
        cfg:default.paths.plugins="$GF_PATHS_PLUGINS" \
        cfg:default.paths.provisioning="$GF_PATHS_PROVISIONING"
fi
