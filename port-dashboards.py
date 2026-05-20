#!/usr/bin/env python3
"""
Port dashboards from tf_grafana_deployment_config into grafana-docker.

Transformations applied:
1. Replace multi-deployment datasource variable refs with legacy "Prometheus" string
2. Remove repeat/repeatDirection from panels and rows
3. Strip deployment-name prefixes from panel titles
4. Remove legacy panel-level alert blocks (alerts are now provisioned via YAML)
5. Remove the datasource-type template variable; keep query/custom variables
6. Re-point query variables that referenced the deployment datasource
7. Prefix output filenames with ops- to avoid collisions
"""

import json
import os
import re
import copy
import sys

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "tf_grafana_deployment_config", "dashboards")
DST_DIR = os.path.join(os.path.dirname(__file__), "dashboards")

LOCAL_PROM_NAME = "Prometheus"

# All dashboards listed in dashboards.auto.tfvars
DASHBOARDS = [
    "deployment_all.json",
    "airflow_job_status.json",
    "containers_status.json",
    "datasource_availability.json",
    "days_until_cert_expire.json",
    "dgraph_alpha_availability.json",
    "disk_usage.json",
    "druidingestiontasklast24hours.json",
    "druid_segments_reindex.json",
    "hdfs_underreplicatedblocks.json",
    "invalid_dataset.json",
    "kafka_ingestion_rate.json",
    "k8s_cluster_monitoring.json",
    "latent.json",
    "object_type_metrics.json",
    "metricsservicereachability.json",
    "node_exporter.json",
    "pv_storage_inserted_datasets.json",
    "roadrunner.json",
    "spark_ingestion_rate.json",
    "streamingapp_topic_ingestion.json",
    "time_since_last_backup.json",
    "elasticsearch.json",
]

# Known datasource-type variable names used across the source dashboards
DS_VAR_NAMES = {"deployment", "datasource", "Deployment", "DS_PROMETHEUS"}


def find_ds_var_names(dashboard):
    """Discover the actual datasource-type template variable names in this dashboard."""
    names = set()
    for tvar in dashboard.get("templating", {}).get("list", []):
        if tvar.get("type") == "datasource" and tvar.get("query") == "prometheus":
            names.add(tvar["name"])
    return names


def _is_ds_var_ref(s, var_names):
    """Return True if s is a datasource variable reference like ${deployment}."""
    if not isinstance(s, str):
        return False
    for vn in var_names:
        if s == f"${{{vn}}}" or s == f"${vn}":
            return True
    return False


def rewrite_datasource(obj, var_names):
    """Recursively replace datasource refs with the legacy string format.

    Collapses object-form {"type": "prometheus", "uid": "${deployment}"}
    into the plain string "Prometheus" to match existing dashboard conventions.
    """
    if isinstance(obj, dict):
        # Detect prometheus datasource objects referencing a deployment variable
        if (
            obj.get("type") == "prometheus"
            and "uid" in obj
            and _is_ds_var_ref(obj["uid"], var_names)
        ):
            return LOCAL_PROM_NAME
        new = {}
        for k, v in obj.items():
            new[k] = rewrite_datasource(v, var_names)
        return new
    elif isinstance(obj, list):
        return [rewrite_datasource(item, var_names) for item in obj]
    elif isinstance(obj, str):
        if _is_ds_var_ref(obj, var_names):
            return LOCAL_PROM_NAME
        return obj
    return obj


def strip_repeat(panel):
    """Remove repeat and repeatDirection keys from a panel dict."""
    panel.pop("repeat", None)
    panel.pop("repeatDirection", None)
    panel.pop("maxPerRow", None)


def strip_title_prefix(title, var_names):
    """Remove deployment variable prefixes from panel titles."""
    if not isinstance(title, str):
        return title
    for vn in var_names:
        # Patterns: "$deployment - Title", "$deployment Title", "${deployment} Title"
        for pattern in [
            rf"\${{{vn}}}\s*[-–]\s*",   # ${deployment} - 
            rf"\${vn}\s*[-–]\s*",         # $deployment - 
            rf"\${{{vn}}}\s+",            # ${deployment} (space)
            rf"\${vn}\s+",                # $deployment (space)
            rf"\${{{vn}}}",               # ${deployment} alone
            rf"\${vn}",                   # $deployment alone
        ]:
            title = re.sub(pattern, "", title, count=1)
    return title.strip()


def strip_legacy_alerts(panel):
    """Remove legacy panel-level alert blocks."""
    panel.pop("alert", None)


def strip_content_prefix(options, var_names):
    """Remove deployment variable prefixes from text panel content fields."""
    if isinstance(options, dict) and "content" in options:
        options["content"] = strip_title_prefix(options["content"], var_names)


def process_panels(panels, var_names):
    """Process a list of panels: strip repeats, title prefixes, legacy alerts, recurse into rows."""
    for panel in panels:
        strip_repeat(panel)
        strip_legacy_alerts(panel)

        if "title" in panel:
            panel["title"] = strip_title_prefix(panel["title"], var_names)

        if "options" in panel:
            strip_content_prefix(panel["options"], var_names)

        # Recurse into row panels
        if "panels" in panel and isinstance(panel["panels"], list):
            process_panels(panel["panels"], var_names)


def process_templating(dashboard, var_names):
    """
    - Remove datasource-type variables that select the deployment
    - Re-point query variables that referenced the deployment datasource
    """
    tlist = dashboard.get("templating", {}).get("list", [])
    new_list = []
    for tvar in tlist:
        if tvar.get("type") == "datasource" and tvar.get("name") in var_names:
            # Drop the multi-deployment datasource selector
            continue

        # Re-point any variable whose datasource references the deployment variable
        if "datasource" in tvar:
            tvar["datasource"] = rewrite_datasource(tvar["datasource"], var_names)

        new_list.append(tvar)

    dashboard.setdefault("templating", {})["list"] = new_list


def convert_dashboard(src_path, dst_path):
    """Read a source dashboard, apply all transformations, write to destination."""
    with open(src_path, "r") as f:
        dashboard = json.load(f)

    # Discover which variable names this dashboard uses for deployments
    var_names = find_ds_var_names(dashboard)
    if not var_names:
        # Fallback: check for known names
        var_names = DS_VAR_NAMES.copy()

    # 1. Rewrite all datasource references to legacy string format
    dashboard = rewrite_datasource(dashboard, var_names)

    # 2. Process panels: strip repeats, title prefixes, legacy alerts
    if "panels" in dashboard:
        process_panels(dashboard["panels"], var_names)

    # 3. Process templating: remove deployment selector, re-point queries
    process_templating(dashboard, var_names)

    # 4. Clear the hardcoded dashboard ID (let Grafana assign on import)
    dashboard.pop("id", None)

    # 5. Update version to 1 for a clean import
    dashboard["version"] = 1

    # Write output
    with open(dst_path, "w") as f:
        json.dump(dashboard, f, indent=2)
        f.write("\n")

    return var_names


def main():
    converted = []
    skipped = []

    for filename in DASHBOARDS:
        src_path = os.path.join(SRC_DIR, filename)
        if not os.path.exists(src_path):
            skipped.append(filename)
            continue

        dst_filename = f"ops-{filename}"
        dst_path = os.path.join(DST_DIR, dst_filename)
        var_names = convert_dashboard(src_path, dst_path)
        converted.append((filename, dst_filename, var_names))

    print(f"\nConverted {len(converted)} dashboards:")
    for src, dst, vnames in converted:
        print(f"  {src} -> {dst}  (vars: {', '.join(vnames)})")

    if skipped:
        print(f"\nSkipped {len(skipped)} (not found):")
        for s in skipped:
            print(f"  {s}")


if __name__ == "__main__":
    main()
