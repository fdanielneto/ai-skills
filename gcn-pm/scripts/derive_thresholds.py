#!/usr/bin/env python3
"""Scan .baseline_cache/ JSON files, compute per-region p99.9/max per (metric, series),
and emit the region_floor entries ready to paste into xcc_metrics.yaml / rtp_metrics.yaml.

Usage:
    python3 scripts/derive_thresholds.py          # print all
    python3 scripts/derive_thresholds.py xcc      # xcc only
    python3 scripts/derive_thresholds.py rtpengine  # rtpengine only
"""
import json
import os
import sys
import statistics

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(SKILL_DIR, ".baseline_cache")

REGION_TOKENS = {
    "eu-south-1", "eu-west-3", "us-east-1", "us-west-2",
    "ap-southeast-1", "ap-southeast-2", "sa-east-1", "ca-central-1",
}


def parse_cache_filename(name):
    stem = name.rsplit(".json", 1)[0]
    parts = stem.split("_")
    for i, p in enumerate(parts):
        if p in REGION_TOKENS:
            region = p
            section = parts[0]
            metric_slug = "_".join(parts[1:i])
            sub_label = "_".join(parts[i + 1:]) if i + 1 < len(parts) else ""
            return section, metric_slug, region, sub_label
    return None


def percentile(sorted_vals, p):
    if not sorted_vals:
        return 0
    k = (len(sorted_vals) - 1) * p / 100.0
    f = int(k)
    c = f + 1
    if c >= len(sorted_vals):
        return sorted_vals[-1]
    return sorted_vals[f] + (k - f) * (sorted_vals[c] - sorted_vals[f])


def round_val(v):
    if isinstance(v, float):
        if v == int(v):
            return int(v)
        return round(v, 4)
    return v


def main():
    filter_section = None
    if len(sys.argv) > 1:
        arg = sys.argv[1].lower()
        if arg in ("xcc", "rtpengine"):
            filter_section = arg

    records = []
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        parsed = parse_cache_filename(fname)
        if parsed is None:
            continue
        section, metric_slug, region, sub_label = parsed

        if filter_section and section != filter_section:
            continue

        path = os.path.join(CACHE_DIR, fname)
        try:
            with open(path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        values = []
        for series_key, pts in data.get("series", {}).items():
            for ts, val in pts:
                try:
                    v = float(val)
                    values.append(v)
                except (TypeError, ValueError):
                    pass

        if not values:
            continue

        values.sort()
        p999 = percentile(values, 99.9)
        p99 = percentile(values, 99)
        max_v = values[-1]
        avg = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0
        p50 = percentile(values, 50)

        records.append({
            "section": section,
            "metric_slug": metric_slug,
            "sub_label": sub_label,
            "region": region,
            "p999": p999,
            "p99": p99,
            "max": max_v,
            "avg": avg,
            "std": std,
            "p50": p50,
            "count": len(values),
        })

    # Group by (metric_slug, sub_label) → {region: p999/max}
    groups = {}
    for r in records:
        key = (r["section"], r["metric_slug"], r["sub_label"])
        groups.setdefault(key, []).append(r)

    print(f"# Derived thresholds from {len(records)} cache files\n")

    for key in sorted(groups):
        section, metric_slug, sub_label = key
        entries = groups[key]
        regions_data = {e["region"]: e for e in entries}

        metric_name = metric_slug.replace("_", " ").title()

        print(f"# {section}/{metric_slug} — sub_label={sub_label!r} ({len(entries)} regions)")
        print(f"# metric name guess: {metric_name}")
        print(f"#   {'Region':<20} {'p99.9':<12} {'p99':<12} {'max':<12} {'avg':<12} {'p50':<12} {'pts':<8}")
        print(f"#   {'-'*20} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*12} {'-'*8}")

        global_max = 0
        global_p999 = 0
        for e in entries:
            global_max = max(global_max, e["max"])
            global_p999 = max(global_p999, e["p999"])
            print(f"#   {e['region']:<20} {e['p999']:<12} {e['p99']:<12} {e['max']:<12} {e['avg']:<12.4f} {e['p50']:<12.4f} {e['count']:<8}")

        # Suggest: region_floor if regional variance > 20%
        if global_max > 0 and entries:
            avg_p999 = statistics.mean([e["p999"] for e in entries]) if len(entries) > 1 else entries[0]["p999"]
            if avg_p999 > 0:
                max_dev = max(abs(e["p999"] - avg_p999) for e in entries) / avg_p999
            else:
                max_dev = 0

            if max_dev > 0.20 and len([e for e in entries if e["p999"] > 0]) > 1:
                print(f"#   ▶ Recommended region_floor (p99.9-based, variance={max_dev:.0%}):")
                for e in sorted(entries, key=lambda x: x["region"]):
                    threshold = round_val(e["p999"] * 1.5)
                    print(f"#     {e['region']}: {{value: {threshold}, op: \">\"}}")
            else:
                print(f"#   ▶ Global threshold sufficient (variance={max_dev:.0%})")

        print()


if __name__ == "__main__":
    main()
