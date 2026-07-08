#!/usr/bin/env python3
import json
import os
import re
import sys
import yaml
from datetime import datetime, timezone
from urllib.parse import quote

from grafana_mcp_client import GrafanaMcpClient

# Sub-query keys look like "A — User", "B — 4xx only" (single letter, space, dash).
SUBQUERY_KEY = re.compile(r'^[A-Z] [—\-]')

def query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region=None, datasource_uid="prometheus"):
    """
    Query Prometheus via the shared grafana-mcp client (range query).
    Returns {"data": {"resultType": ..., "result": [...]}}.

    Per-query failures fall back to an empty result (preserves prior behaviour);
    a dead endpoint is caught earlier at client handshake in main(), which raises.
    """
    if region:
        promql = promql.replace("$region", region)

    step = 300  # 5-minute resolution
    start_s = start_epoch_ms // 1000
    end_s = end_epoch_ms // 1000

    # Grafana dashboard macro: not valid raw PromQL. Substitute the actual sprint
    # window duration so `increase(metric[$__range])` etc. become valid.
    if "$__range" in promql:
        promql = promql.replace("$__range", f"{end_s - start_s}s")

    try:
        return client.query_prometheus(
            datasource_uid, promql, end_s,
            query_type="range", start_time=start_s, step=step,
        )
    except Exception as e:
        print(f"WARN: query failed for {region or 'aggregated'}: {e}", file=sys.stderr)
        return {"data": {"resultType": "matrix", "result": []}}

def calculate_percentile(values, p):
    """Calculate p-th percentile (0-100)."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = int((p / 100.0) * (len(sorted_vals) - 1))
    return sorted_vals[min(idx, len(sorted_vals) - 1)]

def calculate_mad(values):
    """Calculate median and median absolute deviation."""
    if not values:
        return 0, 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = sorted_vals[n//2] if n % 2 != 0 else (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2.0

    deviations = [abs(x - median) for x in values]
    sorted_devs = sorted(deviations)
    mad = sorted_devs[n//2] if n % 2 != 0 else (sorted_devs[n//2 - 1] + sorted_devs[n//2]) / 2.0

    return median, mad

def calculate_iqr(values):
    """Calculate Q1, Q3, and IQR."""
    if len(values) < 4:
        return 0, 0, 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_vals[q1_idx]
    q3 = sorted_vals[q3_idx]
    return q1, q3, q3 - q1

def detect_deviation_resource(metric_name, values, threshold_pct=95):
    """Resource metrics: flag if P95 exceeds threshold."""
    if not values:
        return False, 0
    p95 = calculate_percentile(values, threshold_pct)
    return p95 > 80, p95  # hardcoded 80% as example threshold

def detect_deviation_spike(values):
    """Rate/spike metrics: flag if max > median + 3*MAD."""
    if not values:
        return False, 0
    peak_val = max(values)
    median, mad = calculate_mad(values)
    threshold = median + (3 * mad)
    return peak_val > threshold, peak_val

def detect_deviation_state(values):
    """State metrics: flag a jump above median + 2*IQR, or sustained zeros (>50%)."""
    if not values:
        return False, 0
    peak_val = max(values)
    q1, q3, iqr = calculate_iqr(values)
    median = sorted(values)[len(values) // 2]
    if iqr > 0 and peak_val > median + (2 * iqr):
        return True, peak_val
    if sum(1 for v in values if v == 0) > len(values) * 0.5:
        return True, 0
    return False, peak_val

def detect_deviation(deviation_rule, values):
    """Dispatch on the metric's declared deviation type.

    Free-text/baseline rules (no RESOURCE/RATE/STATE keyword) are not
    auto-detected — they need a historical baseline we don't have here — so
    they never false-flag; their data is still fetched and their Grafana link
    published.
    """
    if not values:
        return False, 0
    if 'RESOURCE' in deviation_rule:
        return detect_deviation_resource(None, values)
    if 'RATE' in deviation_rule or 'Spike' in deviation_rule:
        return detect_deviation_spike(values)
    if 'STATE' in deviation_rule:
        return detect_deviation_state(values)
    return False, max(values)

def series_label(metric):
    """Human label for a series: prefer instance, then a name-ish label."""
    for key in ('instance', 'name', 'metric', 'xheader', '__name__'):
        if metric.get(key):
            return metric[key]
    return 'aggregated'

def series_points(series):
    """Return [(ts, value), ...] for either a range (values) or instant (value) series."""
    raw = series.get('values')
    if raw is None and series.get('value'):
        raw = [series['value']]
    points = []
    for ts, val in (raw or []):
        try:
            points.append((float(ts), float(val)))
        except (ValueError, TypeError):
            continue
    return points

def format_timestamp(epoch_s):
    """Convert a Prometheus timestamp (Unix epoch seconds) to ISO format."""
    return datetime.fromtimestamp(float(epoch_s), tz=timezone.utc).strftime('%Y-%m-%dT%H:%MZ')

def build_grafana_url(base_url, region, start_ms, end_ms):
    """Build parameterized Grafana URL."""
    return f"{base_url}&var-region={region}&from={start_ms}&to={end_ms}"

def analyze_metric(client, metric_name, config, start_epoch_ms, end_epoch_ms, region):
    """Analyze one metric and return HTML for its deviated series (or None).

    Runs BOTH the direct `promql` field and every A/B/C… sub-query, each under
    the metric's deviation rule. Sub-query results are labelled by their key so
    the reader sees which dimension (e.g. "A — 4xx only") deviated.
    """
    deviation_rule = config.get('deviation', '')
    unit = config.get('unit', '')

    # Build the list of (sub-label, promql) to run.
    queries = []
    main = config.get('promql', '')
    if isinstance(main, str) and main.strip():
        queries.append((None, main))
    for key, val in config.items():
        if isinstance(key, str) and SUBQUERY_KEY.match(key) and isinstance(val, str) and val.strip():
            queries.append((key, val))

    if not queries:
        return None

    groups = []  # (sub_label, [ {instance, peak, timestamp} ])
    for sub_label, promql in queries:
        res = query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region)
        deviated = []
        for series in res.get('data', {}).get('result', []):
            points = series_points(series)
            if not points:
                continue
            values = [v for _, v in points]
            peak_ts, peak_val = max(points, key=lambda p: p[1])
            flagged, _ = detect_deviation(deviation_rule, values)
            if flagged:
                deviated.append({
                    "instance": series_label(series.get('metric', {})),
                    "peak": peak_val,
                    "timestamp": peak_ts,
                })
        if deviated:
            groups.append((sub_label, deviated))

    if not groups:
        return None

    html_output = ""
    for sub_label, deviated in groups:
        title = metric_name if not sub_label else f"{metric_name} — {sub_label}"
        html_output += f"<p><strong>{title} deviation detected</strong></p>\n"
        html_output += f"<p>Reference = {deviated[0]['peak']:.2f} {unit}</p>\n"
        html_output += "<ul>\n"
        for dev in deviated:
            timestamp_str = format_timestamp(dev['timestamp']) if dev['timestamp'] else "N/A"
            html_output += f"  <li>{dev['instance']}: peak {dev['peak']:.2f} {unit} at {timestamp_str}</li>\n"
        html_output += "</ul>\n"

    return html_output

def main():
    if len(sys.argv) < 4:
        print("Usage: grafana_analyzer.py <config_yaml> <start_epoch_ms> <end_epoch_ms> [region]")
        sys.exit(1)

    config_file = sys.argv[1]
    start_epoch_ms = int(sys.argv[2])
    end_epoch_ms = int(sys.argv[3])
    region = sys.argv[4] if len(sys.argv) > 4 else None

    os.makedirs("output", exist_ok=True)

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    all_html = ""
    has_deviation = False

    # One client/session per invocation, reused across all metrics.
    # A dead endpoint raises here (FAIL-FAST) instead of masking as "no deviation".
    client = GrafanaMcpClient()
    try:
        for metric_name, cfg in config.items():
            if cfg.get('status') == 'active':
                result = analyze_metric(client, metric_name, cfg, start_epoch_ms, end_epoch_ms, region)
                if result:
                    all_html += result
                    has_deviation = True
    finally:
        client.close()

    # Build final region block. Section + base link derive from the config
    # (was hardcoded to RTPEngine, which mislabelled XCC runs).
    section = "RTPEngine" if "rtp" in os.path.basename(config_file).lower() else "XCC"
    grafana_base = next(
        (cfg.get('grafana') for cfg in config.values()
         if isinstance(cfg, dict) and cfg.get('status') == 'active' and cfg.get('grafana')),
        "https://grafana-general.svc.talkdeskapp.com",
    )
    grafana_link = build_grafana_url(grafana_base, region, start_epoch_ms, end_epoch_ms) if region else grafana_base

    final_html = f'<p><a href="{grafana_link}">Grafana — {section} {region}</a></p>\n'

    if has_deviation:
        final_html += all_html
    else:
        final_html += "<p>No deviation detected ✅</p>\n"

    print(final_html)

if __name__ == "__main__":
    main()
