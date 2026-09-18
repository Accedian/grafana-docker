# AI pull-request review guidance

## Review contract and evidence

- Review the merge-base diff, `AGENTS.md`, affected files, and the nearest existing dashboard/provisioning/runtime analogue. Trace changed values through Docker build, startup copy/migration, Grafana provisioning, Helm rendering, and CircleCI release consumers as applicable.
- Treat CI as partial evidence. `make build` is currently a no-op; passing JSON/YAML syntax checks does not prove PromQL, SQL, alert, startup, or deployment behavior.
- Report only a defect introduced or exposed by changed lines. Anchor every finding to the smallest concrete changed-line range and state the triggering condition, observable impact, and a practical fix or validation direction.
- Use an imperative title with calibrated priority, for example `[P1] Keep UID migration atomic`. Do not report style preferences, formatting churn, vague hardening ideas, or unsupported speculation. If there are no actionable findings, say so and identify material validation gaps separately.

## Architecture and correctness invariants

- The image copies `provisioning/` and `dashboards/` to `/tmp`; `run.sh` refreshes the configured data/provisioning directories unless `DONT_COPY_STOCK_DASHBOARDS` is set, then starts Grafana. Helm mounts a Prometheus datasource ConfigMap over the corresponding `/tmp` file.
- Grafana dashboard identity is the JSON `uid`, not the filename/title. New provisioned dashboards need stable, non-empty, unique UIDs; changed dashboards must preserve intended UIDs, datasource references, variables, and saved-link behavior.
- The canonical Prometheus datasource is `Prometheus`/`prometheus` in organization 1. Review changes across dashboards, alert `datasourceUid` fields, file provisioning, Helm's datasource ConfigMap, and any SQLite migration together.
- Stock dashboards are image-baked to avoid ConfigMap projection races. Flag changes that make startup depend on a separately projected dashboard set or nondeterministic provisioning order.
- The Helm chart deploys a Grafana StatefulSet with a `ReadWriteOnce` PVC and defaults to one replica. Changes to replicas, storage, selectors, service names, image tags, or mounts must remain deployable and must account for concurrent startup/migration access.

## Dashboard and alert review

- Validate PromQL against the actual metric type and labels. Preserve tenant/namespace/node/cluster dimensions where names are only locally unique; prevent accidental many-to-one aggregation, duplicate counting, or cardinality explosions.
- Exercise template variables with default, empty, `All`, multi-select, and URL-provided values. Ensure every variable and panel uses the intended datasource and that selectors still honor the chosen filters.
- Check panel semantics: stat panels should reduce to the intended single value; tables usually need instant queries before joins; legends, transformations, thresholds, units, and sentinel filtering must match returned data.
- Counters require reset-safe `rate`/`increase` and lookbacks containing enough scrape samples. Alert lookback must cover the evaluation interval, and a transient signal must remain true long enough to satisfy `for`.
- Decide `noDataState` and `execErrState` from the monitored failure. Missing data may mean normal absence for event counters but an outage for availability/ingestion signals; flag either false pages or silent failures with a concrete scenario.
- Treat ClickHouse dashboard variables as attacker-controlled SQL input, including URL-synchronized values containing quotes, backslashes, separators, or commas. Do not accept escaping/encoding claims without proving the complete parser boundary; prefer typed query parameters.
- Compare imported/exported dashboards with established repository equivalents. Flag environment-specific defaults, invented metrics, misspelled labels, duplicate UIDs, unresolved `${DS_*}` inputs, or panels whose implementation contradicts their title/description.

## Runtime, persistence, and compatibility review

- `run.sh` operates on a persistent, potentially attacker-modified PVC and may execute as root. Flag recursive ownership/mode changes, top-level symlink dereference, unsafe redirections, broad permissions, or path classification that can escape intended directories.
- Preserve OpenShift random-UID compatibility through GID 0/group access. A fix must work across restarts with a different UID and must not make persisted data world-readable/traversable.
- Check custom `GF_PATHS_DATA`, logs, plugins, provisioning, and config locations, including missing root-owned parents. Root-only OAuth secrets and AWS credential setup must occur without exposing values or creating root-followed symlink/truncation hazards.
- SQLite migrations run before Grafana's own schema migration. Require organization scoping, old-schema guards for optional tables, UID/name collision handling, idempotency, and a single `sqlite3 -bail` transaction whose errors cannot commit partial reference rewrites.
- Review migrations for data custody: target the exact legacy state, preserve administrator-modified or authenticated resources, avoid rewriting unrelated JSON `uid` fields, and retry safely after interruption.
- Preserve compatibility across supported architectures. Docker/Gosu/Grafana URLs, plugin availability, `TARGETARCH`, hardened base-image digest, and Helm image tags must describe artifacts that actually exist for each platform.

## Security, configuration, and deployment review

- Follow untrusted data into shell/Make expansion, SQL, URLs, filenames, Docker tags, and signing inputs. Require allowlisting plus quoting at the final interpreter boundary; multiline values and parser disagreements are concrete bypass cases.
- Never expose credentials in image layers, Helm values/templates, dashboard JSON, logs, `env` output, PR text, or generated artifacts. Secret files and CI contexts must have least privilege and be read only by the intended job/process.
- Repository-controlled CircleCI config is itself mutable by a PR. Verify trust enforcement outside untrusted branch code where needed; scrutinize BES resource classes, contexts, checkout/orb behavior, project-URL checks, fork builds, and release/signing dependencies.
- Release and signing must remain limited to intended upstream `master`/`main` or `release/*` pipelines. Build jobs need usable least-privileged checkout credentials; release jobs need read-write credentials only after a successful build.
- Keep anonymous Grafana access disabled by default and `Viewer`-only when opted in. Review externally reachable services, datasource URLs/authentication, TLS verification, editable provisioning, and any broadened Kubernetes identity or filesystem permission.
- `helm/Chart.yaml` is generated from `helm/Chart.yaml.in`. Flag hand edits, stale generated output when both should change, committed `.tgz` archives, `urlname.txt`, or manual release-version/date churn. Do not demand an ordinary PR bump `current-version`.

## Validation expectations

- All changes: `git diff --check` and an intentional-file check.
- Dashboard JSON: parse every touched file with `jq empty`; verify UID uniqueness and inspect the changed queries/variables in Grafana with representative data. Screenshots are useful behavior evidence, not a substitute for query inspection.
- Provisioning/CircleCI YAML: parse touched non-template YAML. For alert changes, verify evaluation cadence, lookbacks, pending duration, no-data/error behavior, and labels.
- Shell/Make/runtime: run the correct shell syntax check and focused fixtures. Migration tests should cover clean install, representative upgrade, restart/idempotency, collision/error rollback, and missing older-schema tables. Permission tests should cover root and random UID plus symlink/hostile persisted paths in a deliberately privileged environment.
- Helm: run `helm lint helm` and `helm template grafana helm --set grafana.image.tag=test`; inspect rendered selectors, names, mounts, security settings, and values overrides.
- Docker/build changes: require a Buildx image build for relevant platform(s), or clearly identify CI as the missing evidence. A no-op `make build` is not validation.

## Severity and false-positive control

- **P0:** immediate production compromise, credential disclosure, or destructive data loss with broad impact.
- **P1:** exploitable trust-boundary failure, startup/release failure, persistent-data corruption, or a critical alert/dashboard path that is broadly silent or unusable. The condition should be realistic and blocking.
- **P2:** bounded functional, reliability, or compatibility regression with a concrete affected configuration or user workflow.
- **P3:** small but real behavior/documentation defect worth fixing; never use P3 for style, naming preference, or optional cleanup.
- Do not report pre-existing weaknesses unless a changed line worsens them or newly relies on them. Do not infer labels, scrape intervals, schemas, or permissions without repository evidence or authoritative behavior.
- Avoid duplicate findings for one root cause. Prefer the earliest fix point and mention repeated affected sites in the same finding.
- Large exported JSON diffs are not inherently defects. Review semantic fields and query behavior; do not request reformatting or hand cleanup of generated/exported structure.
- Do not require a new framework merely because the repository lacks tests. Ask for the smallest reproducible fixture or rendered/runtime evidence that would catch the identified regression.
