import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def walk(panels):
    for panel in panels:
        yield panel
        yield from walk(panel.get("panels", []))


class CustomerQueryModesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboards = {
            (platform, path.name): json.loads(path.read_text())
            for platform in ("k8s", "swarm")
            for path in (ROOT / f"dashboards/Customer ({platform})").glob("*.json")
        }

    def test_snapshot_panels_use_only_instant_queries(self):
        snapshot_ids = {
            "pca-resource-health.json": {
                3, 4, 5, 6, 7, 16, 17, 18, 23, 24,
                25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35,
            },
            "pca-sensor-connectivity.json": {3, 4, 5, 6, 8},
            "pca-service-health.json": {3, 4, 5, 6, 7, 8},
        }
        for (platform, name), dashboard in self.dashboards.items():
            if name not in snapshot_ids:
                continue
            expected = snapshot_ids[name]
            if platform == "swarm" and name == "pca-resource-health.json":
                expected = expected - {23, 24, 32, 33, 34, 35}
            panels = {
                p["id"]: p for p in walk(dashboard["panels"])
                if p["id"] in expected
            }
            self.assertEqual(set(panels), expected)
            for panel in panels.values():
                self.assertTrue(panel["targets"])
                for target in panel["targets"]:
                    with self.subTest(platform=platform, dashboard=name,
                                      panel=panel["id"], query=target["refId"]):
                        self.assertIs(target["instant"], True)
                        self.assertIs(target["range"], False)

    def test_history_panels_keep_range_queries(self):
        for (platform, name), dashboard in self.dashboards.items():
            for panel in walk(dashboard["panels"]):
                history = panel["type"] in {"timeseries", "state-timeline"}
                sparkline = panel.get("options", {}).get("graphMode") == "area"
                # The edge-agent count already used instant mode before this fix.
                if name == "pca-ingestion-pipeline.json" and panel["id"] == 3:
                    continue
                if not (history or sparkline):
                    continue
                for target in panel["targets"]:
                    with self.subTest(platform=platform, dashboard=name,
                                      panel=panel["id"], query=target["refId"]):
                        self.assertIs(target["instant"], False)
                        self.assertIs(target["range"], True)


if __name__ == "__main__":
    unittest.main()
