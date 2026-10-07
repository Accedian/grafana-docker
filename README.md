# Grafana Docker image

[![CircleCI](https://circleci.com/gh/Accedian/grafana-docker.svg?style=svg)](https://circleci.com/gh/Accedian/grafana-docker)
 
This project builds a Docker image with the latest master build of Grafana.

## System OpenSSL updates

Builds explicitly install `openssl` and `libssl3` from the configured Debian
repositories and require both packages to be at least `3.0.22-1~deb12u1`.
An unavailable repository or an older candidate fails the build. Local builds
and release builds use `--no-cache` to refresh packages instead of reusing an
old dependency layer. `make build` runs the same Dockerfile in the CircleCI
build job before the release job can run.

This minimum is the August 2026 bookworm security update; it does not imply
that every OpenSSL CVE is resolved. Check the
[Debian OpenSSL tracker](https://security-tracker.debian.org/tracker/source-package/openssl)
when updating the floor.

## Image rendering migration

The deprecated `grafana-image-renderer` plugin is no longer bundled, and builds
reject requests to install it through `GF_INSTALL_PLUGINS`. Its embedded OpenSSL
cannot be updated through Debian packages. Grafana documents that the plugin
[no longer receives updates](https://grafana.com/docs/grafana/latest/setup-grafana/image-rendering/).

The image defaults `GF_PLUGINS_DISABLE_PLUGINS` to `grafana-image-renderer`,
and the entrypoint defaults rendering to the loopback HTTP service. Grafana
12.1's renderer backend does not honor the disabled-plugin list on its own;
the HTTP rendering path prevents execution of copies left on persistent data
volumes. No files are deleted from those volumes. Explicit external renderer
URLs in `grafana.ini` or environment settings remain authoritative. If you
override the disabled-plugin list, retain `grafana-image-renderer`. An explicit
environment override takes precedence over `disable_plugins` in `grafana.ini`.
Do not explicitly clear the HTTP renderer URL to restore local-plugin fallback.

The Helm chart enables a separate renderer sidecar by default, pinned to the
supported `v5.12.5` release and its manifest digest. It references the internal
PCA mirror. The renderer and its Grafana callback use loopback inside the same
Pod; the renderer has no Service, Ingress, or published port. Normal interactive
dashboards and panels remain available. PNG exports and alert screenshots use
this service through `GF_RENDERING_SERVER_URL` and `GF_RENDERING_CALLBACK_URL`.
Enabling alert screenshots remains an independent Grafana setting.

Both containers read the same token through Kubernetes Secret references. Helm
generates a 64-character token on first install and reuses the release Secret
on connected upgrades. For GitOps/offline rendering or externally managed
credentials, set `grafana.renderer.existingSecret` and `secretKey`; the operator
then owns Secret creation and rotation. Use a random token of at least 32
characters, with letters, digits or base64/base64url characters; token lists
are rejected to prevent accepting the upstream default token. No token is placed in a ConfigMap or
chart values. Restart both containers together after changing an external
Secret unless the configured reloader performs that restart.

The renderer runs without root, additional capabilities, privilege escalation,
or a writable root filesystem. It has writable temporary storage and shared
memory. Default requests are 500m CPU and 1 GiB RAM; limits allow 4 CPU and
16 GiB RAM. Grafana recommends capacity of at least 4 CPU and 16 GiB for the
service, so size `grafana.renderer.resources` for actual rendering load.

Before release, mirror the pinned image with all platform manifests intact and
verify its digest. Update the aod-deployer Replicated wrapper image mapping and
the verified Grafana chart version when publishing the new component release.
For standalone Docker/Swarm deployments, configure the same three rendering
settings and a shared secret for a supported renderer service. The chart
integration does not update the legacy Swarm stack. Validate PNG exports and
alert screenshots before upgrading a deployment that uses them.

`make build` runs the packaged-plugin check and a real PNG/authentication
integration check against the pinned renderer before release. You can also
run the checks independently:

```bash
bash tests/check-image.sh IMAGE
python3 tests/test-disabled-renderer.py IMAGE
python3 tests/test-renderer.py GRAFANA_IMAGE RENDERER_IMAGE
```

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

In case port 3000 is closed for external clients or you there is no access 
to the browser - you may test it by issuing:
  curl -i localhost:3000/login
Make sure that you are getting "...200 OK" in response.
After that continue testing by modifying your client request to grafana.

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

## Changelog

### v4.2.0
* Plugins are now installed into ${GF_PATHS_PLUGINS}
* Building the container now requires a full url to the deb package instead of just version
* Fixes bug caused by installing multiple plugins

### v4.0.0-beta2
* Plugins dir (`/var/lib/grafana/plugins`) is no longer a separate volume

### v3.1.1
* Make it possible to install specific plugin version https://github.com/grafana/grafana-docker/issues/59#issuecomment-260584026
