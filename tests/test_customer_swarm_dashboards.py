import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("swarm", ROOT / "generate_swarm_dashboards.py")
SWARM = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SWARM)


class CustomerSwarmDashboardsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dashboards = {
            path.name: json.loads(path.read_text())
            for path in (ROOT / "dashboards/Customer (swarm)").glob("*.json")
        }

    def test_supported_subset_is_reproducible(self):
        self.assertEqual(set(self.dashboards), {
            "pca-ingestion-pipeline.json", "pca-sensor-connectivity.json",
            "pca-application-speed.json", "pca-resource-health.json",
            "pca-ue-ingestion.json",
        })
        for name, dashboard in self.dashboards.items():
            with self.subTest(name=name):
                self.assertEqual(dashboard, SWARM.build(name))
                panels = list(SWARM.walk(dashboard["panels"]))
                self.assertEqual(len({p["id"] for p in panels}), len(panels))
                self.assertTrue(any(p.get("targets") for p in panels))
                for panel in panels:
                    if panel["type"] == "row":
                        self.assertTrue(panel.get("panels") or not panel["collapsed"])

    def test_dashboard_uids_do_not_collide_with_other_folders(self):
        other_uids = {
            json.loads(path.read_text()).get("uid")
            for path in (ROOT / "dashboards").rglob("*.json")
            if path.parent.name != "Customer (swarm)"
        }
        uids = [d["uid"] for d in self.dashboards.values()]
        self.assertEqual(len(set(uids)), len(uids))
        self.assertFalse(set(uids) & other_uids)

    def test_queries_use_no_kubernetes_or_opt_in_collectors(self):
        forbidden = r"kube_|kubelet|openebs_|pca_swarm_|node_namespace_pod_|cluster:namespace:|\$(cluster|namespace|pod)\b"
        for name, dashboard in self.dashboards.items():
            for panel in SWARM.walk(dashboard["panels"]):
                for target in panel.get("targets", []):
                    with self.subTest(dashboard=name, panel=panel["id"]):
                        self.assertNotRegex(target["expr"], forbidden)
                        self.assertIn(target["datasource"], ["Prometheus", {"type": "prometheus", "uid": "prometheus"}])

    def test_resource_queries_use_existing_jobs_and_container_identity(self):
        dashboard = self.dashboards["pca-resource-health.json"]
        variables = {v["name"]: v for v in dashboard["templating"]["list"]}
        self.assertEqual(set(variables), {"node", "cadvisorHost", "container"})
        for panel in SWARM.walk(dashboard["panels"]):
            for target in panel.get("targets", []):
                expr = target["expr"]
                self.assertEqual(target["interval"], "2m")
                if "container_" in expr:
                    self.assertIn('job="cadvisor"', expr)
                    self.assertIn("by (instance,name)", expr)
                    self.assertIn('name!=""', expr)
                    self.assertIn('image!=""', expr)
                else:
                    self.assertIn('job=~"sysmetrics|sysmetrics-private-cloud"', expr)
        self.assertNotIn("OOMKilled (last termination", json.dumps(dashboard))

    def test_resource_row_children_follow_their_row(self):
        dashboard = self.dashboards["pca-resource-health.json"]
        for panel in dashboard["panels"]:
            for child in panel.get("panels", []):
                self.assertGreater(child["gridPos"]["y"], panel["gridPos"]["y"])

    def test_spark_pushgateway_counter_names(self):
        dashboard = self.dashboards["pca-ingestion-pipeline.json"]
        throughput = next(p for p in SWARM.walk(dashboard["panels"]) if p["id"] == 32)
        for target in throughput["targets"][1:]:
            self.assertRegex(target["expr"], r"streaming_(recCount|droppedRecCount)_total\{")

    @unittest.skipUnless(shutil.which("promtool"), "promtool is not installed")
    def test_all_queries_parse_as_promql(self):
        rules = []
        for dashboard in self.dashboards.values():
            for panel in SWARM.walk(dashboard["panels"]):
                for target in panel.get("targets", []):
                    expr = re.sub(r"\$__rate_interval|\$__interval", "8m", target["expr"])
                    expr = re.sub(r"\$\{[A-Za-z][A-Za-z0-9]*:regex\}", ".*", expr)
                    expr = re.sub(r"\$[A-Za-z][A-Za-z0-9]*", ".*", expr)
                    rules.append({"record": f"test:query_{len(rules)}", "expr": expr})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rules.json"
            path.write_text(json.dumps({"groups": [{"name": "swarm", "rules": rules}]}))
            result = subprocess.run(
                ["promtool", "check", "rules", str(path)], capture_output=True, text=True,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_copy_layout_matches_disjoint_folder_providers(self):
        script = (ROOT / "run.sh").read_text()
        start = script.index('    # Keep providers disjoint')
        end = script.index("\nfi", start)
        copy_script = script[start:end]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "stock"
            destination = temporary / "data"
            source.mkdir()
            (destination / "dashboards").mkdir(parents=True)
            for folder in ("Customer (k8s)", "Customer (swarm)", "kubernetes"):
                (source / folder).mkdir()
                (source / folder / "dashboard.json").write_text("{}")
            (source / "root.json").write_text("{}")
            copy_script = copy_script.replace("/tmp/dashboards", str(source))
            subprocess.run(
                ["bash", "-e", "-c", copy_script],
                env={"GF_PATHS_DATA": str(destination), "PATH": "/usr/bin:/bin"},
                check=True,
            )
            self.assertTrue((destination / "dashboards/general/root.json").exists())
            self.assertTrue((destination / "dashboards/general/kubernetes/dashboard.json").exists())
            for platform in ("k8s", "swarm"):
                folder = f"Customer ({platform})"
                self.assertTrue((destination / "dashboards" / folder / "dashboard.json").exists())
                self.assertFalse((destination / "dashboards/general" / folder).exists())
        providers = (ROOT / "provisioning/dashboards/system-dashboards.yaml").read_text()
        for platform in ("k8s", "swarm"):
            self.assertIn(f"folderUid: 'pca-customer-{platform}'", providers)
            self.assertIn(f"path: /var/lib/grafana/dashboards/Customer ({platform})", providers)
        self.assertIn("path: /var/lib/grafana/dashboards/general\n", providers)


if __name__ == "__main__":
    unittest.main()
