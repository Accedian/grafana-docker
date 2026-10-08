"""Local negative tests for the assertions used by live browser acceptance."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode
from unittest.mock import Mock

from grafana_browser import (check_authorization, check_navigation, origin,
                             provider_state, verify_provider_logout)

ROOT, ISSUER = "https://root.example.test", "https://auth.example.test"


class BrowserContractTests(unittest.TestCase):
    def logout_fixture(self, final_url=ISSUER + "/ui/login/login"):
        page, context = Mock(), Mock()
        paths, authorization = [], []
        page.url = final_url
        page.locator.return_value.count.return_value = 0
        context.request.get.side_effect = [Mock(status=401), Mock(status=401)]

        def navigate(url, **kwargs):
            if url == ROOT + "/grafana/logout":
                paths.append((ISSUER, "/oidc/v1/end_session"))
            else:
                paths.append((ISSUER, "/oauth/v2/authorize"))
                authorization.append(True)
            return Mock(status=200)

        page.goto.side_effect = navigate
        return page, context, paths, authorization

    def test_logout_requires_provider_authentication_in_the_same_context(self):
        page, context, paths, authorization = self.logout_fixture()
        verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)
        self.assertEqual([call.args[0] for call in page.goto.call_args_list],
                         [ROOT + "/grafana/logout", ROOT + "/grafana/login/generic_oauth"])
        self.assertEqual(context.request.get.call_count, 2)
        for call in context.request.get.call_args_list:
            self.assertEqual(call.args, (ROOT + "/grafana/api/user",))
            self.assertEqual(call.kwargs, {"max_redirects": 0})
        page.locator.return_value.first.wait_for.assert_called_once_with(
            state="visible", timeout=60000)
        self.assertEqual(page.locator.call_args_list[0].args, (
            'form input[name="loginName"]:visible, form input[type="password"]:visible',))
        context.clear_cookies.assert_not_called()
        context.add_cookies.assert_not_called()

    def test_logout_rejects_error_pages_and_silent_reauthentication(self):
        for final_url in (ISSUER + "/ui/login/error", ROOT + "/grafana/"):
            with self.subTest(final_url=final_url):
                page, context, paths, authorization = self.logout_fixture(final_url)
                page.locator.return_value.first.wait_for.side_effect = TimeoutError()
                with self.assertRaises(TimeoutError):
                    verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)
        for final_url in (ROOT + "/grafana/", ISSUER + "/error",
                          "https://other.example.test/ui/login/login"):
            with self.subTest(final_url=final_url):
                page, context, paths, authorization = self.logout_fixture(final_url)
                with self.assertRaises(AssertionError):
                    verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)
        page, context, paths, authorization = self.logout_fixture()
        page.locator.return_value.count.return_value = 1
        with self.assertRaisesRegex(AssertionError, "provider returned a login error"):
            verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)

    def test_logout_rejects_unsuccessful_post_logout_navigation(self):
        for response in (None, Mock(status=400), Mock(status=500)):
            with self.subTest(response=response):
                page, context, paths, authorization = self.logout_fixture()
                navigate = page.goto.side_effect

                def failed_navigation(url, **kwargs):
                    result = navigate(url, **kwargs)
                    return result if url.endswith("/logout") else response

                page.goto.side_effect = failed_navigation
                with self.assertRaisesRegex(AssertionError, "post-logout login failed"):
                    verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)

    def test_logout_rejects_surviving_grafana_sessions(self):
        for statuses in ((200,), (401, 200)):
            with self.subTest(statuses=statuses):
                page, context, paths, authorization = self.logout_fixture()
                context.request.get.side_effect = [Mock(status=s) for s in statuses]
                with self.assertRaises(AssertionError):
                    verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)

    def test_logout_requires_fresh_end_session_and_authorization_requests(self):
        for missing in ("logout", "authorization"):
            with self.subTest(missing=missing):
                page, context, paths, authorization = self.logout_fixture()
                # Earlier login/logout observations must not satisfy this check.
                paths.extend([(ISSUER, "/oidc/v1/end_session"),
                              (ISSUER, "/oauth/v2/authorize")])
                authorization.append(True)
                navigate = page.goto.side_effect

                def omit_request(url, **kwargs):
                    if (url.endswith("/logout")) == (missing == "logout"):
                        return Mock(status=200)
                    return navigate(url, **kwargs)

                page.goto.side_effect = omit_request
                with self.assertRaises(AssertionError):
                    verify_provider_logout(page, context, ROOT, ISSUER, paths, authorization)

    def test_root_and_child_must_start_oauth_on_root(self):
        for entry in (ROOT, "https://child.example.test"):
            paths = [(entry, "/grafana/"), (ROOT, "/grafana/login/generic_oauth"),
                     (ISSUER, "/oauth/v2/authorize"), (ROOT, "/grafana/login/generic_oauth")]
            check_navigation(paths, entry + "/grafana/", ROOT, ISSUER)
            with self.assertRaises(AssertionError):
                check_navigation(paths[:2], entry, ROOT, ISSUER)
        with self.assertRaises(AssertionError):
            check_navigation([(ROOT, "/grafana/"), (ISSUER, "/oauth/v2/authorize"),
                              (ROOT, "/grafana/login/generic_oauth")], ROOT, ROOT, ISSUER)

    def test_authorization_requires_exact_root_callback_and_secure_cookie(self):
        query = {"client_id": "public", "redirect_uri": ROOT + "/grafana/login/generic_oauth",
                 "response_type": "code", "code_challenge_method": "S256",
                 "code_challenge": "x" * 43, "state": "ephemeral-test-state"}
        cookie = {"name": "oauth_state", "domain": "root.example.test",
                  "secure": True, "httpOnly": True, "sameSite": "Lax"}
        check_authorization(ISSUER + "/oauth/v2/authorize?" + urlencode(query),
                            [cookie], ROOT, ISSUER, "public")
        for key, value in (("domain", ".example.test"), ("secure", False),
                           ("httpOnly", False), ("sameSite", "Strict")):
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check_authorization(ISSUER + "/oauth/v2/authorize?" + urlencode(query),
                                    [dict(cookie, **{key: value})], ROOT, ISSUER, "public")
        for key, value in (("client_id", "other"), ("code_challenge_method", "plain"),
                           ("redirect_uri", "https://child.example.test/grafana/login/generic_oauth")):
            with self.subTest(key=key), self.assertRaises(AssertionError):
                check_authorization(ISSUER + "/oauth/v2/authorize?" + urlencode(dict(query, **{key: value})),
                                    [cookie], ROOT, ISSUER, "public")

    def test_state_rejects_existing_grafana_session_and_insecure_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text('{"cookies": []}')
            path.chmod(0o600)
            self.assertEqual(provider_state(path), {"cookies": []})
            path.chmod(0o644)
            with self.assertRaises(AssertionError):
                provider_state(path)
            path.chmod(0o600)
            path.write_text('{"cookies": [{"name": "grafana_session"}]}')
            with self.assertRaises(AssertionError):
                provider_state(path)

    def test_target_rejects_plaintext_and_url_credentials(self):
        for url in ("http://root.example", "https://user:secret@root.example"):
            with self.assertRaises(AssertionError):
                origin(url)
