FROM debian:stable-slim

ARG TARGETARCH
ARG GRAFANA_VERSION
ARG GRAFANA_URL="https://dl.grafana.com/oss/release/grafana_${GRAFANA_VERSION}_${TARGETARCH}.deb"
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
    && apt-get autoremove --yes \
    && apt-get clean \
    && rm --recursive --force /var/lib/apt/lists/*

ENV GRAFANA_PLUGINS_DIR=/var/lib/grafana/plugins
RUN mkdir -p $GRAFANA_PLUGINS_DIR /data/grafana/plugins /var/lib/grafana/dashboards /var/log/grafana /etc/grafana /etc/grafana/provisioning \
    && chgrp -R 0 $GRAFANA_PLUGINS_DIR /data/grafana/plugins /var/lib/grafana /var/log/grafana /etc/grafana \
    && chmod -R g+rwX $GRAFANA_PLUGINS_DIR /data/grafana/plugins /var/lib/grafana /var/log/grafana /etc/grafana

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
