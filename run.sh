#!/bin/bash -e

umask 0002
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

# Ensure existing PVC data is group-writable for OpenShift random UIDs (GID 0).
chmod -R g+rwX "$GF_PATHS_DATA" "$GF_PATHS_LOGS" 2>/dev/null || true


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

  echo "Copying stock dashboards"
    cp -R /tmp/dashboards/. "$GF_PATHS_DATA/dashboards/"
fi

# Migrate legacy Prometheus datasource UIDs -> 'prometheus' within their organizations.
if [ -f "$GF_PATHS_DATA/grafana.db" ] && command -v sqlite3 >/dev/null 2>&1; then
    if ! sqlite3 -bail "$GF_PATHS_DATA/grafana.db" <<'SQL'
BEGIN;
CREATE TEMP TABLE legacy_prometheus AS
SELECT org_id, uid
  FROM data_source
 WHERE name='Prometheus'
   AND uid != 'prometheus'
   AND NOT EXISTS (
       SELECT 1
         FROM data_source AS canonical
        WHERE canonical.org_id=data_source.org_id
          AND canonical.uid='prometheus'
   )
   AND id IN (
       SELECT MIN(id)
         FROM data_source
        WHERE name='Prometheus' AND uid != 'prometheus'
        GROUP BY org_id
   );
UPDATE alert_rule
   SET data = REPLACE(data,
       '"datasourceUid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=alert_rule.org_id) || '"',
       '"datasourceUid":"prometheus"')
 WHERE EXISTS (SELECT 1 FROM legacy_prometheus WHERE org_id=alert_rule.org_id)
   AND data LIKE '%"datasourceUid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=alert_rule.org_id) || '"%';
UPDATE alert_rule_version
   SET data = REPLACE(data,
       '"datasourceUid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=alert_rule_version.rule_org_id) || '"',
       '"datasourceUid":"prometheus"')
 WHERE EXISTS (SELECT 1 FROM legacy_prometheus WHERE org_id=alert_rule_version.rule_org_id)
   AND data LIKE '%"datasourceUid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=alert_rule_version.rule_org_id) || '"%';
UPDATE dashboard
   SET data = REPLACE(data,
       '"uid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=dashboard.org_id) || '"',
       '"uid":"prometheus"')
 WHERE EXISTS (SELECT 1 FROM legacy_prometheus WHERE org_id=dashboard.org_id)
   AND data LIKE '%"uid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=dashboard.org_id) || '"%';
UPDATE library_element
   SET model = REPLACE(model,
       '"uid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=library_element.org_id) || '"',
       '"uid":"prometheus"')
 WHERE EXISTS (SELECT 1 FROM legacy_prometheus WHERE org_id=library_element.org_id)
   AND model LIKE '%"uid":"' || (SELECT uid FROM legacy_prometheus WHERE org_id=library_element.org_id) || '"%';
UPDATE data_source
   SET uid='prometheus'
 WHERE name='Prometheus'
   AND EXISTS (
       SELECT 1
         FROM legacy_prometheus
        WHERE org_id=data_source.org_id AND uid=data_source.uid
   );
COMMIT;
SQL
    then
        echo "Prometheus datasource UID migration failed; all changes were rolled back" >&2
    fi
fi

grafana_args=(
    --homepath=/usr/share/grafana
    --config="$GF_PATHS_CONFIG"
    cfg:default.log.mode="console"
    cfg:default.paths.data="$GF_PATHS_DATA"
    cfg:default.paths.logs="$GF_PATHS_LOGS"
    cfg:default.paths.plugins="$GF_PATHS_PLUGINS"
    cfg:default.paths.provisioning="$GF_PATHS_PROVISIONING"
    "$@"
)

if [ "$(id -u)" = "0" ]; then
    # Fix ownership of files created as root before dropping to grafana user
    chown -R grafana:grafana "$GF_PATHS_DATA" "$GF_PATHS_LOGS" 2>/dev/null || true
    exec gosu grafana /usr/share/grafana/bin/grafana-server "${grafana_args[@]}"
else
    exec /usr/share/grafana/bin/grafana-server "${grafana_args[@]}"
fi
