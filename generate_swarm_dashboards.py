#!/usr/bin/env python3
"""Build the supported Swarm subset of the customer Kubernetes dashboards."""

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "dashboards/Customer (k8s)"
DESTINATION = ROOT / "dashboards/Customer (swarm)"
NODE_JOB = 'job=~"sysmetrics|sysmetrics-private-cloud"'
CADVISOR = 'job="cadvisor",instance=~"$cadvisorHost",name=~"$container",name!="",image!=""'
NO_DATA_NOTE = (
    "\n\n**Swarm availability:** Uses existing application/exporter metrics only. "
    "Optional services and inactive data paths may have no data. Missing metrics "
    "are not evidence that a service is healthy; zero traffic can also be normal."
)


def walk(panels):
    for panel in panels:
        yield panel
        yield from walk(panel.get("panels", []))


def variable(name, label, query):
    return {
        "allValue": ".*",
        "current": {"text": "All", "value": "$__all"},
        "datasource": "Prometheus",
        "definition": query,
        "includeAll": True,
        "label": label,
        "multi": True,
        "name": name,
        "options": [],
        "query": {"query": query, "refId": "StandardVariableQuery"},
        "refresh": 2,
        "regex": "",
        "sort": 1,
        "type": "query",
    }


def compact(panels, start=0):
    """Close layout gaps left by omitted panels, preserving horizontal groups."""
    y = start
    previous_y = None
    height = 0
    for panel in panels:
        position = panel["gridPos"]
        original_y = position["y"]
        if original_y != previous_y:
            y += height
            height = 0
            previous_y = original_y
        position["y"] = y
        height = max(height, position["h"])
        compact(panel.get("panels", []), y + position["h"])


def resource_health(dashboard):
    # No Kubernetes inventory, recording rules, requests, OOM reasons or PVC data.
    omitted = {19, 20, 21, 23, 24, 32, 33, 34, 35}
    for panel in walk(dashboard["panels"]):
        if "panels" in panel:
            panel["panels"] = [p for p in panel["panels"] if p["id"] not in omitted]
    dashboard["panels"] = [p for p in dashboard["panels"] if p["id"] not in omitted]
    dashboard["description"] = (
        "Swarm node and container resource pressure using existing sysmetrics "
        "node-exporter jobs and cAdvisor. CPU, memory, disk, I/O-wait, load per "
        "core and container CPU throttling; no Kubernetes or new collectors."
    )
    dashboard["templating"]["list"] = [
        variable("node", "node-exporter host", f"label_values(node_uname_info{{{NODE_JOB}}}, instance)"),
        variable("cadvisorHost", "cAdvisor host", 'label_values(container_last_seen{job="cadvisor"}, instance)'),
        variable("container", "container", 'label_values(container_last_seen{job="cadvisor",instance=~"$cadvisorHost",name!=""}, name)'),
    ]
    dashboard["panels"][0]["options"]["content"] = (
        "# PCA Swarm Resource Health\n\n"
        "Existing node-exporter and cAdvisor metrics show CPU, memory, disk, "
        "I/O-wait, load per core and container CPU throttling. Start with the "
        "cluster overview, find busy nodes, then inspect heavy containers.\n\n"
        "**Filters:** `node` selects node-exporter instances in per-node panels. "
        "Cluster gauges always cover all reporting nodes. `cadvisorHost` and "
        "`container` select container metrics independently: cloud node-exporter "
        "instances use VM names, whereas cAdvisor instances use target addresses. "
        "Container legends include the cAdvisor instance to distinguish hosts.\n\n"
        "**Not collected:** desired/running Swarm replicas, application readiness, "
        "restart counts, OOM termination reasons, resource requests and per-volume "
        "disk usage. Filesystem panels show host storage, not volume attribution. "
        "Missing cAdvisor task metrics are not zero usage."
    )
    container_panels = {
        16: ("Top containers - CPU (cores)", f"topk(15, sum by (instance,name)(rate(container_cpu_usage_seconds_total{{{CADVISOR}}}[$__rate_interval])))"),
        17: ("Top containers - memory", f"topk(15, sum by (instance,name)(container_memory_working_set_bytes{{{CADVISOR}}}))"),
        18: ("Top containers - CPU throttling %", f"topk(15, 100 * sum by (instance,name)(rate(container_cpu_cfs_throttled_periods_total{{{CADVISOR}}}[$__rate_interval])) / (sum by (instance,name)(rate(container_cpu_cfs_periods_total{{{CADVISOR}}}[$__rate_interval])) > 0))"),
    }
    for panel in walk(dashboard["panels"]):
        panel["title"] = panel["title"].replace("Per-pod", "Per-container").replace("Top Disk / PVC Consumers", "Top Host Filesystems")
        if panel["id"] in container_panels:
            panel["title"], panel["targets"][0]["expr"] = container_panels[panel["id"]]
            panel["targets"][0]["legendFormat"] = "{{instance}} / {{name}}"
            panel["description"] = (
                "Existing cAdvisor task metrics, grouped by host and container name. "
                "CPU is in cores; memory is the working set; throttling is the "
                "percentage of CFS periods throttled (only when periods are reported). "
                "Missing task metrics indicate unavailable telemetry, not zero usage."
            )
        elif panel["id"] == 31:
            panel["gridPos"]["w"] = 24
            panel["description"] = "Fullest host filesystems by node and mount. This does not measure individual Docker volumes."
        elif panel["id"] == 10:
            panel["description"] = "Per-node memory utilisation (1 - MemAvailable/MemTotal). High usage risks memory pressure; inspect container working sets. OOM termination reasons are not collected."
        else:
            panel["description"] = panel.get("description", "").replace("pods", "containers").replace("pod", "container").replace("Disk/PVC consumers", "Host Filesystems")
        for target in panel.get("targets", []):
            target["expr"] = target["expr"].replace('job="node-exporter"', NODE_JOB).replace(',cluster=~"$cluster"', "")
            # Cloud cAdvisor/node-exporter discovery inherits a 120-second scrape.
            target["interval"] = "2m"
    compact(dashboard["panels"])


def build(name):
    dashboard = copy.deepcopy(json.loads((SOURCE / name).read_text()))
    dashboard["uid"] = dashboard["uid"] + "-swarm"
    dashboard["id"] = None
    dashboard["version"] = 1
    dashboard["tags"] = sorted(set(dashboard.get("tags", [])) - {"k8s", "kubernetes"} | {"swarm"})
    if name == "pca-resource-health.json":
        resource_health(dashboard)
    else:
        dashboard["description"] += " Swarm: existing application metrics only."
        dashboard["panels"][0]["options"]["content"] += NO_DATA_NOTE
        for panel in walk(dashboard["panels"]):
            for target in panel.get("targets", []):
                # Existing legacy Spark dashboards use the Pushgateway counter names.
                for metric in ("recCount", "droppedRecCount"):
                    target["expr"] = target["expr"].replace(
                        f"spark_AccedianStreamingMetrics_streaming_{metric}{{",
                        f"spark_AccedianStreamingMetrics_streaming_{metric}_total{{",
                    )
    return dashboard


def main():
    for name in (
        "pca-ingestion-pipeline.json",
        "pca-sensor-connectivity.json",
        "pca-application-speed.json",
        "pca-resource-health.json",
    ):
        (DESTINATION / name).write_text(json.dumps(build(name), indent=2) + "\n")


if __name__ == "__main__":
    main()
