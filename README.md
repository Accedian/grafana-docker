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

### Generic OAuth client discovery

Standalone Generic OAuth configurations remain owned by Grafana. When no
managed `GRAFANA_OAUTH_CLIENT_ID_DISCOVERY_*` or logout settings are supplied,
startup leaves the configured client ID and sign-out redirect URL unchanged.
Supplying a managed setting opts into the root discovery/logout flow; partial
or invalid managed configurations still fail closed.

The chart can enable Generic OAuth with Authorization Code and PKCE. Supply a
public client ID directly with `grafana.auth.genericOAuth.clientId`, or resolve
it at startup from the root tenant's existing onboarding response.

Skylight-AAA prepares `pca-grafana-pkce` in the root Analytics project through
an explicit Replicated upgrade operation. AAA startup does not provision it.
Prepare the client with OAuth disabled, then activate OAuth only after the
verified client is published in the root tenant metadata.

With an empty `clientIdDiscovery.url`, the chart derives
`https://<root-host>/api/v1/onboarding/tenant-info`. The optional discovery
`host` defaults to Grafana's canonical deployment host; `application`
defaults to `pca-grafana-pkce`. The lookup requires a Zitadel-enabled root
tenant and exactly one named `zitadelConfig.clients` entry with nonempty
`appId` and `clientId`. It never chooses a child tenant's client.

Discovery URLs must use HTTPS in both direct and internal-nginx modes, with
certificate verification enabled. Plaintext URLs are rejected before any
request; curl is restricted to HTTPS and redirects are not followed.

The bounded startup wait retries HTTP failures and invalid, missing, duplicate,
or not-ready JSON responses. Each response is limited while reading to 64 KiB,
including chunked responses; oversized data is rejected. Only the public client
ID is used, not a credential. There is no separate client-ID API or dedicated
discovery port. Discovery through the ordinary HTTPS proxy avoids granting
Grafana broad access to AAA's trusted REST API. Certificate verification stays
enabled. Configure the normal CA trust if the deployment uses a private CA.

For Kubernetes deployments without public loopback routing, set
`clientIdDiscovery.internalNginx: true`. Discovery keeps the canonical HTTPS
URL, TLS SNI, certificate-name checks and root tenant headers, but connects to
the same-namespace `nginx-service` on `global.clusterIPPort` (default 443).
Set `clientIdDiscovery.tlsCASecretName` to the serving Nginx Secret when an
additional CA is needed; only its `ca.crt` is mounted read-only. An empty optional
bundle retains default system trust; unreadable or malformed nonempty bundles
fail closed. Redirects are
rejected. This transport applies only to client discovery, not browser URLs
or Grafana's token/UserInfo requests; the configured issuer must remain
reachable from Grafana. OAuth-disabled and lite deployments do not mount the
discovery CA or perform this lookup.

OAuth disabled means no discovery request and no change to the existing
Docker Swarm CAS authentication path.

Umbrella charts that omit Zitadel in a lite deployment can set
`grafana.auth.genericOAuth.fullDeploymentOnly: true`. When
`global.skylight_full_version` is false, the chart disables Generic OAuth and
its client-ID lookup, leaving Grafana's local login available. This opt-in
does not change standalone chart behavior.

When endpoint overrides are empty, the chart derives the Grafana public host
and Zitadel OAuth endpoints from the global deployment, DNS, external IP, and
authentication-port values. Explicit HTTPS endpoint values take precedence for
deployments with nonstandard routing.

Set `grafana.publicOrigin` for a nonstandard Grafana hostname or HTTPS port,
for example `https://grafana.example.test:8443`. It controls the browser root
URL and default logout return URI without changing the deployment root host
used to discover AAA's client. Origins must have no path, credentials, query
or fragment and ports must be in the range 1–65535. Configure external routing
and TLS separately. An umbrella chart can instead supply these browser-only
settings through `grafana.publicOriginConfigMap`; discovery remains unchanged.
Explicit origins are always validated. Deployment-derived placeholders may
render while OAuth is disabled or gated out in lite installations, or when a
parent-origin ConfigMap supplies the browser settings. Without an external
override, direct OAuth activation validates the derived HTTPS browser origin.
The installer must validate the actual origin supplied through the ConfigMap.
This rendering exemption does not make unresolved discovery or issuer settings
usable at runtime; those settings still need valid deployment values.

Grafana 12.1 does not support Generic OAuth ID-token signature validation. To
avoid consuming unverified ID-token claims, the chart configures the supported
`id_token_attribute_name` setting with a field that Zitadel does not return.
Grafana therefore resolves the user's identity through Zitadel's authenticated
UserInfo endpoint using the access token obtained by the authorization-code
exchange. Helm rendering requires the authorization, token, and UserInfo
endpoints to use HTTPS.

No OAuth client secret is used or accepted by this flow. Keep Basic auth
enabled for internal bootstrap and emergency administration. With OAuth
auto-login enabled, append `?disableAutoLogin=true` to `/grafana/login` to
reach the local login form.

The chart derives Zitadel's HTTPS end-session endpoint and the exact registered
post-logout return URI from the same deployment values. Exact
`endSessionUrl` and `postLogoutRedirectUrl` overrides remain available for
nonstandard routing. At startup, Grafana combines those URLs with the validated
public client ID so signing out terminates the Zitadel browser session before
automatic login can run again.

Generic OAuth does not use Grafana Auth Proxy. The reverse proxy routes the
browser to Grafana, but Zitadel and Grafana establish the user identity through
the OAuth authorization-code exchange. When Generic OAuth is enabled, the chart
explicitly disables Auth Proxy rather than trusting an identity header.

When Generic OAuth is active, the chart also disables anonymous access,
regardless of `grafana.auth.anonymous.enabled`, so dashboards cannot bypass
login. When OAuth is inactive, including gated lite deployments, the configured
anonymous setting is preserved.

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
