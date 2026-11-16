# Metrics Simulator — Scenario & Profile Generator

## When to Activate

Activate this skill when the user:
- Asks to add simulation profiles or scenarios for a dashboard
- Wants to test how a Grafana dashboard behaves under specific conditions
- Needs to create failure/stress scenarios for pipeline dashboards
- Says "simulate", "scenario", "metrics simulator", or references `tools/metrics-simulator`

## What It Does

The metrics simulator (`tools/metrics-simulator/`) serves fake Prometheus data for all Grafana dashboards. It has two layers of customization:

1. **Profiles** (in `simulator.py` `PROFILES` dict) — define how each metric generates values (lambda functions, label sets)
2. **Scenarios** (in `scenarios.yaml`) — named presets that override metric values to simulate specific conditions (failures, saturation, etc.)

## How to Add Profiles for a New Dashboard

### Step 1: Extract metrics from the dashboard

```bash
python3 tools/metrics-simulator/extract_metrics.py \
  "dashboards/<folder>/<dashboard>.json" --print
```

This prints every metric name the dashboard uses.

### Step 2: Add profiles to `simulator.py`

Open `tools/metrics-simulator/simulator.py` and add entries to the `PROFILES` dict. Each entry maps a metric name to a dict with:

- `"value"`: a `lambda t:` that returns a numeric value. `t` is seconds since start.
- `"labels"`: a dict of label names to lists of values (cartesian product is generated).

Example patterns:

```python
# Constant gauge (status flag)
"my_service_up": {"value": lambda t: 1, "labels": {"instance": ["svc-1:9090"]}},

# Counter (monotonically increasing)
"my_requests_total": {"value": lambda t: int(t * 5) + random.randint(0,10), "labels": {"method": ["GET","POST"]}},

# Gauge with variation
"my_queue_size": {"value": lambda t: 50 + int(20 * math.sin(t / 60)), "labels": {}},

# Small float (latency)
"my_latency_seconds": {"value": lambda t: round(random.uniform(0.01, 0.1), 4), "labels": {"path": ["/api"]}},
```

Metrics without a profile still appear with random values — profiles just make them realistic.

### Step 3: Add scenarios to `scenarios.yaml`

Scenarios override specific metric values to simulate conditions. Add a new entry under `scenarios:`:

```yaml
scenarios:
  my-failure-mode:
    description: "Service X is down — no data flowing"
    overrides:
      my_service_up: 0
      my_requests_total: 0
      my_error_count: 50
```

**Convention for scenario names:** use lowercase-kebab-case describing the failure mode.

**Convention for overrides:** only override the metrics that change from the healthy default. The fewer overrides, the clearer the scenario.

### Step 4: Test

```bash
make sim-up   # rebuilds and starts everything
# Open http://localhost:9999/ for the web UI
# Switch scenarios and check Grafana at http://localhost:3000
```

## File Locations

| File | Purpose |
|------|---------|
| `tools/metrics-simulator/simulator.py` | Main simulator — `PROFILES` dict + web UI + HTTP server |
| `tools/metrics-simulator/scenarios.yaml` | Named simulation scenarios (YAML) |
| `tools/metrics-simulator/extract_metrics.py` | Dashboard JSON parser — extracts metric names |
| `tools/metrics-simulator/docker-compose.yml` | Local stack: simulator + Prometheus + Grafana |
| `tools/metrics-simulator/prometheus.yml` | Prometheus scrape config |
| `tools/metrics-simulator/grafana-provisioning/` | Datasource override for local Prometheus |

## Web UI API Reference

The simulator serves a web UI at `http://localhost:9999/` and these API endpoints:

| Endpoint | Method | Body | Effect |
|----------|--------|------|--------|
| `/api/state` | GET | — | Returns current state (active scenario, overrides, metric list) |
| `/api/scenario` | POST | `{"scenario": "name"}` | Switch to named scenario (null = default) |
| `/api/override` | POST | `{"metric": "name", "value": 42}` | Set manual override for one metric |
| `/api/override` | DELETE | `{"metric": "name"}` | Clear one manual override |
| `/api/overrides` | DELETE | — | Clear all manual overrides |

**Priority:** manual override > scenario override > profile default > random fallback.

## Existing Scenarios

The following scenarios are pre-built for the Path Analytics pipeline:

- `healthy` — all systems nominal
- `pa-disconnected` — PA source unreachable
- `auth-failing` — CAS/auth token rejected
- `cert-expiring` — PA CA cert < 7 days
- `cert-expired` — PA CA cert expired, TLS failing
- `pathmonitor-failing` — REST registration failing
- `data-dropping` — whitelist mismatch, most events dropped
- `downstream-stalled` — Fedex/Kafka pipeline stalled
- `sky-topo-at-capacity` — node count at maximum
- `agent-overloaded` — high processing times
