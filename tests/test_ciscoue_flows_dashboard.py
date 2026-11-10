import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboards" / "ciscoue-pv-storage-flows.json"


class CiscoUEFlowsDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = json.loads(DASHBOARD.read_text())
        cls.panels = cls.dashboard["panels"]
        cls.targets = [
            target
            for panel in cls.panels
            for target in panel.get("targets", [])
        ]

    def test_modern_dashboard_identity_and_shape(self):
        self.assertIsNone(self.dashboard["id"])
        self.assertEqual(self.dashboard["uid"], "ciscoue-pv-storage-flows")
        self.assertEqual(self.dashboard["title"], "CiscoUE PV Storage Flows")
        self.assertEqual(self.dashboard["schemaVersion"], 41)
        self.assertEqual(self.dashboard["tags"], ["ciscoue", "pca-ue", "pcaueni"])
        self.assertEqual(len(self.panels), 7)
        self.assertEqual(len(self.targets), 10)
        self.assertEqual(
            {panel["title"] for panel in self.panels},
            {
                "Rows per tenant · per minute",
                "Rows per minute",
                "Rows per PCA UE inserter instance · per minute",
                "Inserted datasets per minute",
                "Inserted datasets per PCA UE inserter instance · per minute",
                "Invalid datasets per minute",
                "Invalid datasets per PCA UE inserter instance · per minute",
            },
        )
        self.assertTrue(all(panel["type"] == "timeseries" for panel in self.panels))
        self.assertTrue(
            all(panel["pluginVersion"] == "12.1.0" for panel in self.panels)
        )
        self.assertTrue(
            all(
                panel["datasource"]
                == {"type": "prometheus", "uid": "prometheus"}
                for panel in self.panels
            )
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
        self.assertTrue(all("increase(" in expr for expr in expressions))
        self.assertTrue(all("[1m]" in expr for expr in expressions))
        self.assertFalse(any("rate(" in expr or "[10m]" in expr for expr in expressions))
        self.assertTrue(all(target["interval"] == "1m" for target in self.targets))
        variable = self.dashboard["templating"]["list"][0]
        self.assertEqual(variable["name"], "tenant_id")
        self.assertEqual(
            variable["query"],
            "label_values(pcaueni_inserted_rows_total, tenant_id)",
        )

    def test_invalid_dataset_panels_emphasize_minute_peaks(self):
        panels = {panel["id"]: panel for panel in self.panels}
        for panel_id in (10, 12):
            custom = panels[panel_id]["fieldConfig"]["defaults"]["custom"]
            self.assertEqual(custom["drawStyle"], "bars")
            self.assertEqual(custom["fillOpacity"], 35)

    def test_panels_preserve_compact_non_overlapping_layout(self):
        rectangles = []
        for panel in self.panels:
            position = panel["gridPos"]
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
