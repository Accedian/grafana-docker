"""PCA UE monitoring contracts, including missing/stale telemetry behaviour."""

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("pcaueni", ROOT / "generate_pcaueni_dashboard.py")
PCAUE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PCAUE)
PROMTOOL = os.environ.get("PROMTOOL") or shutil.which("promtool")


class PCAUEDashboardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboard = json.loads((ROOT / "dashboards/Customer (swarm)" / PCAUE.DASHBOARD_NAME).read_text())
        cls.panels = {p["id"]: p for p in cls.dashboard["panels"]}

    def expression(self, panel_id, tenant=".*", schema=".*", consumer_group=".*"):
        expression = self.panels[panel_id]["targets"][0]["expr"]
        for variable, value in {"tenant": tenant, "schema": schema, "consumerGroup": consumer_group}.items():
            expression = expression.replace("${" + variable + ":regex}", value)
        return expression.replace("$__rate_interval", "2m")

    def test_image_provisioned_dashboard_and_drilldowns(self):
        self.assertEqual(self.dashboard, PCAUE.build())
        self.assertEqual(self.dashboard["uid"], "pca-ue-ingestion-swarm")
        self.assertEqual(len(self.panels), len(self.dashboard["panels"]))
        available_uids = {json.loads(p.read_text()).get("uid") for p in (ROOT / "dashboards").rglob("*.json")}
        for link in self.dashboard["links"]:
            with self.subTest(link=link["title"]):
                self.assertTrue(link["url"].startswith("/grafana/d/"))
                self.assertIn(link["url"].rsplit("/", 1)[-1], available_uids)
        self.assertIn("COPY dashboards /tmp/dashboards", (ROOT / "Dockerfile").read_text())

    def test_application_queries_never_invent_a_healthy_zero(self):
        for panel in self.panels.values():
            for target in panel.get("targets", []):
                expression = target["expr"]
                with self.subTest(panel=panel["id"]):
                    self.assertNotIn("vector(0)", expression)
                    self.assertNotRegex(expression, r"\bkube_|\bpvstorage_|\bspark_|\bdruid_")
                    self.assertEqual(target["datasource"], {"type": "prometheus", "uid": "prometheus"})
                    self.assertEqual(target["interval"], "30s")
                    if panel["id"] >= 7:
                        self.assertIn("up{", expression)
                        self.assertIn("== 1", expression)
        for panel_id in (9, 10):
            self.assertEqual(self.panels[panel_id]["fieldConfig"]["defaults"]["noValue"], "No counter yet")

    def test_filter_and_metric_contract(self):
        variables = {v["name"]: v for v in self.dashboard["templating"]["list"]}
        self.assertEqual(set(variables), {"tenant", "schema", "consumerGroup"})
        for panel_id in (7, 8, 9, 10):
            expression = self.expression(panel_id, tenant="tenant-a", schema="edr_flow_network_intelligence")
            self.assertIn('tenant_id=~"tenant-a"', expression)
            self.assertIn('schema=~"edr_flow_network_intelligence"', expression)
            self.assertIn("sum by (tenant_id, schema)", expression)
        for panel_id in (11, 12, 13):
            self.assertIn('topic=~"pcaue[.](', self.expression(panel_id))
        for panel_id in (2, 3, 4, 5, 6, 14, 15, 16, 18):
            self.assertNotRegex(self.expression(panel_id), r"tenant_id|tenant:regex|schema:regex")
        self.assertIn('database="pcaueni"', self.expression(17))
        self.assertIn('table=~"', self.expression(17))
        # Exporter 26.1.15 misreports these two gauges as bytes; never rely on
        # them for row/part counts in a dashboard supporting that image.
        serialized = json.dumps(self.dashboard)
        self.assertNotIn("ClickHousePVX_table_parts_rows", serialized)
        self.assertNotIn("ClickHousePVX_table_parts_count", serialized)

    @unittest.skipUnless(PROMTOOL, "promtool is required for query behaviour checks (make test in CI installs it)")
    def test_promql_behaviour_with_live_idle_down_and_unknown_offsets(self):
        """Run the real PromQL evaluator, not a hand-written expression mock."""
        labels = '{schema="edr_flow_network_intelligence",tenant_id="tenant-a"}'
        series = [
            {"series": 'up{job="pcaueni_inserter1a",instance="a:1664"}', "values": "1x20"},
            {"series": 'up{job="pcaueni_inserter1b",instance="b:1664"}', "values": "1x20"},
            {"series": 'pcaueni_inserted_rows_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a"}', "values": "0+30x20"},
            {"series": 'pcaueni_inserted_rows_total{job="pcaueni_inserter1b",instance="b:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a"}', "values": "0+60x20"},
        ]

        def check(panel_id, samples, **filters):
            return {"expr": self.expression(panel_id, **filters), "eval_time": "8m", "exp_samples": samples}

        def sample(value, sample_labels=labels):
            return {"labels": sample_labels, "value": value}

        healthy = {"name": "successful traffic and lazy error counters", "interval": "30s", "input_series": series,
                   "promql_expr_test": [check(2, [sample(1, "{}")]), check(7, [sample(3)]), check(9, []), check(10, [])]}
        down_series = [dict(s) for s in series]
        down_series[0]["values"] = "1x8 0x12"
        down = {"name": "old counters do not survive a failed scrape", "interval": "30s", "input_series": down_series,
                "promql_expr_test": [check(2, [sample(0, "{}")]), check(7, [sample(2)])]}
        missing = {"name": "missing jobs and counters are not fabricated zeros", "interval": "30s", "input_series": [],
                   "promql_expr_test": [check(i, []) for i in (2, 7, 9, 10, 11, 13, 17)]}
        idle_series = [dict(s) for s in series]
        idle_series[2]["values"] = "100x20"
        idle_series[3]["values"] = "200x20"
        idle = {"name": "initialized counters can truthfully show idle zero", "interval": "30s", "input_series": idle_series,
                "promql_expr_test": [check(7, [sample(0)]), check(9, [])]}
        filtered_series = series + [
            {"series": 'pcaueni_inserted_rows_total{job="pcaueni_inserter1a",instance="a:1664",schema="other_schema",tenant_id="tenant-b"}', "values": "0+300x20"},
            {"series": 'pcaueni_invalid_rows_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a",version="1"}', "values": "0+30x20"},
            {"series": 'pcaueni_invalid_rows_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a",version="2"}', "values": "0+60x20"},
        ]
        filters = {"tenant": "tenant-a", "schema": "edr_flow_network_intelligence"}
        filtered = {"name": "tenant schema and invalid-row version aggregation", "interval": "30s", "input_series": filtered_series,
                    "promql_expr_test": [check(7, [sample(3)], **filters), check(10, [sample(1440)], **filters)]}
        first_error = {"name": "first lazy error event remains visible without a prior zero", "interval": "30s", "input_series": [
            series[0],
            {"series": 'pcaueni_invalid_datasets_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a"}', "values": "_ _ _ _ _ _ _ _ 1x12"},
        ], "promql_expr_test": [check(9, [sample(1)])]}
        topic = "pcaue.tenant-a.edr_flow_network_intelligence.json"
        kafka_series = [{"series": 'up{job="kafka-topic-metrics",instance="kafka-exporter:9308"}', "values": "1x20"}]
        for partition, lag, offset in ((0, 3, 10), (1, 101, -1)):
            for metric, value in (("lag", lag), ("current_offset", offset)):
                kafka_series.append({
                    "series": f'kafka_consumergroup_{metric}{{job="kafka-topic-metrics",instance="kafka-exporter:9308",consumergroup="pv_storage.db",topic="{topic}",partition="{partition}"}}',
                    "values": f"{value}x20",
                })
        kafka_labels = f'{{consumergroup="pv_storage.db",topic="{topic}"}}'
        kafka = {"name": "uncommitted partitions have unknown lag", "interval": "30s", "input_series": kafka_series,
                 "promql_expr_test": [check(11, [sample(3, kafka_labels)]), check(13, [sample(1, kafka_labels)])]}
        kafka_down = {"name": "Kafka scrape failure hides old lag", "interval": "30s", "input_series": [dict(s) for s in kafka_series],
                      "promql_expr_test": [check(11, []), check(13, [])]}
        kafka_down["input_series"][0]["values"] = "0x20"
        test_file = {"rule_files": [], "evaluation_interval": "30s", "tests": [healthy, down, missing, idle, filtered, first_error, kafka, kafka_down]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pcaueni-test.json"
            path.write_text(json.dumps(test_file))
            result = subprocess.run([PROMTOOL, "test", "rules", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
