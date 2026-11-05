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
        for panel_id in (7, 8, 9, 10, 19, 20, 21, 22, 23):
            expression = self.expression(panel_id, tenant="tenant-a", schema="edr_flow_network_intelligence")
            self.assertIn('tenant_id=~"tenant-a"', expression)
            self.assertIn('schema=~"edr_flow_network_intelligence"', expression)
            self.assertIn("sum by (tenant_id, schema", expression)
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
        self.assertNotIn("pcaueni_invalid_rows", serialized)
        self.assertIn("pcaueni_insert_attempts_total", self.expression(10))
        self.assertIn("sum by (tenant_id, schema, result)", self.expression(10))
        for panel_id in (19, 20, 21):
            self.assertIn("histogram_quantile(0.95", self.expression(panel_id))
            self.assertIn("_count{", self.expression(panel_id))
            self.assertIn("> 0", self.expression(panel_id))
        self.assertIn('stage="write"', self.expression(20))
        self.assertIn('stage="readiness"', self.expression(21))
        self.assertIn("pcaueni_insert_in_progress", self.expression(22))
        self.assertIn("pcaueni_insert_batch_rows_sum", self.expression(23))
        self.assertIn("pcaueni_insert_batch_rows_count", self.expression(23))

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
            {"series": 'pcaueni_insert_attempts_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a",result="success"}', "values": "0+30x20"},
            {"series": 'pcaueni_insert_attempts_total{job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a",result="error"}', "values": "0+60x20"},
        ]
        filters = {"tenant": "tenant-a", "schema": "edr_flow_network_intelligence"}
        filtered = {"name": "tenant schema isolation and separate attempt outcomes", "interval": "30s", "input_series": filtered_series,
                    "promql_expr_test": [check(7, [sample(3)], **filters), check(10, [
                        sample(1, '{result="success",schema="edr_flow_network_intelligence",tenant_id="tenant-a"}'),
                        sample(2, '{result="error",schema="edr_flow_network_intelligence",tenant_id="tenant-a"}'),
                    ], **filters)]}
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

    @unittest.skipUnless(PROMTOOL, "promtool is required for query behaviour checks")
    def test_dedicated_inserter_metrics_live_idle_down_and_isolation(self):
        """Evaluate histograms/gauges and ensure idle or missing data stays absent."""
        labels = '{schema="edr_flow_network_intelligence",tenant_id="tenant-a"}'
        source = 'job="pcaueni_inserter1a",instance="a:1664",schema="edr_flow_network_intelligence",tenant_id="tenant-a"'
        series = [{"series": 'up{job="pcaueni_inserter1a",instance="a:1664"}', "values": "1x20"}]

        def add(metric, values, extra=""):
            series.append({"series": f"{metric}{{{source}{extra}}}", "values": values})

        for metric, extra, bounds in (
            ("pcaueni_insert_duration_seconds", ',result="success"', (("1", 5), ("2.5", 10), ("+Inf", 10))),
            ("pcaueni_insert_stage_duration_seconds", ',stage="write",result="success"', (("0.1", 5), ("0.25", 10), ("+Inf", 10))),
            ("pcaueni_insert_stage_duration_seconds", ',stage="readiness",result="success"', (("0.01", 5), ("0.05", 10), ("+Inf", 10))),
        ):
            add(metric + "_count", "0+10x20", extra)
            for bound, increment in bounds:
                add(metric + "_bucket", f"0+{increment}x20", extra + f',le="{bound}"')
        add("pcaueni_insert_in_progress", "2x20")
        add("pcaueni_insert_batch_rows_sum", "0+1000x20")
        add("pcaueni_insert_batch_rows_count", "0+10x20")

        def check(panel_id, values, **filters):
            return {"expr": self.expression(panel_id, **filters), "eval_time": "8m", "exp_samples": [
                {"labels": labels, "value": value} for value in values
            ]}

        active = {"name": "PCA UE dedicated histogram timings and successful batch mean", "interval": "30s", "input_series": series,
                  # Promtool 2.54 compares the evaluator's IEEE-754 values exactly.
                  "promql_expr_test": [check(19, [2.35]), check(20, [0.23500000000000001]), check(21, [0.046000000000000006]), check(22, [2]), check(23, [100.00000000000001])]}
        idle_series = [dict(s) for s in series]
        for s in idle_series[1:]:
            s["values"] = "0x20" if "_in_progress{" in s["series"] else "100x20"
        idle = {"name": "idle timing and batch windows do not produce NaN or false zeros", "interval": "30s", "input_series": idle_series,
                "promql_expr_test": [check(19, []), check(20, []), check(21, []), check(22, [0]), check(23, [])]}
        down_series = [dict(s) for s in series]
        down_series[0]["values"] = "0x20"
        down = {"name": "dedicated telemetry from a DOWN inserter is hidden", "interval": "30s", "input_series": down_series,
                "promql_expr_test": [check(i, []) for i in (19, 20, 21, 22, 23)]}
        missing = {"name": "old or absent PVStorage instrumentation is not fabricated", "interval": "30s", "input_series": series[:1],
                   "promql_expr_test": [check(i, []) for i in (10, 19, 20, 21, 22, 23)]}
        isolated_series = series + [dict(s, series=s["series"].replace('tenant_id="tenant-a"', 'tenant_id="tenant-b"')) for s in series[1:]]
        isolation = {"name": "dedicated diagnostics retain tenant and schema filters", "interval": "30s", "input_series": isolated_series,
                     "promql_expr_test": [check(19, [2.35], tenant="tenant-a"), check(22, [2], tenant="tenant-a"), check(23, [100.00000000000001], tenant="tenant-a"), check(19, [], schema="other_schema")]}
        # A successful ClickHouse call can legitimately report zero written rows.
        zero_batch_series = [dict(s) for s in series]
        next(s for s in zero_batch_series if "_batch_rows_sum{" in s["series"])["values"] = "0x20"
        zero_batch = {"name": "completed zero-row batches remain visible as a real zero", "interval": "30s", "input_series": zero_batch_series,
                      "promql_expr_test": [check(23, [0])]}
        error_histogram = []
        for s in series:
            if "pcaueni_insert_duration_seconds_" in s["series"]:
                error_histogram.append({"series": s["series"].replace('result="success"', 'result="error"'), "values": "0+10x20"})
        outcomes = {"name": "duration p95 aggregates both completed result labels", "interval": "30s", "input_series": series + error_histogram,
                    "promql_expr_test": [check(19, [2.2])]}
        stale_replica = [{"series": 'up{job="pcaueni_inserter1b",instance="b:1664"}', "values": "0x20"}]
        stale_replica += [
            {"series": s["series"].replace('pcaueni_inserter1a', 'pcaueni_inserter1b').replace('instance="a:1664"', 'instance="b:1664"'),
             "values": "10x20" if "_in_progress{" in s["series"] else "0+100x20"}
            for s in series[1:]
        ]
        partial_down = {"name": "DOWN replica does not pollute aggregated histograms or gauges", "interval": "30s", "input_series": series + stale_replica,
                        "promql_expr_test": [check(19, [2.35]), check(22, [2]), check(23, [100.00000000000001])]}
        inflight = {"name": "blocked first attempt has a gauge before any completed timing", "interval": "30s", "input_series": [series[0],
            {"series": f"pcaueni_insert_in_progress{{{source}}}", "values": "1x20"},
        ], "promql_expr_test": [check(19, []), check(20, []), check(21, []), check(22, [1]), check(23, [])]}
        test_file = {"rule_files": [], "evaluation_interval": "30s", "tests": [active, idle, down, missing, isolation, zero_batch, outcomes, partial_down, inflight]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pcaueni-instrumentation-test.json"
            path.write_text(json.dumps(test_file))
            result = subprocess.run([PROMTOOL, "test", "rules", str(path)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
