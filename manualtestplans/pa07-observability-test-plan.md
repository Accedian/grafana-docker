# PA-07 — local Grafana and metrics-simulator test plan

Prepared against `a7a9ad1be8eada1205a1417324959aaca8526fa2`, updated 2026-11-17, including merged [PR #291](https://github.com/Accedian/grafana-docker/pull/291). Local dashboard/simulator implementation, automated tests, live synthetic QA, and native Grafana review have been executed; packaged PCA verification remains separate.

MVP scope confirmed 2026-11-17: observability only, covered by the edge-case scenarios below. New retry/replay and delivery-policy mechanisms are outside PA-07 MVP. Scenarios must accurately represent existing behavior without making those mechanisms a prerequisite or presenting them as implemented.

The canonical ExecPlan and metric/dashboard contract live in `Accedian/docs`, `projects/path-analytics-on-prem-mvp/docs/pa07-observability-*.md`. The companion `sky-topo/manualtestplans/pa07-observability-test-plan.md` verifies real processing. Synthetic metric output verifies the dashboard only.

## Prerequisites and readiness gate

- Python 3.9+ with venv and Docker Compose. The test runner installs hash-locked dependencies into an owned temporary environment.
- Existing dashboard: [pca-pa-ingestion-pipeline.json](../dashboards/Customer%20%28swarm%29/pca-pa-ingestion-pipeline.json), UID `pca-pa-ingestion-pipeline`.
- Implemented exact-label RA profiles, finite reasons, integrated counters, injected test clock, and missing-series controls in [pa07.py](../tools/metrics-simulator/pa07.py).
- An exclusively owned [loopback QA stack](../tools/metrics-simulator/docker-compose.qa.yml). Inspect effective port bindings before starting. The general simulator also now binds host ports to loopback.
- QA uses the production-like `sky-topo` scrape job. Prometheus generates real `up`; the simulator never synthesizes it. The older general stack retains its separate `metrics-simulator` job.

Use the [QA instructions](../tools/metrics-simulator/PA07.md): `make test-observability`, `make pa07-qa-up`, and `make pa07-qa-test`. The last target stops/restarts only the owned QA simulator as a scrape drill. Record versions and bindings; do not treat a developer fixture as a production access boundary.

## Variables and existing simulator APIs

After starting the isolated QA stack and confirming loopback bindings:

```bash
SIM_URL=http://127.0.0.1:19999
PROM_URL=http://127.0.0.1:19090
GRAFANA_URL=http://127.0.0.1:13000
```

These API checks already match [simulator.py](../tools/metrics-simulator/simulator.py). `curl` succeeds on transport errors only when `--fail-with-body` is used; keep expected negative HTTP tests separate.

```bash
curl --fail-with-body --silent --show-error "$SIM_URL/health"
curl --fail-with-body --silent --show-error "$SIM_URL/api/state"
curl --fail-with-body --silent --show-error "$SIM_URL/api/scenarios"
curl --fail-with-body --silent --show-error "$SIM_URL/metrics"
curl --fail-with-body --silent --show-error \
  -H 'Content-Type: application/json' -X POST "$SIM_URL/api/scenario" \
  --data '{"dashboard":"Customer (swarm)/pca-pa-ingestion-pipeline.json","scenario":"healthy"}'
```

Expected: `/health` HTTP 200, body `ok` plus newline; state/scenarios HTTP 200 JSON. Successful scenario selection returns HTTP 200 with `status: "ok"`, selected dashboard, and `scenario: "healthy"`. This existing scenario alone does not exercise the proposed PA-07 metrics.

Query Prometheus with URL encoding, not hand-built URL query strings:

```bash
curl --fail-with-body --silent --show-error --get "$PROM_URL/api/v1/query" \
  --data-urlencode 'query=up{job="sky-topo"}'
curl --fail-with-body --silent --show-error "$PROM_URL/api/v1/targets"
```

Expected query response has `status: "success"`; inspect actual samples and target health rather than treating HTTP 200 as a passing metric assertion. Use the approved credential mechanism when a QA endpoint requires authentication; do not paste credentials into URLs, process arguments, or result files.

## Implemented RA scenario matrix

All scenarios have two synthetic tenants and both RA record types. Faults affect tenant A/type summary by default; an optional validated target can select the other predefined source. Tenant B stays healthy unless explicitly selected. Generic scalar RA overrides are rejected in favor of these finite scenarios/targets.

| Scenario | Controlled observation | Expected interpretation |
| --- | --- | --- |
| `pa07-healthy-active` | Input and published rows grow, failure deltas zero | Healthy active |
| `pa07-idle` | Flat counters, idle start=0, old valid timestamps | Idle, especially event-driven instance |
| `pa07-numeric-quality` | Published rows plus numeric diagnostics | Quality problem, not an invented dropped-row count |
| `pa07-source-discard` | Decode failures and source-discard marks | Source failure; row count unknown |
| `pa07-row-loss` | Published plus skipped rows, row-loss marks | Mixed source loses rows under current behavior |
| `pa07-publish-failed` | Failed output calls, no output/mark increment | Publication failure |
| `pa07-partial-publication` | Some published rows and failed calls, partial counter | Partial output / replay risk |
| `pa07-stalled` | Positive processing start in the past | Active attempt age exceeds QA threshold |
| `pa07-initializing` | Initializing state persists | Initialization blocked, no fabricated receipt |
| `pa07-metrics-missing` | Omit expected new families, scrape still up | Schema/version/configuration unknown |
| `pa07-restart` | Explicit counter reset and zero timestamps | Process reset, no negative rate or epoch timestamp |
| `pa07-recovery` | Input/output resume and failures stop increasing | Recovery after the diagnostic window |

Target-down testing controls the isolated QA scrape target, not a fabricated counter. It is a separate G-05 operation, not just a scenario override. Metrics must have real `tenant_id`, `record_type`, `stage`, `reason`, `outcome`, and `state` labels as applicable. Do not use the simulator's random fallback as evidence that a metric is implemented.

## Cases

### G-01 — source, JSON, and parser checks

Run the existing Python tests from the repository root and record any baseline failures before changing tests:

```bash
make test-observability
```

Validate dashboard JSON, unique panel IDs, unchanged UID/datasource conventions, and usable variable discovery. Coverage now includes the directly maintained PA dashboard separately from the generator's five dashboards, and registers its snapshot panels correctly. The test runner substitutes variables into temporary recording rules and runs the pinned real `promtool` in an offline container; it must not silently skip the parser. Live QA additionally evaluates every panel query and tenant discovery in Prometheus.

### G-02 — API success and failure contracts

Exercise the existing healthy selection above. POST an unknown dashboard/scenario and expect HTTP 400 with `error: "Unknown: <dashboard>/<scenario>"` for the supplied values. POST `/api/override` without `metric`/`value` and expect HTTP 400, `error: "metric and value required"`. DELETE `/api/override` without `metric` expects HTTP 400, `error: "metric required"`. DELETE `/api/overrides` returns HTTP 200, `status: "ok"`. Verify successful scenario selection clears manual overrides. New M3 validation must reject non-finite values and unapproved label keys without corrupting prior scenario state.

### G-03 — tenant/type filters and units

Use two tenants with deliberately different source-message and row rates. Select each tenant, each RA type, then All. Check the Prometheus API results and panel legends: only matching series contribute, and All equals the intended aggregation. Both types remain discoverable when upstream Roadrunner/FedEx series are omitted. Legacy errors without a type label must not pretend to support type filtering. Source messages are not compared one-for-one with rows; failure events are not presented as a rejected-row percentage. Quantities and activity ages are separate; no packet-loss percentage may be inferred from a message/row difference. A tenant dropdown is not an authorization test.

### G-04 — active, quality errors, source loss, row loss, and partial output

Run the first seven scenario rows individually. Inspect direct fixture values, Prometheus query results, and Grafana panels. Numeric diagnostics may coexist with all rows published; decode failure must not invent skipped-row counts. A row skip differs from producer failure. Partial publication is a risk indicator, not the number of duplicates or a transaction abort. Verify scoped diagnostic legends and source-mark dispositions. No rejected-topic panel, replay control, or DLQ prerequisite is introduced.

### G-05 — idle, stalled, initializing, and telemetry failure

Use the controllable clock to test boundaries around the configured diagnostic window and active-age threshold. Old output with no input and idle start=0 is idle, not stalled. An old positive start is stalled. Prolonged initializing is distinct from a running idle processor. Omit a new family with `up=1` to test old-version/missing-metric behavior. Then stop only the owned simulator target to produce actual `up=0`; remove its QA target to demonstrate target absence separately. Do not stop shared services. Missing data must not become healthy zero through Grafana transformations or `or vector(0)`.

### G-06 — scenario transitions, counter reset, and recovery

Run healthy → fault → recovery without restarting the simulator. Every counter must stay monotonic across rate/scenario changes; timestamp/state gauges change as specified. Use an explicit restart fixture to test `rate`/`increase` across resets. Failures stop accumulating after recovery; historical totals stay visible, while the current error window eventually clears. Do not reset counters manually to make the UI green. Record expected scrape interpolation effects rather than demanding exact random counts from `increase`.

### G-07 — exposition and bounded profiles

Parse exposition with the actual Prometheus parser. Require explicit profiles for every new family; verify only the 21 valid stage/reason pairs and at most 36 active samples per configured tenant/type/instance. Include synthetic hostile strings at the appropriate boundary and confirm they cannot create arbitrary labels/series or alter JSON/HTML structure. Scenario controls may select predefined tenant/type/reason series but cannot turn a payload into label structure. Repeat tests with deterministic seeds and a controlled clock.

### G-08 — visual reading and RA flow accuracy

Open the existing dashboard in Grafana and inspect a common laptop viewport and expanded diagnostic rows. Check labels, units, legends, color/value mappings, readable no-data/never-seen states, time-range changes, tooltip content, and navigation back to collector context. Correct the top summary to Kafka → Sky-Topo → Kafka → Druid; do not use Gather batch-ingest counters as proof of the final RA hop. Capture screenshots for active/error/idle/missing states and the associated query JSON. Screenshots alone are insufficient.

### G-09 — access boundary and compatibility

Verify the QA stack binds only to loopback and does not expose unauthenticated controls on a shared interface. In the packaged remote test, verify real Grafana/Prometheus operator access and denied unauthenticated/lower-privilege access where required by that deployment. Preserve existing collector panels and old metric queries; no credentials or fake canary payload appear in screenshots, panel titles, or result artifacts. Do not treat changing a dashboard variable as tenant authorization enforcement.

## Teardown

Clear scenario/manual overrides, save sanitized results, and run `make pa07-qa-down` to stop only the named QA project. The older `make sim-down` removes general-simulator volumes: use it only for an exclusively owned stack. Do not purge unrelated Docker resources or retain authentication material in evidence.

## Agent Demo Mode

For an interactive live walkthrough, perform setup first, report setup failures, then present one case at a time with sanitized command/query, relevant result, and objective verdict. Wait for user continuation between interactive cases. A requested written demo or screenshot walkthrough is prepared as a complete artifact without per-case pauses; see the [recorded observability demo](pa07-observability-demo.md). Normal test execution runs the selected suite without per-case confirmation. Use the companion exploratory plan for agent-chosen scenarios/order.

## Test Run Results

2026-11-16 — G-01 baseline portion executed on the inspected master revision before any runtime code changes: `python3 -m unittest discover -s tests -v` ran 23 tests, reported 11 failing assertions across two methods, and skipped one PromQL test because `promtool` is not installed. Ten failures concern snapshot/sparkline panels 3–8 and 44–47 of the existing PA dashboard, which is absent from `SNAPSHOT_IDS`; the other concerns the supported Swarm dashboard set excluding the PA dashboard. M3 must reconcile intended snapshot/history behavior and explicit dashboard coverage, rather than changing all stat panels to range queries merely to satisfy a stale assumption.

At the 2026-11-16 planning checkpoint, the new G-01 additions and G-02–G-09 runtime cases were NOT RUN; metrics, scenarios, QA entry point, and dashboard changes were pending implementation. This historical status is superseded by the local implementation result below.

2026-11-17 — local implementation run: 33 Python tests passed with the actual PromQL parser and no skips. The old snapshot/list baseline failures are resolved by explicit PA coverage and query-mode contracts. Actual HTTP tests exercise valid controls plus malformed roots, invalid targets, unknown scenarios, negative/non-finite/extreme rates, and preservation of prior state. Both Compose files parse, bind host ports to loopback, and pass Docker Compose configuration validation. Live Prometheus/Grafana QA passed all panel queries, tenant discovery, scoped quality/loss/partial/source scenarios, stall versus idle, missing telemetry with healthy scrape, explicit reset/recovery, and actual scrape failure/recovery by stopping only the owned simulator. Native Grafana 12.1.0 review confirmed quantities, readable state/activity tables, neutral inactive state, and tenant/type selection down to one source. Timestamp formatting is limited to timestamp columns, not tenant/instance strings. G-09's packaged authorization matrix and full target-removal/capacity qualification remain NOT RUN; synthetic QA does not prove real Kafka or Druid delivery.

2026-11-17 — requested screenshot walkthrough: captured seven original Grafana views for healthy traffic, numeric quality, partial publication, idle, stalled processing, missing source telemetry and recovery. Companion real-Prometheus JSON samples passed scenario/scope/dashboard-checksum and expected-observation checks. The documented curl helper was exercised for recovery; its unsupported-scenario guard and all 13 shell blocks passed Bash/Zsh checks. The demo remains running on loopback in recovery state for review. No application code, remote deployment or processing policy changed in this documentation/demo increment.
