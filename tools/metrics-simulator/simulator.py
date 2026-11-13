#!/usr/bin/env python3
"""Metrics simulator with scenario support and web UI.

Reads dashboard JSON files, extracts Prometheus metric names, and serves
simulated values on /metrics. Supports named scenarios from a YAML config
and a web UI for switching scenarios and overriding individual metrics.

Usage:
    python simulator.py [--scenarios scenarios.yaml] [--port 9999]
"""

import argparse
import json
import math
import random
import sys
import time
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

# Allow importing the extractor from the same directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_metrics import extract_from_dashboard  # noqa: E402

_here = Path(__file__).resolve().parent
ROOT = _here
for _ancestor in (_here, *_here.parents):
    if (_ancestor / "dashboards").is_dir():
        ROOT = _ancestor
        break

# ---------------------------------------------------------------------------
# Default label values
# ---------------------------------------------------------------------------
DEFAULT_TENANTS = ["tenant-abc-123", "tenant-xyz-456"]
DEFAULT_INSTANCES = ["ra-collector-1:9100", "ra-collector-2:9100"]
DEFAULT_OBJECT_TYPES = ["ra_summary", "ra_instance"]

# ---------------------------------------------------------------------------
# Built-in metric profiles
# ---------------------------------------------------------------------------
PROFILES = {
    # RA Collector agent health
    "message_agentHealth_RoutingAnalyticsStatusSet": {"value": lambda t: 1.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_SensorAgentStatusSet": {"value": lambda t: 1.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_ConsumedTopologyEventsCount": {"value": lambda t: random.randint(40, 120), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_SuccessfullySentEventsCount": {"value": lambda t: random.randint(35, 115), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_UnsuccessfullySentEventsCount": {"value": lambda t: random.randint(0, 2), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_UnprovisionedTopologyEventsCount": {"value": lambda t: random.randint(0, 5), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_DuplicatedTopologyEventsCount": {"value": lambda t: random.randint(0, 3), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AggregatedTopologyEventsCount": {"value": lambda t: random.randint(5, 25), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AggregationTimePerReductionCount": {"value": lambda t: round(random.uniform(0.001, 0.05), 4), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_CurrentNumLinksSet": {"value": lambda t: 1200 + int(50 * math.sin(t / 300)), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_CurrentUpdateCadenceSet": {"value": lambda t: 900.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AvgEventReadTime": {"value": lambda t: round(random.uniform(0.001, 0.01), 4), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AvgSegmentProcessingTime": {"value": lambda t: round(random.uniform(0.01, 0.08), 4), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AvgBatchProcessingTime": {"value": lambda t: round(random.uniform(0.1, 0.5), 3), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_ProcessedSegmentsCount": {"value": lambda t: random.randint(50, 200), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_PersistenceUsageCount": {"value": lambda t: round(random.uniform(0.005, 0.03), 4), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_CncCaCertExpiryDays": {"value": lambda t: 245.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_CncCaCertExpired": {"value": lambda t: 0.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_ConnectionAttemptsCount": {"value": lambda t: 1, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_ConnectionFailuresCount": {"value": lambda t: 0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AuthTokenRefreshCount": {"value": lambda t: 1, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_AuthTokenFailureCount": {"value": lambda t: 0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_PathmonitorSyncCount": {"value": lambda t: 1, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_PathmonitorRegisteredCount": {"value": lambda t: 350, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_PathmonitorFailureCount": {"value": lambda t: 0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_SubscriptionCount": {"value": lambda t: 1, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_ConfigTlsModeSet": {"value": lambda t: 2, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "message_agentHealth_WhitelistedSegmentsCount": {"value": lambda t: 12, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    # Roadrunner / Sensor Collector
    "roadrunner_connection": {"value": lambda t: 1.0, "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "roadrunner_record_count": {"value": lambda t: int(t * 15) + random.randint(0, 100), "labels": {"tenant": DEFAULT_TENANTS, "objectType": DEFAULT_OBJECT_TYPES}},
    "roadrunner_persistence_service_cached_files": {"value": lambda t: random.randint(0, 5), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "roadrunner_persistence_service_available_batches": {"value": lambda t: random.randint(0, 3), "labels": {"tenant": DEFAULT_TENANTS, "instance": DEFAULT_INSTANCES}},
    "roadrunner_data_dropped_count": {"value": lambda t: int(t * 0.1), "labels": {"tenant": DEFAULT_TENANTS, "reason": ["invalid_data", "no_tenant"]}},
    "roadrunner_websocket_teardown_count": {"value": lambda t: int(t * 0.01), "labels": {}},
    "roadrunner_websocket_rejected_count": {"value": lambda t: 0, "labels": {}},
    "roadrunner_rejected_batches_due_to_unauthorized_tenant_count": {"value": lambda t: 0, "labels": {"connectorId": ["conn-1"]}},
    "roadrunner_rejected_batches_due_to_bad_data_count": {"value": lambda t: 0, "labels": {"connectorId": ["conn-1"]}},
    "roadrunner_rejected_batches_due_to_internal_errors_count": {"value": lambda t: 0, "labels": {"connectorId": ["conn-1"]}},
    # Fedex
    "fedex_record_count": {"value": lambda t: int(t * 12) + random.randint(0, 80), "labels": {"tenant": DEFAULT_TENANTS, "objectType": DEFAULT_OBJECT_TYPES}},
    "fedex_kafka_producer_msg_count": {"value": lambda t: int(t * 10) + random.randint(0, 50), "labels": {"tenant": DEFAULT_TENANTS, "objectType": DEFAULT_OBJECT_TYPES}},
    "fedex_kafka_producer_error_count": {"value": lambda t: 0, "labels": {"tenant": DEFAULT_TENANTS, "objectType": DEFAULT_OBJECT_TYPES, "topic": ["skytopo_raw_in"]}},
    "file_processing_time_seconds_count": {"value": lambda t: int(t * 5) + random.randint(0, 20), "labels": {"tenant": DEFAULT_TENANTS}},
    # Sky-Topo
    "sky_topo_records_processed_total": {"value": lambda t: int(t * 8) + random.randint(0, 40), "labels": {"instance": ["sky-topo:9191"]}},
    "sky_topo_errors_total": {"value": lambda t: int(t * 0.01), "labels": {"instance": ["sky-topo:9191"]}},
    "sky_topo_current_nodes": {"value": lambda t: 85, "labels": {"tenant_id": DEFAULT_TENANTS, "state": ["ACTIVE"]}},
    "sky_topo_max_nodes": {"value": lambda t: 150, "labels": {}},
    "sky_topo_node_provisioning_duration_seconds_sum": {"value": lambda t: t * 0.3, "labels": {}},
    "sky_topo_node_provisioning_duration_seconds_count": {"value": lambda t: int(t * 0.5), "labels": {}},
    # Node Processor
    "node_processor_available_agents": {"value": lambda t: 3, "labels": {}},
    "node_processor_all_segments": {"value": lambda t: 1200, "labels": {}},
    "node_processor_segments_per_agent_we_aim_to": {"value": lambda t: 400, "labels": {}},
    "node_processor_not_assigned_segments": {"value": lambda t: 0, "labels": {}},
    # Gather
    "gather_batch_ingest_reqs_read": {"value": lambda t: int(t * 2) + random.randint(0, 10), "labels": {"tenantId": DEFAULT_TENANTS, "changeType": ["APPEND", "REFRESH"]}},
    "gather_batch_ingest_submit_success": {"value": lambda t: int(t * 1.8) + random.randint(0, 8), "labels": {"tenantId": DEFAULT_TENANTS, "changeType": ["APPEND", "REFRESH"]}},
    "gather_batch_ingest_submit_fail": {"value": lambda t: 0, "labels": {"tenantId": DEFAULT_TENANTS, "changeType": ["APPEND"]}},
    "gather_ingest_pacemaker_queue_size": {"value": lambda t: random.randint(0, 10), "labels": {"datasource": ["tenant-abc-123-some-suffix"]}},
    "gather_ingest_pacemaker_slots_available": {"value": lambda t: random.randint(3, 8), "labels": {}},
    # Druid
    "gather_batch_ingest_long_running_tasks": {"value": lambda t: 0, "labels": {"type": ["refreshed", "delta"]}},
}


# ---------------------------------------------------------------------------
# Simulation state — shared across threads via a lock
# ---------------------------------------------------------------------------
class SimState:
    """Thread-safe simulation state: scenarios and overrides grouped by dashboard."""

    def __init__(self):
        self.lock = threading.Lock()
        # dashboards[name] = {scenarios: {name: {description, overrides}},
        #                      metrics: [{name, description}]}
        self.dashboards = {}
        self.active_dashboard = None   # selected dashboard name or None
        self.active_scenario = None    # selected scenario name or None
        self.manual_overrides = {}     # metric_name -> float value
        self.catalog = []
        self.start_time = time.time()

    def discover_dashboards(self):
        """Auto-discover all dashboard JSON files and group by folder."""
        dashboards_dir = ROOT / "dashboards"
        if not dashboards_dir.is_dir():
            return
        discovered = {}
        for f in sorted(dashboards_dir.rglob("*.json")):
            rel = f.relative_to(dashboards_dir)
            # Key: "folder/file.json" or just "file.json" for root
            key = str(rel)
            discovered[key] = {"scenarios": {}, "metrics": []}
        with self.lock:
            # Merge: discovered provides the full list, existing config adds on top
            for key in discovered:
                if key not in self.dashboards:
                    self.dashboards[key] = discovered[key]
        print(f"Discovered {len(discovered)} dashboard(s) from {dashboards_dir}")

    def load_scenarios(self, path):
        """Load scenarios from a YAML file (grouped by dashboard path)."""
        try:
            import yaml
        except ImportError:
            print("WARNING: pyyaml not installed, scenarios disabled")
            return
        if not path or not Path(path).exists():
            return
        with open(path) as f:
            data = yaml.safe_load(f)
        with self.lock:
            for key, cfg in data.get("dashboards", {}).items():
                if key not in self.dashboards:
                    self.dashboards[key] = {"scenarios": {}, "metrics": []}
                self.dashboards[key]["scenarios"] = cfg.get("scenarios", {})
                self.dashboards[key]["metrics"] = cfg.get("metrics", [])
        total = sum(len(d.get("scenarios", {})) for d in self.dashboards.values())
        configured = sum(1 for d in self.dashboards.values() if d.get("scenarios"))
        print(f"Loaded scenarios for {configured} dashboard(s), {total} scenario(s) from {path}")

    def set_scenario(self, dashboard, scenario):
        with self.lock:
            if dashboard and dashboard not in self.dashboards:
                return False
            if scenario:
                scenarios = self.dashboards.get(dashboard, {}).get("scenarios", {})
                if scenario not in scenarios:
                    return False
            self.active_dashboard = dashboard
            self.active_scenario = scenario
            self.manual_overrides = {}
            return True

    def set_override(self, metric, value):
        with self.lock:
            self.manual_overrides[metric] = float(value)

    def clear_override(self, metric):
        with self.lock:
            self.manual_overrides.pop(metric, None)

    def clear_all_overrides(self):
        with self.lock:
            self.manual_overrides.clear()

    def get_effective_value(self, metric_name, default_val):
        """Return the effective value: manual override > scenario > default."""
        with self.lock:
            if metric_name in self.manual_overrides:
                return self.manual_overrides[metric_name]
            if self.active_dashboard and self.active_scenario:
                db = self.dashboards.get(self.active_dashboard, {})
                sc = db.get("scenarios", {}).get(self.active_scenario, {})
                overrides = sc.get("overrides", {})
                if metric_name in overrides:
                    return float(overrides[metric_name])
        return default_val

    def get_state_dict(self):
        """Return JSON-serialisable state for the API."""
        with self.lock:
            # Group dashboards by folder
            folders = {}
            for key, d in sorted(self.dashboards.items()):
                parts = key.rsplit("/", 1)
                folder = parts[0] if len(parts) > 1 else "General"
                filename = parts[-1]
                if folder not in folders:
                    folders[folder] = {}
                folders[folder][key] = {
                    "filename": filename,
                    "scenarios": {
                        sn: {"description": sv.get("description", ""),
                             "overrides": sv.get("overrides", {})}
                        for sn, sv in d.get("scenarios", {}).items()
                    },
                    "metrics": d.get("metrics", []),
                }
            return {
                "active_dashboard": self.active_dashboard,
                "active_scenario": self.active_scenario,
                "folders": folders,
                "manual_overrides": dict(self.manual_overrides),
                "profiled_metrics": sorted(PROFILES.keys()),
                "total_metrics": len(self.catalog),
            }


STATE = SimState()


# ---------------------------------------------------------------------------
# Metrics generation
# ---------------------------------------------------------------------------
def generate_line(name, labels, value):
    if labels:
        label_str = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}} {value}"
    return f"{name} {value}"


def generate_metrics():
    t = time.time() - STATE.start_time
    lines = []
    seen = set()

    for metric in STATE.catalog:
        name = metric["name"]
        mtype = metric["type"]
        if name in seen:
            continue
        seen.add(name)

        profile = PROFILES.get(name)
        if not profile:
            lines.append(f"# HELP {name} Simulated metric (no profile)")
            lines.append(f"# TYPE {name} {mtype}")
            raw = random.uniform(0, 100) if mtype == "gauge" else int(t * random.uniform(1, 10))
            val = STATE.get_effective_value(name, raw)
            lines.append(f"{name} {val}")
            continue

        lines.append(f"# HELP {name} Simulated metric")
        lines.append(f"# TYPE {name} {mtype}")

        label_spec = profile.get("labels", {})
        if not label_spec:
            raw = profile["value"](t)
            val = STATE.get_effective_value(name, raw)
            lines.append(generate_line(name, {}, val))
        else:
            label_names = sorted(label_spec.keys())
            combos = [{}]
            for lname in label_names:
                new_combos = []
                for combo in combos:
                    for lval in label_spec[lname]:
                        c = dict(combo)
                        c[lname] = lval
                        new_combos.append(c)
                combos = new_combos
            for combo in combos:
                raw = profile["value"](t)
                val = STATE.get_effective_value(name, raw)
                lines.append(generate_line(name, combo, val))

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Web UI HTML
# ---------------------------------------------------------------------------
WEB_UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Metrics Simulator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,-apple-system,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px}
h1{color:#e94560;margin-bottom:4px;font-size:1.5rem}
.subtitle{color:#888;margin-bottom:20px;font-size:.85rem}
.status{padding:8px 12px;border-radius:6px;margin-bottom:16px;font-size:.82rem}
.status.ok{background:#0a3d0a;border:1px solid #1a6e1a;color:#8f8}
.status.info{background:#1a1a4e;border:1px solid #3a3a8e;color:#aaf}
.db-tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.db-tab{padding:8px 16px;background:#0f3460;border:1px solid #1a1a6e;border-radius:6px;
  color:#aaa;cursor:pointer;font-size:.85rem;transition:all .15s}
.db-tab:hover{border-color:#e94560}
.db-tab.active{background:#e94560;color:#fff;border-color:#e94560;font-weight:600}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
.card{background:#16213e;border-radius:8px;padding:16px;border:1px solid #0f3460}
.card h2{color:#e94560;font-size:1rem;margin-bottom:12px;border-bottom:1px solid #0f3460;padding-bottom:8px}
.scenario-btn{display:block;width:100%;text-align:left;padding:10px 14px;margin-bottom:6px;
  background:#0f3460;border:1px solid #1a1a6e;border-radius:6px;color:#e0e0e0;cursor:pointer;
  font-size:.85rem;transition:all .15s}
.scenario-btn:hover{background:#1a1a6e;border-color:#e94560}
.scenario-btn.active{background:#e94560;color:#fff;border-color:#e94560;font-weight:600}
.scenario-btn .desc{font-size:.75rem;color:#aaa;margin-top:3px}
.scenario-btn.active .desc{color:#fcc}
.metric-row{display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid #0f3460;font-size:.82rem}
.metric-row:last-child{border-bottom:none}
.metric-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.metric-name code{color:#7ec8e3;font-size:.8rem}
.metric-desc{font-size:.7rem;color:#888}
.metric-val{width:90px}
.metric-val input{width:100%;padding:4px 6px;background:#0f3460;border:1px solid #1a1a6e;
  border-radius:4px;color:#e0e0e0;font-size:.8rem;font-family:monospace}
.metric-val input:focus{outline:none;border-color:#e94560}
.metric-val input.overridden{border-color:#e94560;background:#2a1030}
.btn-sm{padding:3px 8px;font-size:.7rem;background:#0f3460;border:1px solid #1a1a6e;
  border-radius:4px;color:#e0e0e0;cursor:pointer}
.btn-sm:hover{background:#e94560;border-color:#e94560}
.filter-input{width:100%;padding:8px 10px;background:#0f3460;border:1px solid #1a1a6e;
  border-radius:6px;color:#e0e0e0;font-size:.85rem;margin-bottom:10px}
.filter-input:focus{outline:none;border-color:#e94560}
.metrics-list{max-height:500px;overflow-y:auto}
.actions{display:flex;gap:8px;margin-bottom:12px;align-items:center}
.empty{color:#666;padding:20px;text-align:center;font-size:.85rem}
</style>
</head>
<body>
<h1>Metrics Simulator</h1>
<p class="subtitle">Dashboard-driven Prometheus metrics simulation &mdash;
  <a href="/metrics" style="color:#7ec8e3">/metrics</a> |
  <a href="http://localhost:3000" style="color:#7ec8e3" target="_blank">Grafana</a></p>

<div id="status" class="status info">Loading...</div>

<div class="db-tabs" id="folder-tabs"></div>
<div class="db-tabs" id="file-tabs" style="margin-top:-12px"></div>

<div class="grid">
  <div class="card">
    <h2>Scenarios</h2>
    <div id="scenarios"></div>
  </div>
  <div class="card">
    <h2>Metric Overrides</h2>
    <div class="actions">
      <button class="btn-sm" onclick="clearAll()">Clear all overrides</button>
      <span style="flex:1"></span>
      <span id="override-count" style="font-size:.75rem;color:#888"></span>
    </div>
    <input class="filter-input" id="filter" placeholder="Filter metrics..." oninput="renderMetrics()">
    <div class="metrics-list" id="metrics"></div>
  </div>
</div>

<script>
let state = {};
let selectedFolder = null;
let selectedDashboard = null; // full key like "Customer (swarm)/pca-pa-ingestion-pipeline.json"

async function fetchState() {
  const r = await fetch('/api/state');
  state = await r.json();
  const folders = Object.keys(state.folders || {});
  if (!selectedFolder && folders.length > 0) {
    // Prefer a folder with scenarios
    selectedFolder = folders.find(f =>
      Object.values(state.folders[f]).some(d => Object.keys(d.scenarios||{}).length > 0)
    ) || folders[0];
  }
  if (selectedFolder && !selectedDashboard) {
    const files = Object.keys(state.folders[selectedFolder] || {});
    // Prefer a file with scenarios
    selectedDashboard = files.find(k =>
      Object.keys(state.folders[selectedFolder][k].scenarios||{}).length > 0
    ) || files[0];
  }
  renderFolderTabs();
  renderFileTabs();
  renderScenarios();
  renderMetrics();
  updateStatus();
}

function updateStatus() {
  const el = document.getElementById('status');
  const db = state.active_dashboard;
  const sc = state.active_scenario;
  if (db && sc) {
    const folder = Object.keys(state.folders).find(f => db in state.folders[f]);
    const info = folder ? state.folders[folder][db] : null;
    const desc = info?.scenarios[sc]?.description || '';
    el.className = 'status ok';
    el.innerHTML = `<strong>${db}</strong> &rarr; <strong>${sc}</strong> &mdash; ${desc}`;
  } else {
    const n = Object.keys(state.manual_overrides).length;
    el.className = 'status info';
    el.innerHTML = `Default profiles active. ${n} manual override(s).`;
  }
  document.getElementById('override-count').textContent =
    `${Object.keys(state.manual_overrides).length} override(s)`;
}

function renderFolderTabs() {
  const el = document.getElementById('folder-tabs');
  let html = '';
  for (const folder of Object.keys(state.folders || {})) {
    const active = selectedFolder === folder ? 'active' : '';
    const count = Object.keys(state.folders[folder]).length;
    const hasScenarios = Object.values(state.folders[folder]).some(d => Object.keys(d.scenarios||{}).length > 0);
    const dot = hasScenarios ? ' *' : '';
    html += `<div class="db-tab ${active}" onclick="selectFolder('${folder}')">${folder} (${count})${dot}</div>`;
  }
  el.innerHTML = html;
}

function renderFileTabs() {
  const el = document.getElementById('file-tabs');
  if (!selectedFolder || !state.folders[selectedFolder]) { el.innerHTML = ''; return; }
  const files = state.folders[selectedFolder];
  let html = '';
  for (const [key, d] of Object.entries(files)) {
    const active = selectedDashboard === key ? 'active' : '';
    const sc = Object.keys(d.scenarios || {}).length;
    const style = sc > 0
      ? `font-weight:${active?'600':'normal'};color:${active?'#fff':'#e0e0e0'}`
      : `color:${active?'#fff':'#666'}`;
    html += `<div class="db-tab ${active}" style="${style}" onclick="selectFile('${key}')">
      ${d.filename.replace('.json','')}${sc ? ` (${sc}s)` : ''}</div>`;
  }
  el.innerHTML = html;
}

function selectFolder(name) {
  selectedFolder = name;
  const files = Object.keys(state.folders[name] || {});
  selectedDashboard = files.find(k =>
    Object.keys(state.folders[name][k].scenarios||{}).length > 0
  ) || files[0] || null;
  renderFolderTabs(); renderFileTabs(); renderScenarios(); renderMetrics();
}

function selectFile(key) {
  selectedDashboard = key;
  renderFileTabs(); renderScenarios(); renderMetrics();
}

function getSelectedDb() {
  if (!selectedFolder || !selectedDashboard) return null;
  return (state.folders[selectedFolder] || {})[selectedDashboard] || null;
}

function renderScenarios() {
  const el = document.getElementById('scenarios');
  const db = getSelectedDb();
  if (!db) { el.innerHTML = '<div class="empty">Select a dashboard</div>'; return; }

  const scenarios = db.scenarios || {};
  if (Object.keys(scenarios).length === 0) {
    el.innerHTML = '<div class="empty">No scenarios defined for this dashboard.<br>Add them to scenarios.yaml</div>';
    return;
  }
  const isDefault = !(state.active_dashboard === selectedDashboard && state.active_scenario);
  let html = `<button class="scenario-btn ${isDefault ? 'active' : ''}"
    onclick="setScenario(null)"><strong>Default</strong>
    <div class="desc">Built-in profiles, no scenario overrides</div></button>`;

  for (const [name, s] of Object.entries(scenarios)) {
    const active = (state.active_dashboard === selectedDashboard && state.active_scenario === name) ? 'active' : '';
    const count = Object.keys(s.overrides || {}).length;
    html += `<button class="scenario-btn ${active}" onclick="setScenario('${name}')">
      <strong>${name}</strong> <span style="color:#888;font-size:.7rem">(${count} overrides)</span>
      <div class="desc">${s.description || ''}</div></button>`;
  }
  el.innerHTML = html;
}

function renderMetrics() {
  const el = document.getElementById('metrics');
  const filter = document.getElementById('filter').value.toLowerCase();
  const db = getSelectedDb();
  if (!db) { el.innerHTML = '<div class="empty">Select a dashboard</div>'; return; }

  let metricList = (db.metrics || []).slice();

  if (filter) metricList = metricList.filter(m =>
    m.name.toLowerCase().includes(filter) || (m.description||'').toLowerCase().includes(filter));

  let scenarioOverrides = {};
  if (state.active_dashboard === selectedDashboard && state.active_scenario) {
    const sc = (db.scenarios || {})[state.active_scenario];
    if (sc) scenarioOverrides = sc.overrides || {};
  }

  let html = '';
  for (const m of metricList) {
    const isOverridden = m.name in state.manual_overrides;
    const val = isOverridden ? state.manual_overrides[m.name] : '';
    const cls = isOverridden ? 'overridden' : '';
    const scVal = m.name in scenarioOverrides ? scenarioOverrides[m.name] : null;
    const placeholder = scVal !== null ? `sc:${scVal}` : 'default';
    html += `<div class="metric-row">
      <div class="metric-name">
        <code>${m.name}</code>
        ${m.description ? `<div class="metric-desc">${m.description}</div>` : ''}
      </div>
      <div class="metric-val">
        <input class="${cls}" type="number" step="any" value="${val}"
          placeholder="${placeholder}"
          onchange="setOverride('${m.name}', this.value)"
          title="${m.description || m.name}">
      </div>
      ${isOverridden ? `<button class="btn-sm" onclick="clearOverride('${m.name}')">x</button>` : ''}
    </div>`;
  }
  el.innerHTML = html || '<div class="empty">No metrics defined for this dashboard.<br>Add them to scenarios.yaml</div>';
}

async function setScenario(name) {
  await fetch('/api/scenario', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({dashboard: name ? selectedDashboard : null, scenario: name})
  });
  await fetchState();
}

async function setOverride(metric, value) {
  if (value === '' || value === null) { clearOverride(metric); return; }
  await fetch('/api/override', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({metric, value: parseFloat(value)})
  });
  await fetchState();
}

async function clearOverride(metric) {
  await fetch('/api/override', {
    method: 'DELETE',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({metric})
  });
  await fetchState();
}

async function clearAll() {
  await fetch('/api/overrides', {method: 'DELETE'});
  await fetchState();
}

fetchState();
setInterval(fetchState, 5000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------
class MetricsHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, code=200):
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html, code=200):
        body = html.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/" or path == "/ui":
            self._send_html(WEB_UI_HTML)
        elif path == "/metrics":
            body = generate_metrics().encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok\n")
        elif path == "/api/state":
            self._send_json(STATE.get_state_dict())
        elif path == "/api/scenarios":
            self._send_json({"folders": STATE.get_state_dict()["folders"]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/scenario":
            data = self._read_body()
            dashboard = data.get("dashboard")
            scenario = data.get("scenario")
            if STATE.set_scenario(dashboard, scenario):
                label = f"{dashboard}/{scenario}" if dashboard and scenario else "default"
                print(f"Scenario switched to: {label}")
                self._send_json({"status": "ok", "dashboard": dashboard, "scenario": scenario})
            else:
                self._send_json({"error": f"Unknown: {dashboard}/{scenario}"}, 400)
        elif path == "/api/override":
            data = self._read_body()
            metric = data.get("metric")
            value = data.get("value")
            if metric and value is not None:
                STATE.set_override(metric, value)
                self._send_json({"status": "ok", "metric": metric, "value": value})
            else:
                self._send_json({"error": "metric and value required"}, 400)
        else:
            self.send_response(404)
            self.end_headers()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/override":
            data = self._read_body()
            metric = data.get("metric")
            if metric:
                STATE.clear_override(metric)
                self._send_json({"status": "ok"})
            else:
                self._send_json({"error": "metric required"}, 400)
        elif path == "/api/overrides":
            STATE.clear_all_overrides()
            self._send_json({"status": "ok"})
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


# ---------------------------------------------------------------------------
# Catalog loading
# ---------------------------------------------------------------------------
def load_catalog(args):
    if args.catalog:
        with open(args.catalog) as f:
            return json.load(f)["metrics"]
    files = args.dashboards
    if not files:
        files = sorted(ROOT.joinpath("dashboards").rglob("*.json"))
    all_metrics = {}
    for path in files:
        for name, defn in extract_from_dashboard(Path(path)).items():
            if name not in all_metrics:
                all_metrics[name] = defn
    return sorted(all_metrics.values(), key=lambda m: m["name"])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dashboards", nargs="*", type=Path,
                        help="Dashboard JSON files to simulate")
    parser.add_argument("--catalog", type=Path,
                        help="Pre-built catalog JSON from extract_metrics.py")
    parser.add_argument("--scenarios", type=Path,
                        help="YAML file with named simulation scenarios")
    parser.add_argument("--port", type=int, default=9999,
                        help="Port to serve metrics on (default: 9999)")
    args = parser.parse_args()

    STATE.catalog = load_catalog(args)
    STATE.discover_dashboards()

    if args.scenarios:
        STATE.load_scenarios(args.scenarios)

    profiled = sum(1 for m in STATE.catalog if m["name"] in PROFILES)
    print(f"Loaded {len(STATE.catalog)} metrics ({profiled} profiled, "
          f"{len(STATE.catalog) - profiled} fallback)")
    print(f"Web UI:  http://0.0.0.0:{args.port}/")
    print(f"Metrics: http://0.0.0.0:{args.port}/metrics")

    server = HTTPServer(("0.0.0.0", args.port), MetricsHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
