import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = "templates/prometheus-datasource.yaml"
BUNDLED_URL = (
    "http://kube-prometheus-stack-prometheus.monitoring.svc.cluster.local:9090/prometheus"
)


def render_datasource(*set_args):
    command = ["helm", "template", "grafana", str(ROOT / "helm"), "--show-only", TEMPLATE]
    for arg in set_args:
        command += ["--set", arg]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    # Flat "key: value" fields of the single datasource; stdlib only (no PyYAML).
    datasource = dict(re.findall(r"^\s+-?\s*(\w+): (.*)$", result.stdout, re.MULTILINE))
    # The url is rendered with Helm's quote, i.e. a JSON-compatible string literal.
    datasource["url"] = json.loads(datasource["url"])
    datasource["isDefault"] = datasource["isDefault"] == "true"
    return datasource


@unittest.skipUnless(shutil.which("helm"), "helm is required to render the chart")
class PrometheusDatasourceTest(unittest.TestCase):
    def test_default_url_uses_bundled_prometheus_route_prefix(self):
        # kube-prometheus-stack is installed with routePrefix=/prometheus/, so its API
        # lives under /prometheus/api/v1; the bare :9090 root answers 404.
        self.assertEqual(render_datasource()["url"], BUNDLED_URL)

    def test_explicit_url_overrides_default(self):
        url = "http://prometheus-operated.observability.svc.cluster.local:9090"
        self.assertEqual(render_datasource(f"prometheusUrl={url}")["url"], url)

    def test_url_with_yaml_special_characters_is_preserved(self):
        url = "http://prometheus.example:9090/prometheus?x=a #b"
        self.assertEqual(render_datasource(f"prometheusUrl={url}")["url"], url)

    def test_empty_url_falls_back_to_bundled_prometheus(self):
        self.assertEqual(render_datasource("prometheusUrl=")["url"], BUNDLED_URL)

    def test_datasource_identity_is_unchanged(self):
        datasource = render_datasource()
        self.assertEqual(datasource["uid"], "prometheus")
        self.assertEqual(datasource["type"], "prometheus")
        self.assertTrue(datasource["isDefault"])

    def test_datasource_has_no_version_so_provisioning_always_applies(self):
        # Grafana stores version 2 for the datasource on the first restart. A provisioned
        # "version: 1" is then never newer than the DB, so later url changes (e.g. after a
        # patch) are skipped and the pod keeps querying the old url. Without a version,
        # provisioning overwrites the DB row on every start.
        self.assertNotIn("version", render_datasource())


class BakedPrometheusDatasourceTest(unittest.TestCase):
    def test_baked_datasource_has_no_version(self):
        baked = (ROOT / "provisioning/datasources/prometheus-datasource.yaml").read_text()
        self.assertIsNone(re.search(r"^\s+version:", baked, re.MULTILINE))


if __name__ == "__main__":
    unittest.main()
