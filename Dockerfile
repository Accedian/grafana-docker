FROM debian:stretch

#ARG DOWNLOAD_URL="https://s3-us-west-2.amazonaws.com/grafana-releases/release/dist/grafana_latest_amd64.deb"
ARG DOWNLOAD_URL="https://dl.grafana.com/oss/release/grafana_9.1.3_amd64.deb"
RUN apt-get update && \
    apt-get -y --no-install-recommends install libfontconfig curl ca-certificates && \
    apt-get clean && \
    curl ${DOWNLOAD_URL} > /tmp/grafana.deb && \
    dpkg -i /tmp/grafana.deb && \
    rm /tmp/grafana.deb && \
    curl -L https://github.com/tianon/gosu/releases/download/1.10/gosu-amd64 > /usr/sbin/gosu && \
    chmod +x /usr/sbin/gosu && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

VOLUME ["/var/lib/grafana", "/var/log/grafana", "/etc/grafana"]

RUN grafana-cli plugins install xginn8-pagerduty-datasource && \
    grafana-cli plugins install grafana-image-renderer && \
    grafana-cli plugins install grafana-clock-panel 1.0.3 && \
    grafana-cli plugins install grafana-piechart-panel

EXPOSE 3000

COPY ./run.sh /run.sh
COPY provisioning/ /tmp/provisioning/
COPY dashboards/ /tmp/dashboards/


ENTRYPOINT ["/run.sh"]
