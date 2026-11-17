"""Finite RA fixtures matching Sky-Topo's observability contract.

Counters integrate the previous rate up to each transition, even between scrapes.
The injected clock makes transitions, reset and age boundaries reproducible.
This models observations only: it does not implement Kafka retry/replay.
"""

import threading
import time

from prometheus_client import CollectorRegistry, generate_latest
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

TENANTS = ("11111111-1111-4111-8111-111111111111", "22222222-2222-4222-8222-222222222222")
TYPES = ("ra_summary", "ra_instance")
PAIRS = (
    ("topic", "unsupported_object_type"), ("dictionary", "lookup_failed"),
    ("decode", "protobuf_invalid"), ("decode", "metadata_invalid"), ("decode", "csv_invalid"),
    ("numeric", "invalid_integer"), ("numeric", "integer_overflow"), ("numeric", "trailing_data"),
    ("numeric", "invalid_float"), ("numeric", "non_finite"),
    ("validation", "missing_required_field"), ("validation", "invalid_field"),
    ("inventory", "node_missing"), ("inventory", "node_lookup_failed"),
    ("inventory", "segment_lookup_failed"), ("inventory", "segment_id_missing"),
    ("serialization", "json_marshal_failed"), ("publish", "kafka_output_failed"),
    ("consume", "kafka_consume_failed"), ("lifecycle", "initialization_failed"),
    ("unexpected", "unknown"),
)
OUTCOMES = ("published", "skipped", "publish_failed")
DISPOSITIONS = ("complete", "row_loss", "source_discard", "empty_source")
STATES = ("initializing", "consuming", "stopped")
FAMILIES = {
    "source_messages_total": ("counter", ()),
    "rows_total": ("counter", ("outcome",)),
    "failures_total": ("counter", ("stage", "reason")),
    "offset_marks_total": ("counter", ("disposition",)),
    "partial_publications_total": ("counter", ()),
    "processor_state": ("gauge", ("state",)),
    "processing_started_timestamp_seconds": ("gauge", ()),
    "last_input_timestamp_seconds": ("gauge", ()),
    "last_output_timestamp_seconds": ("gauge", ()),
}
PREFIX = "sky_topo_ra_"
SCENARIOS = {
    "healthy-active": "Input messages and acknowledged rows, no diagnostic errors",
    "idle": "Healthy event-driven inactivity; old timestamps are not a stall",
    "numeric-quality": "Bad number coerced by existing code, rows still published",
    "source-discard": "Malformed source; source discarded, row count unknown",
    "row-loss": "One row skipped and four published in each source attempt",
    "publish-failed": "Output calls fail; this source is not marked",
    "partial-publication": "Some output acknowledged and some failed: replay risk",
    "stalled": "Current source attempt has been active for more than 60 seconds",
    "initializing": "Blocked before the source-message loop is ready",
    "metrics-missing": "Scrape works, but the new source schema is absent",
    "restart": "Explicit process reset: counters/timestamps start again",
    "recovery": "Input/output resume; historical counters remain",
}
SCENARIOS = {"pa07-" + key: {"description": value, "overrides": {}} for key, value in SCENARIOS.items()}


class RAProfiles:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.scenario = "pa07-healthy-active"
        self.target = (TENANTS[0], TYPES[0])
        self.last_tick = self.changed = clock()
        self.counters = {}
        self.last_input = {}
        self.last_output = {}
        self.registry = CollectorRegistry(auto_describe=False)
        self.registry.register(self)

    def select(self, scenario, target=None):
        if scenario not in SCENARIOS:
            raise ValueError("unknown RA scenario")
        if target is not None:
            if not isinstance(target, dict) or set(target) != {"tenant_id", "record_type"}:
                raise ValueError("target needs tenant_id and record_type")
            selected = (target["tenant_id"], target["record_type"])
            if selected[0] not in TENANTS or selected[1] not in TYPES:
                raise ValueError("unknown RA target")
        else:
            selected = (TENANTS[0], TYPES[0])
        with self.lock:
            now = self.clock()
            self._tick(now)
            self.scenario, self.target, self.changed = scenario, selected, now
            if scenario == "pa07-restart":
                self.counters.clear()
                self.last_input.clear()
                self.last_output.clear()
            if scenario == "pa07-idle":
                self.last_input[selected] = now - 900
                self.last_output[selected] = now - 900
            if scenario == "pa07-stalled":
                key = (selected, "source_messages_total", ())
                self.counters[key] = self.counters.get(key, 0) + 1
                self.last_input[selected] = now - 120

    def _rates(self, source):
        rates = {("source_messages_total", ()): 1,
                 ("rows_total", ("published",)): 5,
                 ("offset_marks_total", ("complete",)): 1}
        if source != self.target:
            return rates
        scenario = self.scenario.removeprefix("pa07-")
        if scenario in {"idle", "initializing", "restart", "metrics-missing", "stalled"}:
            return {}
        if scenario == "numeric-quality":
            rates[("failures_total", ("numeric", "invalid_float"))] = 1
        elif scenario == "source-discard":
            rates = {("source_messages_total", ()): 1,
                     ("failures_total", ("decode", "csv_invalid")): 1,
                     ("offset_marks_total", ("source_discard",)): 1}
        elif scenario == "row-loss":
            rates[("rows_total", ("published",))] = 4
            rates[("rows_total", ("skipped",))] = 1
            rates[("failures_total", ("inventory", "node_missing"))] = 1
            del rates[("offset_marks_total", ("complete",))]
            rates[("offset_marks_total", ("row_loss",))] = 1
        elif scenario in {"publish-failed", "partial-publication"}:
            rates = {("source_messages_total", ()): 1,
                     ("rows_total", ("publish_failed",)): 1,
                     ("failures_total", ("publish", "kafka_output_failed")): 1}
            if scenario == "partial-publication":
                rates[("rows_total", ("published",))] = 4
                rates[("partial_publications_total", ())] = 1
        return rates

    def _tick(self, now):
        elapsed = max(0, now - self.last_tick)
        for tenant in TENANTS:
            for kind in TYPES:
                source = (tenant, kind)
                rates = self._rates(source)
                for (name, labels), rate in rates.items():
                    key = (source, name, labels)
                    self.counters[key] = self.counters.get(key, 0) + rate * elapsed
                if elapsed and rates.get(("source_messages_total", ()), 0):
                    self.last_input[source] = now
                if elapsed and rates.get(("rows_total", ("published",)), 0):
                    self.last_output[source] = now
        self.last_tick = max(self.last_tick, now)

    def collect(self):
        with self.lock:
            now = self.clock()
            self._tick(now)
            for name, (kind, extras) in FAMILIES.items():
                cls = CounterMetricFamily if kind == "counter" else GaugeMetricFamily
                family = cls(PREFIX + name, "Synthetic RA observations; not Kafka or Druid evidence.",
                             labels=["tenant_id", "record_type", *extras])
                for tenant in TENANTS:
                    for record_type in TYPES:
                        source = (tenant, record_type)
                        if source == self.target and self.scenario == "pa07-metrics-missing":
                            continue
                        if kind == "counter":
                            labels = {"rows_total": [(v,) for v in OUTCOMES],
                                      "offset_marks_total": [(v,) for v in DISPOSITIONS],
                                      "failures_total": PAIRS}.get(name, [()])
                            for values in labels:
                                family.add_metric([*source, *values], self.counters.get((source, name, tuple(values)), 0))
                        elif name == "processor_state":
                            state = "initializing" if source == self.target and self.scenario == "pa07-initializing" else "consuming"
                            for value in STATES:
                                family.add_metric([*source, value], int(value == state))
                        else:
                            value = 0
                            if name == "last_input_timestamp_seconds":
                                value = self.last_input.get(source, 0)
                            elif name == "last_output_timestamp_seconds":
                                value = self.last_output.get(source, 0)
                            elif source == self.target and self.scenario == "pa07-stalled":
                                value = self.changed - 120
                            family.add_metric(list(source), value)
                yield family

    def render(self):
        return generate_latest(self.registry).decode()
