import importlib.util
import sys
import types
import unittest
from pathlib import Path


sys.modules.setdefault(
    "yaml",
    types.SimpleNamespace(safe_load=lambda *args, **kwargs: {}),
)

SCRIPT_PATH = Path(__file__).with_name("seed-alerts.py")
SPEC = importlib.util.spec_from_file_location("seed_alerts", SCRIPT_PATH)
seed_alerts = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seed_alerts)


class EnsureFolderTests(unittest.TestCase):
    def setUp(self):
        self.original_request = seed_alerts.grafana_request
        self.original_log = seed_alerts._log
        self.original_err = seed_alerts._err
        seed_alerts._log = lambda msg: None
        seed_alerts._err = lambda msg: None

    def tearDown(self):
        seed_alerts.grafana_request = self.original_request
        seed_alerts._log = self.original_log
        seed_alerts._err = self.original_err

    def test_uses_existing_folder_with_same_title_and_different_uid(self):
        calls = []

        def fake_request(path, method="GET", data=None, headers=None):
            calls.append((method, path, data))
            if path == "/api/folders/general-alerting":
                return {"status": 404, "error": "not found"}
            if path == "/api/folders?limit=1000&page=1":
                return [{"uid": "existing-folder", "title": "General Alerting"}]
            self.fail(f"Unexpected request: {method} {path}")

        seed_alerts.grafana_request = fake_request

        self.assertEqual(
            seed_alerts.ensure_folder("General Alerting"),
            "existing-folder",
        )
        self.assertNotIn(
            ("POST", "/api/folders"),
            [(method, path) for method, path, _data in calls],
        )

    def test_title_lookup_wins_when_requested_uid_has_different_title(self):
        responses = [
            (
                ("GET", "/api/folders/general-alerting"),
                {"uid": "general-alerting", "title": "Different Folder"},
            ),
            (
                ("GET", "/api/folders?limit=1000&page=1"),
                [{"uid": "actual-folder", "title": "General Alerting"}],
            ),
        ]

        def fake_request(path, method="GET", data=None, headers=None):
            expected, response = responses.pop(0)
            self.assertEqual(expected, (method, path))
            return response

        seed_alerts.grafana_request = fake_request

        self.assertEqual(
            seed_alerts.ensure_folder("General Alerting"),
            "actual-folder",
        )
        self.assertEqual(responses, [])

    def test_uses_existing_folder_when_create_collides(self):
        responses = [
            (
                ("GET", "/api/folders/ingestion"),
                {"status": 404, "error": "not found"},
            ),
            (("GET", "/api/folders?limit=1000&page=1"), []),
            (
                ("POST", "/api/folders"),
                {"status": 412, "error": "folder already exists"},
            ),
            (
                ("GET", "/api/folders?limit=1000&page=1"),
                [{"uid": "existing-ingestion", "title": "Ingestion"}],
            ),
        ]

        def fake_request(path, method="GET", data=None, headers=None):
            expected, response = responses.pop(0)
            self.assertEqual(expected, (method, path))
            return response

        seed_alerts.grafana_request = fake_request

        self.assertEqual(
            seed_alerts.ensure_folder("Ingestion"),
            "existing-ingestion",
        )
        self.assertEqual(responses, [])

    def test_fails_when_folder_cannot_be_created_or_resolved(self):
        responses = [
            (
                ("GET", "/api/folders/ingestion"),
                {"status": 404, "error": "not found"},
            ),
            (("GET", "/api/folders?limit=1000&page=1"), []),
            (
                ("POST", "/api/folders"),
                {"status": 500, "error": "database error"},
            ),
            (("GET", "/api/folders?limit=1000&page=1"), []),
        ]

        def fake_request(path, method="GET", data=None, headers=None):
            expected, response = responses.pop(0)
            self.assertEqual(expected, (method, path))
            return response

        seed_alerts.grafana_request = fake_request

        with self.assertRaisesRegex(
            RuntimeError,
            "Could not find or create folder",
        ):
            seed_alerts.ensure_folder("Ingestion")
        self.assertEqual(responses, [])


class BaseUrlTests(unittest.TestCase):
    """Tests for get_runbook_base_url()."""

    def _set_env(self, value):
        import os
        self._old = os.environ.pop("GF_SERVER_ROOT_URL", None)
        if value is not None:
            os.environ["GF_SERVER_ROOT_URL"] = value

    def _restore_env(self):
        import os
        os.environ.pop("GF_SERVER_ROOT_URL", None)
        if self._old is not None:
            os.environ["GF_SERVER_ROOT_URL"] = self._old

    def tearDown(self):
        self._restore_env()

    def test_no_env_falls_back_to_grafana_url(self):
        self._set_env(None)
        self.assertEqual(
            seed_alerts.get_runbook_base_url(),
            seed_alerts.GRAFANA_URL + "/",
        )

    def test_empty_env_falls_back_to_grafana_url(self):
        self._set_env("")
        self.assertEqual(
            seed_alerts.get_runbook_base_url(),
            seed_alerts.GRAFANA_URL + "/",
        )

    def test_plain_localhost(self):
        self._set_env("http://localhost:3000")
        self.assertEqual(seed_alerts.get_runbook_base_url(), "http://localhost:3000/")

    def test_subpath_with_trailing_slash(self):
        self._set_env("https://host/grafana/")
        self.assertEqual(seed_alerts.get_runbook_base_url(), "https://host/grafana/")

    def test_subpath_without_trailing_slash(self):
        self._set_env("https://host/grafana")
        self.assertEqual(seed_alerts.get_runbook_base_url(), "https://host/grafana/")

    def test_deep_subpath(self):
        self._set_env("https://host/org/grafana/")
        self.assertEqual(seed_alerts.get_runbook_base_url(), "https://host/org/grafana/")


class ResolveRunbookUrlsTests(unittest.TestCase):
    """Tests for resolve_runbook_urls()."""

    def test_rewrites_to_full_url(self):
        rules = [{"annotations": {"runbook_url": "/public/help/foo.html"}}]
        seed_alerts.resolve_runbook_urls(rules, "https://host/grafana/")
        self.assertEqual(
            rules[0]["annotations"]["runbook_url"],
            "https://host/grafana/public/help/foo.html",
        )

    def test_rewrites_with_root_base_url(self):
        rules = [{"annotations": {"runbook_url": "/public/help/foo.html"}}]
        seed_alerts.resolve_runbook_urls(rules, "http://localhost:3000/")
        self.assertEqual(
            rules[0]["annotations"]["runbook_url"],
            "http://localhost:3000/public/help/foo.html",
        )

    def test_skips_rules_without_runbook_url(self):
        rules = [{"annotations": {"summary": "test"}}]
        seed_alerts.resolve_runbook_urls(rules, "https://host/grafana/")
        self.assertNotIn("runbook_url", rules[0]["annotations"])

    def test_skips_rules_without_annotations(self):
        rules = [{"labels": {"foo": "bar"}}]
        seed_alerts.resolve_runbook_urls(rules, "https://host/grafana/")

    def test_preserves_absolute_urls(self):
        rules = [{"annotations": {"runbook_url": "https://example.com/docs"}}]
        seed_alerts.resolve_runbook_urls(rules, "https://host/grafana/")
        self.assertEqual(
            rules[0]["annotations"]["runbook_url"],
            "https://example.com/docs",
        )


if __name__ == "__main__":
    unittest.main()
