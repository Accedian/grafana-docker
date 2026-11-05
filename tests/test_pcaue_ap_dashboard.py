"""Evaluate AP queries with real PromQL under traffic, idle and failed scrapes."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROMTOOL = os.environ.get("PROMTOOL") or shutil.which("promtool")


class PCAUEAPDashboardTest(unittest.TestCase):
    @unittest.skipUnless(PROMTOOL, "promtool is required for behaviour tests")
    def test_live_idle_missing_down_and_tenant_scope(self):
        dashboard = json.loads((ROOT / "dashboards/Customer (swarm)/pca-ue-ap-ingestion.json").read_text())
        panels = {p["id"]: p for p in dashboard["panels"]}

        def query(id_, samples):
            expr = panels[id_]["targets"][0]["expr"].replace("${tenant:regex}", "tenant-a").replace("$__rate_interval", "2m")
            return {"expr": expr, "eval_time": "8m", "exp_samples": samples}

        def sample(labels, value):
            return {"labels": labels, "value": value}

        labels = '{objectType="CiscoUE-edr-access-endpoint",tenantId="tenant-a"}'
        tenant = 'tenantId="tenant-a",objectType="CiscoUE-edr-access-endpoint"'
        source = 'job="ignite",instance="ignite:8090",' + tenant
        series = [
            {"series": 'up{job="ignite",instance="ignite:8090"}', "values": "1x20"},
            {"series": 'up{job="pcaue-ap-agent",instance="agent:2112"}', "values": "1x20"},
            {"series": 'up{job="gather",instance="gather:9191"}', "values": "1x20"},
            {"series": 'telegraf_status{job="pcaue-ap-agent",instance="agent:2112"}', "values": "1x20"},
            {"series": 'received_data_total{job="pcaue-ap-agent",instance="agent:2112"}', "values": "0+300x20"},
            {"series": 'ignite_kafka_total_sent{' + source + '}', "values": "0+30x20"},
            {"series": 'ignite_kafka_total_sent{job="ignite",instance="ignite:8090",tenantId="tenant-b",objectType="CiscoUE-edr-access-endpoint"}', "values": "0+300x20"},
            {"series": 'ignite_kafka_total_sent{job="ignite",instance="ignite:8090",tenantId="tenant-a",objectType="another-type"}', "values": "0+300x20"},
            {"series": 'gather_ingest_pacemaker_queue_size{job="gather",instance="gather:9191",datasource="tenant-a-npav-ts-metrics"}', "values": "4x20"},
            {"series": 'gather_ingest_pacemaker_queue_size{job="gather",instance="gather:9191",datasource="tenant-b-npav-ts-metrics"}', "values": "40x20"},
            {"series": 'gather_metric_ds_last_hour_rowCount_per_type{job="gather",instance="gather:9191",' + tenant + '}', "values": "6x20"},
        ]
        live = {"name": "AP rows isolated from other tenants and object types", "interval": "30s", "input_series": series,
                "promql_expr_test": [query(6, [sample(labels, 1)]), query(7, []),
                                     query(9, [sample('{instance="agent:2112"}', 10)]),
                                     query(12, [sample('{datasource="tenant-a-npav-ts-metrics"}', 4)]),
                                     query(14, [sample(labels, 6)])]}
        idle_series = [dict(s) for s in series]
        idle_series[5]["values"] = "30x20"
        idle = {"name": "Initialized idle counter is a true zero rate", "interval": "30s", "input_series": idle_series,
                "promql_expr_test": [query(6, [sample(labels, 0)]), query(7, [])]}
        down_series = [dict(s) for s in series]
        for i in (0, 1, 2):
            down_series[i]["values"] = "0x20"
        down = {"name": "Failed scrapes hide old application values", "interval": "30s", "input_series": down_series,
                "promql_expr_test": [query(i, []) for i in (3, 6, 7, 9, 12, 14, 16)]}
        missing = {"name": "Absent counters and targets do not become zero", "interval": "30s", "input_series": [],
                   "promql_expr_test": [query(i, []) for i in range(2, 17)]}
        errors = {"name": "A first lazy dropped-input counter remains visible", "interval": "30s", "input_series": series + [
            {"series": 'ignite_kafka_total_dropped{' + source + ',reason="missing_dictionary"}', "values": "_ _ _ _ _ _ _ _ 1x12"},
        ], "promql_expr_test": [query(7, [sample('{objectType="CiscoUE-edr-access-endpoint",reason="missing_dictionary",tenantId="tenant-a"}', 1)])]}
        malformed = {"name": "A rejected CSV batch stays visible without any published rows", "interval": "30s", "input_series": [
            {"series": 'up{job="ignite",instance="ignite:8090"}', "values": "1x20"},
            {"series": 'ignite_normalizer_csv_parse_errors_total{' + source + '}', "values": "_ _ _ _ _ _ _ _ 1x12"},
            {"series": 'ignite_normalizer_csv_parse_errors_total{job="ignite",instance="ignite:8090",tenantId="tenant-b",objectType="CiscoUE-edr-access-endpoint"}', "values": "10x20"},
        ], "promql_expr_test": [query(6, []), query(16, [sample(labels, 1)])]}
        malformed_down = {"name": "Failed scrape hides stale CSV error counts", "interval": "30s", "input_series": [
            {"series": 'up{job="ignite",instance="ignite:8090"}', "values": "0x20"},
            {"series": 'ignite_normalizer_csv_parse_errors_total{' + source + '}', "values": "1x20"},
        ], "promql_expr_test": [query(16, [])]}
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "ap-promql.json"
            p.write_text(json.dumps({"rule_files": [], "evaluation_interval": "30s", "tests": [live, idle, down, missing, errors, malformed, malformed_down]}))
            result = subprocess.run([PROMTOOL, "test", "rules", str(p)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
