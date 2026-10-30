# Customer dashboards for Docker Swarm

The first four dashboards are a supported subset of `Customer (k8s)`. They
require no new collector, scrape target, recording rule, or Swarm opt-in feature.
The native PCA UE EDR dashboard additionally requires the PCA UE scrape jobs
described below, supplied by the matching aod-deployer change.

| Dashboard | Existing telemetry |
| --- | --- |
| Ingestion Pipeline | Sensor/collector metrics exposed through Fedex, Ignite, Spark Pushgateway, Kafka topic exporter and Gather |
| Sensor Connectivity | Fedex/collector, Foxtrot and Skylight-AAA application metrics |
| Application Speed | Application API/database timings, CouchDB/OpenSearch exporters, Spark Pushgateway and Kafka topic exporter |
| Resource Health | Node-exporter jobs `sysmetrics` / `sysmetrics-private-cloud` and `cadvisor` |
| PCA UE · EDR Ingestion | PCA UE inserters, Kafka topic exporter, native ClickHouse and ClickHouse table exporter |

The source of deployment support is aod-deployer's
`files/templates/prometheus_config` and
`onprem/ansible/roles/skylight-aod-files/templates/prometheus_config`, with
their corresponding Docker Compose templates. Spark counters use the legacy
Pushgateway `_total` names, as in `SparkKafkaIngestionAndLag.json`.
Application dashboards otherwise retain the Kubernetes versions' metric
queries: these metrics come from the applications, not Kubernetes.

## Deliberate omissions

- Service Health is not included: its Kubernetes readiness, pending/crash-loop,
  restart and Job/CronJob status metrics have no default Swarm equivalent.
  Scrape `up` or a running container is not application readiness.
- Resource Health omits Kubernetes requests/limits comparisons, OOM termination
  reasons and PVC disk attribution. The supported container panels show CPU
  usage, working-set memory and CPU throttling directly from cAdvisor.
- No dashboard depends on the optional `pca_swarm_*` collector.

Optional/disabled applications and unused sensor data paths can have no data.
This does not prove health. The inherited application dashboards retain their
zero fallbacks for count panels; confirm telemetry availability before treating
those zeros as evidence of disconnection or failure.

## Resource filters

`node` filters per-node charts, not whole-cluster gauges. `cadvisorHost` and
`container` filter the container charts independently. Cloud node-exporter
instances are VM names; cAdvisor instances are target addresses, so they cannot
be joined by instance without new relabeling. Container identity is the pair
`instance,name`, not Kubernetes `namespace,pod`.

Resource queries set a two-minute minimum step, matching the cloud templates'
inherited 120-second scrape interval so Grafana's rate window includes enough
samples. On-prem scraping is more frequent.

## Provisioning and maintenance

Customer folder UIDs are explicitly provisioned as `pca-customer-k8s` and
`pca-customer-swarm`. Deployment UI uses these stable UIDs for direct folder
links. The startup script copies general dashboards into `dashboards/general`
and customer dashboards into sibling directories so recursive providers do not
compete for the same dashboard. Source directories and general Grafana folders
are unchanged.

Ship the Grafana image containing these providers/dashboards together with the
Deployment UI link change; an older Grafana image will not have the new folders.

Regenerate and validate after updating the Kubernetes originals:

```sh
python3 generate_swarm_dashboards.py
python3 -m unittest discover -s tests -v
```

The tests check regeneration, UID collisions, unsupported dependencies, Swarm
labels, copy/provisioning layout and (when installed) PromQL syntax via promtool.

## PCA UE EDR ingestion

`pca-ue-ingestion.json` (UID `pca-ue-ingestion-swarm`) is generated natively by
[`generate_pcaueni_dashboard.py`](../../generate_pcaueni_dashboard.py), rather
than copied from a Kubernetes dashboard. The Dockerfile copies it with the
other stock dashboards; `run.sh` and the existing `customer-swarm` provider
automatically provision it into **Customer (swarm)** on a fresh volume and on
an image upgrade. No API import or dashboard mounting is required. The usual
`DONT_COPY_STOCK_DASHBOARDS` opt-out still applies.

This dashboard covers the EDR path ending in ClickHouse. It works with
Analytics Lite and does not require Ignite, Spark, HDFS or Druid. It does not
claim to monitor the separate session-metrics path or prove customer API
readiness, data freshness or collector connectivity.

### Required deployment contracts

The matching aod-deployer change must enable these internal scrape jobs for
the installed profile, with a 30-second scrape interval:

- `pcaueni_inserter<node id>` → `pcaueni_inserter<node id>:1664/metrics`, when
  `with_pcaueni` is enabled. PVStorage runs `multi-tenant-harvest --pcaueni`
  with `PVSTORAGE_PROMETHEUS_ENABLED=1`.
- `clickhouse<node id>` → `clickhouse<node id>:8001/metrics`, and
  `ch_prometheus_exporter<node id>` →
  `ch_prometheus_exporter<node id>:9116/metrics`, when `with_clickhouse` is
  enabled, including `with_passive=false`.
- `kafka-topic-metrics` → `kafka-topic-metric-exporter:9308/metrics`.
- `prometheus` → `localhost:9090/prometheus/metrics` for the server's existing
  `/prometheus` route prefix.

The datasource is the provisioned Prometheus UID `prometheus`. Diagnostic
links use the standard Swarm reverse proxy prefix `/grafana/`; deployments
that customize that prefix must adjust those links.

PVStorage metrics are `pcaueni_inserted_rows_total`,
`pcaueni_inserted_datasets_total`, `pcaueni_invalid_datasets_total` (labels
`tenant_id`, `schema`), and `pcaueni_invalid_rows_total` (also `version`).
These labelled counters are created lazily: before the first applicable event,
there can be no series. An absent invalid counter is normal and is not proof
of zero errors. The dashboard leaves it absent, labelled **No counter yet**,
rather than inventing a healthy zero or declaring a failure. Invalid-data
panels show current counters (reset per process restart) so the first error
is visible even without the prior zero sample that a rate needs. Row-level errors
do not cover every rejected JSON dataset; inspect failed dataset attempts too.

Tenant and schema variables come from Kafka topics
`pcaue.<tenant UUID>.<schema>.json`. The consumer-group variable is discovered
from those topics, so custom group prefixes are supported. The standard
PVStorage destination group is `pv_storage.db`. Kafka lag counts messages,
not EDR rows. Partitions with an uncommitted offset of `-1` are excluded from
lag and shown separately as unknown progress, rather than a healthy zero.

All application queries require their own current `up == 1` scrape state.
The health panels show **DOWN** for failed scrapes and **No targets** for
missing/disabled jobs. Partial ingestion totals can still occur when one of
several inserters is down, so inspect health first. `up` measures successful
scraping, not application readiness.

ClickHouse table bytes are per replica, scoped to `database="pcaueni"` and
the selected schema/table. They have no tenant attribution and are not summed
across replicas. Backend memory, merge and disk-pressure panels cover all
databases and ignore tenant/schema filters. The table exporter can retain
previous values if a database query fails, so its internal query-failure
counter is shown alongside scrape health. Older exporter images also
misreport table row/part gauges; this dashboard does not use those gauges.

### Validation

Regeneration remains `python3 generate_swarm_dashboards.py`. With `promtool`
from the deployed Prometheus version on `PATH`, run `make test`. CircleCI
extracts Prometheus 2.54.1's tool from its official container and runs this
before building the Grafana image. The checks include real PromQL evaluation
for traffic, idle initialized counters, lazy absent error counters, failed
scrapes with old samples, missing targets, the first lazy error event, tenant/schema isolation,
row-version aggregation and unknown Kafka consumer offsets. They also verify
that linked dashboard UIDs exist in the image and that all queries parse.

For runtime acceptance, start the built image on a fresh data volume, confirm
the dashboard UID in `/api/dashboards/uid/pca-ue-ingestion-swarm`, and exercise
the Prometheus queries against the rendered deployment. Generate a known EDR
batch, verify counters/lag/storage, then briefly stop one inserter and verify
its scrape state becomes DOWN without creating a healthy zero. The dashboard
image and aod-deployer scrape configuration must ship together.
