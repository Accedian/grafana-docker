# Live Grafana browser acceptance

These tests use real Chromium, Grafana and Zitadel/CAS, with no mocked network
responses. They are opt-in and do not run during image builds. The normal
`make test` checks their assertions with local negative tests.

Install the pinned test dependency in an isolated environment:

```sh
python3 -m venv .acceptance/venv
.acceptance/venv/bin/pip install -r tests/requirements-browser.txt
.acceptance/venv/bin/python -m playwright install chromium
```

Use HTTPS endpoints with certificates trusted by Chromium and the host. For a
lab CA, install its trust explicitly; do not bypass certificate verification.
No screenshots, HAR files or traces are produced: they could contain passwords,
authorization codes or session cookies.

Provide a private Playwright storage-state file containing a valid **provider
session only**. Log in to the disposable Zitadel/CAS instance to obtain it,
without first logging into Grafana, and set its permissions to `0600`. The
suite rejects existing Grafana session cookies and confirms anonymous Grafana
API access is denied before each OIDC login. Expired provider sessions fail
the test instead of skipping it. Never commit storage state or credentials.

Create a private JSON configuration using this shape:

```json
{
  "disposable": true,
  "targets": [{
    "name": "fresh-dns",
    "browser": {
      "mode": "oidc",
      "dns": true,
      "root_url": "https://root.example.test",
      "issuer_url": "https://auth.example.test",
      "entry_urls": [
        "https://root.example.test/grafana/",
        "https://child.example.test/grafana/"
      ],
      "storage_state": ".acceptance/provider-state.json",
      "grafana_login": "expected-zitadel-subject"
    }
  }]
}
```

`grafana_login` is the test identity's immutable Zitadel subject, not its
display name or Grafana's automatically allocated database ID. The client ID
is read from root tenant-info; an optional `client_id` expectation can pin a
known existing client. Use a newly auto-provisioned Viewer test identity.
DNS cases require both root and child URLs. IP-only cases use the external IP
on port 443 and the Zitadel issuer on port 3443; they need only the root entry.
All configuration/state paths are relative to the command's working directory.

```sh
PATH="$PWD/.acceptance/venv/bin:$PATH" make browser-test \
  ACCEPTANCE_CONFIG=.acceptance/targets.json ACCEPTANCE_TARGET=fresh-dns
```

Each entry uses a new browser context. Assertions check the root redirect
before OAuth, exact callback/client ID, S256 PKCE, a Secure/HttpOnly root-scoped
state cookie, completion of the real callback, the expected authenticated
Grafana identity and Viewer role. Child callbacks must return 404. Provider
logout is checked last, since it revokes the shared provider fixture session.
Refresh the provider state before rerunning the suite.

For live Swarm CAS non-regression, use `mode: "swarm"`, `dns: true`, a CAS
`issuer_url`, root Grafana URL and CAS-only storage state. The browser verifies
anonymous entry reaches CAS, authenticated access succeeds, and no browser
OIDC authorization or tenant-info request occurs. Deployer acceptance also
checks service environment and absence of the Grafana application in IAM;
browser observations alone cannot prove absence of server-side discovery.

The full disposable deployment matrix and failure/restart/rollback driver
live in aod-deployer's `docs/GRAFANA_OIDC_ACCEPTANCE.md`. A successful local
assertion test is not a successful live qualification.
