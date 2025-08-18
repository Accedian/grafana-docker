FROM debian:stable-slim

ARG TARGETARCH
ARG GRAFANA_VERSION
ARG GRAFANA_URL="https://dl.grafana.com/oss/release/grafana_${GRAFANA_VERSION}_${TARGETARCH}.deb"
ARG GOSU_URL="https://github.com/tianon/gosu/releases/download/1.17/gosu-${TARGETARCH}"
ARG GF_INSTALL_PLUGINS

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

ENV GRAFANA_PLUGINS_DIR=/var/lib/grafana/plugins
RUN mkdir -p $GRAFANA_PLUGINS_DIR && chown -R grafana:grafana $GRAFANA_PLUGINS_DIR
RUN mkdir -p /data/grafana/plugins && chown -R grafana:grafana /data/grafana/plugins

RUN echo "Installing plugins: $GF_INSTALL_PLUGINS" && \
    IFS=','; for plugin_entry in $GF_INSTALL_PLUGINS; do \
      plugin=$(echo "$plugin_entry" | awk '{print $1}'); \
      version=$(echo "$plugin_entry" | awk '{print $2}'); \
      if [ -n "$version" ]; then \
        grafana-cli --pluginsDir $GRAFANA_PLUGINS_DIR plugins install "$plugin" "$version"; \
      else \
        grafana-cli --pluginsDir $GRAFANA_PLUGINS_DIR plugins install "$plugin"; \
      fi; \
      status=$?; \
      if [ $status -ne 0 ]; then \
        echo "❌ Failed to install plugin: $plugin (version: ${version:-latest})"; \
        exit $status; \
      fi; \
    done && \
    cp -r /var/lib/grafana/plugins/* /data/grafana/plugins/

VOLUME ["/var/lib/grafana", "/var/log/grafana", "/etc/grafana"]

EXPOSE 3000

COPY ./run.sh /run.sh

COPY provisioning /tmp/provisioning

COPY dashboards /tmp/dashboards

ENTRYPOINT ["/run.sh"]
