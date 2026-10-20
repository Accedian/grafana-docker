# Customer dashboards for Docker Swarm

These dashboards are a supported subset of `Customer (k8s)`. They require no
new collector, scrape target, recording rule, or Swarm opt-in feature.

| Dashboard | Existing telemetry |
| --- | --- |
| Ingestion Pipeline | Sensor/collector metrics exposed through Fedex, Ignite, Spark Pushgateway, Kafka topic exporter and Gather |
| Sensor Connectivity | Fedex/collector, Foxtrot and Skylight-AAA application metrics |
| Application Speed | Application API/database timings, CouchDB/OpenSearch exporters, Spark Pushgateway and Kafka topic exporter |
| Resource Health | Node-exporter jobs `sysmetrics` / `sysmetrics-private-cloud` and `cadvisor` |

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
