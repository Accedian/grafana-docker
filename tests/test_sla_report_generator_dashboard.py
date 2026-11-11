import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_PATH = ROOT / "dashboards" / "SLA Report Generator.json"


def walk(panels):
    for panel in panels:
        yield panel
        yield from walk(panel.get("panels", []))


class SLAReportGeneratorDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = json.loads(DASHBOARD_PATH.read_text())
        cls.panels = list(walk(cls.dashboard["panels"]))

    def test_dashboard_identity_is_stable_and_production_safe(self):
        self.assertEqual(self.dashboard["uid"], "sla-report-generator")
        self.assertEqual(self.dashboard["title"], "SLA Report Generator")
        self.assertNotIn("local-demo", self.dashboard.get("tags", []))

    def test_query_panels_use_the_provisioned_datasource_uid(self):
        query_panels = [panel for panel in self.panels if panel.get("targets")]
        self.assertTrue(query_panels)
        for panel in query_panels:
            with self.subTest(panel=panel["title"]):
                self.assertEqual(panel["datasource"]["uid"], "prometheus")

    def test_weld_upload_panels_count_successful_artifacts(self):
        expected_artifacts = {
            "PDF reports uploaded": "pdf",
            "Rebate reports uploaded": "rebate_json",
        }
        panels_by_title = {panel["title"]: panel for panel in self.panels}

        for title, artifact in expected_artifacts.items():
            with self.subTest(panel=title):
                expression = panels_by_title[title]["targets"][0]["expr"]
                self.assertIn("report_upload_total", expression)
                self.assertIn('destination="weld"', expression)
                self.assertIn(f'artifact="{artifact}"', expression)
                self.assertIn('outcome="success"', expression)

    def test_dashboard_uid_does_not_collide(self):
        matching_paths = []
        for path in (ROOT / "dashboards").rglob("*.json"):
            dashboard = json.loads(path.read_text())
            if dashboard.get("uid") == self.dashboard["uid"]:
                matching_paths.append(path)
        self.assertEqual(matching_paths, [DASHBOARD_PATH])


if __name__ == "__main__":
    unittest.main()
