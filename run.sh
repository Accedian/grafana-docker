#!/bin/bash -e

export GF_USERS_DEFAULT_THEME=light

: "${GF_PATHS_CONFIG:=/etc/grafana/grafana.ini}"
: "${GF_PATHS_DATA:=/var/lib/grafana}"
: "${GF_PATHS_LOGS:=/var/log/grafana}"
: "${GF_PATHS_PLUGINS:=/var/lib/grafana/plugins}"
: "${GF_PATHS_PROVISIONING:=/etc/grafana/provisioning}"
: "${DS_PROMETHEUS:=http://localhost:9090}"

chown -R grafana:grafana "$GF_PATHS_DATA" "$GF_PATHS_LOGS"

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

    chown grafana:grafana -R ~grafana/.aws
    chmod 600 ~grafana/.aws/credentials
fi

if [ ! -z "${GF_INSTALL_PLUGINS}" ]; then
  OLDIFS=$IFS
  IFS=','
  for plugin in ${GF_INSTALL_PLUGINS}; do
    IFS=$OLDIFS
    if [[ $plugin =~ .*\;.* ]]; then
        pluginUrl=$(echo "$plugin" | cut -d';' -f 1)
        pluginInstallFolder=$(echo "$plugin" | cut -d';' -f 2)
        gosu grafana cli --pluginUrl ${pluginUrl} --pluginsDir "${GF_PATHS_PLUGINS}" plugins install "${pluginInstallFolder}"
    else
        gosu grafana cli --pluginsDir "${GF_PATHS_PLUGINS}" plugins install ${plugin}
    fi
  done
fi

if [ "z$DONT_COPY_STOCK_DASHBOARDS"  = "z" ]; then
  rm -rf /etc/grafana/provisioning/*
  rm -rf /var/lib/grafana/dashboards/*

  cp -R /tmp/provisioning/ /etc/grafana/
  cp -R /tmp/dashboards/ /var/lib/grafana/
fi

exec gosu grafana /usr/sbin/grafana-server              \
  --homepath=/usr/share/grafana                         \
  --config="$GF_PATHS_CONFIG"                           \
  cfg:default.log.mode="console"                        \
  cfg:default.paths.data="$GF_PATHS_DATA"               \
  cfg:default.paths.logs="$GF_PATHS_LOGS"               \
  cfg:default.paths.plugins="$GF_PATHS_PLUGINS"         \
  cfg:default.paths.provisioning=$GF_PATHS_PROVISIONING \
  "$@"
