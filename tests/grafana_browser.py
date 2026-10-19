"""Opt-in browser acceptance against real Grafana and Zitadel/CAS services.

Use a private provider-only Playwright storage state, never a Grafana session.
No request mocking, TLS bypass, screenshots or token-bearing traces are used.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def origin(url):
    value = urlsplit(url)
    if value.scheme != "https" or not value.hostname or value.username or value.password:
        raise AssertionError("acceptance endpoints must be credential-free HTTPS URLs")
    return f"https://{value.netloc.lower()}"


def provider_state(path):
    path = Path(path)
    if path.stat().st_mode & 0o077:
        raise AssertionError("provider state must be readable only by its owner")
    state = json.loads(path.read_text())
    if any(c["name"].startswith("grafana_session") for c in state.get("cookies", [])):
        raise AssertionError("a pre-existing Grafana session would bypass the OAuth test")
    return state


def check_authorization(url, cookies, root, issuer, client_id, role_project=None):
    query = parse_qs(urlsplit(url).query)
    assert origin(url) == issuer, "unexpected authorization provider"
    assert query.get("client_id") == [client_id], "unexpected public client"
    assert query.get("redirect_uri") == [root + "/grafana/login/generic_oauth"]
    assert query.get("response_type") == ["code"]
    assert query.get("code_challenge_method") == ["S256"]
    assert len(query.get("code_challenge", [""])[0]) >= 43
    assert query.get("state"), "missing OAuth state"
    if role_project is not None:
        assert len(query.get("scope", [])) == 1, "missing or ambiguous role scopes"
        scopes = set(query["scope"][0].split())
        assert {f"urn:zitadel:iam:org:project:id:{role_project}:aud",
                "urn:zitadel:iam:org:projects:roles"} <= scopes, "missing role scopes"
    state = [c for c in cookies if c["name"] == "oauth_state"]
    assert len(state) == 1, "root OAuth state cookie missing or ambiguous"
    cookie, = state
    assert cookie["domain"] == urlsplit(root).hostname, "state must be root-host scoped"
    assert cookie["secure"] and cookie["httpOnly"], "OAuth state cookie is not protected"
    assert cookie["sameSite"] in ("Lax", "None"), "callback cannot receive state cookie"


def check_navigation(paths, entry, root, issuer):
    root, issuer = origin(root), origin(issuer)
    assert paths and paths[0][0] == origin(entry), "entry URL was not exercised"
    auth = next((n for n, p in enumerate(paths)
                 if p == (issuer, "/oauth/v2/authorize")), None)
    assert auth is not None, "login bypassed the real OIDC provider"
    assert any(p == (root, "/grafana/login/generic_oauth") for p in paths[:auth]), \
        "OAuth must start on the root host, including child-host entry"
    assert any(p == (root, "/grafana/login/generic_oauth") for p in paths[auth + 1:]), \
        "the real OAuth callback was not completed"
    assert not any(p[1] == "/grafana/login/generic_oauth" and p[0] != root for p in paths)


def verify_provider_logout(page, context, root, issuer, paths, authorization):
    paths.clear()
    page.goto(root + "/grafana/logout", wait_until="domcontentloaded")
    assert (issuer, "/oidc/v1/end_session") in paths, \
        "logout did not invoke the IdP end-session endpoint"
    assert context.request.get(root + "/grafana/api/user", max_redirects=0).status == 401, \
        "Grafana session survived logout"

    # Keep the actual browser cookies. Clearing them, reseeding the fixture or
    # forcing prompt=login would hide a provider session that survived logout.
    paths.clear()
    authorization.clear()
    response = page.goto(root + "/grafana/login/generic_oauth",
                         wait_until="domcontentloaded")
    assert response is not None and response.status < 400, "post-logout login failed"
    assert authorization and (issuer, "/oauth/v2/authorize") in paths, \
        "post-logout login did not reach the provider"
    # Recognize credential entry, not merely any page on the provider origin.
    # A provider error or silent Grafana login must fail within this deadline.
    login = page.locator(
        'form input[name="loginName"]:visible, form input[type="password"]:visible'
    ).first
    login.wait_for(state="visible", timeout=60000)
    assert origin(page.url) == issuer and urlsplit(page.url).path.startswith("/ui/login/"), \
        "post-logout login did not require provider authentication"
    assert page.locator(".lgn-error-message:visible").count() == 0, \
        "provider returned a login error instead of requiring authentication"
    assert context.request.get(root + "/grafana/api/user", max_redirects=0).status == 401, \
        "provider session silently authenticated Grafana after logout"


def check_grafana_role(user, organizations, expected):
    assert expected in ("Viewer", "Admin")
    assert user.get("isGrafanaAdmin") is False, "OAuth granted server administrator access"
    assert organizations and all(org["role"] == expected for org in organizations), \
        "unexpected Grafana organization role"


def run_oidc(browser, target):
    root, issuer = target["root_url"].rstrip("/"), origin(target["issuer_url"])
    assert urlsplit(root).path == "" and not urlsplit(root).query and not urlsplit(root).fragment
    origin(root)
    state = provider_state(target["storage_state"])
    entries = target["entry_urls"]
    assert root + "/grafana/" in entries
    if target["dns"]:
        assert any(origin(entry) != origin(root) for entry in entries), "DNS case needs child entry"
    for entry in entries:
        origin(entry)
        with browser.new_context(storage_state=state) as context:
            context.set_default_timeout(60000)
            anonymous = context.request.get(root + "/grafana/api/user", max_redirects=0)
            assert anonymous.status == 401, "Grafana must not already be authenticated"
            info = context.request.get(root + "/api/v1/onboarding/tenant-info")
            assert info.status == 200
            attributes = info.json()["data"]["attributes"]
            assert attributes["tenantId"].lower() == "aaa_root" and attributes["zitadelAuth"] is True
            clients = [c for c in attributes["zitadelConfig"]["clients"] if c["name"] == "pca-grafana-pkce"]
            assert len(clients) == 1 and clients[0]["appId"] and clients[0]["clientId"]
            client_id = clients[0]["clientId"]
            role_project = None
            if "expected_org_role" in target:
                projects = [p for p in attributes["zitadelConfig"]["projects"]
                            if p["name"] == "Analytics"]
                assert len(projects) == 1 and projects[0]["projectId"]
                role_project = projects[0]["projectId"]
            if "client_id" in target:
                assert client_id == target["client_id"]
            page = context.new_page()
            paths, authorization = [], []

            def inspect(request):
                if not request.is_navigation_request() or request.frame != page.main_frame:
                    return
                parsed = urlsplit(request.url)
                paths.append((origin(request.url), parsed.path))
                if parsed.path == "/oauth/v2/authorize":
                    # Discard state/code values immediately; never log the raw URL.
                    check_authorization(request.url, context.cookies(root + "/grafana/"),
                                        root, issuer, client_id, role_project)
                    authorization.append(True)

            page.on("request", inspect)
            page.goto(entry, wait_until="domcontentloaded")
            # Do not accept a login form or just a successful redirect as proof of login.
            page.wait_for_function("window.grafanaBootData?.user?.isSignedIn === true")
            assert origin(page.url) == origin(root)
            assert authorization
            check_navigation(paths, entry, root, issuer)
            user = context.request.get(root + "/grafana/api/user")
            assert user.status == 200
            assert user.json()["login"] == target["grafana_login"], "wrong Grafana identity"
            organizations = context.request.get(root + "/grafana/api/user/orgs")
            assert organizations.status == 200
            check_grafana_role(user.json(), organizations.json(),
                               target.get("expected_org_role", "Viewer"))
            if origin(entry) != origin(root):
                wrong_callback = context.request.get(
                    origin(entry) + "/grafana/login/generic_oauth?code=invalid&state=invalid",
                    max_redirects=0,
                )
                assert wrong_callback.status == 404, "child callback must not be redirected"
            if entry == entries[-1]:
                # Revoking the shared provider session earlier would invalidate
                # the provider-only fixture for the next independent entry test.
                verify_provider_logout(page, context, root, issuer, paths, authorization)
        print("PASS: root/child OIDC browser entry and provider logout")


def run_swarm(browser, target):
    root, cas = origin(target["root_url"]), origin(target["issuer_url"])
    for authenticated in (False, True):
        state = provider_state(target["storage_state"]) if authenticated else None
        with browser.new_context(storage_state=state) as context:
            context.set_default_timeout(60000)
            page = context.new_page()
            paths = []
            page.on("request", lambda r: paths.append(urlsplit(r.url).path))
            page.goto(root + "/grafana/", wait_until="domcontentloaded")
            if authenticated:
                assert origin(page.url) == root
                response = context.request.get(root + "/grafana/api/user", max_redirects=0)
                assert response.status == 200, "CAS-authenticated Grafana access failed"
            else:
                assert origin(page.url) == cas, "anonymous entry bypassed the CAS gate"
            assert "/oauth/v2/authorize" not in paths
            assert not any("onboarding/tenant-info" in p for p in paths)
    print("PASS: live Swarm CAS gate remains unchanged")


def role_targets(target, selected=None):
    cases = target.get("role_mapping_cases")
    if cases is None:
        assert selected is None, "role cases are not configured"
        return [target]
    names = {"administrator", "viewer", "other-organization", "other-project",
             "revoked-administrator"}
    assert set(cases) == names, "configure the complete role-mapping matrix"
    assert cases["administrator"]["grafana_login"] == cases["revoked-administrator"]["grafana_login"], \
        "demotion must exercise the previously promoted administrator"
    assert len({cases[name]["grafana_login"] for name in names - {"revoked-administrator"}}) == 4
    for case in cases.values():
        assert case["grafana_login"] and case["storage_state"]
    assert selected is None or selected in names
    chosen = [selected] if selected else ["administrator", "viewer", "other-organization", "other-project"]
    return [dict(target, **{key: cases[name][key] for key in ("grafana_login", "storage_state")},
                 expected_org_role="Admin" if name == "administrator" else "Viewer")
            for name in chosen]


def run_target(target, role_case=None):
    # Missing dependencies or expired provider sessions fail acceptance, not skip it.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        with playwright.chromium.launch() as browser:
            if target.get("mode", "oidc") == "swarm":
                assert role_case is None and "role_mapping_cases" not in target
                run_swarm(browser, target)
            else:
                for identity in role_targets(target, role_case):
                    run_oidc(browser, identity)


def main():
    if not __debug__:
        raise SystemExit("do not disable acceptance assertions with python -O")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--role-case")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text())
    assert config.get("disposable") is True, "use a disposable acceptance environment"
    targets = [t for t in config["targets"] if t["name"] == args.target]
    assert len(targets) == 1, "select one explicit target"
    try:
        run_target(targets[0]["browser"], args.role_case)
    except Exception:
        # Playwright errors can contain callback URLs or cookie values.
        raise SystemExit("FAIL: browser acceptance; inspect the disposable deployment") from None


if __name__ == "__main__":
    main()
