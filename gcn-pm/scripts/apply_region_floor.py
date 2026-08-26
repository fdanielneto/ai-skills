#!/usr/bin/env python3
"""Read xcc_metrics.yaml / rtp_metrics.yaml and the .baseline_cache/ data,
then regenerate the YAML files with region_floor entries for every
SPIKE/RESOURCE metric that has multi-region baseline data.

Ceiling-relative config is preserved verbatim: the metric-level 'ceiling'
field (manual scalar with optional region override, or a panel series) and
per-series 'series_floor' entries carrying 'of'/'ceiling' are re-emitted
unchanged — auto-injection of region_floor is skipped for these because the
auto-generated values are absolute thresholds, not percentage overrides.

Usage:
    python3 scripts/apply_region_floor.py          # preview changes to stdout
    python3 scripts/apply_region_floor.py --write  # apply changes to files
"""
import json
import os
import re
import sys
import yaml

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
CACHE_DIR = os.path.join(SKILL_DIR, ".baseline_cache")
CONFIG_DIR = os.path.join(SKILL_DIR, "config")

REGION_TOKENS = {
    "eu-south-1", "eu-west-3", "us-east-1", "us-west-2",
    "ap-southeast-1", "ap-southeast-2", "sa-east-1", "ca-central-1",
}

SUBQUERY_KEY = re.compile(r'^[A-Z]+\s*(?:[—–-]\s*)?')


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def normalize_series_key(sub_label):
    if not sub_label:
        return ''
    return slugify(SUBQUERY_KEY.sub('', sub_label))


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


def cache_sub_label_to_yaml_key(sub_label):
    """Convert cache sub_label like 'a_total_error_rate' to series_floor key like 'total_error_rate'.
    Strips the letter prefix (first _-separated component) and optionally 'instance_'."""
    parts = sub_label.split("_", 1)
    if len(parts) < 2:
        return sub_label
    rest = parts[1]
    # Some sub-labels have 'instance_' prefix that gets stripped
    if rest.startswith("instance_"):
        rest = rest[9:]
    return rest


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
        if abs(v) < 0.0001:
            return 0
        if v == int(v):
            return int(v)
        # Round to 4 significant digits or 4 decimal places
        if abs(v) >= 10:
            return round(v, 1)
        elif abs(v) >= 1:
            return round(v, 2)
        elif abs(v) >= 0.01:
            return round(v, 4)
        else:
            return round(v, 6)
    return v


def load_cache_data(section_filter=None):
    """Load ALL cache files and group by (metric_slug, yaml_key, region)."""
    groups = {}
    for fname in os.listdir(CACHE_DIR):
        if not fname.endswith(".json"):
            continue
        parsed = parse_cache_filename(fname)
        if parsed is None:
            continue
        section, metric_slug, region, sub_label = parsed
        if section_filter and section != section_filter:
            continue
        if not sub_label:
            continue  # skip metrics without sub-labels (single expr)

        yaml_key = cache_sub_label_to_yaml_key(sub_label)

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
        gk = (section, metric_slug, yaml_key)
        groups.setdefault(gk, {})[region] = {
            "p999": percentile(values, 99.9),
            "max": values[-1],
            "p99": percentile(values, 99),
            "count": len(values),
        }
    return groups


def build_region_floor(regions_data, op=">"):
    """Build region_floor map for regions where p99.9 differs significantly (>20%)
    from the global average. Uses p99.9 * 1.5 as the threshold."""
    if len(regions_data) < 2:
        return None

    values = [v["p999"] for v in regions_data.values()]
    max_v = max(values)
    if max_v == 0:
        return None

    avg = sum(values) / len(values)

    region_floor = {}
    for region, data in sorted(regions_data.items()):
        if data["p999"] == 0:
            continue
        dev = abs(data["p999"] - avg) / max(avg, 0.001)
        if dev > 0.20:
            threshold = round_val(data["p999"] * 1.5)
            region_floor[region] = {"value": threshold, "op": op}

    return region_floor if region_floor else None


def rebuild_yaml(config_path, section, cache_groups):
    """Rebuild the YAML with region_floor entries."""
    with open(config_path) as f:
        config = yaml.safe_load(f)

    defaults = config.get("defaults", {})
    out = ["defaults:"]
    for k, v in defaults.items():
        out.append(f"  {k}: {v}")
    out.append("")

    for metric_name, metric_cfg in config.items():
        if metric_name == "defaults":
            continue

        metric_slug = slugify(metric_name)
        series_floor = metric_cfg.get("series_floor")

        out.append(f"{metric_name}:")

        # Non-series_floor fields
        for key in ("status", "deviation", "data_view", "panel_id", "dashboard",
                     "floor_value", "floor_op", "deviation_threshold", "description",
                     "expr", "baseline_weeks", "band_k", "render"):
            if key in metric_cfg:
                val = metric_cfg[key]
                if isinstance(val, str):
                    out.append(f"  {key}: {val}")
                elif isinstance(val, dict):
                    out.append(f"  {key}:")
                    for sk, sv in val.items():
                        out.append(f"    {sk}: {sv}")
                else:
                    out.append(f"  {key}: {val}")

        # ceiling: manual scalar capacity (optionally region-overridden) or a
        # panel series, used as the RESOURCE deviation denominator. Emitted here
        # rather than via the generic dict handler above, which only renders one
        # level deep and would mangle a nested region_floor.
        ceiling = metric_cfg.get("ceiling")
        if ceiling:
            if "series" in ceiling:
                out.append(f"  ceiling: {{series: {ceiling['series']}}}")
            elif "value" in ceiling:
                rf = ceiling.get("region_floor")
                if rf:
                    out.append("  ceiling:")
                    out.append(f"    value: {ceiling['value']}")
                    out.append("    region_floor:")
                    for rgn, rv in rf.items():
                        out.append(f"      {rgn}: {{value: {rv['value']}}}")
                else:
                    out.append(f"  ceiling: {{value: {ceiling['value']}}}")

        # series_floor with region_floor
        if series_floor:
            out.append("  series_floor:")
            for s_key, s_val in series_floor.items():
                if s_val is None:
                    out.append(f"    {s_key}: null")
                    continue

                # Ceiling-relative entry ({value, unit?, op, of|ceiling}): preserve
                # verbatim. A manually-written region_floor inside a ceiling-relative
                # entry is a percentage override, not an absolute threshold, so
                # auto-injection below would generate the wrong kind of value.
                if isinstance(s_val, dict) and ("of" in s_val or "ceiling" in s_val):
                    v = s_val.get("value")
                    o = s_val.get("op", ">")
                    ceiling_key = s_val.get("ceiling") or s_val["of"]
                    key_name = "ceiling" if "ceiling" in s_val else "of"
                    parts = [f"value: {v}"]
                    unit = s_val.get("unit")
                    if unit:
                        parts.append(f"unit: {unit!r}")
                    parts.append(f"op: {o!r}")
                    parts.append(f"{key_name}: {ceiling_key}")
                    rf = s_val.get("region_floor")
                    if rf:
                        rf_parts = []
                        for rgn, rv in rf.items():
                            rv_parts = [f"value: {rv['value']}"]
                            if "op" in rv:
                                rv_parts.append(f"op: {rv['op']!r}")
                            rf_parts.append(f"{rgn}: {{{', '.join(rv_parts)}}}")
                        parts.append(f"region_floor: {{{', '.join(rf_parts)}}}")
                    out.append(f"    {s_key}: {{{', '.join(parts)}}}")
                    continue

                # Check if we have cache data for this YAML key
                cache_key = (section, metric_slug, s_key)
                regions_data = cache_groups.get(cache_key, {})

                # Determine the op
                if isinstance(s_val, dict):
                    base_value = s_val.get("value")
                    base_op = s_val.get("op", ">")
                else:
                    base_value = s_val
                    base_op = ">"

                # Build region_floor if multi-region data exists
                rf = build_region_floor(regions_data, base_op) if regions_data else None

                if rf:
                    # Write block format
                    out.append(f"    {s_key}:")
                    out.append(f"      value: {base_value}")
                    out.append(f"      op: {base_op!r}")
                    out.append(f"      region_floor:")
                    for rgn, rv in rf.items():
                        out.append(f"        {rgn}: {{value: {rv['value']}, op: {rv['op']!r}}}")
                else:
                    # Keep compact format
                    if isinstance(s_val, dict) and "value" in s_val:
                        v = s_val.get("value")
                        o = s_val.get("op", ">")
                        out.append(f"    {s_key}: {{value: {v}, op: {o!r}}}")
                    else:
                        out.append(f"    {s_key}: {s_val}")

        out.append("")

    return "\n".join(out)


def main():
    write = "--write" in sys.argv

    for section, config_file in [("xcc", "xcc_metrics.yaml"), ("rtpengine", "rtp_metrics.yaml")]:
        config_path = os.path.join(CONFIG_DIR, config_file)
        cache_groups = load_cache_data(section)

        new_yaml = rebuild_yaml(config_path, section, cache_groups)

        if write:
            backup = config_path + ".bak"
            with open(config_path) as f:
                original = f.read()
            with open(backup, "w") as f:
                f.write(original)
            with open(config_path, "w") as f:
                f.write(new_yaml)
            print(f"Written {config_path} (backup at {backup})", file=sys.stderr)
        else:
            print(f"# === {config_file} ===")
            print(new_yaml)

    # Print summary
    print("\n# === METRICS WITH REGION_FLOOR ADDED ===", file=sys.stderr)
    for section, config_file in [("xcc", "xcc_metrics.yaml"), ("rtpengine", "rtp_metrics.yaml")]:
        config_path = os.path.join(CONFIG_DIR, config_file)
        cache_groups = load_cache_data(section)
        for (sec, ms, yk), regions in sorted(cache_groups.items()):
            rf = build_region_floor(regions)
            if rf:
                print(f"  {sec}/{ms}/{yk}: {len(regions)} regions → region_floor for {list(rf.keys())}", file=sys.stderr)


if __name__ == "__main__":
    main()
