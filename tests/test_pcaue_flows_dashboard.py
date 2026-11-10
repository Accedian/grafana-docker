import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboards" / "pca-ue-flows.json"


class PCAUEFlowsDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = json.loads(DASHBOARD.read_text())
        cls.panels = cls.dashboard["panels"]
        cls.targets = [
            target
            for panel in cls.panels
            for target in panel.get("targets", [])
        ]

    def test_identity_and_baseline_shape(self):
        self.assertIsNone(self.dashboard["id"])
        self.assertEqual(self.dashboard["uid"], "pca-ue-flows")
        self.assertEqual(self.dashboard["title"], "PCA UE Flows")
        self.assertEqual(self.dashboard["tags"], ["pca-ue", "pcaueni"])
        self.assertEqual(len(self.panels), 7)
        self.assertEqual(len(self.targets), 10)
        self.assertEqual(
            {panel["title"] for panel in self.panels},
            {
                "Rows per tenant",
                "Rows",
                "Rows per PCA UE inserter instance",
                "Inserted datasets",
                "Inserted datasets per PCA UE inserter instance",
                "Invalid datasets",
                "Invalid datasets per PCA UE inserter instance",
            },
        )

    def test_queries_use_only_master_pcaueni_counters(self):
        expressions = [target["expr"] for target in self.targets]
        self.assertFalse(any("pvstorage_" in expr for expr in expressions))
        self.assertEqual(
            {
                metric
                for expr in expressions
                for metric in re.findall(r"\bpcaueni_[a-z_]+_total\b", expr)
            },
            {
                "pcaueni_inserted_rows_total",
                "pcaueni_inserted_datasets_total",
                "pcaueni_invalid_datasets_total",
            },
        )
        self.assertTrue(all('tenant_id=~"$tenant_id"' in expr for expr in expressions))
        variable = self.dashboard["templating"]["list"][0]
        self.assertEqual(variable["name"], "tenant_id")
        self.assertEqual(
            variable["query"],
            "label_values(pcaueni_inserted_rows_total, tenant_id)",
        )

    def test_panels_have_no_layout_overlap(self):
        rectangles = []
        for panel in self.panels:
            position = panel["gridPos"]
            self.assertGreater(position["w"], 0)
            self.assertGreater(position["h"], 0)
            self.assertLessEqual(position["x"] + position["w"], 24)
            rectangle = (
                position["x"],
                position["y"],
                position["x"] + position["w"],
                position["y"] + position["h"],
                panel["title"],
            )
            for other in rectangles:
                overlaps = (
                    rectangle[0] < other[2]
                    and rectangle[2] > other[0]
                    and rectangle[1] < other[3]
                    and rectangle[3] > other[1]
                )
                self.assertFalse(overlaps, f"{rectangle[4]} overlaps {other[4]}")
            rectangles.append(rectangle)


if __name__ == "__main__":
    unittest.main()
