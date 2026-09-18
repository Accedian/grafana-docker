# AGENTS.md

## Scope and review routing

- These instructions apply to the whole repository. A nearer `AGENTS.md` would take precedence for its subtree.
- For review, audit, inspection, or PR-feedback work, read and follow `code_review.md`; keep review-only detail there.
- Check `git status` before editing. Preserve unrelated user changes and keep generated or temporary output out of commits.

## Repository purpose and layout

This repository packages Grafana as a hardened Docker image, preloads dashboards and provisioning, and publishes a Helm chart.

- `Dockerfile`, `Makefile`, and `run.sh`: image construction, startup initialization, privilege drop, and persisted-data migrations.
- `dashboards/`: file-provisioned Grafana dashboard JSON, including Kubernetes dashboards under `dashboards/kubernetes/`.
- `provisioning/`: Grafana datasource, dashboard-provider, and unified-alerting YAML copied into the image.
- `helm/`: the StatefulSet, services, configuration, Prometheus datasource override, and blackbox exporter.
- `.circleci/config.yml`: BES-backed image/chart build, release, and image-signing workflows.
- `current-version` and `CHANGELOG.md`: release state maintained by the release workflow.

There is no application dependency manager or general test suite. Validation is based on shell syntax, JSON/YAML parsing, Helm rendering, focused fixtures, and image/runtime tests.

## Build and development commands

- `make docker DOCKER_VER=<tag>` builds and loads the local-platform image with Docker Buildx.
- Release pushes default to `linux/amd64`; arm64 is excluded from `BUILD_PLATFORMS` because a bundled plugin is unsupported. On an arm64 workstation, use `LOCAL_BUILD_PLATFORM=linux/amd64` when that plugin prevents a native test build.
- `helm lint helm` lints the checked-in chart; `helm template grafana helm --set grafana.image.tag=test` renders it.
- `make helm DOCKER_VER=<semver>` regenerates `helm/Chart.yaml`, lints, and creates a chart archive. Do not commit the resulting `.tgz`.
- `make url-file` validates `current-version` and writes the image-signing input `urlname.txt`; remove that temporary file after focused testing.
- `make build` is currently a phony target with no recipe, although CI invokes it. A successful `make build` or `build.sh` is not evidence that the image built.

## Dashboard and provisioning changes

- Keep dashboard files valid JSON and avoid whole-file reformatting when making a focused change.
- Give each new provisioned dashboard a stable, non-empty, repository-unique `uid`. Preserve existing UIDs when renaming or extending dashboards so upgrades do not replace the wrong dashboard or break saved links.
- Bind queries and template variables to the intended datasource. The provisioned Prometheus identity is name `Prometheus`, UID `prometheus`, and organization 1; the Helm deployment overlays its Prometheus datasource file with a ConfigMap.
- Verify variable defaults, `All`/multi-select behavior, URL synchronization, label names, grouping dimensions, legends, transformations, units, thresholds, and instant-versus-range query mode. Exercise representative multi-tenant, multi-namespace, multi-node, and multi-cluster cases.
- For counters, use reset-safe PromQL and a range long enough for the scrape/evaluation interval. For alerts, align lookback, evaluation interval, `for`, `noDataState`, and `execErrState` with the failure being detected.
- Treat URL-synchronized variables used in ClickHouse SQL as untrusted input. Prefer query parameters; formatting such as `singlequote`, percent encoding, or disabling URL sync is not by itself a safe SQL boundary.
- Keep stock dashboards baked into the image and file-provisioned from `/var/lib/grafana/dashboards`; do not reintroduce the Kubernetes ConfigMap projection race removed from this path.

## Runtime, image, and deployment invariants

- `run.sh` may start as root, prepares configurable `GF_PATHS_*` locations, reads mounted credentials, copies stock assets, migrates SQLite state, and then runs Grafana through `gosu`. Preserve that ordering for root-only reads and custom paths.
- Persistent volume contents are untrusted and survive restarts. Do not recursively `chown`/`chmod` them or dereference attacker-controlled symlinks as root. Preserve group access for OpenShift random UIDs using GID 0 without broadening world permissions.
- Make SQLite migrations organization-scoped, idempotent, collision-aware, schema-version compatible, and atomic with `sqlite3 -bail` plus rollback behavior. Test both upgrade and restart paths; never leave references rewritten when the owning row update fails.
- Keep the governed base image pinned by readable version and immutable digest. Preserve `TARGETARCH` handling and verify downloaded Grafana/gosu/plugin artifacts for every supported build platform.
- Helm changes must keep selectors, service names, ConfigMap names, image tags, PVC mounts, and `ReadWriteOnce`/replica assumptions mutually consistent. Anonymous access defaults remain disabled; if enabled, its default role remains `Viewer`.
- Treat `.circleci/config.yml` as a credential and deployment boundary. Untrusted revisions can change repository CI configuration, so do not assume branch-local conditions alone protect contexts or runners. Keep read-write credentials on release/signing jobs, never print full environments, and preserve repository/branch restrictions.

## Generated and release-managed files

- `helm/Chart.yaml` declares that it is generated. Edit `helm/Chart.yaml.in`, then regenerate through the Make target when the generated file belongs in the change; never hand-edit it.
- Do not manually bump `current-version` or the generated release headings/dates in `CHANGELOG.md`. If a change needs a human release note, place only that note above `## Current Release` for the release script to consume.
- Do not commit packaged charts, `urlname.txt`, local Grafana data, credentials, rendered secrets, or editor files.

## Required validation

Run the smallest relevant set and report anything that could not be run:

```sh
git diff --check
find dashboards -type f -name '*.json' -print0 | xargs -0 -n1 jq empty
bash -n run.sh start_container.sh push_to_docker_hub.sh
sh -n build.sh
find .circleci provisioning -type f \( -name '*.yml' -o -name '*.yaml' \) -print0 | xargs -0 ruby -e 'require "yaml"; ARGV.each { |f| YAML.load_file(f) }'
helm lint helm
helm template grafana helm --set grafana.image.tag=test >/dev/null
```

- Run shell checks only for touched scripts and Helm checks for chart/configuration changes.
- For `run.sh` migrations or permission handling, add a focused temporary-directory/SQLite fixture covering failure, restart, old-schema, and hostile-path cases.
- For dashboard or alert behavior, validate in Grafana against representative Prometheus/ClickHouse data and include concise visual or query evidence in the PR.
- For Dockerfile, plugin, or architecture changes, run `make docker DOCKER_VER=<test-tag>` when registry/network access is available; otherwise state that CI must supply image-build evidence.
- Before committing, inspect `git diff --stat`, `git diff`, and `git status --short`; the diff must contain only intended source and instruction files.
