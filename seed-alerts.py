#!/usr/bin/env python3
"""Seed Grafana alert rules via API from factory-default YAML files.

On first boot (no existing rules), pushes all alert definitions from
/tmp/provisioning/alerting/*.yaml into Grafana via the Provisioning API
with X-Disable-Provenance so customers can edit them in the UI.

Usage:
  seed-alerts.py          # Seed only if no rules exist (first-boot)
  seed-alerts.py --force  # Factory reset: delete existing rules and re-seed
"""

import glob
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error

import yaml

GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://localhost:3000")
ALERT_DEFAULTS_DIR = "/tmp/provisioning/alerting"
MAX_WAIT_SECONDS = 120
POLL_INTERVAL = 2

# Map folder display names to stable UIDs for the API
FOLDER_UIDS = {
    "General Alerting": "general-alerting",
    "Ingestion": "ingestion",
}


def parse_duration(val):
    """Convert a duration value to integer seconds.

    Accepts: int, float, or strings like '14400s', '1m', '5m', '2h', '1d'.
    The Grafana Provisioning API expects interval as integer seconds.
    """
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().lower()
    if s.endswith("d"):
        return int(s[:-1]) * 86400
    if s.endswith("h"):
        return int(s[:-1]) * 3600
    if s.endswith("m"):
        return int(s[:-1]) * 60
    if s.endswith("s"):
        return int(s[:-1])
    return int(s)


def _log(msg):
    print(f"[seed-alerts] {msg}", flush=True)


def _err(msg):
    print(f"[seed-alerts] ERROR: {msg}", file=sys.stderr, flush=True)


def grafana_request(path, method="GET", data=None, headers=None):
    """Make an HTTP request to the local Grafana instance."""
    url = f"{GRAFANA_URL}{path}"
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        resp_body = e.read().decode() if e.fp else ""
        return {"error": resp_body, "status": e.code}
    except Exception as e:
        return {"error": str(e)}


def wait_for_grafana():
    """Poll Grafana health endpoint until ready."""
    deadline = time.time() + MAX_WAIT_SECONDS
    while time.time() < deadline:
        try:
            req = urllib.request.Request(f"{GRAFANA_URL}/api/health")
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    _log("Grafana is ready")
                    return True
        except Exception:
            pass
        time.sleep(POLL_INTERVAL)
    _err("Grafana did not become ready within %ds" % MAX_WAIT_SECONDS)
    return False


def get_existing_rules():
    """Return list of existing alert rules, or empty list."""
    result = grafana_request("/api/v1/provisioning/alert-rules")
    if isinstance(result, list):
        return result
    return []


def ensure_folder(name):
    """Create a Grafana folder if it doesn't exist; return its UID."""
    uid = FOLDER_UIDS.get(name, name.lower().replace(" ", "-"))
    result = grafana_request(f"/api/folders/{uid}")
    if isinstance(result, dict) and result.get("uid") == uid:
        return uid
    result = grafana_request(
        "/api/folders", method="POST", data={"uid": uid, "title": name}
    )
    if isinstance(result, dict) and result.get("uid"):
        _log(f"Created folder: {name} (uid={uid})")
        return result["uid"]
    # Folder may already exist with a different UID — try by title
    _err(f"Could not create folder '{name}': {result}")
    return uid


def delete_all_rules():
    """Delete all existing alert rules for factory reset."""
    rules = get_existing_rules()
    for rule in rules:
        uid = rule.get("uid")
        if uid:
            grafana_request(
                f"/api/v1/provisioning/alert-rules/{uid}", method="DELETE"
            )
    _log(f"Deleted {len(rules)} existing rules")


def _fix_yaml_types(obj):
    """Recursively fix values that PyYAML may parse with wrong types.

    - datasourceUid/uid: unquoted 000000001 → octal int 1 → back to "000000001"
    - evaluator.params: ensure values are numeric (Grafana expects float64)
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "datasourceUid" and isinstance(v, int):
                obj[k] = str(v).zfill(9)
            elif k == "uid" and isinstance(v, int):
                obj[k] = str(v).zfill(9)
            elif k == "evaluator" and isinstance(v, dict):
                params = v.get("params", [])
                if isinstance(params, list):
                    v["params"] = [
                        float(p) if isinstance(p, str) else p
                        for p in params
                    ]
                _fix_yaml_types(v)
            else:
                _fix_yaml_types(v)
    elif isinstance(obj, list):
        for item in obj:
            _fix_yaml_types(item)


def seed_from_yaml(yaml_path):
    """Read a provisioning YAML file and seed its rule groups via API."""
    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    if not doc or "groups" not in doc:
        return 0

    total = 0
    for group in doc["groups"]:
        folder_name = group.get("folder", "General Alerting")
        folder_uid = ensure_folder(folder_name)
        group_name = group["name"]
        interval = parse_duration(group.get("interval", "1m"))

        rules_raw = group.get("rules", [])
        for r in rules_raw:
            _fix_yaml_types(r)

        api_rules = []
        for rule in rules_raw:
            api_rules.append(
                {
                    "uid": rule.get("uid", ""),
                    "title": rule["title"],
                    "condition": rule["condition"],
                    "data": rule["data"],
                    "noDataState": rule.get("noDataState", "NoData"),
                    "execErrState": rule.get("execErrState", "Error"),
                    "for": rule.get("for", "5m"),
                    "labels": rule.get("labels", {}),
                    "annotations": rule.get("annotations", {}),
                    "isPaused": rule.get("isPaused", False),
                }
            )

        payload = {
            "name": group_name,
            "interval": interval,
            "rules": api_rules,
        }

        # X-Disable-Provenance makes the rules editable in the UI
        encoded_group = urllib.parse.quote(group_name, safe="")
        result = grafana_request(
            f"/api/v1/provisioning/folder/{folder_uid}/rule-groups/{encoded_group}",
            method="PUT",
            data=payload,
            headers={"X-Disable-Provenance": "true"},
        )

        if isinstance(result, dict) and "error" in result:
            _err(f"Seeding group '{group_name}': {result}")
            if result.get("status") == 400:
                _err(f"  Payload sent: {json.dumps(payload, indent=2)[:2000]}")
        else:
            total += len(api_rules)
            _log(
                f"Seeded group '{group_name}' "
                f"({len(api_rules)} rules) -> {folder_name}"
            )

    return total


def main():
    force = "--force" in sys.argv

    if not wait_for_grafana():
        sys.exit(1)

    existing = get_existing_rules()
    if existing and not force:
        _log(
            f"{len(existing)} alert rules already exist — skipping seed "
            "(use --force to factory-reset)"
        )
        return

    if force and existing:
        _log(f"Factory reset: deleting {len(existing)} existing rules")
        delete_all_rules()

    yaml_files = sorted(glob.glob(os.path.join(ALERT_DEFAULTS_DIR, "*.yaml")))
    if not yaml_files:
        _log(f"No YAML files found in {ALERT_DEFAULTS_DIR}")
        return

    total = 0
    for yf in yaml_files:
        _log(f"Processing {os.path.basename(yf)}")
        total += seed_from_yaml(yf)

    _log(f"Done — seeded {total} alert rules")


if __name__ == "__main__":
    main()
