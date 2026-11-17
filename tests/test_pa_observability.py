"""PA dashboard and scenario behavior; install the simulator requirements first."""

import importlib.util
import json
import math
from pathlib import Path
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import HTTPServer
import yaml

ROOT = Path(__file__).resolve().parents[1]
SIM_DIR = ROOT / "tools/metrics-simulator"
sys.path.insert(0, str(SIM_DIR))
import simulator
from pa07 import RAProfiles, SCENARIOS, TENANTS, PREFIX
from prometheus_client.parser import text_string_to_metric_families


class Clock:
    def __init__(self): self.now = 1800000000.0
    def __call__(self): return self.now
    def advance(self, seconds): self.now += seconds


def samples(text):
    return {(sample.name, tuple(sorted(sample.labels.items()))): sample.value
            for family in text_string_to_metric_families(text) for sample in family.samples}


def value(rendered, suffix, **labels):
    expected = {"tenant_id": TENANTS[0], "record_type": "ra_summary", **labels}
    return rendered[(PREFIX + suffix, tuple(sorted(expected.items())))]


class PAObservabilityTest(unittest.TestCase):
    def test_compose_entry_points_parse_and_bind_only_loopback(self):
        for name in ("docker-compose.yml", "docker-compose.qa.yml"):
            with self.subTest(compose=name):
                config = yaml.safe_load((SIM_DIR / name).read_text())
                self.assertEqual(set(config["services"]), {"simulator", "prometheus", "grafana"})
                for service in config["services"].values():
                    for port in service.get("ports", []):
                        self.assertTrue(port.startswith("127.0.0.1:"), port)
                    if "image" in service:
                        self.assertIn("@sha256:", service["image"])
                command = config["services"]["simulator"]["command"]
                self.assertEqual(command[:2], ["sh", "-c"])
                self.assertIn("--require-hashes", command[2])
                self.assertIn("exec python simulator.py", command[2])

    def test_http_controls_reject_invalid_input_without_state_change(self):
        state = simulator.SimState(Clock())
        state.catalog = [{"name": "test_total", "type": "counter"}]
        state.discover_dashboards()
        old = simulator.STATE; simulator.STATE = state
        server = HTTPServer(("127.0.0.1", 0), simulator.MetricsHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def call(path, body, method="POST"):
            req = urllib.request.Request("http://127.0.0.1:" + str(server.server_port) + path,
                                         data=json.dumps(body).encode(), method=method,
                                         headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=3) as response:
                    return response.status, json.load(response)
            except urllib.error.HTTPError as error:
                return error.code, json.load(error)
        try:
            self.assertEqual(call("/api/override", {})[1], {"error": "metric and value required"})
            self.assertEqual(call("/api/override", {}, "DELETE")[1], {"error": "metric required"})
            self.assertEqual(call("/api/override", {"metric": "test_total", "value": 2})[0], 200)
            for bad in (float("nan"), float("inf"), -1, 1e99, True):
                self.assertEqual(call("/api/override", {"metric": "test_total", "value": bad})[0], 400)
                self.assertEqual(state.manual_overrides, {"test_total": 2})
            self.assertEqual(call("/api/scenario", [])[0], 400)
            self.assertEqual(call("/api/scenario", {"dashboard": simulator.PA_DASHBOARD, "scenario": "not-a-scenario"})[0], 400)
            self.assertEqual(call("/api/scenario", {"dashboard": simulator.PA_DASHBOARD, "scenario": "pa07-idle", "target": {"tenant_id": "foreign", "record_type": "ra_summary"}})[0], 400)
            self.assertEqual(state.manual_overrides, {"test_total": 2})
            self.assertEqual(call("/api/scenario", {"dashboard": simulator.PA_DASHBOARD, "scenario": "pa07-idle"})[0], 200)
            self.assertEqual(state.manual_overrides, {})
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3); simulator.STATE = old

    def test_exact_schema_and_stable_cardinality(self):
        clock = Clock(); ra = RAProfiles(clock)
        data = samples(ra.render())
        self.assertEqual(len(data), 4 * 36)
        for name in SCENARIOS:
            ra.select(name); clock.advance(5)
            parsed = samples(ra.render())
            self.assertEqual(len(parsed), 3 * 36 if name == "pa07-metrics-missing" else 4 * 36)
            self.assertTrue(all(math.isfinite(v) and v >= 0 for v in parsed.values()))

    def test_transitions_integrate_old_rates_without_counter_resets(self):
        clock = Clock(); ra = RAProfiles(clock)
        clock.advance(10)
        initial = samples(ra.render())
        self.assertEqual(value(initial, "source_messages_total"), 10)
        self.assertEqual(value(initial, "rows_total", outcome="published"), 50)
        ra.select("pa07-partial-publication")
        clock.advance(7)  # no scrape while the fault is active
        ra.select("pa07-recovery")
        clock.advance(3)
        recovered = samples(ra.render())
        self.assertEqual(value(recovered, "rows_total", outcome="published"), 50 + 28 + 15)
        self.assertEqual(value(recovered, "rows_total", outcome="publish_failed"), 7)
        self.assertEqual(value(recovered, "partial_publications_total"), 7)
        self.assertTrue(all(recovered[k] >= v for k, v in initial.items() if k[0].endswith("_total")))

    def test_quality_is_not_row_loss_and_tenants_are_scoped(self):
        clock = Clock(); ra = RAProfiles(clock)
        ra.select("pa07-numeric-quality"); clock.advance(10)
        data = samples(ra.render())
        self.assertEqual(value(data, "rows_total", outcome="published"), 50)
        self.assertEqual(value(data, "rows_total", outcome="skipped"), 0)
        self.assertEqual(value(data, "failures_total", stage="numeric", reason="invalid_float"), 10)
        self.assertEqual(value(data, "failures_total", tenant_id=TENANTS[1], stage="numeric", reason="invalid_float"), 0)
        ra.select("pa07-row-loss", {"tenant_id": TENANTS[0], "record_type": "ra_instance"})
        clock.advance(2)
        self.assertEqual(value(samples(ra.render()), "rows_total", record_type="ra_instance", outcome="skipped"), 2)

    def test_idle_busy_missing_and_explicit_restart(self):
        clock = Clock(); ra = RAProfiles(clock)
        clock.advance(5); active = samples(ra.render())
        ra.select("pa07-idle"); clock.advance(1200); idle = samples(ra.render())
        self.assertEqual(value(active, "source_messages_total"), value(idle, "source_messages_total"))
        self.assertEqual(value(idle, "processing_started_timestamp_seconds"), 0)
        self.assertGreater(clock() - value(idle, "last_output_timestamp_seconds"), 900)
        ra.select("pa07-stalled"); clock.advance(61); busy = samples(ra.render())
        self.assertGreater(clock() - value(busy, "processing_started_timestamp_seconds"), 60)
        ra.select("pa07-metrics-missing")
        self.assertFalse(any(dict(k[1]).get("tenant_id") == TENANTS[0] and dict(k[1]).get("record_type") == "ra_summary" for k in samples(ra.render())))
        ra.select("pa07-restart"); restarted = samples(ra.render())
        self.assertEqual(value(restarted, "source_messages_total"), 0)
        self.assertEqual(value(restarted, "last_output_timestamp_seconds"), 0)

    def test_invalid_controls_preserve_state(self):
        clock = Clock(); ra = RAProfiles(clock)
        for target in ({"bad": "x"}, {"tenant_id": "foreign", "record_type": "ra_summary"}):
            with self.assertRaises(ValueError): ra.select("pa07-row-loss", target)
            self.assertEqual(ra.scenario, "pa07-healthy-active")
        state = simulator.SimState(clock)
        state.catalog = [{"name": "test_total", "type": "counter"}]
        state.set_override("test_total", 2)
        state.get_effective_value("test_total", 0, mtype="counter")
        clock.advance(5); state.set_override("test_total", 0); clock.advance(5)
        self.assertEqual(state.get_effective_value("test_total", 0, mtype="counter"), 10)
        for invalid in (float("nan"), float("inf"), -1, 1e99, True):
            with self.assertRaises(ValueError): state.set_override("test_total", invalid)
            self.assertEqual(state.manual_overrides["test_total"], 0)
        with self.assertRaises(ValueError): state.set_override("payload\nlabel", 1)

    def test_complete_exposition_never_synthesizes_scrape_up(self):
        state = simulator.SimState(Clock())
        state.catalog = [{"name": "up", "type": "gauge"}, {"name": PREFIX + "source_messages_total", "type": "counter"}]
        old = simulator.STATE; simulator.STATE = state
        try:
            data = samples(simulator.generate_metrics())
            self.assertFalse(any(k[0] == "up" for k in data))
            self.assertEqual(len(data), 4 * 36)
            hostile = samples(simulator.generate_line("label_test", {"label": 'quote"\\\n</script>'}, 1))
            self.assertEqual(next(iter(hostile))[1][0][1], 'quote"\\\n</script>')
        finally: simulator.STATE = old

    def test_legacy_counter_warms_up_after_initial_zero(self):
        clock = Clock(); state = simulator.SimState(clock)
        self.assertEqual(state.get_effective_value("legacy_total", 0, t=0, mtype="counter"), 0)
        clock.advance(5)
        state.get_effective_value("legacy_total", 50, t=5, mtype="counter")
        clock.advance(5)
        self.assertEqual(state.get_effective_value("legacy_total", 100, t=10, mtype="counter"), 50)

    def test_dashboard_contract_and_query_units(self):
        dashboard = json.loads((ROOT / "dashboards/Customer (swarm)/pca-pa-ingestion-pipeline.json").read_text())
        def walk(items):
            for item in items:
                yield item
                yield from walk(item.get("panels", []))
        panels = {p["id"]: p for p in walk(dashboard["panels"])}
        self.assertEqual(dashboard["uid"], "pca-pa-ingestion-pipeline")
        self.assertIn("source_messages_total", panels[101]["targets"][0]["expr"])
        self.assertIn('outcome="published"', panels[102]["targets"][0]["expr"])
        self.assertIn('job="sky-topo"', panels[106]["targets"][0]["expr"])
        for pid in (101, 102, 103, 104, 105, 107, 108, 109, 110, 111, 112, 113, 114, 117):
            self.assertIn('${tenant:regex}', panels[pid]["targets"][0]["expr"])
            self.assertIn('${objectType:regex}', panels[pid]["targets"][0]["expr"])
            self.assertNotIn("or vector(0)", panels[pid]["targets"][0]["expr"])
        variables = {v["name"]: v for v in dashboard["templating"]["list"]}
        self.assertIn("sky_topo_ra_processor_state", variables["tenant"]["query"]["query"])
        self.assertEqual(variables["objectType"]["type"], "custom")
        self.assertEqual(set(variables["objectType"]["allValue"].split("|")), {"ra_summary", "ra_instance", "unknown"}, "All must not include unrelated power record types")
        self.assertIn("Druid ingestion", panels[102]["description"])
        self.assertIn("failures_total", panels[117]["targets"][0]["expr"], "quality events need visibility even when all rows publish")
        intro = panels[1]["options"]["content"]
        self.assertNotIn("Sky-Topo → Gather → Druid", intro)
        self.assertNotIn("red (0)", intro)
        self.assertEqual(panels[109]["type"], "table")
        self.assertEqual(panels[109]["fieldConfig"]["defaults"]["unit"], "string", "timestamps must not format tenant/instance strings as dates")
        self.assertTrue(any(p.get("id") == "unit" and p.get("value") == "dateTimeFromNow"
                            for o in panels[109]["fieldConfig"]["overrides"] for p in o["properties"]))
        self.assertIn("check coverage", panels[108]["fieldConfig"]["defaults"]["noValue"])


if __name__ == "__main__":
    unittest.main()
