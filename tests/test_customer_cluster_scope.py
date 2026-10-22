import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE_NOTE = (
    "Shows the Kubernetes cluster monitored by this deployment's "
    "Prometheus datasource."
)


class CustomerClusterScopeTest(unittest.TestCase):
    def test_customer_kubernetes_dashboards_have_no_cluster_selection(self):
        paths = sorted((ROOT / "dashboards/Customer (k8s)").glob("*.json"))
        self.assertTrue(paths)
        for path in paths:
            with self.subTest(dashboard=path.name):
                dashboard = json.loads(path.read_text())
                variables = dashboard["templating"]["list"]
                self.assertNotIn("cluster", [v["name"] for v in variables])
                content = json.dumps(dashboard)
                self.assertNotRegex(content, r"\$(?:cluster\b|\{cluster\})|\[\[cluster\]\]")
                self.assertNotRegex(content, r'\bcluster\s*(?:=|!)')

    def test_infrastructure_dashboards_explain_datasource_scope(self):
        expected_variables = {
            "pca-resource-health.json": {"node", "namespace", "pod"},
            "pca-service-health.json": {"namespace"},
        }
        for name, expected in expected_variables.items():
            with self.subTest(dashboard=name):
                path = ROOT / "dashboards/Customer (k8s)" / name
                dashboard = json.loads(path.read_text())
                self.assertEqual(
                    {v["name"] for v in dashboard["templating"]["list"]},
                    expected,
                )
                help_text = dashboard["panels"][0]["options"]["content"]
                self.assertIn(SCOPE_NOTE, help_text)


if __name__ == "__main__":
    unittest.main()
