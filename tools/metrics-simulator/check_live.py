#!/usr/bin/env python3
"""Exercise the owned, loopback-only PA07 QA stack against real Prometheus.

This is synthetic dashboard evidence, not Kafka/Druid processing evidence.
The optional scrape drill stops/restarts only this named QA simulator service.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

from pa07 import PREFIX, TENANTS

SIM = "http://127.0.0.1:19999"
PROM = "http://127.0.0.1:19090"
GRAFANA = "http://127.0.0.1:13000"
KEY = "Customer (swarm)/pca-pa-ingestion-pipeline.json"
FILTER = '{tenant_id="' + TENANTS[0] + '",record_type="ra_summary"'


def request(url, body=None):
    data = None if body is None else json.dumps(body, allow_nan=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.load(response)


def query(expr):
    result = request(PROM + "/api/v1/query?" + urllib.parse.urlencode({"query": expr}))
    assert result["status"] == "success", result
    return result["data"]["result"]


def number(expr):
    result = query(expr)
    assert len(result) == 1, (expr, result)
    return float(result[0]["value"][1])


def metric(suffix, extra=""):
    return PREFIX + suffix + FILTER + ("," + extra if extra else "") + "}"


def wait_for(check, description, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            print("PASS:", description, flush=True)
            return
        time.sleep(.5)
    raise AssertionError("timed out: " + description)


def select(name):
    result = request(SIM + "/api/scenario", {"dashboard": KEY, "scenario": "pa07-" + name})
    assert result["status"] == "ok", result


def walk(panels):
    for panel in panels:
        yield panel
        yield from walk(panel.get("panels", []))


def run(scrape_drill=False):
    assert request(GRAFANA + "/api/health")["database"] == "ok"
    dashboard = request(GRAFANA + "/api/dashboards/uid/pca-pa-ingestion-pipeline")["dashboard"]
    wait_for(lambda: number('up{job="sky-topo"}') == 1, "real scrape target is up")
    for panel in walk(dashboard["panels"]):
        for target in panel.get("targets", []):
            expr = re.sub(r"\$__rate_interval|\$__interval|\$__range", "1m", target["expr"])
            expr = expr.replace("${tenant:regex}", TENANTS[0]).replace("${objectType:regex}", "ra_summary")
            expr = expr.replace("$tenant", TENANTS[0]).replace("$objectType", "ra_summary")
            query(expr)
    tenant_query = dashboard["templating"]["list"][0]["query"]["query"]
    assert {v["metric"]["tenant_id"] for v in query(tenant_query[len("query_result("):-1])} == set(TENANTS)
    print("PASS: every dashboard query evaluates in real Prometheus; both tenant choices resolve", flush=True)

    for scenario, suffix, extra in (
        ("numeric-quality", "failures_total", 'stage="numeric",reason="invalid_float"'),
        ("row-loss", "rows_total", 'outcome="skipped"'),
        ("partial-publication", "partial_publications_total", ""),
        ("source-discard", "failures_total", 'stage="decode",reason="csv_invalid"'),
    ):
        expr = metric(suffix, extra)
        before = number(expr)
        select(scenario)
        wait_for(lambda: number(expr) > before, scenario + " reaches Prometheus")
    select("stalled")
    wait_for(lambda: number("time() - " + metric("processing_started_timestamp_seconds")) > 60
             and number(metric("processing_started_timestamp_seconds")) > 0, "active attempt age is visible")
    select("idle")
    wait_for(lambda: number(metric("processing_started_timestamp_seconds")) == 0
             and number("time() - " + metric("last_output_timestamp_seconds")) >= 900, "idle is distinct from active work")
    select("metrics-missing")
    wait_for(lambda: query(metric("source_messages_total")) == [] and number('up{job="sky-topo"}') == 1,
             "missing source telemetry stays absent while scrape is healthy")
    select("restart")
    def reset_visible():
        result = query(metric("last_output_timestamp_seconds"))
        return bool(result) and float(result[0]["value"][1]) == 0
    wait_for(reset_visible, "explicit reset has never-seen timestamps")
    select("recovery")
    wait_for(lambda: number("time() - " + metric("last_output_timestamp_seconds")) < 15
             and number(metric("last_output_timestamp_seconds")) > 0, "acknowledged output recovers")
    for result in query("rate(" + metric("source_messages_total") + "[1m])"):
        assert float(result["value"][1]) >= 0
    assert number(PREFIX + 'failures_total{tenant_id="' + TENANTS[1]
                  + '",record_type="ra_summary",stage="publish",reason="kafka_output_failed"}') == 0
    previous = request(SIM + "/api/state")["active_scenario"]
    for body in ([], {"dashboard": KEY, "scenario": "pa07-row-loss", "target": {"tenant_id": "foreign", "record_type": "ra_summary"}}):
        try:
            request(SIM + "/api/scenario", body)
            raise AssertionError("invalid control was accepted")
        except urllib.error.HTTPError as error:
            assert error.code == 400
        assert request(SIM + "/api/state")["active_scenario"] == previous
    print("PASS: scoped failures, reset-aware rates, and invalid-control containment", flush=True)

    if scrape_drill:
        compose = ["docker", "compose", "-f", str(Path(__file__).with_name("docker-compose.qa.yml"))]
        try:
            subprocess.run([*compose, "stop", "simulator"], check=True)
            wait_for(lambda: number('up{job="sky-topo"}') == 0, "actual scrape failure is reported")
        finally:
            subprocess.run([*compose, "up", "-d", "--wait", "simulator"], check=True)
        wait_for(lambda: number('up{job="sky-topo"}') == 1, "scrape recovers after owned fixture restart")
    print("PASS: local synthetic QA complete; no claim of Druid delivery", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scrape-drill", action="store_true")
    run(parser.parse_args().scrape_drill)
