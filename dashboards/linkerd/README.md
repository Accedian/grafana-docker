# Official Linkerd dashboards

These dashboards come from the [Linkerd edge-26.6.3 dashboard catalog](https://github.com/linkerd/linkerd2/blob/edge-26.6.3/grafana/values.yaml).
They are bundled in the image, so startup does not require an Internet connection.

Import-only Prometheus placeholders are replaced with PCA's existing datasource UID,
`prometheus`. Upstream dashboard UIDs, queries, and navigation links are preserved.
Instance-specific dashboard IDs are cleared for file provisioning.

| File | Grafana dashboard ID | Revision |
| --- | --- | --- |
| `top-line.json` | [15474](https://grafana.com/grafana/dashboards/15474/) | 4 |
| `health.json` | [15486](https://grafana.com/grafana/dashboards/15486/) | 3 |
| `kubernetes.json` | [15479](https://grafana.com/grafana/dashboards/15479/) | 2 |
| `namespace.json` | [15478](https://grafana.com/grafana/dashboards/15478/) | 3 |
| `deployment.json` | [15475](https://grafana.com/grafana/dashboards/15475/) | 6 |
| `pod.json` | [15477](https://grafana.com/grafana/dashboards/15477/) | 3 |
| `service.json` | [15480](https://grafana.com/grafana/dashboards/15480/) | 3 |
| `route.json` | [15481](https://grafana.com/grafana/dashboards/15481/) | 3 |
| `authority.json` | [15482](https://grafana.com/grafana/dashboards/15482/) | 3 |
| `cronjob.json` | [15483](https://grafana.com/grafana/dashboards/15483/) | 3 |
| `job.json` | [15487](https://grafana.com/grafana/dashboards/15487/) | 3 |
| `daemonset.json` | [15484](https://grafana.com/grafana/dashboards/15484/) | 3 |
| `replicaset.json` | [15491](https://grafana.com/grafana/dashboards/15491/) | 3 |
| `statefulset.json` | [15493](https://grafana.com/grafana/dashboards/15493/) | 3 |
| `replicationcontroller.json` | [15492](https://grafana.com/grafana/dashboards/15492/) | 4 |
| `prometheus.json` | [15489](https://grafana.com/grafana/dashboards/15489/) | 2 |
| `prometheus-benchmark.json` | [15490](https://grafana.com/grafana/dashboards/15490/) | 2 |
| `multicluster.json` | [15488](https://grafana.com/grafana/dashboards/15488/) | 3 |
