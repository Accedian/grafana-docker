# Grafana Docker image

[![CircleCI](https://circleci.com/gh/Accedian/grafana-docker.svg?style=svg)](https://circleci.com/gh/Accedian/grafana-docker)
 
This project builds a Docker image with the latest master build of Grafana.
## Important Notes
If you've modified any of the dashboards that come with packged in this repository, 
make sure to save them as copies of the originals. If you don't do this, you will
lose your changes when you redeploy.

## Running your Grafana container

Start your container binding the external port `3000`.

```
docker run -d --name=grafana -p 3000:3000 grafana/grafana
```

Try it out, default admin user is admin/admin.

In case port 3000 is closed for external clients or there is no access
to the browser - you may test it by issuing:
  curl -i localhost:3000/login
Make sure that you are getting "...200 OK" in response.
After that continue testing by modifying your client request to grafana.

### How production connects to Prometheus

Dashboards refer to the Prometheus datasource by its stable UID, `prometheus`.
They do not contain the Prometheus server URL. Grafana obtains that URL from a
provisioned datasource file when the container starts.

For a Docker Swarm deployment, the image includes
`provisioning/datasources/prometheus-datasource.yaml`. The Dockerfile copies the
`provisioning` directory into the image, and `run.sh` installs it into Grafana's
runtime provisioning directory. Its Prometheus URL is:

```text
http://prometheus:9090/prometheus
```

The `prometheus` hostname is resolved through the deployment's Docker network.
The `/prometheus` path is the route exposed by the production Prometheus
service.

For a Kubernetes deployment, the Helm chart mounts the
`prometheus-datasource` ConfigMap over the image's datasource file. That
ConfigMap points to the in-cluster Prometheus service:

```text
http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090
```

For a self-contained local demonstration of the SLA Report Generator dashboard,
see [`examples/sla-report-generator`](examples/sla-report-generator/README.md).

## Configuring your Grafana container

All options defined in conf/grafana.ini can be overriden using environment
variables by using the syntax `GF_<SectionName>_<KeyName>`.
For example:

```
docker run \
  -d \
  -p 3000:3000 \
  --name=grafana \
  -e "GF_SERVER_ROOT_URL=http://grafana.server.name" \
  -e "GF_SECURITY_ADMIN_PASSWORD=secret" \
  grafana/grafana
```

You can use your own grafana.ini file by using environment variable `GF_PATHS_CONFIG`.

More information in the grafana configuration documentation: http://docs.grafana.org/installation/configuration/

## Grafana container with persistent storage (recommended)

```
# create /var/lib/grafana as persistent volume storage
docker run -d -v /var/lib/grafana --name grafana-storage busybox:latest

# start grafana
docker run \
  -d \
  -p 3000:3000 \
  --name=grafana \
  --volumes-from grafana-storage \
  grafana/grafana
```

## Installing plugins for Grafana 3

Pass the plugins you want installed to docker with the `GF_INSTALL_PLUGINS` environment variable as a comma seperated list. This will pass each plugin name to `grafana-cli plugins install ${plugin}`.

```
docker run \
  -d \
  -p 3000:3000 \
  --name=grafana \
  -e "GF_INSTALL_PLUGINS=grafana-clock-panel,grafana-simple-json-datasource" \
  grafana/grafana
```

## Running specific version of Grafana

```
# specify right tag, e.g. 2.6.0 - see Docker Hub for available tags
docker run \
  -d \
  -p 3000:3000 \
  --name grafana \
  grafana/grafana:2.6.0
```

## Configuring AWS credentials for CloudWatch support

```
docker run \
  -d \
  -p 3000:3000 \
  --name=grafana \
  -e "GF_AWS_PROFILES=default" \
  -e "GF_AWS_default_ACCESS_KEY_ID=YOUR_ACCESS_KEY" \
  -e "GF_AWS_default_SECRET_ACCESS_KEY=YOUR_SECRET_KEY" \
  -e "GF_AWS_default_REGION=us-east-1" \
  grafana/grafana
```

You may also specify multiple profiles to `GF_AWS_PROFILES` (e.g.
`GF_AWS_PROFILES=default another`).

Supported variables:

- `GF_AWS_${profile}_ACCESS_KEY_ID`: AWS access key ID (required).
- `GF_AWS_${profile}_SECRET_ACCESS_KEY`: AWS secret access  key (required).
- `GF_AWS_${profile}_REGION`: AWS region (optional).

## Metrics Simulator

A local development environment that reads dashboard JSON files, extracts every
Prometheus metric name, and serves simulated values so you can preview dashboards
without a real deployment.

### Quick start

```bash
make sim-up
```

Opens three services:

| Service    | URL                          | Notes                    |
|------------|------------------------------|--------------------------|
| Grafana    | http://localhost:3000         | admin / admin            |
| Prometheus | http://localhost:9090         | scrapes simulator at 5s  |
| Simulator  | http://localhost:9999/metrics | raw exposition format    |

Grafana is built from the repo's own Dockerfile, so **all dashboards** from
every folder (General, Customer k8s, Customer swarm, kubernetes) are
auto-provisioned — exactly as in production. Requires GCR auth (`gcloud auth login`).

### Other commands

```bash
make sim-down      # stop and remove containers + volumes
make sim-restart   # restart the simulator (pick up profile changes)
make sim-logs      # tail logs from all three services
make sim-extract   # print every metric name extracted from all dashboards
```

### How it works

1. `tools/metrics-simulator/extract_metrics.py` parses every `expr` field in
   dashboard JSON files and extracts Prometheus metric names using PromQL
   lexical rules.
2. `tools/metrics-simulator/simulator.py` serves a `/metrics` HTTP endpoint in
   Prometheus exposition format. Metrics with a simulation profile get
   realistic values (sinusoidal topology sizes, random jitter on processing
   times, counter increments); the rest get a random fallback.
3. `docker-compose.yml` wires Prometheus (scraping the simulator) and Grafana
   (provisioned with the swarm dashboards and pointing at that Prometheus).

### Web UI & scenarios

The simulator includes a web UI at http://localhost:9999/ for switching between
named failure/stress scenarios and overriding individual metric values in
real-time. Scenarios are defined in `tools/metrics-simulator/scenarios.yaml`.

Pre-built scenarios for the Path Analytics pipeline:

| Scenario | What it simulates |
|---|---|
| `healthy` | All systems nominal |
| `pa-disconnected` | PA source unreachable |
| `auth-failing` | CAS/auth token rejected |
| `cert-expiring` | PA CA cert < 7 days |
| `cert-expired` | PA CA cert expired, TLS failing |
| `pathmonitor-failing` | REST registration failing |
| `data-dropping` | Whitelist mismatch, events dropped |
| `downstream-stalled` | Fedex/Kafka pipeline stalled |
| `sky-topo-at-capacity` | Node count at maximum |
| `agent-overloaded` | High processing times |

### Adding profiles & scenarios for other dashboards

Scenarios and profiles can be generated for any dashboard — see the
`.devin/skills/metrics-simulator/SKILL.md` skill for step-by-step instructions
that AI agents can follow, or use this quick workflow:

1. Extract metrics: `python3 tools/metrics-simulator/extract_metrics.py "dashboards/<folder>/<dashboard>.json" --print`
2. Add entries to `PROFILES` in `simulator.py` (value lambdas + label sets)
3. Add failure scenarios to `scenarios.yaml`
4. `make sim-restart` to pick up changes

Metrics without a profile still appear with random values.

### Customising

To simulate a specific dashboard only:

```bash
cd tools/metrics-simulator
python3 simulator.py --dashboards ../../dashboards/Customer\ \(swarm\)/pca-pa-ingestion-pipeline.json
```

To generate a metric catalog JSON for inspection:

```bash
python3 tools/metrics-simulator/extract_metrics.py \
  "dashboards/Customer (swarm)/pca-pa-ingestion-pipeline.json" \
  -o catalog.json
```

## Changelog

### v4.2.0
* Plugins are now installed into ${GF_PATHS_PLUGINS}
* Building the container now requires a full url to the deb package instead of just version
* Fixes bug caused by installing multiple plugins

### v4.0.0-beta2
* Plugins dir (`/var/lib/grafana/plugins`) is no longer a separate volume

### v3.1.1
* Make it possible to install specific plugin version https://github.com/grafana/grafana-docker/issues/59#issuecomment-260584026

