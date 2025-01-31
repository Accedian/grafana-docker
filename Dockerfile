FROM debian:stable-slim

ARG GRAFANA_URL="https://dl.grafana.com/oss/release/grafana_11.5.0_amd64.deb"
ARG GOSU_URL="https://github.com/tianon/gosu/releases/download/1.17/gosu-amd64"

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get --yes --no-install-recommends install \
        adduser \
        ca-certificates \
        curl \
        libfontconfig \
        musl \
    && curl \
        --no-progress-meter \
        --write-out "curl: %{filename_effective} %{size_download}B %{speed_download}B/s\n" \
        --location \
        --output "/tmp/${GRAFANA_URL##*/}" \
        "${GRAFANA_URL}" \
    && dpkg --install "/tmp/${GRAFANA_URL##*/}" \
    && rm "/tmp/${GRAFANA_URL##*/}" \
    && curl \
        --no-progress-meter \
        --write-out "curl: %{filename_effective} %{size_download}B %{speed_download}B/s\n" \
        --location \
        --output /usr/sbin/gosu \
        "${GOSU_URL}" \
    && chmod 0775 /usr/sbin/gosu \
    && apt-get autoremove --yes \
    && apt-get clean \
    && rm --recursive --force /var/lib/apt/lists/*

RUN mkdir -p /data/grafana/plugins && chown -R grafana:grafana /data/grafana/plugins
RUN grafana-cli --pluginsDir "/data/grafana/plugins" plugins install xginn8-pagerduty-datasource
RUN grafana-cli --pluginsDir "/data/grafana/plugins" plugins install grafana-image-renderer 3.7.2
#TODO  remove grafana-image-renderer version when official fix is implemented for the latest version
RUN grafana-cli --pluginsDir "/data/grafana/plugins" plugins install grafana-clock-panel
RUN grafana-cli --pluginsDir "/data/grafana/plugins" plugins install grafana-piechart-panel
RUN grafana-cli --pluginsDir "/data/grafana/plugins" plugins install grafana-clickhouse-datasource

VOLUME ["/var/lib/grafana", "/var/log/grafana", "/etc/grafana"]

EXPOSE 3000

COPY ./run.sh /run.sh

COPY provisioning /tmp/provisioning

COPY dashboards /tmp/dashboards

ENTRYPOINT ["/run.sh"]
