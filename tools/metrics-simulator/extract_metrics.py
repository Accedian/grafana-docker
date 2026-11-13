#!/usr/bin/env python3
"""Extract Prometheus metric names from Grafana dashboard JSON files.

Parses all `expr` fields in dashboard panels, extracts metric names using
PromQL lexical rules, and produces a JSON catalog suitable for the simulator.

Usage:
    python extract_metrics.py [dashboard.json ...] [-o catalog.json]

If no files are given, scans all JSON files under dashboards/.
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Resolve repo root: walk up from this file until we find a dashboards/ dir.
# Works both from within the repo (tools/metrics-simulator/) and inside a
# container where scripts and dashboards are mounted under /app/.
_here = Path(__file__).resolve().parent
ROOT = _here
for _ancestor in (_here, *_here.parents):
    if (_ancestor / "dashboards").is_dir():
        ROOT = _ancestor
        break

# PromQL function names that should NOT be treated as metric names.
PROMQL_FUNCTIONS = {
    "abs", "absent", "absent_over_time", "avg", "avg_over_time", "bottomk",
    "ceil", "changes", "clamp", "clamp_max", "clamp_min", "count",
    "count_over_time", "count_values", "day_of_month", "day_of_week",
    "days_in_month", "delta", "deriv", "exp", "floor", "group",
    "histogram_quantile", "holt_winters", "hour", "idelta", "increase",
    "irate", "label_join", "label_replace", "label_values", "last_over_time",
    "ln", "log10", "log2", "max", "max_over_time", "min", "min_over_time",
    "minute", "month", "pi", "predict_linear", "present_over_time",
    "quantile", "quantile_over_time", "rate", "resets", "round", "scalar",
    "sgn", "sort", "sort_desc", "sqrt", "stddev", "stddev_over_time",
    "stdvar", "stdvar_over_time", "sum", "sum_over_time", "time",
    "timestamp", "topk", "vector", "year",
    # aggregation modifiers / keywords
    "by", "without", "on", "ignoring", "group_left", "group_right",
    "bool", "offset", "or", "and", "unless",
}

# Metric name regex: alphanumeric + underscore + colon, starting with letter/underscore.
METRIC_RE = re.compile(r'\b([a-zA-Z_:][a-zA-Z0-9_:]*)\b')

# Labels found alongside the metric in the original expr (for context).
LABEL_RE = re.compile(r'\{([^}]*)\}')
LABEL_KV_RE = re.compile(r'(\w+)\s*[=~!]+\s*"([^"]*)"')


def walk_panels(panels):
    """Recursively yield every panel (including row children)."""
    for panel in panels:
        yield panel
        yield from walk_panels(panel.get("panels", []))


def extract_from_expr(expr):
    """Return set of (metric_name, frozenset_of_label_names) from a PromQL expr."""
    results = set()
    # Find all metric{label} pairs
    for match in re.finditer(r'([a-zA-Z_:][a-zA-Z0-9_:]*)\s*\{', expr):
        name = match.group(1)
        if name.lower() in PROMQL_FUNCTIONS:
            continue
        # Extract label names from the following {...}
        rest = expr[match.end() - 1:]
        brace = LABEL_RE.match(rest)
        labels = set()
        if brace:
            for lm in LABEL_KV_RE.finditer(brace.group(1)):
                labels.add(lm.group(1))
        results.add((name, frozenset(labels)))

    # Also catch bare metric names (no braces) — e.g. `node_processor_available_agents`
    # but only if they look like real metric names (contain underscore, not just a word)
    for match in METRIC_RE.finditer(expr):
        name = match.group(1)
        if name.lower() in PROMQL_FUNCTIONS:
            continue
        if name.startswith("$") or name.startswith("__"):
            continue
        if re.match(r'^[0-9]+$', name):
            continue
        if name in {"NaN", "Inf", "inf", "nan", "true", "false"}:
            continue
        # Must contain at least one underscore to look like a real metric name;
        # bare words like "ACTIVE", "tenant", "state" are label values/names.
        if "_" not in name:
            continue
        # Skip if this word appears as a label value in the expression
        # (inside quotes after = or =~)
        if re.search(rf'[=~]+"[^"]*\b{re.escape(name)}\b[^"]*"', expr):
            continue
        results.add((name, frozenset()))

    return results


def guess_type(name):
    """Heuristic: counter if name ends with _total or _count, gauge otherwise."""
    if name.endswith("_total") or name.endswith("_count"):
        return "counter"
    if "count" in name.lower() and "Count" in name:
        # RA agent health metrics are collect-and-reset gauges
        return "gauge"
    return "gauge"


def extract_from_dashboard(dashboard_path):
    """Parse a dashboard JSON and return a dict of metric definitions."""
    with open(dashboard_path) as f:
        dashboard = json.load(f)

    metrics = {}
    for panel in walk_panels(dashboard.get("panels", [])):
        for tgt in panel.get("targets", []):
            expr = tgt.get("expr", "")
            for name, labels in extract_from_expr(expr):
                if name not in metrics:
                    metrics[name] = {
                        "name": name,
                        "type": guess_type(name),
                        "labels": sorted(labels),
                        "dashboards": [],
                    }
                else:
                    existing = set(metrics[name]["labels"])
                    existing.update(labels)
                    metrics[name]["labels"] = sorted(existing)
                src = dashboard_path.name
                if src not in metrics[name]["dashboards"]:
                    metrics[name]["dashboards"].append(src)

    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path, help="Dashboard JSON files")
    parser.add_argument("-o", "--output", type=Path, help="Output catalog JSON")
    parser.add_argument("--print", dest="print_names", action="store_true",
                        help="Print metric names to stdout")
    args = parser.parse_args()

    files = args.files
    if not files:
        files = sorted(ROOT.joinpath("dashboards").rglob("*.json"))

    all_metrics = {}
    for path in files:
        metrics = extract_from_dashboard(path)
        for name, definition in metrics.items():
            if name in all_metrics:
                existing = set(all_metrics[name]["labels"])
                existing.update(definition["labels"])
                all_metrics[name]["labels"] = sorted(existing)
                for d in definition["dashboards"]:
                    if d not in all_metrics[name]["dashboards"]:
                        all_metrics[name]["dashboards"].append(d)
            else:
                all_metrics[name] = definition

    catalog = {"metrics": sorted(all_metrics.values(), key=lambda m: m["name"])}

    if args.print_names:
        for m in catalog["metrics"]:
            print(f"{m['type']:8s} {m['name']}")
        print(f"\n{len(catalog['metrics'])} metrics extracted from {len(files)} dashboard(s)")

    if args.output:
        args.output.write_text(json.dumps(catalog, indent=2) + "\n")
        print(f"Wrote {len(catalog['metrics'])} metrics to {args.output}", file=sys.stderr)
    elif not args.print_names:
        json.dump(catalog, sys.stdout, indent=2)
        print()


if __name__ == "__main__":
    main()
