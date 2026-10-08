"""Local negative tests for the assertions used by live browser acceptance."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlencode

from grafana_browser import check_authorization, check_navigation, origin, provider_state

ROOT, ISSUER = "https://root.example.test", "https://auth.example.test"


class BrowserContractTests(unittest.TestCase):
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
