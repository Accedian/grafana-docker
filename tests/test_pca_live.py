import json
import math
import os
import re
import unittest
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE = os.environ.get("PCA_SWARM_MONITORING_LIVE") == "1"


def get_json(url):
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.load(response)


def panels(value):
    for panel in value.get("panels", []):
        yield panel
        yield from panels(panel)


def panel_query(filename, title):
    board = json.loads((ROOT / "dashboards" / filename).read_text())
    panel = next(panel for panel in panels(board) if panel.get("title") == title)
    query = panel["targets"][0]["expr"].replace("$__rate_interval", "8m")
    return re.sub(r"\$[A-Za-z_][A-Za-z_0-9]*", ".*", query)


def query_prometheus(query):
    result = get_json("http://127.0.0.1:19090/api/v1/query?" + urllib.parse.urlencode({"query": query}))
    if result["status"] != "success":
        raise AssertionError(result)
    return result["data"]["result"]


@unittest.skipUnless(LIVE, "requires the isolated Swarm monitoring VM and loopback SSH forwards")
class LiveDashboardTests(unittest.TestCase):
    def test_all_five_dashboards_are_provisioned_in_grafana_12_1(self):
        self.assertEqual(get_json("http://127.0.0.1:13000/api/health")["version"], "12.1.0")
        available = get_json("http://127.0.0.1:13000/api/search?tag=pca")
        expected = {json.loads(path.read_text())["uid"] for path in (ROOT / "dashboards").glob("pca-*.json")}
        self.assertEqual({item["uid"] for item in available}, expected)

    def test_service_dashboard_matches_real_swarm_states(self):
        for title, expected in (("Swarm collector healthy", 1), ("Swarm services fully running %", 50),
                                ("Swarm services degraded", 2), ("Swarm active services", 4)):
            with self.subTest(title=title):
                values = query_prometheus(panel_query("pca-service-health.json", title))
                self.assertEqual(len(values), 1)
                self.assertEqual(float(values[0]["value"][1]), expected)
        timeline = query_prometheus(panel_query("pca-service-health.json", "Swarm — Running / desired service replicas"))
        self.assertEqual({item["metric"]["service"]: float(item["value"][1]) for item in timeline},
                         {"aod_healthy": 1, "aod_partial": 0.5, "aod_down": 0, "aod_global": 1})

    def test_kubernetes_summary_is_unavailable_not_healthy_zero_on_swarm(self):
        for title in ("Workloads ready", "Workloads degraded", "CrashLoopBackOff", "Restarts (24h)", "Failed jobs"):
            with self.subTest(title=title):
                self.assertEqual(query_prometheus(panel_query("pca-service-health.json", title)), [])

    def test_real_node_exporter_metrics_support_the_shared_resource_summary(self):
        for title in ("Cluster CPU utilisation", "Cluster memory utilisation"):
            with self.subTest(title=title):
                values = query_prometheus(panel_query("pca-resource-health.json", title))
                self.assertEqual(len(values), 1)
                self.assertTrue(math.isfinite(float(values[0]["value"][1])))

    def test_cadvisor_exports_actual_swarm_task_metrics_not_only_a_healthy_http_target(self):
        for title in ("Observed Swarm tasks", "Swarm — Top tasks CPU cores", "Swarm — Top tasks memory working set",
                      "Swarm — CPU throttled periods %", "Swarm — CPU usage vs quota %", "Swarm — Memory usage vs limit %"):
            with self.subTest(title=title):
                values = query_prometheus(panel_query("pca-resource-health.json", title))
                self.assertTrue(values, "cAdvisor is reachable but Docker task metrics/labels are unavailable")


if __name__ == "__main__":
    unittest.main()
