#!/usr/bin/env python3
"""Build the native PCA UE Swarm dashboard shipped by the Grafana image."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DASHBOARD_NAME = "pca-ue-ingestion.json"
INSERTER = 'job=~"pcaueni_inserter.*"'
CLICKHOUSE = 'job=~"clickhouse[0-9]+[a-z]+"'
CH_EXPORTER = 'job=~"ch_prometheus_exporter.*"'
KAFKA = 'job="kafka-topic-metrics"'
FILTERS = 'tenant_id=~"${tenant:regex}",schema=~"${schema:regex}"'
TOPIC = 'pcaue[.](${tenant:regex})[.](${schema:regex})[.]json'
PROMETHEUS = {"type": "prometheus", "uid": "prometheus"}


def healthy_metric(metric, selectors, rate=False, group=None):
    """Hide stale application samples when their own scrape target is down."""
    sample = f"{metric}{{{selectors}}}"
    if rate:
        sample = f"rate({sample}[$__rate_interval])"
    # Only job is shared by the target health selector; application labels are
    # deliberately absent from up (which must never be filtered by tenant).
    job_selector = selectors.split(",", 1)[0]
    expression = f"({sample} and on (job, instance) (up{{{job_selector}}} == 1))"
    if group:
        expression = f"sum by ({group}) {expression}"
    return expression


def inserter_metric(metric, rate=True, group="tenant_id, schema", selectors=""):
    return healthy_metric(metric, f"{INSERTER},{FILTERS}{selectors}", rate, group)


def inserter_quantile(metric, selectors=""):
    """Leave idle histograms empty, rather than exposing NaN or a healthy zero."""
    buckets = inserter_metric(metric + "_bucket", group="le, tenant_id, schema", selectors=selectors)
    count = inserter_metric(metric + "_count", selectors=selectors)
    return (
        f"histogram_quantile(0.95, {buckets}) "
        f"and on (tenant_id, schema) ({count} > 0)"
    )


def kafka_metric(metric, rate=False, group="consumergroup, topic"):
    selectors = f'{KAFKA},topic=~"{TOPIC}"'
    if "consumergroup" in metric:
        selectors += ',consumergroup=~"${consumerGroup:regex}"'
    sample = f"{metric}{{{selectors}}}"
    if rate:
        # Kafka offsets are gauges. deriv shows the producer's offset movement;
        # rate would treat a retention/recreation reset as a counter reset.
        sample = f"clamp_min(deriv({sample}[$__rate_interval]), 0)"
    else:
        sample = f"clamp_min({sample}, 0)"
    return f"sum by ({group}) ({sample} and on (job, instance) (up{{{KAFKA}}} == 1))"


def variable(name, label, query, regex=""):
    return {
        "allValue": ".*", "current": {"text": "All", "value": "$__all"},
        "datasource": PROMETHEUS, "definition": query, "includeAll": True,
        "label": label, "multi": True, "name": name, "options": [],
        "query": {"query": query, "refId": "StandardVariableQuery"},
        "refresh": 2, "regex": regex, "sort": 1, "type": "query",
    }


def target(expr, legend, ref="A", instant=False):
    return {
        "datasource": PROMETHEUS, "editorMode": "code", "expr": expr,
        "legendFormat": legend, "refId": ref, "range": not instant,
        "instant": instant, "interval": "30s",
    }


def panel(id_, title, expr, legend, x, y, w=12, h=8, description="", unit="short", type_="timeseries", no_value="No data"):
    defaults = {
        "color": {"mode": "palette-classic"}, "mappings": [],
        "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]},
        "unit": unit, "noValue": no_value,
    }
    options = {
        "legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull"]},
        "tooltip": {"mode": "multi", "sort": "desc"},
    }
    if type_ == "stat":
        defaults.update({
            "color": {"mode": "thresholds"}, "decimals": 0,
            "mappings": [{"type": "value", "options": {
                "0": {"text": "DOWN", "color": "red", "index": 0},
                "1": {"text": "UP", "color": "green", "index": 1},
            }}],
            "thresholds": {"mode": "absolute", "steps": [
                {"color": "red", "value": None}, {"color": "green", "value": 1},
            ]},
        })
        options = {"colorMode": "background", "graphMode": "none", "justifyMode": "auto",
                   "orientation": "auto", "textMode": "auto", "wideLayout": True,
                   "reduceOptions": {"calcs": ["last"], "fields": "", "values": False}}
    else:
        defaults["custom"] = {"drawStyle": "line", "lineInterpolation": "linear",
                              "lineWidth": 1, "fillOpacity": 10, "showPoints": "never",
                              "spanNulls": False, "axisCenteredZero": False}
    return {
        "id": id_, "type": type_, "title": title, "description": description,
        "datasource": PROMETHEUS, "gridPos": {"h": h, "w": w, "x": x, "y": y},
        "fieldConfig": {"defaults": defaults, "overrides": []}, "options": options,
        "targets": [target(expr, legend, instant=type_ == "stat")],
    }


def build():
    help_text = (
        "# PCA UE · EDR ingestion on Docker Swarm\n\n"
        "Fedex → Kafka `pcaue.<tenant UUID>.<schema>.json` → "
        "PVStorage `--pcaueni` → ClickHouse.\n\n"
        "**Start with scrape health:** UP confirms telemetry availability, not "
        "successful end-to-end ingestion. `No counter yet` is normal before the "
        "first event; Kafka offset `-1` means unknown.\n\n"
        "Write diagnostics require the instrumented PVStorage image from "
        "`pv-back#1986`."
    )
    panels = [{
        "id": 1, "type": "text", "title": "How to read this dashboard",
        "gridPos": {"h": 5, "w": 24, "x": 0, "y": 0},
        "fieldConfig": {"defaults": {}, "overrides": []},
        "options": {"mode": "markdown", "content": help_text},
    }]
    for id_, title, selector, x in [
        (2, "PCA UE inserter scrapes", INSERTER, 0),
        (3, "Kafka topic exporter scrape", KAFKA, 6),
        (4, "ClickHouse native scrapes", CLICKHOUSE, 12),
        (5, "ClickHouse table exporter scrapes", CH_EXPORTER, 18),
    ]:
        panels.append(panel(id_, title, f"min(up{{{selector}}})", "", x, 5, w=6, h=4,
                            type_="stat", no_value="No targets",
                            description="Worst current scrape state across this component's configured targets. No result means no matching jobs, not healthy. Independent of tenant/schema filters; up measures scrape availability only."))
    health = 'up{job=~"pcaueni_inserter.*|kafka-topic-metrics|clickhouse[0-9]+[a-z]+|ch_prometheus_exporter.*|prometheus"}'
    panels.append(panel(6, "Scrape state by target", health, "{{job}} / {{instance}}", 0, 9, w=24, h=5,
                        description="0 = failed scrape, 1 = successful scrape. Missing targets leave a gap; inspect Prometheus /targets and the deployed profile. Includes Prometheus self-scrape."))
    panels += [
        panel(7, "EDR rows inserted / second", inserter_metric("pcaueni_inserted_rows_total"), "{{tenant_id}} / {{schema}}", 0, 14,
              unit="ops", no_value="No counter yet",
              description="Successful inserted EDR rows per second, summed over inserters, scoped by tenant/schema. Counter starts on the first successful insert. A zero rate can be normal when idle. Only currently UP inserters contribute; compare the health panels before interpreting a partial total."),
        panel(8, "Datasets inserted / second", inserter_metric("pcaueni_inserted_datasets_total"), "{{tenant_id}} / {{schema}}", 12, 14,
              unit="ops", no_value="No counter yet",
              description="Successful dataset insertions per second (batches, not Kafka messages or EDR rows). Lazily initialized after the first insert; UP inserters only."),
        panel(9, "Failed dataset insert attempts · current counters", inserter_metric("pcaueni_invalid_datasets_total", rate=False), "{{tenant_id}} / {{schema}}", 0, 22,
              no_value="No counter yet",
              description="Current cumulative insertion failures across UP inserters, including failed retry attempts; not permanently lost datasets. Each process restart resets its counter. The raw count makes the first-ever failure visible even when rate cannot observe a prior zero sample. Missing counter before the first failure is normal. Inspect inserter logs and ClickHouse pressure when this increases."),
        panel(10, "PCA UE insert attempts / second · by result", inserter_metric("pcaueni_insert_attempts_total", group="tenant_id, schema, result"), "{{tenant_id}} / {{schema}} / {{result}}", 12, 22,
              no_value="No counter yet",
              unit="ops", description="Completed PCA UE insertion attempts per second, split by success/error. A retry is another attempt; errors include cancellation and can include input rejection, readiness or ClickHouse failures. This is not a malformed-row count or permanently lost datasets. First-ever errors are also shown by the current failed-attempt counter. Requires the instrumented PVStorage image; older images expose no series."),
        panel(11, "Kafka consumer lag · messages", kafka_metric("kafka_consumergroup_lag"), "{{consumergroup}} / {{topic}}", 0, 30,
              description="Sum of non-negative lag over partitions for selected PCA UE topics/groups. Kafka message counts differ from EDR row counts. Read with the uncommitted-partition panel: no committed offset (-1) makes lag unknown. Only currently UP topic exporters contribute."),
        panel(12, "PCA UE Kafka topic offset movement / second", kafka_metric("kafka_topic_partition_current_offset", rate=True, group="topic"), "{{topic}}", 12, 30,
              unit="ops", description="Positive movement of the partition end offsets, summed by PCA UE topic. Offsets are gauges, so this uses deriv rather than counter rate; topic recreation/offset resets can make this estimate inaccurate. This is Kafka messages per second, not EDR rows or network bytes."),
        panel(13, "Kafka partitions with no committed consumer offset", f'sum by (consumergroup, topic) ((kafka_consumergroup_current_offset{{{KAFKA},topic=~"{TOPIC}",consumergroup=~"${{consumerGroup:regex}}"}} < bool 0) and on (job, instance) (up{{{KAFKA}}} == 1))', "{{consumergroup}} / {{topic}}", 0, 38,
              description="Number of partitions reporting offset -1. Nonzero means consumer progress/lag cannot yet be established for those partitions. No series may mean the group has not registered, an exporter problem, or no topics; it is not a zero-lag guarantee."),
        panel(14, "ClickHouse exporter query failures / second", healthy_metric("ClickHousePVX_exporter_scrape_failures_total", CH_EXPORTER, rate=True), "{{job}} / {{instance}}", 12, 38,
              unit="ops", no_value="No counter yet", description="Exporter HTTP scrape can be UP even when its database queries fail. Rising failures require investigation of credentials, ClickHouse reachability and exporter query support. Deployment-wide; not filtered by tenant or schema."),
        panel(15, "ClickHouse tracked memory · all databases", healthy_metric("ClickHouseMetrics_MemoryTracking", CLICKHOUSE), "{{job}} / {{instance}}", 0, 46,
              unit="bytes", description="Current ClickHouse tracked memory per node, across all databases. This is backend pressure, not PCA UE tenant memory attribution."),
        panel(16, "ClickHouse background merges · all databases", healthy_metric("ClickHouseMetrics_Merge", CLICKHOUSE), "{{job}} / {{instance}}", 12, 46,
              description="Currently running background merges per node, across all databases. High merge load with rising Kafka lag can indicate storage pressure. Follow the ClickHouse data/cluster analysis links for table parts and disk detail."),
        panel(17, "PCA UE table storage · bytes per replica", healthy_metric("ClickHousePVX_table_parts_bytes", f'{CH_EXPORTER},database="pcaueni",table=~"${{schema:regex}}"'), "{{job}} / {{table}}", 0, 54,
              unit="bytes", description="Bytes in active system.parts for the pcaueni database, one series per table and replica. Schema selects tables; tenant does not filter this panel because these metrics have no tenant label. Do not sum replicas as logical storage. Check exporter query failures too: a reachable exporter can retain a previous table gauge after a failed collection."),
        panel(18, "ClickHouse default disk used · per node", f'(100 * (1 - ClickHouseAsyncMetrics_DiskAvailable_default{{{CLICKHOUSE}}} / (ClickHouseAsyncMetrics_DiskTotal_default{{{CLICKHOUSE}}} > 0))) and on (job, instance) (up{{{CLICKHOUSE}}} == 1)', "{{job}} / {{instance}}", 12, 54,
              unit="percent", description="Used percentage of the default ClickHouse disk per node, across all databases. On a one-VM lab, multiple replicas can report the same underlying disk. Never sum these percentages. Tenant/schema filters do not apply."),
        panel(19, "PCA UE completed attempt duration · p95", inserter_quantile("pcaueni_insert_duration_seconds"), "{{tenant_id}} / {{schema}}", 0, 62,
              unit="s", no_value="No completed attempts in window", description="Estimated p95 duration of completed success/error attempts, including open, readiness waits, ClickHouse write and close. Retries are separate attempts. Histogram buckets are summed across currently UP inserters for the selected tenant/schema. An idle rate window is empty, not zero; open attempts are only visible in the in-progress gauge. Requires instrumented PVStorage."),
        panel(20, "PCA UE ClickHouse write duration · p95", inserter_quantile("pcaueni_insert_stage_duration_seconds", ',stage="write"'), "{{tenant_id}} / {{schema}}", 12, 62,
              unit="s", no_value="No completed writes in window", description="Estimated p95 of completed ClickHouse client.execute calls, including successful and failed calls. Excludes readiness waits, opening/closing input and Kafka transport. Empty when no write call completed in the rate window. Requires instrumented PVStorage."),
        panel(21, "PCA UE readiness waits · p95", inserter_quantile("pcaueni_insert_stage_duration_seconds", ',stage="readiness"'), "{{tenant_id}} / {{schema}}", 0, 70,
              unit="s", no_value="No completed readiness checks in window", description="Estimated p95 of the table-existence, write-access and merge-partition readiness checks combined, including failures. No write-stage observation exists when readiness fails before the write. Empty when idle. Requires instrumented PVStorage."),
        panel(22, "PCA UE inserts in progress", inserter_metric("pcaueni_insert_in_progress", rate=False), "{{tenant_id}} / {{schema}}", 12, 70,
              no_value="No attempt yet", description="Current insertion attempts in progress across UP inserters. The gauge is initialized for a tenant/schema at its first attempt and returns to zero after success/error, including cancellation. It is not Kafka backlog or a queued-dataset count. Requires instrumented PVStorage."),
        panel(23, "PCA UE mean successful batch · EDR rows", f'({inserter_metric("pcaueni_insert_batch_rows_sum")}) / ({inserter_metric("pcaueni_insert_batch_rows_count")} > 0)', "{{tenant_id}} / {{schema}}", 0, 78, w=24,
              no_value="No successful batches in window", description="Mean ClickHouse-reported written rows per successful insertion attempt in the rate window: rate(histogram sum) / rate(histogram count). A successful zero-row write contributes zero; failed attempts do not contribute. Does not parse or count individual malformed input rows. No completed successful batch leaves the panel empty. Requires instrumented PVStorage."),
    ]
    # A negative offset is an uninitialized consumer; exclude its reported lag
    # instead of letting a clamp turn it into an apparently healthy zero.
    lag_selector = f'{KAFKA},topic=~"{TOPIC}",consumergroup=~"${{consumerGroup:regex}}"'
    lag_panel = next(panel for panel in panels if panel["id"] == 11)
    lag_panel["targets"][0]["expr"] = (
        f"sum by (consumergroup, topic) ((kafka_consumergroup_lag{{{lag_selector}}} >= 0) "
        f"and on (job, instance, consumergroup, topic, partition) "
        f"(kafka_consumergroup_current_offset{{{lag_selector}}} >= 0) "
        f"and on (job, instance) (up{{{KAFKA}}} == 1))"
    )
    topics = f'label_values(kafka_topic_partitions{{{KAFKA},topic=~"pcaue[.][^.]+[.][^.]+[.]json"}},topic)'
    schema_topics = f'label_values(kafka_topic_partitions{{{KAFKA},topic=~"pcaue[.](${{tenant:regex}})[.][^.]+[.]json"}},topic)'
    return {
        "id": None, "uid": "pca-ue-ingestion-swarm", "title": "PCA UE · EDR Ingestion",
        "description": "Docker Swarm PCA UE EDR ingestion: scrape health, tenant/schema row and dataset counters, dedicated attempt/stage timings, in-progress writes, batch size, Kafka lag, and ClickHouse pressure. Supports Analytics Lite without Spark or Druid.",
        "tags": ["pca", "pcaue", "swarm", "clickhouse", "kafka"],
        "editable": True, "fiscalYearStartMonth": 0, "graphTooltip": 1,
        "schemaVersion": 41, "version": 1, "refresh": "30s",
        "time": {"from": "now-1h", "to": "now"}, "timepicker": {},
        "timezone": "browser", "weekStart": "", "annotations": {"list": []},
        "links": [
            {"type": "link", "title": title, "url": url, "targetBlank": False, "keepTime": True, "includeVars": False}
            for title, url in [
                ("Roadrunner", "/grafana/d/PNGklt9ik"), ("Fedex", "/grafana/d/crA9QWAVk"),
                ("Kafka consumers", "/grafana/d/jwPKIsniz"), ("ClickHouse", "/grafana/d/NL8v6NlZk"),
                ("ClickHouse data / disk", "/grafana/d/-B3tt7a7z"),
                ("ClickHouse cluster", "/grafana/d/_hAsuzBnz"),
                ("Swarm resources", "/grafana/d/pca-resource-health-swarm"),
            ]
        ],
        "panels": panels,
        "templating": {"list": [
            variable("tenant", "Tenant UUID", topics, "/^pcaue[.]([^.]+)[.].*[.]json$/"),
            variable("schema", "EDR schema", schema_topics, "/^pcaue[.][^.]+[.]([^.]+)[.]json$/"),
            variable("consumerGroup", "PCA UE consumer group", f'label_values(kafka_consumergroup_lag{{{KAFKA},topic=~"{TOPIC}"}},consumergroup)'),
        ]},
    }


if __name__ == "__main__":
    path = ROOT / "dashboards/Customer (swarm)" / DASHBOARD_NAME
    path.write_text(json.dumps(build(), indent=2) + "\n")
