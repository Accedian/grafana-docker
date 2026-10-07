# Grafana renderer migration execution plan

## Purpose and scope

Preserve PNG rendering while retiring the unmaintained Image Renderer plugin
and upgrading system OpenSSL in the PCA Grafana image. Work is in this
repository and PR #274. Helm integration is the repository's deployment path;
Swarm integration remains outside scope. On 2026-10-07 the user explicitly
authorized publishing a test component and single-stack Replicated release
on the private unstable-grzegorz channel, updating the disposable offline
test node replicated-grzegorz.pv.lab (172.25.77.12), and testing rendering
through APIs. Preserve rollback information and existing Grafana data.
Production deployments and protected release channels remain outside scope.

## Canonical inputs

- User decision on 2026-10-07: remove the unsupported plugin and preserve
  rendering through the supported service.
- [Grafana rendering documentation](https://grafana.com/docs/grafana/latest/setup-grafana/image-rendering/).
- [Current image build](../Dockerfile), [build and release entry points](../Makefile),
  [Grafana workload](../helm/templates/statefulset.yaml), and
  [chart values](../helm/values.yaml).
- PCA product security registry: authentication-authorization, credential
  containment, failure handling, security review and testing rules. Apply
  PCA-SEC-AUTH-001/003, PCA-SEC-CRED-001, PCA-SEC-FAIL-001,
  PCA-SEC-REVIEW-001/002/003 and PCA-SEC-TEST-003/004/005.
- AOD Deployer instructions require internal registry images and matching
  Replicated wrapper overrides for offline/customer registry use.

## Product and security contract

Interactive dashboards and panels remain available. PNG rendering uses the
Grafana HTTP renderer integration, with no local plugin. The sidecar shares
the Grafana Pod and listens on loopback only, without a public Service or
Ingress; callbacks use loopback as well. Both processes use the same token
from a Kubernetes Secret. No token is hardcoded, logged, or placed in a
ConfigMap. A missing/wrong token must reject render requests.

Pin the supported renderer release by version and digest, reference its
internal mirror for shipped charts, and verify a real PNG before claiming
feature preservation. The entrypoint selects HTTP rendering by default so
persistent copies of the old plugin cannot execute. Grafana 12.1.0's rendering
backend ignores the disabled-plugin list on its own. The list is retained as
an additional control; no customer volume files are deleted.

## Implementation sequence

1. Retain the system package floor and build/release checks from commit
   59f2bb4; remove the renderer from default and custom build plugin lists.
2. Add chart sidecar configuration, loopback callback and token references,
   with a stable generated Secret or an operator-supplied Secret.
3. Add real packaged-image/renderer integration tests and chart structure
   checks to the existing build prerequisite.
4. Wire the internal image mirror and update the Replicated wrapper in an
   isolated aod-deployer checkout. Follow that repository's default Helm
   scope; update Swarm only if the user explicitly includes the legacy path.
5. Update PR #274 around the final behavior; retain migration/rollback notes
   and verify the final head in CI.
6. Under the user's later test-deployment authorization, publish uniquely
   tagged preview artifacts, preserve the current private channel's other
   components, update the specified test node and exercise real rendering.

## Verification

Run `git diff --check`, shell syntax checks, Helm lint/template checks, the
packaged-plugin check, a real PNG request with Grafana 12.1.0 plus the pinned
renderer, and missing/wrong-token denial checks. Verify startup with a
persistent copy of the former renderer. Record exact image IDs, revisions,
commands and limitations in the PR. Verify edited canonical wording and the
absence of superseded statements. Check Replicated image mapping if touched.

## Recovery checkpoint

2026-10-07: System OpenSSL commit 59f2bb4 is pushed and its CircleCI build passed.
The migration is on codex/update-openssl in
[PR #274](https://github.com/Accedian/grafana-docker/pull/274). The local packaged image
is built (ID 5d4d5cf73f74) with Grafana 12.1.0, system OpenSSL 3.0.22, the four
remaining plugins and no renderer plugin. Packaged-file and shell checks pass.
The persistent-backend check passes with a benign fixture: default HTTP mode
does not invoke it, while a positive control restoring plugin mode does.
Helm lint and template checks pass for default, disabled and existing-Secret
configurations. The startup script's five negative checks reject missing,
empty, default, short and list-valued tokens before starting the service.
Renderer v5.12.5 has manifest digest
sha256:76542ccc4c045e5ff9f80f87b25de6fcc71b31222172de5031a8ceba33772ee1.
The public Google mirror supplied that exact manifest after Docker Hub
downloads stalled. Real integration checks now pass: Grafana produces an
800x400 PNG (7014 bytes), missing/wrong tokens receive HTTP 401, an
authenticated malformed request receives HTTP 400, and credential/query
markers are absent from both containers' logs. The service's upstream
1000x500 minimum was explicitly lowered to 100x100 to preserve smaller
exports. Access logging for render paths is silenced to avoid logging
Grafana's temporary renderKey. The renderer image contains OpenSSL 3.5.7
(Debian package 3.5.7-1~deb13u3); this does not establish absence of all CVEs.

Gcloud authentication now works. Copied the full upstream index to
gcr.io/npav-172917/3rdparty/docker.io/grafana/grafana-image-renderer:v5.12.5;
the copy preserved the original manifest digest and both amd64/arm64 images.
The integration checks also pass with the internal image reference and the
chart's explicit UID/GID 65532:65532.
The aod-deployer companion
[PR #7155](https://github.com/Accedian/aod-deployer/pull/7155) is based on master
47f60cf0d and adds the local/proxy registry mapping. Its snippet validation,
generated YAML checks and reported CI checks pass; full Replicated lint is
blocked by missing umbrella chart archives. The manifest remains on the
published Grafana chart 0.230.0 until a new verified component release is
available. No live Kubernetes, Replicated or Swarm deployment was validated.

Superseded by the deployment checkpoint below: final migration head f2fb105
now passes CI. Both PRs remain draft pending deployment evidence and a final
production component-version decision.

2026-10-07 deployment checkpoint: final source head f2fb105 passes both
CircleCI checks. The user supplied direct Vault CA SSH access to the offline
single-node test deployment and authorized its update. Initial SSH and
Replicated channel discovery are in progress. Next: record the current
deployment/version, build a uniquely tagged test component/chart, publish a
single-stack release only to unstable-grzegorz, transfer the airgap assets,
update the node and verify real rendering with negative authentication checks.

2026-10-07 publication checkpoint: Vault SSH works after VPN activation. The
node is a Ready Kubernetes 1.32.13/k0s Embedded Cluster 2.16.0 with KOTS
1.130.0-ec.1. The current application/channel release is 9521, channel
sequence 173, version 26.8.10-1682-g2f40f54f8-grafana-auth-values-e6ba0566b.
Its Helm revision 2 is already failed due to unrelated services; Grafana
0.230.0 itself is Ready with anonymous access disabled. This is an online
install restricted to internal PCA endpoints, not an airgap installation:
update.pca.cisco.com and proxy-registry.pca.cisco.com are reachable.

Published the previously validated image, unchanged, under unique tag
0.232.0-pr274-f2fb105 with digest
sha256:fcb8efe8ec2ac99a68e705090a88536cdf1c32e59afb960b75e1765abb3ee880.
The source head's Dockerfile differs from that built image only in comments;
the VERSION build argument is unused. Its chart has OCI digest
sha256:4d73ac3380707a377edd12b55be32a4667d651c434b017f786aaa68769a675ae.
Prepared a single-stack preview from downloaded release 9521, replacing only
the Grafana subchart, chart-version metadata and renderer wrapper mapping.
Verified 724 other umbrella/component files are byte-for-byte unchanged,
along with all other Replicated manifests and the preinstall package. Removed
the umbrella's obsolete dependency lock from this already bundled preview.
Replicated lint exits successfully with warnings inherited from the base; default Helm
rendering includes both internal images, the shared Secret and no renderer
port exposure. Rollback
inputs are release 9521 and the unchanged previous package; no reset or data
deletion is planned.

2026-10-07 live verification checkpoint (supersedes the earlier unpublished,
missing-package and untested-deployment statements): release 9584 is published
to pca-dev/unstable-grzegorz, channel sequence 174, version
26.8.10-1682-g2f40f54f8-renderer-pr274-f2fb105. KOTS downloaded it and deployed
the updated Grafana StatefulSet through the internal PCA proxy registry.
Both Grafana and renderer containers are Ready with zero restarts. Grafana's
PVC UID bc61af5e-a73b-4621-93ca-1e0e0bdc3ebe is unchanged and Bound. Anonymous
access remains disabled. OpenSSL in Grafana is 3.0.22; the bundled retired
plugin is absent.

Live API checks created a temporary dashboard using the existing Grafana
bootstrap credential Secret in memory and rendered a real panel PNG (800x400,
12119 bytes), then removed the dashboard. The first full-dashboard PNG had
valid dimensions but visual inspection revealed a Page not found screen;
that result does not validate dashboard rendering. Reproduced the same Page
not found screenshot in an isolated Docker run with the previous 0.230.0
image and HTTP renderer. The old plugin-mode comparison instead returned
500, so it does not establish a working full-dashboard baseline. The core's
render-only empty appSubUrl and dashboard API's configured /grafana metadata
URL are a plausible routing cause; no Grafana core patch was attempted.
The existing impex service account correctly rejected dashboard
creation with HTTP 403; its permissions were not widened. Missing/wrong
renderer tokens returned 401; a correctly authenticated malformed request
returned 400. A Grafana export without credentials returned 302 to login.
Both containers' recent logs contain neither the tested credentials nor
renderKey query strings. No renderer port or public Service was added.

The umbrella's Helm revision 3 and KOTS application status remain failed:
the pre-existing nginx-config ownership conflict with kubectl-patch repeats
the same failure from revision 2. Other application services also had failures
before this work. This does not prevent the updated Grafana/renderer from
running or the API checks above, but it prevents claiming a healthy whole-PCA
upgrade. No unrelated nginx ownership repair or application reset was made.
Alert-notification image delivery and a true airgap-bundle install were not
exercised; the target uses internal online update/proxy endpoints.

The repeatable verification script is retained on the test node. It reads
existing Kubernetes Secrets internally, prints only test outcomes and deletes
its temporary dashboard. It writes a credential-free panel PNG under /tmp;
inspect its visible test text. An optional --full-dashboard flag captures the
known dashboard failure without falsely declaring its PNG content valid.

```bash
sudo python3 /tmp/test-grafana-renderer-live.py
```

## Completion criteria

The shipped Grafana image excludes the retired plugin; the configured
supported renderer produces a valid PNG; wrong/missing tokens are denied;
upgrades ignore stale persisted plugins; chart/image checks gate release;
the PR describes feature preservation and real deployment prerequisites.
Any unpublished mirror or unvalidated deployment path remains explicit and
prevents a release-ready claim.
