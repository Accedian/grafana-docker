# Customer Alert Guidance (Phase 1)

This document replaces internal Notion references used inside alert annotations with guidance that can be safely shared with customers. It focuses on the alerts whose annotations or `xops-alerting-docs` fields referenced private Notion pages and maps them to customer-ready instructions that rely on public Grafana and upstream documentation.

## Architecture: bundled HTML help pages

Customer-facing troubleshooting guides are shipped as static HTML pages inside the Grafana Docker image.

- **Source:** `help/` directory in the `grafana-docker` repository
- **Image location:** `/usr/share/grafana/public/help/` (added via `COPY` in `Dockerfile`)
- **URL pattern:** `<grafana-origin>/public/help/<topic>.html`
- **Current pages:**
  - `airflow-ingestion.html` — Airflow DAG failure, scheduler health, and job duration
  - `disk-usage.html` — High disk utilization
  - `backup-recency.html` — Backup schedule and retention
  - `streaming-ingestion.html` — Streaming pipeline, Kafka, consumer lag, collectors
  - `hdfs-health.html` — HDFS/Hadoop storage node health and data integrity
  - `druid-health.html` — Query engine availability, task scheduling, data segments
  - `infrastructure-health.html` — CPU, I/O, memory, NTP, container scheduling, database nodes
  - `service-health.html` — Application processing throughput, alert pipeline, message delivery

Alert annotations reference these pages with a relative path (e.g., `/public/help/airflow-ingestion.html`) so the link works regardless of the customer's Grafana hostname. The pages are self-contained (inline CSS, no external dependencies) and support both light and dark system themes.

## 1. Mapping internal Notion links to customer-safe intent

| Internal reference | Alerts referencing it | Customer-safe intent |
| --- | --- | --- |
| `Fixing-A-Broken-Spark-Job` | `cloudops-airflow-dag-failed`, `cloudops-af-dag-failed-custom-reports`, `cloudops-af-dag-failed-dhl-get-configs` | Airflow DAG failures indicate ingestion tasks that need investigation and a manual rerun if the failure persists. |
| `Airflow-Batch-Ingestions` | `cloudops-airflow-dag-failed`, `cloudops-airflow-dag-failed-dhl-jobs`, `cloudops-airflow-health-status`, `cloudops-airflow-job-duration`, `cloudops-airflow-jobs-stopped` | Monitor scheduler, worker, and DAG runtime health for batch ingestion. |
| `How-To-s` | `cloudops-disk-usage` | Disk utilization has crossed the defined threshold; free space must be reclaimed or capacity expanded. |
| `CouchDB-Postgres-Backups-Fail` | `cloudops-time-since-last-backup` | Backup recency exceeded the target interval, signaling a failed or stalled backup workflow. |

## 2. Customer-safe response playbooks

### 2.1 Airflow ingestion reliability alerts

**Impacted alerts:** `cloudops-airflow-dag-failed`, `cloudops-af-dag-failed-custom-reports`, `cloudops-af-dag-failed-dhl-get-configs`, `cloudops-airflow-dag-failed-dhl-jobs`, `cloudops-airflow-health-status`, `cloudops-airflow-job-duration`, `cloudops-airflow-jobs-stopped`

**What the alert means:** These rules monitor Airflow DAG run status, scheduler health, and job duration metrics collected via Grafana. A trigger means a DAG run has failed repeatedly, the scheduler is unhealthy, jobs stopped progressing, or a DAG exceeded its expected runtime.

**Customer-facing impact statement:** "Data ingestion tasks are not completing on schedule. Recent Airflow runs are either failing or exceeding the expected runtime, which may delay data availability in dashboards."

**Investigation steps:**

1. Open the alert in Grafana and review recent evaluations and labels to identify the DAG ID or owner involved (Grafana Unified Alerting workflow guide: <https://grafana.com/docs/grafana/latest/alerting/>).
2. Use the Airflow UI to inspect the DAG's latest run, task logs, and scheduler health (Apache Airflow monitoring guide: <https://airflow.apache.org/docs/apache-airflow/stable/administration-and-deployment/logging-monitoring/index.html>).
3. Confirm the upstream data source (e.g., Kafka topic or files) is delivering records and that Airflow workers have capacity.

**Remediation guidance:**

- Clear transient task failures by re-running the DAG from the Airflow UI once the underlying issue is resolved.
- If the scheduler is marked unhealthy, restart the Airflow scheduler service and verify heartbeats recover.
- Adjust concurrency, task-level retries, or SLA expectations if sustained high runtimes are expected for large backfills.

**Verification:** Confirm the alert returns to `Normal` after the next evaluation window and that new DAG runs complete successfully.

### 2.2 Infrastructure disk usage alerts

**Impacted alert:** `cloudops-disk-usage`

**What the alert means:** Disk utilization reported by the monitored instance has passed the configured threshold.

**Customer-facing impact statement:** "The monitored deployment is running low on disk space, which can interrupt ingestion, backups, or query workloads if not addressed."

**Investigation steps:**

1. Use Grafana to inspect the `node_filesystem_avail_bytes` (or equivalent) series associated with the alert to locate the filesystem under pressure.<br>
2. Log into the affected host (or management console) and run a disk usage tool such as `df -h` or `du` to identify large directories.
3. Review application-specific directories (logs, staging areas, cache) for rapid growth.

**Remediation guidance:**

- Rotate or compress historical logs.
- Purge temporary files that are no longer required by the application.
- Expand the filesystem or attach additional storage if usage reflects steady growth rather than spikes.

**Verification:** Ensure disk usage returns below the alert threshold and confirm the Grafana alert clears on the subsequent evaluation cycle.

### 2.3 Backup recency alerts

**Impacted alert:** `cloudops-time-since-last-backup`

**What the alert means:** The time elapsed since the most recent CouchDB/Postgres backup exceeded one day, implying the scheduled backup did not complete.

**Customer-facing impact statement:** "The most recent automated database backup is older than the target interval. Continued data changes are currently unprotected."

**Investigation steps:**

1. Inspect the backup job status in Grafana to confirm when the last successful run was recorded.
2. Review the backup job logs (for example, Cron job output or Kubernetes job logs) to identify errors such as authentication failures, storage quotas, or network interruptions.
3. Validate that the backup destination (object storage bucket, NFS share, etc.) is reachable and has available capacity.

**Remediation guidance:**

- Re-run the backup job manually after correcting the root cause (credentials, connectivity, quota).
- Implement monitoring on the storage target to detect quota exhaustion earlier.
- Consider staggered backup schedules or incremental backups to shorten the recovery point objective.

**Verification:** Confirm a fresh backup artifact exists with the expected timestamp and that the Grafana alert state returns to `Normal`.

## 3. Recommended follow-up work

1. ~~Update the alert annotations to reference this document and the public documentation links above.~~ **Done** — annotations now link to `/public/help/*.html`.
2. ~~Replace remaining placeholder text in other alerts ("Need tips") with similar customer-safe summaries and new help pages.~~ **Done** — all placeholder descriptions replaced.
3. ~~Schedule a subsequent phase to cover medium/low severity alerts (e.g., Druid, HDFS, Streamingapp), ensuring each gets a dedicated help page and updated annotation.~~ **Done** — 5 additional help pages created (`streaming-ingestion`, `hdfs-health`, `druid-health`, `infrastructure-health`, `service-health`) and all medium/low severity alert annotations updated across `cloudops-alerts.yaml`, `ingestion-alerts.yaml`, and `general-alerts.yaml`.
4. ~~Add an `index.html` page that lists all available help topics for discoverability.~~ **Done** — `index.html` created at `/public/help/index.html`.
