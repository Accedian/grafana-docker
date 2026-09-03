# Branch `feat/grafana-sync` — Alerts & Dashboards Review

> Generated: 2025-06-11  
> Base: `master` (12be169)  
> Head: `feat/grafana-sync` (241527b)

---

## Table of Contents

- [New Alert Rules](#new-alert-rules)
  - [cloudops-alerts.yaml (39 rules)](#cloudops-alertsyaml--39-rules)
  - [general-alerts.yaml (10 rules)](#general-alertsyaml--10-rules)
  - [ingestion-alerts.yaml (4 rules)](#ingestion-alertsyaml--4-rules)
- [New Dashboards (23)](#new-dashboards-23)
- [Pre-Existing Alert Rules](#pre-existing-alert-rules)
- [Pre-Existing Dashboards (58)](#pre-existing-dashboards-58)
- [Overlaps — New ops/ Dashboards vs Pre-Existing](#overlaps--new-ops-dashboards-vs-pre-existing)
- [Alert Cross-Overlaps](#alert-cross-overlaps)

---

## New Alert Rules

All three YAML files under `provisioning/alerting/` are **new** (the directory previously only had `.gitempty`).

### `cloudops-alerts.yaml` — 39 rules

Folder: CloudOps Alerts

| # | Alert Title |
|---|-------------|
| 1 | 1 Day Cert Expiry |
| 2 | 5 Day Cert Expiry |
| 3 | Airflow DAG Failed |
| 4 | Airflow DAG Failed - custom reports |
| 5 | Airflow DAG Failed - dhl_get_configs |
| 6 | Airflow DAG Failed - DHL Jobs |
| 7 | Airflow Health Status |
| 8 | Airflow job duration |
| 9 | Airflow Jobs Stopped |
| 10 | All Druid Task Slots Full for 2H |
| 11 | Clickhouse nodes up |
| 12 | CPU usage high over half hour |
| 13 | DataSource Availability alert |
| 14 | Dgraph Alpha Availability |
| 15 | Disk usage |
| 16 | Docker Pending Task 30m |
| 17 | Druid Status check |
| 18 | Druid's overlord view of the cluster |
| 19 | ElasticSearch Heap |
| 20 | Hadoop dead nodes |
| 21 | HDFS Corrupt Blocks |
| 22 | HDFS - Under-Replicated Blocks |
| 23 | HDFS Time Since Last CheckPoint |
| 24 | High IO Wait |
| 25 | Historical usage |
| 26 | Kafka Consumergroup Lag |
| 27 | Streamingapp Lag Growing |
| 28 | Kafka Ingestion Rate |
| 29 | Latent Data Lag Growing |
| 30 | Metrics Service Reachability |
| 31 | NTP Time Sync |
| 32 | Prometheus NODATA |
| 33 | PVStorage Inserted Rows |
| 34 | Query Node Count |
| 35 | RoadRunner Persistence_service_cached_files |
| 36 | Streamingapp alert-events Topic Ingestion |
| 37 | Streamingapp mo-summary Topic Ingestion |
| 38 | Streamingapp Raw Topic Ingestion |
| 39 | Time since last backup |

### `general-alerts.yaml` — 10 rules

Folder: General Alerting

| # | Alert Title |
|---|-------------|
| 1 | AvailableMemory |
| 2 | BatchProcessingDuration |
| 3 | CouchDBClientRequestingChanges |
| 4 | GatherAlertParsingErrors |
| 5 | KafkaIngestionRate |
| 6 | KafkaMQTTDivergence |
| 7 | ProcessingRatio |
| 8 | SparkBatchStartDelay |
| 9 | IncidentBuilderThroughput |
| 10 | IncidentBuilderHeartbeat |

### `ingestion-alerts.yaml` — 4 rules

Folder: Ingestion

| # | Alert Title |
|---|-------------|
| 1 | StreamingappTopicIngestion |
| 2 | SparkIngestionRate |
| 3 | RoadrunnerDisconnected |
| 4 | AirflowBatchDAGFailed |

---

## New Dashboards (23)

All in `dashboards/ops/` — new subfolder introduced by this branch.

| # | Title | UID | File |
|---|-------|-----|------|
| 1 | Airflow job status | `IUhlWpDVz` | `ops-airflow_job_status.json` |
| 2 | Containers_status | `jsmkTuQ4z` | `ops-containers_status.json` |
| 3 | DataSource Availability alert | `Vb0vmv4Vk` | `ops-datasource_availability.json` |
| 4 | Days until cert expires | `NwXkRD4Vk` | `ops-days_until_cert_expire.json` |
| 5 | General Deployment Overview | `MenNkgemz-DHUS2` | `ops-deployment_all.json` |
| 6 | Dgraph Alpha Availability | `iB9eU2LVz` | `ops-dgraph_alpha_availability.json` |
| 7 | Disk usage | `N638sFS4z` | `ops-disk_usage.json` |
| 8 | Druid_segments_reindex | `xjpL9Fw4z` | `ops-druid_segments_reindex.json` |
| 9 | Druid ingestion task Last 24 Hour (rate [15m]) | `77Fih_O4z` | `ops-druidingestiontasklast24hours.json` |
| 10 | ElasticSearch metrics | `lV4ga8r4ztest` | `ops-elasticsearch.json` |
| 11 | HDFS - Under-Replicated Blocks | `ogAwlnTVz` | `ops-hdfs_underreplicatedblocks.json` |
| 12 | Invalid datasets per pv-storage | `9tMN-qD4z` | `ops-invalid_dataset.json` |
| 13 | Kubernetes cluster monitoring (via Prometheus) | `oDULMvQVz` | `ops-k8s_cluster_monitoring.json` |
| 14 | Kafka Ingestion Rate | `kqe0kDVVz` | `ops-kafka_ingestion_rate.json` |
| 15 | Overall Latent Data | `A6KKqnxRF` | `ops-latent.json` |
| 16 | Metrics Service Reachability Status | `Ch14KD0Vz` | `ops-metricsservicereachability.json` |
| 17 | Node Exporter Full | `rYdddlPWk` | `ops-node_exporter.json` |
| 18 | Object type metrics | `cf3f24e1-ea47-4459-b0c6-9e8b23600292` | `ops-object_type_metrics.json` |
| 19 | Pv Storage Inserted Datasets | `364BWad4z` | `ops-pv_storage_inserted_datasets.json` |
| 20 | RoadRunner | `J0hZRZTVk` | `ops-roadrunner.json` |
| 21 | Spark Ingestion Rate | `oftqr4LVz` | `ops-spark_ingestion_rate.json` |
| 22 | StreamingApp Topic Ingestion | `9EGCVuLVz` | `ops-streamingapp_topic_ingestion.json` |
| 23 | Time since last backup | `Is9RZvV4k` | `ops-time_since_last_backup.json` |

---

## Pre-Existing Alert Rules

Only `roadrunner-ha-alerts.yaml` existed on `master` — 5 rules:

| # | Alert Title |
|---|-------------|
| 1 | RoadrunnerLivenessDegraded |
| 2 | RoadrunnerReadinessNotReady |
| 3 | RoadrunnerFoxtrotDisconnected |
| 4 | RoadrunnerFedexDisconnected |
| 5 | RoadrunnerNoConnectedAgents |

---

## Pre-Existing Dashboards (58)

All in `dashboards/` root (no subfolder).

| # | Title | UID | File |
|---|-------|-----|------|
| 1 | Airflow | `vrJSQunM3` | `Airflow.json` |
| 2 | Alert Export Service | `UiWnVvcVk` | `Alert Export Service.json` |
| 3 | Analytics-Streamer API | `L1-exxdVa` | `Analytics-Streamer API.json` |
| 4 | Analytics-Streamer gNMI | `L1-exxdVz` | `Analytics-Streamer gNMI.json` |
| 5 | CouchDB metrics | `m6c315ezk` | `CouchDB metrics-1519688661301.json` |
| 6 | Custom Reports | `f33903e7k` | `Custom Reports.json` |
| 7 | CybersecuritySparkApp | `h1nGBjTGz` | `CybersecuritySparkApp.json` |
| 8 | Docker Host & Container Overview | `C0AnnIezk` | `Docker Host & Container Overview-1519675385777.json` |
| 9 | Docker and system monitoring | `QGtVAvekk` | `Docker and system monitoring-1519680126576.json` |
| 10 | Druid | `ZrN6g4-mk` | `Druid.json` |
| 11 | adh-fedex | `crA9QWAVk` | `Fedex.json` |
| 12 | GatherMetrics | `8zk2JXbnz` | `GatherMetrics.json` |
| 13 | Go Metrics | `U0o_Zfezz` | `GoMetrics.json` |
| 14 | HDFS | `J6lLP-jMk` | `HDFS.json` |
| 15 | Ignite Dashboard | `XRZc5xNVz` | `Ignite Dashboard.json` |
| 16 | Incidents | `CzJKZFYnk` | `Incidents.json` |
| 17 | Ingestion | _(none)_ | `Ingestion.json` |
| 18 | Interceptor Condition Rules | `itzJv_lVk` | `Interceptor Condition Rules.json` |
| 19 | License Metrics | `-zRnPtg7z` | `LicenseMetrics.json` |
| 20 | Node Exporter Server Metrics | `K8r7nI6zz` | `Node Exporter Server Metrics-1519675437738.json` |
| 21 | Node Exporter Server Metricsv2 | `yqdjpdSSz` | `Node Exporter Server Metricsv2-1734616002261.json` |
| 22 | Object Type Metrics | `IyiPrpPVk` | `Object-Type-Metrics.json` |
| 23 | RabbitMQ-Overview | `Kn5xm-gZk` | `RabbitMQ-Overview.json` |
| 24 | Tech Support Report Tool | `SkcZKiyIz` | `Remote-Tech-Support.json` |
| 25 | Roadrunner (Detailed) | `jrDp0304k` | `Roadrunner (Detailed).json` |
| 26 | Roadrunner | `PNGklt9ik` | `Roadrunner.json` |
| 27 | Routing Analytics Collector Metrics | `f31ee279-…` | `Routing Analytics Collector.json` |
| 28 | SSH Logins | `lS1jDvHGz` | `SSH Logins.json` |
| 29 | Server Certificate | `fJsreNHMk` | `Server Certificate.json` |
| 30 | Sky-Topo | `bcc2ca7f-…` | `Sky-Topo.json` |
| 31 | Skylight-AAA | `fb94b524-…` | `Skylight-aaa.json` |
| 32 | Spark Resources | `O5pMZ3eMk` | `Spark Resources.json` |
| 33 | Spark Batch Jobs Monitoring | `d26AACL7k` | `SparkBatchJobMonitoring.json` |
| 34 | Spark Ingestion and Lag | `oaePhsqGz` | `SparkKafkaIngestionAndLag.json` |
| 35 | StitchitMetrics | `aef5d77duw4cgf` | `StitchitMetrics.json` |
| 36 | Telemetry Collector | `d566c8ec-…` | `Telemetry Collector.json` |
| 37 | Traefik2 | `3ipsWfViz` | `Traefik.json` |
| 38 | VictoriaMetrics - vmagent | `G7Z9GzMGz` | `VictoriaMetrics-vmagent.json` |
| 39 | Weld-watcher | `CVyHOPrVz` | `Weld-watcher.json` |
| 40 | Alert Policies | `954e61d6-…` | `alert-policies.json` |
| 41 | Alert Service Metrics | `6f7e92a8` | `alert_service_dashboard.json` |
| 42 | Alerts | `kzGizW3Wz` | `alerting.json` |
| 43 | Bellhop Microservice Monitoring | `bellhop-monitoring` | `bellhop-grafana-dashboard.json` |
| 44 | Capture sensors | `VbvXRYUVz` | `capture_sensors.json` |
| 45 | ClickHouse - Cluster Analysis | `_hAsuzBnz` | `clickhouse-dashboard-cluster-analysis.json` |
| 46 | ClickHouse - Data Analysis | `-B3tt7a7z` | `clickhouse-dashboard-data-analysis.json` |
| 47 | ClickHouse - Query Analysis | `w5Q2Otank` | `clickhouse-dashboard-query-analysis.json` |
| 48 | Clickhouse | `NL8v6NlZk` | `clickhouse-dashboard.json` |
| 49 | Foxtrot Service | `8x_bV3f4k` | `foxtrot_service_dashboard.json` |
| 50 | Index Management | `n_nxrE_mk` | `index_management.json` |
| 51 | Kafka Overview (Consumers) | `jwPKIsniz` | `kafka-overview-consumers.json` |
| 52 | Kafka Overview (JMX) | `mcJMsjrZk` | `kafka-overview-jmx.json` |
| 53 | PV Storage Flows | `iB103jrWz` | `pv-storage-flows.json` |
| 54 | Pyloth | `66nMQ1fMk` | `pyloth.json` |
| 55 | Roadrunner data flow | `a8cc1bba-…` | `roadrunner-data-flow.json` |
| 56 | Sky Topo Node Processor | `e4491211-…` | `sky-topo-node-processor.json` |
| 57 | update server | `B0mIbRaVk` | `updateserver-dashboard.json` |
| 58 | ZooKeeper by Prometheus | `SDE76m7Zzz` | `zookeeper.json` |

---

## Overlaps — New ops/ Dashboards vs Pre-Existing

UIDs are all different (no hard collision), but these are **conceptual/functional duplicates** covering the same domain:

| New (ops/) | Pre-Existing | Notes |
|-----------|-------------|-------|
| **Airflow job status** (`IUhlWpDVz`) | **Airflow** (`vrJSQunM3`) | Both cover Airflow monitoring |
| **RoadRunner** (`J0hZRZTVk`) | **Roadrunner** (`PNGklt9ik`), **Roadrunner (Detailed)** (`jrDp0304k`), **Roadrunner data flow** (`a8cc1bba-…`) | 3 pre-existing Roadrunner dashboards |
| **Disk usage** (`N638sFS4z`) | **Docker and system monitoring** (`QGtVAvekk`) | System-level disk metrics likely overlap |
| **Node Exporter Full** (`rYdddlPWk`) | **Node Exporter Server Metrics** (`K8r7nI6zz`), **Node Exporter Server Metricsv2** (`yqdjpdSSz`) | 2 pre-existing Node Exporter variants |
| **Object type metrics** (`cf3f24e1-…`) | **Object Type Metrics** (`IyiPrpPVk`) | Same domain, different UIDs |
| **Kafka Ingestion Rate** (`kqe0kDVVz`) | **Spark Ingestion and Lag** (`oaePhsqGz`), **Kafka Overview (Consumers)** / **(JMX)** | Kafka ingestion overlap |
| **Spark Ingestion Rate** (`oftqr4LVz`) | **Spark Ingestion and Lag** (`oaePhsqGz`), **Spark Batch Jobs Monitoring** (`d26AACL7k`) | Spark overlap |
| **StreamingApp Topic Ingestion** (`9EGCVuLVz`) | **Ingestion** (no UID) | General ingestion overlap |
| **HDFS - Under-Replicated Blocks** (`ogAwlnTVz`) | **HDFS** (`J6lLP-jMk`) | HDFS overlap |
| **Pv Storage Inserted Datasets** (`364BWad4z`) | **PV Storage Flows** (`iB103jrWz`) | PV Storage overlap |
| **Containers_status** (`jsmkTuQ4z`) | **Docker Host & Container Overview** (`C0AnnIezk`) | Container monitoring overlap |
| **Days until cert expires** (`NwXkRD4Vk`) | **Server Certificate** (`fJsreNHMk`) | Certificate monitoring overlap |

---

## Alert Cross-Overlaps

### Between the three new alert files

| Alert Concept | cloudops-alerts.yaml | general-alerts.yaml | ingestion-alerts.yaml |
|--------------|---------------------|--------------------|-----------------------|
| Kafka Ingestion Rate | Kafka Ingestion Rate | KafkaIngestionRate | — |
| Streamingapp Topic Ingestion | Streamingapp alert-events / mo-summary / Raw Topic Ingestion | — | StreamingappTopicIngestion |
| Spark Ingestion Rate | (implicit via Kafka/Streamingapp) | — | SparkIngestionRate |
| Airflow DAG Failed | Airflow DAG Failed (4 variants) | — | AirflowBatchDAGFailed |

### Between new alerts and pre-existing `roadrunner-ha-alerts.yaml`

| New (ingestion-alerts.yaml) | Pre-Existing (roadrunner-ha-alerts.yaml) | Notes |
|---------------------------|----------------------------------------|-------|
| RoadrunnerDisconnected | RoadrunnerFoxtrotDisconnected, RoadrunnerFedexDisconnected, RoadrunnerNoConnectedAgents | Generic vs. specific disconnect alerts |

---

## Design Notes

- The new `ops/` dashboards live in a **separate subfolder** (mapped to a dedicated Grafana folder for CloudOps), while pre-existing dashboards are in `dashboards/` root (default Grafana folder).
- The intent appears to be giving CloudOps a **dedicated curated view**, but the functional overlaps above are worth reviewing to decide if both copies should coexist or if some pre-existing dashboards should be deprecated.
- All alert rules are seeded via `seed-alerts.py` using the Grafana Provisioning API with `X-Disable-Provenance: true`, making them **fully editable** by customers after deployment.
