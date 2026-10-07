# Grafana renderer migration execution plan

## Purpose and scope

Preserve PNG rendering while retiring the unmaintained Image Renderer plugin
and upgrading system OpenSSL in the PCA Grafana image. Work is in this
repository and PR #274. Helm integration is the repository's deployment path;
Swarm integration in aod-deployer is pending confirmation of target scope.
Do not deploy, publish a release image, or alter customer data volumes.

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
   and verify the final head in CI. No release publication or deployment.

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

Next: verify CI on the final Grafana source head.
Both PRs remain draft until the release prerequisites are resolved. The
earlier successful CI only validated the system package update.

## Completion criteria

The shipped Grafana image excludes the retired plugin; the configured
supported renderer produces a valid PNG; wrong/missing tokens are denied;
upgrades ignore stale persisted plugins; chart/image checks gate release;
the PR describes feature preservation and real deployment prerequisites.
Any unpublished mirror or unvalidated deployment path remains explicit and
prevents a release-ready claim.
