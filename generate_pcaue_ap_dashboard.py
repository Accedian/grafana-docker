#!/usr/bin/env python3
"""Build the separate PCA UE access-endpoint/session monitoring view."""

import json
from pathlib import Path

from generate_pcaueni_dashboard import PROMETHEUS, healthy_metric, panel, variable


ROOT = Path(__file__).resolve().parent
DASHBOARD_NAME = "pca-ue-ap-ingestion.json"
AP = 'tenantId=~"${tenant:regex}",objectType="CiscoUE-edr-access-endpoint"'
AGENT = 'job="pcaue-ap-agent"'
IGNITE = 'job="ignite"'
GATHER = 'job="gather"'
DRUID = 'job=~"druid-.*-jmx"'


def ignite(metric, rate=False, group="tenantId, objectType"):
    return healthy_metric(metric, f"{IGNITE},{AP}", rate, group)


def gather(metric, rate=False, group="tenantId, granularity, changeType"):
    return healthy_metric(metric, f'{GATHER},tenantId=~"${{tenant:regex}}"', rate, group)


def pacemaker(metric, rate=False):
    selector = f'{GATHER},datasource=~"(${{tenant:regex}})-npav-ts-metrics.*"'
    return healthy_metric(metric, selector, rate, "datasource")


def build():
    description = (
        "# PCA UE · Access Endpoint / Session Agent\n\n"
        "**Path:** source RedPanda `edr-access-endpoint` → Go Telemetry Collector "
        "with embedded Telegraf → Roadrunner Gateway → Fedex → Kafka "
        "`spark_raw_in` → Ignite → Spark → HDFS → Gather → Druid. "
        "Spark/HDFS/Druid require full analytics.\n\n"
        "**Read the units:** Ignite sent counts normalized rows published to Kafka, "
        "not individual KPI values or Druid inserts. Agent received counts payload "
        "bytes from embedded Telegraf, including its internal metrics. "
        "Gather submission counters count requests/tasks, not data rows. "
        "Gather panels include all metric object types of the selected tenant; "
        "only the Ignite and Druid inventory panels select the PCA UE AP object type.\n\n"
        "**Availability and completeness:** UP proves a metrics scrape. "
        "Telegraf status proves the embedded process is running. "
        "Counters are filtered to currently UP targets; missing lazy counters "
        "are not manufactured zero values. Druid inventory comes from Gather's "
        "periodic inventory for the previous completed clock hour; current-hour "
        "records are excluded. Verify a test run "
        "through its actual Druid/Gather query before declaring end-to-end success. "
        "Tenant filters apply to data panels; health and agent transport cover "
        "configured deployment targets. Configure optional `pcaue-ap-agent` scrape "
        "targets to populate the two agent panels.\n\n"
        "For NI flow rows written to ClickHouse, open **PCA UE · EDR Ingestion**. "
        "Its `pcaueni_*` counters measure the separate NI path."
    )
    panels = [{
        "id": 1, "type": "text", "title": "What this dashboard measures",
        "gridPos": {"h": 9, "w": 24, "x": 0, "y": 0},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"mode": "markdown", "content": description},
    }]
    for id_, title, expression, x in [
        (2, "Telemetry agent scrape", f"min(up{{{AGENT}}})", 0),
        (3, "Embedded Telegraf process", f"min({healthy_metric('telegraf_status', AGENT)})", 6),
        (4, "Ignite scrapes", f"min(up{{{IGNITE}}})", 12),
        (5, "Druid JMX scrapes", f"min(up{{{DRUID}}})", 18),
    ]:
        panels.append(panel(id_, title, expression, "", x, 9, w=6, h=4,
                            type_="stat", no_value="No targets",
                            description="Worst current target state across the deployment, independent of tenant. UP means telemetry is reachable; no matching target is not healthy. Embedded Telegraf uses its real process-status gauge, filtered by successful agent scrapes."))
    panels += [
        panel(6, "AP normalized rows published / second", ignite("ignite_kafka_total_sent", rate=True),
              "{{tenantId}} / {{objectType}}", 0, 13, unit="ops", no_value="No counter yet",
              description="Successful normalized-row Kafka publishes by Ignite. One row contains multiple KPI values; this does not count Druid inserts. UP Ignite targets only."),
        panel(7, "AP dropped inputs · current counters", ignite("ignite_kafka_total_dropped", group="tenantId, objectType, reason"),
              "{{tenantId}} / {{reason}}", 12, 13, no_value="No counter yet",
              description="Current dropped-input counters split by reason. Depending on reason this counts a row or a whole Fedex batch. A missing lazy error counter is not proof of zero failures. Process restarts reset counters."),
        panel(8, "AP input lag last sampled by Ignite · messages", ignite("ignite_ingestion_lag", group="tenantId, objectType, topic, partition"),
              "{{topic}} / partition {{partition}}", 0, 21,
              description="Last sampled partition high-watermark minus consumed-message offset. Updated when Ignite receives a message, so an idle value can be old even while scrape is UP. Check Kafka consumer-group offsets for current broker-side progress."),
        panel(9, "Telemetry agent received payload / second · all data", healthy_metric("received_data_total", AGENT, rate=True, group="instance"),
              "{{instance}}", 12, 21, unit="Bps", no_value="No counter yet",
              description="Payload bytes received from embedded Telegraf, including internal agent metrics. This is not AP row throughput, source network bitrate or exact bytes stored in Druid."),
        panel(10, "Gather ingestion submissions / second · tenant", gather("gather_batch_ingest_submit_success", rate=True),
              "{{tenantId}} / {{granularity}} / {{changeType}}", 0, 29, unit="ops", no_value="No counter yet",
              description="Gather requests processed successfully for the tenant, across metric object types. A successful submission is not proof the asynchronous Druid indexing task succeeded."),
        panel(11, "Gather failed submissions · tenant counters", gather("gather_batch_ingest_submit_fail"),
              "{{tenantId}} / {{granularity}} / {{changeType}}", 12, 29, no_value="No counter yet",
              description="Current failed Gather submission counters for all metric object types of the tenant. Missing lazy counters do not establish zero failures; process restarts reset them."),
        panel(12, "Druid ingestion tasks waiting in Gather", pacemaker("gather_ingest_pacemaker_queue_size"),
              "{{datasource}}", 0, 37,
              description="Current Gather pacemaker queue for the tenant's metric datasources. Includes all metric object types. A missing series means the datasource queue has not been observed, not necessarily an empty queue."),
        panel(13, "Druid tasks submitted by Gather / second", pacemaker("gather_ingest_pacemaker_task_submission", rate=True),
              "{{datasource}}", 12, 37, unit="ops", no_value="No counter yet",
              description="Asynchronous task submissions to Druid by datasource. Counted tasks can contain many rows and must be checked for their actual completion status."),
        panel(14, "AP rows in Druid · previous completed hour", healthy_metric("gather_metric_ds_last_hour_rowCount_per_type", f"{GATHER},{AP}", group="tenantId, objectType"),
              "{{tenantId}} / {{objectType}}", 0, 45,
              description="Gather's periodically refreshed Druid inventory for PCA UE AP object type over the previous completed clock hour (not a rolling hour). Current-hour records are excluded. It is a gauge, not a cumulative insert counter or a per-run acceptance result."),
        panel(15, "Telemetry by backend target", 'up{job=~"ignite|gather|prometheus-gateway|pcaue-ap-agent|druid-.*-jmx"}',
              "{{job}} / {{instance}}", 12, 45,
              description="Deployment telemetry only: 0 failed, 1 successful scrape. Spark application metrics use the Pushgateway; its UP alone does not establish a live Spark application or fresh pushed samples."),
        panel(16, "AP CSV batches rejected · current counters", ignite("ignite_normalizer_csv_parse_errors_total"),
              "{{tenantId}} / {{objectType}}", 0, 53, w=24, no_value="No error counter yet",
              description="Fedex batches rejected by Ignite's CSV parser, not rows. Malformed quoting or column counts can make the entire batch unreadable. Requires the matching instrumented Ignite image; a missing lazy counter is not proof of zero rejected batches. UP targets only; process restarts reset counters."),
    ]
    return {
        "id": None, "uid": "pca-ue-ap-ingestion-swarm", "title": "PCA UE · AP Ingestion",
        "description": "Access-endpoint/session pipeline telemetry, separate from NI ClickHouse insertion.",
        "tags": ["PCA UE", "Swarm", "AP", "ingestion"], "timezone": "browser",
        "schemaVersion": 39, "version": 1, "refresh": "15s", "editable": False,
        "time": {"from": "now-1h", "to": "now"}, "panels": panels,
        "templating": {"list": [variable("tenant", "Tenant", 'label_values(ignite_kafka_total_sent{objectType="CiscoUE-edr-access-endpoint"}, tenantId)')]},
        "annotations": {"list": []},
        "links": [{"title": "PCA UE · EDR Ingestion", "type": "link", "url": "/grafana/d/pca-ue-ingestion-swarm", "targetBlank": False}],
    }


if __name__ == "__main__":
    path = ROOT / "dashboards" / "Customer (swarm)" / DASHBOARD_NAME
    path.write_text(json.dumps(build(), indent=2) + "\n")
    print(path)
