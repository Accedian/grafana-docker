# Grafana Alert Rule Annotations

Generated from alert rule files in this repository.

## Runbook URL resolution

Alert rules store a `runbook_url` annotation with a path relative to the Grafana root
(e.g. `/public/help/airflow-ingestion.html`). At seed time, `seed-alerts.py` rewrites
these paths into full URLs using `GF_SERVER_ROOT_URL` so that Grafana renders them as
clickable links in the alert detail view.

For example, when `GF_SERVER_ROOT_URL=https://host/grafana/`, the seeded annotation
becomes `https://host/grafana/public/help/airflow-ingestion.html`. When
`GF_SERVER_ROOT_URL` is not set, the script falls back to the internal `GRAFANA_URL`.

### Cross-domain limitation

Grafana validates `runbook_url` with `new URL()` and only renders a clickable link
when the value is a full URL with a scheme (Grafana PR [#90523](https://github.com/grafana/grafana/pull/90523)).
Relative paths are displayed as plain text.

Because the full URL is derived from `GF_SERVER_ROOT_URL`, the link is bound to a
single domain (the deployment URL). Users accessing Grafana via a different domain
(e.g. a tenant-specific hostname) will encounter an authentication error when clicking
the link, since their session cookie is scoped to the other origin.

This is a fundamental limitation: a static annotation cannot adapt to the viewer's
current domain. The deployment URL is the primary and most common access path, so
the current behaviour is acceptable. If cross-domain access becomes a priority, the
options are:

- Configure shared cookie domains at the reverse-proxy / auth layer.
- Revert to relative paths (`/grafana/public/help/...`) — universally correct but
  not rendered as clickable links by Grafana.

## Customer-facing sensitivity issues

Severity is ranked by customer exposure risk. High includes internal URLs/domains, internal runbooks, explicit operational remediation, or internal customer workflow details. Medium includes internal topology, service names, metric/topic names, host labels, and implementation details. Low includes incomplete placeholder text or non-customer-facing wording.

| Severity | Alert | Source | Annotation issue | Why this is an issue |
| --- | --- | --- | --- | --- |
| High | Airflow DAG Failed (`cloudops-airflow-dag-failed`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Notion runbook URL. | Exposes an internal knowledge-base path and organization namespace. Customer-facing annotations should not leak private documentation locations. |
| High | Airflow DAG Failed - custom reports (`cloudops-af-dag-failed-custom-reports`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL and names a specific custom reports DAG. | Reveals an internal monitoring domain, dashboard path, and implementation-specific job naming. |
| High | Airflow DAG Failed - dhl_get_configs (`cloudops-af-dag-failed-dhl-get-configs`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL and the `dhl_get_configs` job name. | Reveals an internal monitoring domain plus a specific integration/job name that may identify customer or tenant-specific processing. |
| High | Airflow DAG Failed - DHL Jobs (`cloudops-airflow-dag-failed-dhl-jobs`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL and a named DHL job family. | Reveals an internal dashboard and customer/integration-specific operational detail. |
| High | Airflow Health Status (`cloudops-airflow-health-status`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL and scheduler/service health details. | Exposes private dashboard infrastructure and backend scheduler implementation details. |
| High | Airflow job duration (`cloudops-airflow-job-duration`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL. | Exposes a private monitoring endpoint that customers should not see or attempt to access. |
| High | Airflow Jobs Stopped (`cloudops-airflow-jobs-stopped`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Grafana URL and says Airflow may need to be restarted. | Combines private dashboard exposure with privileged remediation guidance. |
| High | DataSource Availability alert (`cloudops-datasource-availability-alert`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal deployment URL pattern and detailed Druid topology. | Reveals private domain structure plus node roles, services, and troubleshooting steps that map the backend architecture. |
| High | Disk usage (`cloudops-disk-usage`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Notion runbook URL. | Exposes internal documentation and organization namespace in a customer-visible alert. |
| High | Time since last backup (`cloudops-time-since-last-backup`) | provisioning/alerting/cloudops-alerts.yaml | Description contains an internal Notion runbook URL and names CouchDB/Postgres backup troubleshooting. | Exposes private runbooks and specific data-store technologies involved in backup handling. |
| High | All Druid Task Slots Full for 2H (`cloudops-druid-task-slots-full-2h`) | provisioning/alerting/cloudops-alerts.yaml | Description says stuck tasks may need to be deleted manually and mentions middlemanager capacity. | Gives operational remediation and internal Druid capacity details that are not suitable for customers. |
| High | HDFS - Under-Replicated Blocks (`cloudops-hdfs-under-replicated-blocks`) | provisioning/alerting/cloudops-alerts.yaml | Description tells reviewers to check namenode logs and possibly restart `aod_namenode`. | Exposes internal service names and privileged remediation steps. |
| High | Kafka Ingestion Rate (`cloudops-kafka-ingestion-rate`) | provisioning/alerting/cloudops-alerts.yaml | Description says traffic may have stopped from customer sources and directs CSM follow-up. | Exposes internal escalation workflow and may alarm customers with unqualified statements about lost traffic. |
| High | StreamingappTopicIngestion (`streamingapp-topic-ingestion`) | provisioning/alerting/ingestion-alerts.yaml | Summary exposes `{{ $labels.topic }}` and description tells operators to check logs or restart Streamingapp. | Topic labels can reveal internal data pipelines, and restart/log guidance is internal remediation. |
| High | RoadrunnerDisconnected (`roadrunner-disconnected`) | provisioning/alerting/ingestion-alerts.yaml | Summary and description expose `{{ $labels.hostname }}` and `{{ $labels.zone }}`. | Hostnames and zones can reveal infrastructure naming, topology, or customer deployment structure. |
| High | AirflowBatchDAGFailed (`airflow-batch-dag-failed`) | provisioning/alerting/ingestion-alerts.yaml | Description says the DAG needs to be re-run manually. | Exposes an internal recovery procedure rather than a customer-safe impact statement. |
| High | Streamingapp alert-events Topic Ingestion (`cloudops-sa-alert-events-ingestion`) | provisioning/alerting/cloudops-alerts.yaml | Description tells operators to check Streamingapp logs and potentially restart the service. | Exposes internal service remediation steps and a specific topic name. |
| High | Streamingapp mo-summary Topic Ingestion (`cloudops-sa-mo-summary-ingestion`) | provisioning/alerting/cloudops-alerts.yaml | Description tells operators to check Streamingapp logs and potentially restart the service. | Exposes internal service remediation steps and a specific topic name. |
| High | Streamingapp Raw Topic Ingestion (`cloudops-sa-raw-topic-ingestion`) | provisioning/alerting/cloudops-alerts.yaml | Description tells operators to check Streamingapp logs and potentially restart the service. | Exposes internal remediation steps and raw session metric pipeline details. |
| Medium | Docker Pending Task 30m (`cloudops-docker-pending-task-30m`) | provisioning/alerting/cloudops-alerts.yaml | Description references Docker tasks, node resource availability, and labels. | Reveals container orchestration implementation and scheduling failure modes. |
| Medium | Druid's overlord view of the cluster (`cloudops-druid-overlord-cluster-view`) | provisioning/alerting/cloudops-alerts.yaml | Description names coordinator/overlord behavior and node connectivity internals. | Gives customers a view into internal Druid cluster control-plane architecture. |
| Medium | ElasticSearch Heap (`cloudops-elasticsearch-heap`) | provisioning/alerting/cloudops-alerts.yaml | Description explains JVM heap allocation on Elasticsearch nodes. | Exposes backend technology and node-level runtime details. |
| Medium | HDFS Corrupt Blocks (`cloudops-hdfs-corrupt-blocks`) | provisioning/alerting/cloudops-alerts.yaml | Description states HDFS has corrupt blocks and a data integrity issue. | Customer-facing wording may disclose storage-layer failure details before they are qualified for external communication. |
| Medium | HDFS Time Since Last CheckPoint (`cloudops-hdfs-time-since-last-checkpoint`) | provisioning/alerting/cloudops-alerts.yaml | Description names namenode and secondary namenode health. | Reveals storage topology and internal component names. |
| Medium | Streamingapp Lag Growing (`cloudops-streamingapp-lag-growing`) | provisioning/alerting/cloudops-alerts.yaml | Description references `ignite.contemporary` topics, Streamingapp logs, and consumer lag behavior. | Exposes internal topic naming and backend consumer implementation. |
| Medium | Latent Data Lag Growing (`cloudops-latent-data-lag-growing`) | provisioning/alerting/cloudops-alerts.yaml | Description references Latentstreamingapp logs and a stuck consumer. | Exposes internal service naming and troubleshooting details. |
| Medium | Metrics Service Reachability (`cloudops-metrics-service-reachability`) | provisioning/alerting/cloudops-alerts.yaml | Description names Druid historicals, brokers, overlord, coordinators, disk checks, and logs. | Reveals backend topology and troubleshooting process. |
| Medium | NTP Time Sync (`cloudops-ntp-time-sync`) | provisioning/alerting/cloudops-alerts.yaml | Description says VMs in the swarm are on-prem and not time synced. | Reveals deployment model, VM usage, and orchestration topology. |
| Medium | PVStorage Inserted Rows (`cloudops-pvstorage-inserted-rows`) | provisioning/alerting/cloudops-alerts.yaml | Description names PVStorage instances and associated ClickHouse nodes. | Reveals storage pipeline architecture and backend dependency mapping. |
| Medium | RoadRunner Persistence_service_cached_files (`cloudops-rr-persistence-cached-files`) | provisioning/alerting/cloudops-alerts.yaml | Summary and description expose an internal service metric name. | Internal metric/service names are not customer-friendly and can reveal pipeline internals. |
| Medium | SparkIngestionRate (`spark-ingestion-rate`) | provisioning/alerting/ingestion-alerts.yaml | Description names Streamingapp, Kafka, and Roadrunner as the ingestion path. | Reveals internal data pipeline components and dependency relationships. |
| Medium | AvailableMemory (`available-memory`) | provisioning/alerting/general-alerts.yaml | Summary references container RSS memory and possible container failure. | Exposes container-level infrastructure detail rather than customer-level service impact. |
| Medium | CouchDBClientRequestingChanges (`couchdb-client-changes`) | provisioning/alerting/general-alerts.yaml | Summary names CouchDB and client-change request counts. | Reveals specific database technology and operational threshold. |
| Medium | KafkaIngestionRate (`kafka-ingestion-rate`) | provisioning/alerting/general-alerts.yaml | Summary names `npav-ts-metrics` and `spark_raw_in`. | Exposes internal topic/metric names and ingestion architecture. |
| Medium | KafkaMQTTDivergence (`kafka-mqtt-divergence`) | provisioning/alerting/general-alerts.yaml | Summary names Kafka-to-MQTT divergence and a numeric threshold. | Reveals messaging architecture and internal alert threshold. |
| Medium | IncidentBuilderThroughput (`incident-builder-throughput`) | provisioning/alerting/general-alerts.yaml | Summary names IncidentBuilder and throughput ratio. | Exposes internal service names and performance semantics. |
| Medium | IncidentBuilderHeartbeat (`incident-builder-heartbeat`) | provisioning/alerting/general-alerts.yaml | Summary names IncidentBuilder and streaming timestamp checks. | Exposes internal service health-check implementation. |
| Low | Clickhouse nodes up (`cloudops-clickhouse-nodes-up`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Need tips" and "Maybe a Notion page". | Placeholder/internal drafting language looks unpolished and implies missing customer-ready guidance. |
| Low | Dgraph Alpha Availability (`cloudops-dgraph-alpha-availability`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Need tips" and "Maybe a Notion page". | Placeholder/internal drafting language is not suitable for customer-visible annotations. |
| Low | Druid Status check (`cloudops-druid-status-check`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Need tips" and "Maybe a Notion page". | Placeholder/internal drafting language is not suitable for customer-visible annotations. |
| Low | Hadoop dead nodes (`cloudops-hadoop-dead-nodes`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Need tips" and "Maybe a Notion page". | Placeholder/internal drafting language is not suitable for customer-visible annotations. |
| Low | Query Node Count (`cloudops-query-node-count`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Need tips" and "Maybe a Notion page". | Placeholder/internal drafting language is not suitable for customer-visible annotations. |
| Low | CPU usage high over half hour (`cloudops-cpu-usage-high-over-half-hour`) | provisioning/alerting/cloudops-alerts.yaml | Description says "Validate if avg over 2 hours of failed status is bigger then 2". | Internal validation wording is unclear and not customer-friendly. |
| Low | High IO Wait (`cloudops-high-io-wait`) | provisioning/alerting/cloudops-alerts.yaml | Description says to validate iowait over a threshold. | Reads like an internal test note rather than a customer-safe impact description. |

## Unified alert provisioning rules

| Source | Group | UID | Title | Summary | Description | Runbook URL |
| --- | --- | --- | --- | --- | --- | --- |
| provisioning/alerting/cloudops-alerts.yaml | 1 Day Cert Expiry | cloudops-1-day-cert-expiry | 1 Day Cert Expiry | 1 Day Cert Expiry |  |  |
| provisioning/alerting/cloudops-alerts.yaml | 5 Day Cert Expiry | cloudops-5-day-cert-expiry | 5 Day Cert Expiry | 5 Day Cert Expiry |  |  |
| provisioning/alerting/cloudops-alerts.yaml | Airflow DAG Failed | cloudops-airflow-dag-failed | Airflow DAG Failed | Airflow DAG Failed | The indicated Airflow DAG failed and has failed one or more times in last 4 hours. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow DAG Failed - custom reports | cloudops-af-dag-failed-custom-reports | Airflow DAG Failed - custom reports | Airflow DAG Failed - custom reports | The indicated Airflow DAG failed and has failed one or more times in last 4 hours. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow DAG Failed - dhl_get_configs | cloudops-af-dag-failed-dhl-get-configs | Airflow DAG Failed - dhl_get_configs | Airflow DAG Failed - dhl_get_configs | The Airflow dhl_get_configs job has failed repeatedly. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow DAG Failed - DHL Jobs | cloudops-airflow-dag-failed-dhl-jobs | Airflow DAG Failed - DHL Jobs | Airflow DAG Failed - DHL Jobs | The indicated Airflow DAG failed and has not run successfully in last 6 hours. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow Health Status | cloudops-airflow-health-status | Airflow Health Status | Airflow Health Status | Airflow is not in a healthy state. The scheduler may be down or inter-service communication is broken. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow job duration | cloudops-airflow-job-duration | Airflow job duration | Airflow job duration | An Airflow DAG run has exceeded the expected duration threshold. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Airflow Jobs Stopped | cloudops-airflow-jobs-stopped | Airflow Jobs Stopped | Airflow Jobs Stopped | Airflow is not in a healthy state. The scheduler may be down and jobs have stopped running. | /public/help/airflow-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | All Druid Task Slots Full for 2H | cloudops-druid-task-slots-full-2h | All Druid Task Slots Full for 2H | All Druid Task Slots Full for 2H | All ingestion task slots have been occupied for over 2 hours. New data ingestion tasks are queued. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Clickhouse nodes up | cloudops-clickhouse-nodes-up | Clickhouse nodes up | Clickhouse nodes up | One or more ClickHouse database nodes are not responding. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | CPU usage high over half hour | cloudops-cpu-usage-high-over-half-hour | CPU usage high over half hour | CPU usage high over half hour | CPU utilization has been elevated for a sustained period, which may impact service performance. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | DataSource Availability alert | cloudops-datasource-availability-alert | DataSource Availability alert | DataSource Availability alert | Some data segments are not fully loaded and may be unavailable for queries. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Dgraph Alpha Availability | cloudops-dgraph-alpha-availability | Dgraph Alpha Availability | Dgraph Alpha Availability | One or more Dgraph database nodes are unavailable. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Disk usage | cloudops-disk-usage | Disk usage | Disk usage | Disk usage for the deployment has exceeded the configured threshold. | /public/help/disk-usage.html |
| provisioning/alerting/cloudops-alerts.yaml | Docker Pending Task 30m | cloudops-docker-pending-task-30m | Docker Pending Task 30m | Docker Pending Task 30m | Container tasks have been pending for an extended period, indicating resource constraints or scheduling issues. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Druid Status check | cloudops-druid-status-check | Druid Status check | Druid Status check | The query engine status check has failed, indicating one or more nodes may be unreachable. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Druid's overlord view of the cluster | cloudops-druid-overlord-cluster-view | Druid's overlord view of the cluster | Druid's overlord view of the cluster | The cluster coordinator's view of connected nodes disagrees with what nodes report, indicating a connectivity or registration issue. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | ElasticSearch Heap | cloudops-elasticsearch-heap | ElasticSearch Heap | ElasticSearch Heap | ElasticSearch JVM heap utilization has exceeded the safe threshold and may lead to out-of-memory conditions. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Hadoop dead nodes | cloudops-hadoop-dead-nodes | Hadoop dead nodes | Hadoop dead nodes | One or more Hadoop DataNodes are no longer responding. Data availability may be impacted. | /public/help/hdfs-health.html |
| provisioning/alerting/cloudops-alerts.yaml | HDFS Corrupt Blocks | cloudops-hdfs-corrupt-blocks | HDFS Corrupt Blocks | HDFS Corrupt Blocks | HDFS has reported corrupt blocks indicating a data integrity issue. | /public/help/hdfs-health.html |
| provisioning/alerting/cloudops-alerts.yaml | HDFS - Under-Replicated Blocks | cloudops-hdfs-under-replicated-blocks | HDFS - Under-Replicated Blocks | HDFS - Under-Replicated Blocks | HDFS has a significant number of under-replicated blocks, indicating potential node failures or capacity issues. | /public/help/hdfs-health.html |
| provisioning/alerting/cloudops-alerts.yaml | HDFS Time Since Last CheckPoint | cloudops-hdfs-time-since-last-checkpoint | HDFS Time Since Last CheckPoint | HDFS Time Since Last CheckPoint | The HDFS filesystem checkpoint is overdue, which increases recovery risk in the event of a failure. | /public/help/hdfs-health.html |
| provisioning/alerting/cloudops-alerts.yaml | High IO Wait | cloudops-high-io-wait | High IO Wait | High IO Wait | Disk I/O wait time has been elevated for a sustained period, indicating storage bottlenecks. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Historical usage | cloudops-historical-usage | Historical usage | Historical usage | Storage utilization on query-serving nodes is approaching capacity. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Kafka Consumergroup Lag | cloudops-kafka-consumergroup-lag | Kafka Consumergroup Lag | Kafka Consumergroup Lag | Consumer lag on summary data topics has not decreased in the last hour, indicating a sustained processing backlog. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Streamingapp Lag Growing | cloudops-streamingapp-lag-growing | Streamingapp Lag Growing | Streamingapp Lag Growing | The streaming application's consumer lag is consistently growing, indicating it is falling behind on data processing. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Kafka Ingestion Rate | cloudops-kafka-ingestion-rate | Kafka Ingestion Rate | Kafka Ingestion Rate | The ingestion rate for session and capture data has dropped below the expected threshold. Data collection may have stopped. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Latent Data Lag Growing | cloudops-latent-data-lag-growing | Latent Data Lag Growing | Latent Data Lag Growing | Latent data processing lag is consistently growing, indicating the consumer may be stuck or under-resourced. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Metrics Service Reachability | cloudops-metrics-service-reachability | Metrics Service Reachability | Metrics Service Reachability | The metrics query service cannot fully reach all query-serving nodes. Data availability for dashboards may be impacted. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | NTP Time Sync | cloudops-ntp-time-sync | NTP Time Sync | NTP Time Sync | System time is not synchronized across all hosts. Time drift can cause data ordering issues and certificate validation failures. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | Prometheus NODATA | cloudops-prometheus-nodata | Prometheus NODATA | Prometheus NODATA | Grafana cannot reach the Prometheus metrics data source. Other alert rules may not evaluate correctly while this persists. | /public/help/infrastructure-health.html |
| provisioning/alerting/cloudops-alerts.yaml | PVStorage Inserted Rows | cloudops-pvstorage-inserted-rows | PVStorage Inserted Rows | PVStorage Inserted Rows | One or more storage writer instances have stopped inserting data. Downstream data freshness is affected. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Query Node Count | cloudops-query-node-count | Query Node Count | Query Node Count | The deployment has fewer query nodes than expected, which may degrade query performance. | /public/help/druid-health.html |
| provisioning/alerting/cloudops-alerts.yaml | RoadRunner Persistence_service_cached_files | cloudops-rr-persistence-cached-files | RoadRunner Persistence_service_cached_files | RoadRunner Persistence_service_cached_files | The data collector is caching a large number of files locally, indicating delivery delays. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Streamingapp alert-events Topic Ingestion | cloudops-sa-alert-events-ingestion | Streamingapp alert-events Topic Ingestion | Streamingapp alert-events Topic Ingestion | The streaming application is falling behind on processing alert event data. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Streamingapp mo-summary Topic Ingestion | cloudops-sa-mo-summary-ingestion | Streamingapp mo-summary Topic Ingestion | Streamingapp mo-summary Topic Ingestion | The streaming application is falling behind on processing summary data. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Streamingapp Raw Topic Ingestion | cloudops-sa-raw-topic-ingestion | Streamingapp Raw Topic Ingestion | Streamingapp Raw Topic Ingestion | The streaming application is falling behind on processing raw session metrics. | /public/help/streaming-ingestion.html |
| provisioning/alerting/cloudops-alerts.yaml | Time since last backup | cloudops-time-since-last-backup | Time since last backup | Time since last backup | The time since the last backup has exceeded the target interval. The backup may have failed. | /public/help/backup-recency.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | available-memory | AvailableMemory | Total container memory utilization is below expected levels. |  | /public/help/infrastructure-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | batch-processing-duration | BatchProcessingDuration | Batch analytics processing has stalled — processing timestamps are not advancing. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | couchdb-client-changes | CouchDBClientRequestingChanges | Configuration database change-feed request count is abnormally high. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | gather-alert-parsing-errors | GatherAlertParsingErrors | The alert processing service has encountered parsing errors. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | kafka-ingestion-rate | KafkaIngestionRate | Data ingestion rate has dropped to near zero while upstream sources are active. |  | /public/help/streaming-ingestion.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | kafka-mqtt-divergence | KafkaMQTTDivergence | Message delivery rate divergence detected between the message bus and notification channel. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | processing-ratio | ProcessingRatio | Analytics processing ratio is below 1, indicating the service is not keeping pace with incoming data. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | spark-batch-start-delay | SparkBatchStartDelay | Batch analytics processing start is delayed. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | incident-builder-throughput | IncidentBuilderThroughput | Incident processing throughput has dropped below expected levels. |  | /public/help/service-health.html |
| provisioning/alerting/general-alerts.yaml | GeneralAlerts | incident-builder-heartbeat | IncidentBuilderHeartbeat | Incident processing service appears to have stalled — no activity detected. |  | /public/help/service-health.html |
| provisioning/alerting/ingestion-alerts.yaml | IngestionAlerts | streamingapp-topic-ingestion | StreamingappTopicIngestion | Streamingapp is falling behind on ingesting topic: {{ $labels.topic }} | The streaming application is falling behind on ingesting the indicated topic(s). | /public/help/streaming-ingestion.html |
| provisioning/alerting/ingestion-alerts.yaml | IngestionAlerts | spark-ingestion-rate | SparkIngestionRate | Spark Ingestion Rate has dropped to zero for Streamingapp | The volume of records read by the streaming application has dropped significantly. Data ingestion may have stopped. | /public/help/streaming-ingestion.html |
| provisioning/alerting/ingestion-alerts.yaml | IngestionAlerts | roadrunner-disconnected | RoadrunnerDisconnected | Roadrunner disconnected: {{ $labels.hostname }} (zone: {{ $labels.zone }}) | Data collector {{ $labels.hostname }} in zone {{ $labels.zone }} has been disconnected for more than 5 minutes. Data collection has stopped for this collector. | /public/help/streaming-ingestion.html |
| provisioning/alerting/ingestion-alerts.yaml | IngestionAlerts | airflow-batch-dag-failed | AirflowBatchDAGFailed | Airflow Batch DAG Failed: {{ $labels.dag_id }} | A Batch Airflow DAG has failed recently. | /public/help/airflow-ingestion.html |

## Legacy dashboard panel alerts

These dashboard-embedded legacy alert objects do not contain an `annotations` map. Their `message` fields are listed as the closest legacy equivalent for review.

| Source | Panel | Alert name | Alert annotations | Alert message | Alert rule tags |
| --- | --- | --- | --- | --- | --- |
| dashboards/CybersecuritySparkApp.json | Batch processing duration | Batch processing duration alert | {} |  | {} |
| dashboards/CybersecuritySparkApp.json | Spark batch start delay | Spark batch start delay alert | {} |  | {} |
| dashboards/CybersecuritySparkApp.json | Processing rate | Processing ratio alert | {} | Cyberapp is performing inadequate. | {} |
| dashboards/Docker and system monitoring-1519680126576.json | Load | Panel Title alert | {} |  | {} |
| dashboards/Docker and system monitoring-1519680126576.json | Used Disk Space | Free/Used Disk Space alert | {} |  | {} |
| dashboards/Docker and system monitoring-1519680126576.json | Available Memory | Available Memory alert | {} |  | {} |
| dashboards/Incidents.json | Trhroughput | Trhroughput alert | {} | IncidentBuilder is slow | {} |
| dashboards/Incidents.json | heartbeat | heartbeat alert | {} | IncidentBuilder is down | {} |
| dashboards/Ingestion.json | Ingestion Rate | Kafka Ingestion Rate alert | {} |  | {} |
| dashboards/SSH Logins.json | SSH Logins NOT using Vault | SSH Logins NOT using Vault alert | {} |  | {} |
| dashboards/Server Certificate.json | Days Until Certificate Expires | Days until Certificate Expires alert | {} |  | {} |
| dashboards/alerting.json | Gather Kafka MQTT Divergence | Kafka MQTT Divergence alert | {} |  | {} |
| dashboards/alerting.json | Gather Alert Parsing Errors | Gather Alert Parsing Errors alert | {} |  | {} |
