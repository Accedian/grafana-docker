#!/usr/bin/env python3
"""Seed Grafana alert rules via API from factory-default YAML files.

Pushes alert definitions from /tmp/provisioning/alerting/*.yaml into Grafana
via the Provisioning API with X-Disable-Provenance so customers can edit them
in the UI. Existing editable rules are preserved on restart.

Usage:
  seed-alerts.py          # Seed missing defaults; preserve editable rules
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
EDITABLE_HEADERS = {"X-Disable-Provenance": "true"}
FOLDER_PAGE_LIMIT = 1000

# Map folder display names to stable UIDs for the API
FOLDER_UIDS = {
    "General Alerting": "general-alerting",
    "Ingestion": "ingestion",
}

HELP_PATH_PREFIX = "/public/help/"


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


def get_runbook_base_url():
    """Return the full base URL for constructing runbook links.

    Uses GF_SERVER_ROOT_URL (the externally-reachable Grafana URL) when set,
    falls back to GRAFANA_URL.

    Examples:
        GF_SERVER_ROOT_URL=https://host/grafana/  -> https://host/grafana/
        GF_SERVER_ROOT_URL=https://host/grafana    -> https://host/grafana/
        GF_SERVER_ROOT_URL unset, GRAFANA_URL=http://localhost:3000
                                                   -> http://localhost:3000/
    """
    root_url = os.environ.get("GF_SERVER_ROOT_URL", "") or GRAFANA_URL
    if not root_url.endswith("/"):
        root_url += "/"
    return root_url


def resolve_runbook_urls(rules, base_url):
    """Rewrite runbook_url annotations to full, clickable URLs.

    Bare paths like /public/help/foo.html become
    https://host/grafana/public/help/foo.html.
    """
    for rule in rules:
        annotations = rule.get("annotations") or {}
        url = annotations.get("runbook_url", "")
        if url.startswith(HELP_PATH_PREFIX):
            annotations["runbook_url"] = base_url + url.lstrip("/")


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
            resp_body = resp.read().decode()
            if not resp_body:
                return {}
            return json.loads(resp_body)
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


def is_file_provisioned(rule):
    """Return true when Grafana says a rule came from file provisioning."""
    return str(rule.get("provenance", "")).lower() == "file"


def rule_uid(rule):
    """Return a normalized rule UID."""
    uid = rule.get("uid", "")
    return str(uid) if uid is not None else ""


def rule_title(rule):
    """Return a normalized rule title."""
    title = rule.get("title", "")
    return str(title) if title is not None else ""


def rule_folder_uid(rule):
    """Return the folder UID field from Grafana's API response."""
    return rule.get("folderUID") or rule.get("folderUid") or ""


def rule_group_name(rule):
    """Return the rule group field from Grafana's API response."""
    return rule.get("ruleGroup") or rule.get("ruleGroupName") or ""


def index_rules(rules):
    """Build lookup tables for existing alert rules."""
    by_uid = {}
    by_title = {}
    for rule in rules:
        uid = rule_uid(rule)
        title = rule_title(rule)
        if uid:
            by_uid[uid] = rule
        if title and title not in by_title:
            by_title[title] = rule
    return by_uid, by_title


def find_existing_rule(default_rule, by_uid, by_title):
    """Find an existing rule by stable UID, falling back to title."""
    uid = rule_uid(default_rule)
    if uid and uid in by_uid:
        return by_uid[uid]
    title = rule_title(default_rule)
    if title:
        return by_title.get(title)
    return None


def get_group_rules(existing_rules, folder_uid, group_name):
    """Return existing rules that Grafana reports in a folder/rule group."""
    return [
        rule for rule in existing_rules
        if rule_folder_uid(rule) == folder_uid
        and rule_group_name(rule) == group_name
    ]


def find_folder_uid_by_title(name):
    """Return the UID for an existing Grafana folder title, if present."""
    page = 1
    while True:
        query = urllib.parse.urlencode({
            "limit": FOLDER_PAGE_LIMIT,
            "page": page,
        })
        result = grafana_request(f"/api/folders?{query}")
        if not isinstance(result, list):
            _err(f"Looking up folder '{name}' by title: {result}")
            return ""

        for folder in result:
            if str(folder.get("title", "")) == name:
                uid = folder.get("uid")
                if uid:
                    return str(uid)

        if len(result) < FOLDER_PAGE_LIMIT:
            return ""
        page += 1


def ensure_folder(name):
    """Create a Grafana folder if it doesn't exist; return its UID."""
    requested_uid = FOLDER_UIDS.get(name, name.lower().replace(" ", "-"))
    result = grafana_request(f"/api/folders/{requested_uid}")
    if isinstance(result, dict) and result.get("uid") == requested_uid:
        if str(result.get("title", "")) == name:
            return requested_uid
        _err(
            f"Folder uid={requested_uid} already exists with title "
            f"'{result.get('title', '')}', looking up '{name}' by title"
        )

    existing_uid = find_folder_uid_by_title(name)
    if existing_uid:
        if existing_uid != requested_uid:
            _log(
                f"Using existing folder: {name} "
                f"(uid={existing_uid}, requested uid={requested_uid})"
            )
        return existing_uid

    result = grafana_request(
        "/api/folders",
        method="POST",
        data={"uid": requested_uid, "title": name},
    )
    if isinstance(result, dict) and result.get("uid"):
        created_uid = str(result["uid"])
        _log(f"Created folder: {name} (uid={created_uid})")
        return created_uid

    existing_uid = find_folder_uid_by_title(name)
    if existing_uid:
        _log(
            f"Using existing folder after create failed: {name} "
            f"(uid={existing_uid}, requested uid={requested_uid})"
        )
        return existing_uid

    msg = (
        f"Could not find or create folder '{name}' "
        f"(requested uid={requested_uid}): {result}"
    )
    _err(msg)
    raise RuntimeError(msg)


def delete_all_rules():
    """Delete all existing alert rules for factory reset."""
    rules = get_existing_rules()
    deleted = 0
    for rule in rules:
        uid = rule.get("uid")
        if uid:
            result = grafana_request(
                f"/api/v1/provisioning/alert-rules/{uid}",
                method="DELETE",
                headers=EDITABLE_HEADERS,
            )
            if isinstance(result, dict) and "error" in result:
                _err(f"Deleting rule '{uid}': {result}")
            else:
                deleted += 1
    _log(f"Deleted {deleted} existing rules")


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


def rule_payload(rule):
    """Convert a YAML rule into the payload shape Grafana's API accepts."""
    payload = {
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
    if "keepFiringFor" in rule:
        payload["keepFiringFor"] = rule["keepFiringFor"]
    return payload


def single_rule_payload(rule, folder_uid, group_name, org_id):
    """Build a payload for POST/PUT /api/v1/provisioning/alert-rules."""
    payload = rule_payload(rule)
    payload.update({
        "folderUID": folder_uid,
        "ruleGroup": group_name,
        "orgId": org_id,
    })
    return payload


def put_rule_group(folder_uid, group_name, interval, rules):
    """Create or replace a rule group with editable API-provisioned rules."""
    payload = {
        "folderUid": folder_uid,
        "title": group_name,
        "interval": interval,
        "rules": [rule_payload(rule) for rule in rules],
    }
    encoded_group = urllib.parse.quote(group_name, safe="")
    result = grafana_request(
        f"/api/v1/provisioning/folder/{folder_uid}/rule-groups/{encoded_group}",
        method="PUT",
        data=payload,
        headers=EDITABLE_HEADERS,
    )
    if isinstance(result, dict) and "error" in result:
        _err(f"Seeding group '{group_name}': {result}")
        if result.get("status") == 400:
            _err(f"  Payload sent: {json.dumps(payload, indent=2)[:2000]}")
        return False
    return True


def post_rule(rule, folder_uid, group_name, org_id):
    """Create one editable alert rule without overwriting the whole group."""
    payload = single_rule_payload(rule, folder_uid, group_name, org_id)
    result = grafana_request(
        "/api/v1/provisioning/alert-rules",
        method="POST",
        data=payload,
        headers=EDITABLE_HEADERS,
    )
    if isinstance(result, dict) and "error" in result:
        _err(f"Seeding rule '{rule_title(rule)}': {result}")
        if result.get("status") == 400:
            _err(f"  Payload sent: {json.dumps(payload, indent=2)[:2000]}")
        return False
    return True


def seed_from_yaml(yaml_path, existing_rules, base_url):
    """Read a provisioning YAML file and seed its rule groups via API."""
    with open(yaml_path) as f:
        doc = yaml.safe_load(f)

    if not doc or "groups" not in doc:
        return 0

    existing_by_uid, existing_by_title = index_rules(existing_rules)
    total = 0
    for group in doc["groups"]:
        folder_name = group.get("folder", "General Alerting")
        folder_uid = ensure_folder(folder_name)
        group_name = group["name"]
        org_id = group.get("orgId", 1)
        interval = parse_duration(group.get("interval", "1m"))

        rules_raw = group.get("rules", [])
        for r in rules_raw:
            _fix_yaml_types(r)
        resolve_runbook_urls(rules_raw, base_url)

        default_uids = {rule_uid(rule) for rule in rules_raw if rule_uid(rule)}
        default_titles = {
            rule_title(rule) for rule in rules_raw if rule_title(rule)
        }
        group_existing = get_group_rules(existing_rules, folder_uid, group_name)
        non_default_group_rules = [
            rule for rule in group_existing
            if rule_uid(rule) not in default_uids
            and rule_title(rule) not in default_titles
        ]

        file_provisioned = []
        missing = []
        editable_existing = []
        for rule in rules_raw:
            existing = find_existing_rule(rule, existing_by_uid,
                                          existing_by_title)
            if not existing:
                missing.append(rule)
            elif is_file_provisioned(existing):
                file_provisioned.append(rule)
            else:
                editable_existing.append(rule)

        if file_provisioned:
            if editable_existing or non_default_group_rules:
                _err(
                    f"Group '{group_name}' has file-provisioned defaults "
                    "mixed with existing editable or non-default rules; "
                    "not overwriting the group"
                )
                continue
            if put_rule_group(folder_uid, group_name, interval, rules_raw):
                total += len(rules_raw)
                _log(
                    f"Converted file-provisioned group '{group_name}' "
                    f"({len(rules_raw)} rules) -> {folder_name}"
                )
            continue

        if not missing:
            _log(
                f"Group '{group_name}' already has editable defaults; "
                "preserving existing rules"
            )
            continue

        if len(missing) == len(rules_raw) and not group_existing:
            if put_rule_group(folder_uid, group_name, interval, rules_raw):
                total += len(rules_raw)
                _log(
                    f"Seeded group '{group_name}' "
                    f"({len(rules_raw)} rules) -> {folder_name}"
                )
            continue

        seeded = 0
        for rule in missing:
            if post_rule(rule, folder_uid, group_name, org_id):
                seeded += 1
        total += seeded
        if seeded:
            _log(
                f"Seeded {seeded} missing rule(s) in group '{group_name}' "
                f"-> {folder_name}"
            )

    return total


def main():
    force = "--force" in sys.argv

    if not wait_for_grafana():
        sys.exit(1)

    base_url = get_runbook_base_url()
    _log(f"Runbook base URL: {base_url}")

    existing = get_existing_rules()

    if force and existing:
        _log(f"Factory reset: deleting {len(existing)} existing rules")
        delete_all_rules()
        existing = []

    yaml_files = sorted(glob.glob(os.path.join(ALERT_DEFAULTS_DIR, "*.yaml")))
    if not yaml_files:
        _log(f"No YAML files found in {ALERT_DEFAULTS_DIR}")
        return

    total = 0
    for yf in yaml_files:
        _log(f"Processing {os.path.basename(yf)}")
        total += seed_from_yaml(yf, existing, base_url)

    _log(f"Done — seeded or converted {total} alert rules")


if __name__ == "__main__":
    main()
