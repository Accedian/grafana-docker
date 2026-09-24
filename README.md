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

The chart can enable Generic OAuth with Authorization Code and PKCE. A public
client ID can be supplied directly with `grafana.auth.genericOAuth.clientId`,
or resolved at container startup from the configured discovery endpoint. The
startup lookup is bounded and fails closed if the endpoint never returns a
valid public client ID for the exact organization, project, and application
names.

When endpoint overrides are empty, the chart derives the Grafana public host
and Zitadel OAuth endpoints from the global deployment, DNS, external IP, and
authentication-port values. Explicit HTTPS endpoint values take precedence for
deployments with nonstandard routing.

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
explicitly disables Auth Proxy rather than trusting an identity header. The
`grafana.networkPolicy.trustedIngress` peers control Kubernetes network
reachability only; they are not identity-header trust anchors.

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
