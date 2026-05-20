# Alert Management

Grafana ships with a set of factory-default alert rules that monitor the health of the platform. These alerts are fully customizable — you can edit, disable, or delete any alert directly in the Grafana UI.

## How It Works

On first startup, Grafana automatically seeds a set of default alert rules into two folders:

- **General Alerting** — infrastructure-level alerts (CPU, memory, disk, certificates, datasource health, etc.)
- **Ingestion** — data pipeline alerts (Kafka lag, Airflow jobs, Druid status, HDFS health, etc.)

Once seeded, these alerts are yours. The system will not overwrite or reset them on subsequent restarts, so any edits you make in the Grafana UI are preserved across upgrades and pod restarts.

## Editing Alerts

1. Open the Grafana UI and navigate to **Alerting > Alert rules**.
2. Select the alert you want to modify.
3. Click **Edit** to adjust thresholds, queries, evaluation intervals, labels, or annotations.
4. Click **Save rule and exit**.

All standard Grafana alert editing capabilities are available — there are no restrictions on modifying the default alerts.

## Adding New Alerts

You can create new alert rules through the Grafana UI alongside the default ones:

1. Navigate to **Alerting > Alert rules**.
2. Click **+ New alert rule**.
3. Configure the rule as needed and save it to any folder.

New alerts you create behave identically to the defaults and are preserved across restarts.

## Deleting Alerts

To remove an alert you no longer need:

1. Navigate to **Alerting > Alert rules**.
2. Locate the alert and click the **Delete** icon.

Deleted alerts will not reappear on restart.

## Exporting Alerts

To export your current alert configuration (for backup or migration):

```bash
curl -s http://localhost:3000/api/v1/provisioning/alert-rules | python3 -m json.tool > my-alerts.json
```

This returns all alert rules as JSON, including any customizations you have made.

## Factory Reset

If you want to discard all customizations and restore the original default alerts, run the following command from within the Grafana container:

```bash
/usr/local/bin/seed-alerts.py --force
```

This will:

1. Delete all existing alert rules.
2. Re-seed the factory defaults.

> **Warning:** Factory reset is irreversible. Any custom alerts or modifications will be permanently lost. Export your alerts before resetting if you need to preserve them.

## Default Alert Summary

### General Alerting

| Alert | Description |
|-------|-------------|
| 1 Day Cert Expiry | Certificate expires within 1 day |
| 5 Day Cert Expiry | Certificate expires within 5 days |
| AvailableMemory | Total container RSS memory below threshold |
| BatchProcessingDuration | Batch processing taking too long |
| Clickhouse nodes up | Clickhouse node availability |
| CPU usage high over half hour | Sustained high CPU usage |
| DataSource Availability alert | Prometheus datasource reachability |
| DatasourceError | Datasource returning errors |
| DatasourceNoData | Datasource returning no data |
| Dgraph Alpha Availability | Dgraph Alpha node health |
| Disk usage | Disk utilization above threshold |
| ElasticSearch Heap | Elasticsearch heap pressure |
| High IO Wait | Sustained high I/O wait |
| Historical usage | Historical data storage utilization |
| Metrics Service Reachability | Metrics service endpoint health |
| NTP Time Sync | NTP synchronization status |
| Prometheus NODATA | Prometheus scrape target returning no data |
| Query Node Count | Expected query node count |
| Time since last backup | Backup recency check |

### Ingestion

| Alert | Description |
|-------|-------------|
| Airflow DAG Failed | Airflow DAG execution failure |
| Airflow Health Status | Airflow scheduler/webserver health |
| Airflow job duration | Airflow job exceeding expected duration |
| Airflow Jobs Stopped | Airflow jobs not running |
| All Druid Task Slots Full for 2H | Druid task slot exhaustion |
| Docker Pending Task 30m | Docker tasks stuck in pending state |
| Druid Status check | Druid cluster health |
| Druid's overlord view of the cluster | Druid overlord availability |
| Hadoop dead nodes | Hadoop DataNode availability |
| HDFS Corrupt Blocks | HDFS block corruption |
| HDFS - Under-Replicated Blocks | HDFS replication health |
| HDFS Time Since Last CheckPoint | HDFS NameNode checkpoint recency |
| Kafka Consumergroup Lag | Kafka consumer group lag |
| Kafka Ingestion Rate | Kafka message ingestion rate |
| Latent Data Lag Growing | Latent data processing lag |
| PVStorage Inserted Rows | PV storage insertion rate |
| RoadRunner Persistence cached files | RoadRunner file cache health |
| Streamingapp Lag Growing | Streaming application lag |
| Streamingapp alert-events Topic Ingestion | Alert events topic processing |
| Streamingapp mo-summary Topic Ingestion | MO summary topic processing |
| Streamingapp Raw Topic Ingestion | Raw metrics topic processing |
