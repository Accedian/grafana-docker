#!/usr/bin/env python3
"""Verify that all ported ops-*.json dashboards have correct transformations."""

import json
import glob
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DASHBOARD_DIR = os.path.join(SCRIPT_DIR, "dashboards")

BAD_UIDS = [
    "${deployment}",
    "${datasource}",
    "${Deployment}",
    "${DS_PROMETHEUS}",
    "$deployment",
    "$datasource",
    "$Deployment",
    "$DS_PROMETHEUS",
]

errors = []

for fpath in sorted(glob.glob(os.path.join(DASHBOARD_DIR, "ops-*.json"))):
    fname = os.path.basename(fpath)
    try:
        with open(fpath) as fh:
            d = json.load(fh)
    except json.JSONDecodeError as e:
        errors.append(f"{fname}: INVALID JSON: {e}")
        continue

    txt = json.dumps(d)

    # Check no deployment var refs remain
    for bad in BAD_UIDS:
        if bad in txt:
            errors.append(f"{fname}: still contains {bad}")

    # Check templating has no datasource-type vars selecting prometheus
    for tv in d.get("templating", {}).get("list", []):
        if tv.get("type") == "datasource" and tv.get("query") == "prometheus":
            errors.append(
                f"{fname}: still has deployment datasource variable: {tv['name']}"
            )

    # Check no panel-level alerts or repeats
    def check_panels(panels, path):
        for i, p in enumerate(panels):
            if "alert" in p:
                errors.append(f"{fname}: {path}[{i}] still has legacy alert block")
            if "repeat" in p:
                errors.append(f"{fname}: {path}[{i}] still has repeat")
            if "panels" in p and isinstance(p["panels"], list):
                check_panels(p["panels"], f"{path}[{i}].panels")

    check_panels(d.get("panels", []), "panels")

    # Check datasource references use the legacy string format "Prometheus"
    def check_ds_refs(obj, path):
        if isinstance(obj, dict):
            if obj.get("type") == "prometheus" and "uid" in obj:
                errors.append(
                    f"{fname}: {path} has object-form prometheus datasource (should be string \"Prometheus\")"
                )
            for k, v in obj.items():
                check_ds_refs(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                check_ds_refs(item, f"{path}[{i}]")

    check_ds_refs(d, "root")

print(f"Checked {len(glob.glob(os.path.join(DASHBOARD_DIR, 'ops-*.json')))} dashboards")

if errors:
    print(f"\nERRORS ({len(errors)}):")
    for e in errors:
        print(f"  {e}")
    sys.exit(1)
else:
    print("All dashboards pass validation!")
