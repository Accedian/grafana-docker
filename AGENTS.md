# Grafana Dashboard Verification

The five `dashboards/pca-*.json` dashboards are shared by Kubernetes and Docker
Swarm deployments. Preserve their UIDs when changing them. Provisioning loads
these files from the Grafana image; there is no separate Swarm dashboard set.

Run `make test` (or `python3 -m unittest discover -s tests -v`). Tests use only
the Python standard library and promtool. Install promtool to run PromQL syntax
and fixture evaluations; without it those tests are explicitly skipped. The
fixtures cover unavailable/stale monitoring, desired=0, global services,
rollouts, duplicate scrapes, filters, and cAdvisor total/per-core CPU counters.

Swarm node-exporter jobs are `sysmetrics` and `sysmetrics-private-cloud`;
Kubernetes uses `node-exporter`. Swarm cAdvisor is a separate job/address,
usually port 15001 rather than node-exporter's 9100. Use the separate Swarm host
picker for task resources, and leave cluster at All for metrics without that
label. Shared node and Swarm rate queries use a 2-minute minimum step for
120-second cloud scrapes; Kubernetes-only pod/PVC queries keep their resolution.

Swarm service replicas come from the opt-in host collector in
`../aod-deployer/onprem/ansible/roles/skylight-swarm-metrics`. Its metrics have
`deployment`, `stack`, `service`, `workload` and `mode` labels. Availability
queries require collection success, a last-success timestamp less than 300
seconds old, and a healthy exporter scrape; the window accommodates a
60-second collection timer and 120-second cloud scrapes. Timestamps more than
30 seconds ahead of Prometheus are rejected. Running replicas are not
application readiness. Native job modes and explicitly excluded one-shot
workloads are omitted by the collector; airflow-dags-registry is excluded by
default, without inferring whether its job succeeded. Kubernetes requests, pod restart/termination
reasons, jobs and PVC/OpenEBS usage have no equivalent in these Swarm queries.

## Opt-in runtime checks

The sibling deployer repo contains guarded runtime playbooks for dedicated
Lima VMs; see its AGENTS.md. The active representative dev-baseline VM is
`pca-swarm-baseline-amd64`; the initial ARM/Docker 29 fixture is stopped.
With loopback SSH forwards
from host ports 13000/19090 to guest Grafana 3000/Prometheus 9090, run:

```bash
PCA_SWARM_MONITORING_LIVE=1 python3 -m unittest discover -s tests -p test_pca_live.py -v
python3 tests/capture_pca_ui.py
```

Live tests are skipped by default, require synthetic fixture services and check
Grafana 12.1 provisioning, actual dashboard queries, healthy/partial/down/global
replica states, node metrics and cAdvisor task usage/throttling/limits. The UI
capture script uses installed macOS Chrome with fresh temporary profiles, never
the user's browser profile, and saves screenshots/DOM under a new temp directory.
Unavailable values must use a neutral special-value mapping, not a green colour.

The supplied dev baseline was reproduced on amd64 with Docker 25.0.2, API 1.44
(minimum 1.24), containerd 1.7.24, runc 1.2.2, overlay2 and cgroups v1. All live
checks passed with the existing cAdvisor v0.47.2, including task CPU/memory,
throttling and quota/limit panels, without added capabilities or privileged mode.
No cAdvisor upgrade is required for that tested baseline; production image
references remain unchanged. The initial Docker 29 VM's need for a newer client
is a separate forward-compatibility finding, not a deployed-fleet requirement.
The runtime checks do not validate availability of all real PCA application
metrics; application components are not installed in the synthetic VM.
