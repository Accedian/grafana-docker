import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = sorted((ROOT / "dashboards").glob("pca-*.json"))
PROMTOOL = shutil.which("promtool")


def panels(dashboard):
    for panel in dashboard.get("panels", []):
        yield panel
        yield from panels(panel)


def expression(query):
    query = query.replace("$__rate_interval", "8m")
    return re.sub(r"\$[A-Za-z_][A-Za-z_0-9]*", ".*", query)


def dashboard(name):
    return json.loads((ROOT / "dashboards" / name).read_text())


def panel_by_title(name, title):
    return next(panel for panel in panels(dashboard(name)) if panel.get("title") == title)


def scalar(value):
    return [{"labels": "{}", "value": value}]


class DashboardStructureTests(unittest.TestCase):
    def test_json_panel_ids_targets_and_variables(self):
        uids = set()
        for path in FILES:
            with self.subTest(path=path.name):
                board = json.loads(path.read_text())
                self.assertNotIn(board["uid"], uids)
                uids.add(board["uid"])
                all_panels = list(panels(board))
                ids = [panel["id"] for panel in all_panels]
                self.assertEqual(len(ids), len(set(ids)))
                variables = board["templating"]["list"]
                names = [variable["name"] for variable in variables]
                self.assertEqual(len(names), len(set(names)))
                for variable in variables:
                    if variable["type"] == "query":
                        self.assertEqual(variable["definition"], variable["query"]["query"])
                for panel in all_panels:
                    targets = panel.get("targets", [])
                    refs = [target["refId"] for target in targets]
                    self.assertEqual(len(refs), len(set(refs)))
                    for target in targets:
                        referenced = set(re.findall(r"\$([A-Za-z_][A-Za-z_0-9]*)", target["expr"]))
                        self.assertFalse(referenced - set(names) - {"__rate_interval", "__interval"})

    def test_unavailable_swarm_values_have_neutral_colours(self):
        for name in ("pca-resource-health.json", "pca-service-health.json"):
            for panel in panels(dashboard(name)):
                defaults = panel.get("fieldConfig", {}).get("defaults", {})
                if defaults.get("noValue") == "Unavailable":
                    mappings = defaults.get("mappings", [])
                    self.assertTrue(any(mapping.get("type") == "special" and
                                        mapping["options"]["match"] == "null+nan" and
                                        mapping["options"]["result"]["color"] == "text" for mapping in mappings))

    def test_swarm_queries_do_not_use_kubernetes_filters_or_zero_fallbacks(self):
        for name in ("pca-resource-health.json", "pca-service-health.json"):
            for panel in panels(dashboard(name)):
                if panel.get("id", 0) < (37 if "resource" in name else 34):
                    continue
                for target in panel.get("targets", []):
                    query = target["expr"]
                    for unsupported in ("$namespace", "$pod", "kube_", "or vector(0)"):
                        self.assertNotIn(unsupported, query)

    def test_swarm_resource_filters_are_independent_of_node_exporter_addresses(self):
        board = dashboard("pca-resource-health.json")
        for panel in panels(board):
            for target in panel.get("targets", []):
                if "node_" in target["expr"] and 'job=~"node-exporter|' in target["expr"]:
                    self.assertIn("sysmetrics-private-cloud", target["expr"])
                    self.assertEqual(target["interval"], "2m")
                if panel["id"] >= 37:
                    self.assertNotIn("$node", target["expr"])
                elif "$namespace" in target["expr"]:
                    self.assertNotIn("interval", target)

    def test_application_boards_explain_shared_metric_requirements(self):
        for name in ("pca-application-speed.json", "pca-ingestion-pipeline.json", "pca-sensor-connectivity.json"):
            content = dashboard(name)["panels"][0]["options"]["content"]
            self.assertIn("Kubernetes and Docker Swarm", content)

    @unittest.skipUnless(PROMTOOL, "promtool is not installed")
    def test_all_dashboard_promql_parses(self):
        rules = []
        for path in FILES:
            for panel in panels(json.loads(path.read_text())):
                for target in panel.get("targets", []):
                    rules.append({"record": "pca_dashboard_test_" + str(len(rules)), "expr": expression(target["expr"])})
        with tempfile.TemporaryDirectory() as directory:
            rule_file = Path(directory) / "rules.yml"
            rule_file.write_text(json.dumps({"groups": [{"name": "dashboards", "rules": rules}]}))
            result = subprocess.run([PROMTOOL, "check", "rules", str(rule_file)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


@unittest.skipUnless(PROMTOOL, "promtool is not installed")
class DashboardQueryTests(unittest.TestCase):
    def run_queries(self, series, expectations, name="pca-service-health.json", eval_time="10m", overrides=None):
        queries = []
        for title, ref, expected in expectations:
            target = next(target for target in panel_by_title(name, title)["targets"] if target["refId"] == ref)
            query = expression(target["expr"])
            for old, new in (overrides or {}).items():
                query = query.replace(old, new)
            queries.append({"expr": query, "eval_time": eval_time, "exp_samples": expected})
        specification = {"evaluation_interval": "1m", "fuzzy_compare": True, "tests": [{"interval": "1m", "input_series": series, "promql_expr_test": queries}]}
        with tempfile.TemporaryDirectory() as directory:
            test_file = Path(directory) / "test.yml"
            test_file.write_text(json.dumps(specification))
            result = subprocess.run([PROMTOOL, "test", "rules", str(test_file)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def swarm_series(self, success="1x20", timestamp="0+60x20", up="1x20", instance="manager:9100"):
        labels = f'deployment="test",stack="aod",job="sysmetrics-private-cloud",instance="{instance}"'
        series = [{"series": f"pca_swarm_collector_success{{{labels}}}", "values": success},
                  {"series": f"pca_swarm_collector_timestamp_seconds{{{labels}}}", "values": timestamp},
                  {"series": f"pca_swarm_collector_last_success_timestamp_seconds{{{labels}}}", "values": timestamp},
                  {"series": f'up{{job="sysmetrics-private-cloud",instance="{instance}"}}', "values": up}]
        for service, desired, running, mode in (("fedex", 2, 2, "replicated"), ("gather", 2, 1, "replicated"),
                                                ("ignite", 1, 0, "replicated"), ("latentapp", 0, 0, "replicated"),
                                                ("cadvisor", 2, 2, "global")):
            service_labels = labels + f',service="aod_{service}",workload="{service}",mode="{mode}"'
            for state, value in (("desired", desired), ("running", running)):
                series.append({"series": f"pca_swarm_service_{state}_replicas{{{service_labels}}}", "values": f"{value}x20"})
        return series

    def timeline(self):
        return [{"labels": '{deployment="test",service="aod_' + service + '",stack="aod"}', "value": value}
                for service, value in (("cadvisor", 1), ("fedex", 1), ("gather", 0.5), ("ignite", 0))]

    def test_swarm_partial_down_global_and_scaled_zero(self):
        self.run_queries(self.swarm_series(), [
            ("Swarm collector healthy", "A", scalar(1)),
            ("Swarm services fully running %", "A", scalar(50)),
            ("Swarm services degraded", "A", scalar(2)),
            ("Swarm active services", "A", scalar(4)),
            ("Swarm — Running / desired service replicas", "A", self.timeline()),
            ("CrashLoopBackOff", "A", []), ("Restarts (24h)", "A", []), ("Failed jobs", "A", []),
        ])

    def test_failed_stale_missing_and_unreachable_collector_never_show_health(self):
        for kwargs in ({"success": "0x20"}, {"timestamp": "0x20"}, {"timestamp": "9999x20"}, {"up": "0x20"}, None):
            with self.subTest(kwargs=kwargs):
                series = self.swarm_series(**kwargs) if kwargs is not None else []
                self.run_queries(series, [("Swarm collector healthy", "A", scalar(0) if kwargs is not None else []),
                                          ("Swarm services fully running %", "A", []),
                                          ("Swarm services degraded", "A", []),
                                          ("Swarm active services", "A", []),
                                          ("Swarm — Running / desired service replicas", "A", [])])

    def test_duplicate_scrapes_do_not_double_count_services(self):
        self.run_queries(self.swarm_series() + self.swarm_series(instance="duplicate:9100"), [
            ("Swarm active services", "A", scalar(4)), ("Swarm services degraded", "A", scalar(2)),
            ("Swarm — Running / desired service replicas", "A", self.timeline()),
        ])

    def test_federated_clusters_with_reused_addresses_do_not_cross_match_scrape_health(self):
        healthy = self.swarm_series()
        failed = self.swarm_series(up="0x20")
        for rows, cluster in ((healthy, "one"), (failed, "two")):
            for row in rows:
                row["series"] = row["series"].replace("{", '{cluster="' + cluster + '",', 1)
                if cluster == "two":
                    row["series"] = row["series"].replace('deployment="test"', 'deployment="other"')
        self.run_queries(healthy + failed, [("Swarm active services", "A", scalar(4)),
                                           ("Swarm — Running / desired service replicas", "A", self.timeline())])

    def test_rollout_surplus_replicas_are_capped_in_timeline(self):
        series = self.swarm_series()
        for row in series:
            if row["series"].startswith("pca_swarm_service_running_replicas") and 'service="aod_fedex"' in row["series"]:
                row["values"] = "4x20"
        self.run_queries(series, [("Swarm services fully running %", "A", scalar(50)),
                                  ("Swarm — Running / desired service replicas", "A", self.timeline())])

    def test_service_filter_applies_to_summary_and_timeline(self):
        self.run_queries(self.swarm_series(), [("Swarm active services", "A", scalar(1)),
                                               ("Swarm services fully running %", "A", scalar(0)),
                                               ("Swarm — Running / desired service replicas", "A", [self.timeline()[2]])],
                         overrides={'service=~".*"': 'service=~"aod_gather"'})

    def test_kubernetes_summaries_require_healthy_kube_state_metrics(self):
        series = [{"series": 'up{job="kube-state-metrics",instance="ksm:8080",cluster="test"}', "values": "1x20"}]
        for name, ready in (("fedex", 2), ("gather", 1)):
            labels = f'namespace="pca",cluster="test",deployment="{name}"'
            series.extend([
                {"series": f'kube_deployment_spec_replicas{{{labels}}}', "values": "2x20"},
                {"series": f'kube_deployment_status_replicas_available{{{labels}}}', "values": f"{ready}x20"},
            ])
        for ready_metric, desired_metric, label in (
            ("kube_statefulset_status_replicas_ready", "kube_statefulset_replicas", 'statefulset="postgres"'),
            ("kube_daemonset_status_number_ready", "kube_daemonset_status_desired_number_scheduled", 'daemonset="agent"'),
        ):
            labels = 'namespace="pca",cluster="test",' + label
            series.extend([{"series": f'{ready_metric}{{{labels}}}', "values": "1x20"},
                           {"series": f'{desired_metric}{{{labels}}}', "values": "1x20"}])
        self.run_queries(series, [("Workloads ready", "A", scalar(75)),
                                  ("Workloads ready", "B", scalar(3)),
                                  ("Workloads ready", "C", scalar(4)),
                                  ("Workloads degraded", "A", scalar(1)),
                                  ("CrashLoopBackOff", "A", scalar(0))])
        series[0]["values"] = "0x20"
        self.run_queries(series, [("Workloads ready", "A", []),
                                  ("Workloads ready", "B", []),
                                  ("Workloads ready", "C", []),
                                  ("Workloads degraded", "A", []),
                                  ("CrashLoopBackOff", "A", [])])

    def test_spark_counter_suffix_variants_work_without_double_counting(self):
        title = "Streaming App – Throughput (rows per Kafka batch)"
        labels = 'job="spark_streamingapp",tenant="test",objectType="ports"'
        for suffixes in (("",), ("_total",), ("", "_total")):
            with self.subTest(suffixes=suffixes):
                series = []
                for suffix in suffixes:
                    series.extend([
                        {"series": f'spark_AccedianStreamingMetrics_streaming_recCount{suffix}{{{labels}}}', "values": "0+120x20"},
                        {"series": f'spark_AccedianStreamingMetrics_streaming_droppedRecCount{suffix}{{{labels},cause="parse"}}', "values": "0+6x20"},
                    ])
                self.run_queries(series, [(title, "B", [{"labels": '{objectType="ports"}', "value": 2}]),
                                          (title, "C", [{"labels": '{cause="parse",objectType="ports"}', "value": 0.1}])],
                                 name="pca-ingestion-pipeline.json")
        self.run_queries([], [(title, "B", []), (title, "C", [])], name="pca-ingestion-pipeline.json")

    def test_unlabelled_swarm_nodes_and_cadvisor_usage_limits_and_throttling(self):
        labels = 'job="cadvisor",instance="worker:15001",container_label_com_docker_stack_namespace="aod",container_label_com_docker_swarm_service_name="aod_fedex",container_label_com_docker_swarm_task_name="aod_fedex.1.task"'
        series = [
            {"series": 'node_cpu_seconds_total{job="sysmetrics-private-cloud",instance="worker:9100",cpu="0",mode="idle"}', "values": "0+30x20"},
            {"series": 'up{job="cadvisor",instance="worker:15001"}', "values": "1x20"},
            {"series": f'container_cpu_usage_seconds_total{{{labels},cpu="total"}}', "values": "0+30x20"},
            {"series": f'container_cpu_cfs_throttled_periods_total{{{labels}}}', "values": "0+6x20"},
            {"series": f'container_cpu_cfs_periods_total{{{labels}}}', "values": "0+60x20"},
            {"series": f'container_memory_working_set_bytes{{{labels}}}', "values": "2000x20"},
            {"series": f'container_spec_memory_limit_bytes{{{labels}}}', "values": "4000x20"},
            {"series": f'container_spec_cpu_quota{{{labels}}}', "values": "100000x20"},
            {"series": f'container_spec_cpu_period{{{labels}}}', "values": "100000x20"},
            {"series": 'machine_memory_bytes{job="cadvisor",instance="worker:15001"}', "values": "8000x20"},
        ]
        group = '{container_label_com_docker_swarm_service_name="aod_fedex",container_label_com_docker_swarm_task_name="aod_fedex.1.task",instance="worker:15001"}'
        task = '{container_label_com_docker_swarm_task_name="aod_fedex.1.task",instance="worker:15001"}'
        self.run_queries(series, [("Cluster CPU utilisation", "A", scalar(50)),
                                  ("Observed Swarm tasks", "A", scalar(1)),
                                  ("Swarm — Top tasks CPU cores", "A", [{"labels": group, "value": 0.5}]),
                                  ("Swarm — CPU throttled periods %", "A", [{"labels": group, "value": 10}]),
                                  ("Swarm — CPU usage vs quota %", "A", [{"labels": group, "value": 50}]),
                                  ("Swarm — Selected tasks memory vs limit", "B", [{"labels": task, "value": 4000}]),
                                  ("Swarm — Memory usage vs limit %", "A", [{"labels": task, "value": 50}]),
                                  ("Swarm — Selected tasks CPU vs quota", "A", [{"labels": task, "value": 0.5}]),
                                  ("Swarm — Selected tasks CPU vs quota", "B", [{"labels": task, "value": 1}])],
                         name="pca-resource-health.json")
        for row in series:
            if row["series"].startswith("container_cpu_usage_seconds_total"):
                row["series"] = row["series"].replace('cpu="total"', 'cpu="cpu00"')
                row["values"] = "0+15x20"
        series.append({"series": f'container_cpu_usage_seconds_total{{{labels},cpu="cpu01"}}', "values": "0+15x20"})
        self.run_queries(series, [("Swarm — Top tasks CPU cores", "A", [{"labels": group, "value": 0.5}]),
                                  ("Swarm — CPU usage vs quota %", "A", [{"labels": group, "value": 50}]),
                                  ("Swarm — Selected tasks CPU vs quota", "A", [{"labels": task, "value": 0.5}])],
                         name="pca-resource-health.json")
        for row in series:
            if row["series"].startswith("container_spec_cpu_period"):
                row["values"] = "0x20"
        self.run_queries(series, [("Swarm — CPU usage vs quota %", "A", []),
                                  ("Swarm — Selected tasks CPU vs quota", "B", [])], name="pca-resource-health.json")
        for row in series:
            if row["series"].startswith("container_spec_cpu_period"):
                row["values"] = "100000x20"
            if row["series"].startswith("container_spec_cpu_quota"):
                row["values"] = "-1x20"
            if row["series"].startswith("container_spec_memory_limit_bytes"):
                row["values"] = "8000x20"
        self.run_queries(series, [("Swarm — CPU usage vs quota %", "A", []),
                                  ("Swarm — Selected tasks memory vs limit", "B", []),
                                  ("Swarm — Memory usage vs limit %", "A", []),
                                  ("Swarm — Selected tasks CPU vs quota", "B", [])], name="pca-resource-health.json")


if __name__ == "__main__":
    unittest.main()
