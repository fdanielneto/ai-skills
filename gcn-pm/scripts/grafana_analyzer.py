#!/usr/bin/env python3
import json
import os
import sys
import yaml
from datetime import datetime, timezone
from urllib.parse import quote

from grafana_mcp_client import GrafanaMcpClient

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

def format_timestamp(epoch_s):
    """Convert a Prometheus timestamp (Unix epoch seconds) to ISO format."""
    return datetime.fromtimestamp(float(epoch_s), tz=timezone.utc).strftime('%Y-%m-%dT%H:%MZ')

def build_grafana_url(base_url, region, start_ms, end_ms):
    """Build parameterized Grafana URL."""
    return f"{base_url}&var-region={region}&from={start_ms}&to={end_ms}"

def analyze_metric(client, metric_name, config, start_epoch_ms, end_epoch_ms, region):
    """Analyze a single metric and return HTML output if deviated."""

    # Extract promql: either direct 'promql' field or from sub-fields (A, B, C, etc.)
    promql = config.get('promql', '')
    sub_queries = {}
    for key, val in config.items():
        if key.startswith(('A ', 'B ', 'C ', 'D ', 'E ')) and isinstance(val, str) and val:
            sub_queries[key] = val

    if not promql and not sub_queries:
        return None

    # Fetch data
    all_deviated = []

    if promql:
        res = query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region)
        data = res.get('data', {}).get('result', [])

        for series in data:
            instance = series.get('metric', {}).get('instance', 'aggregated')
            values = [float(v[1]) for v in series.get('values', []) if v[1]]
            if not values:
                continue

            peak_val = max(values)
            peak_time_idx = values.index(peak_val)
            peak_timestamp = series.get('values', [[0, 0]])[peak_time_idx][0] if series.get('values') else 0

            # Check deviation based on metric type
            deviated = False
            if 'RESOURCE' in config.get('deviation', ''):
                deviated, _ = detect_deviation_resource(metric_name, values)
            elif 'RATE' in config.get('deviation', '') or 'Spike' in config.get('deviation', ''):
                deviated, _ = detect_deviation_spike(values)

            if deviated:
                all_deviated.append({
                    "instance": instance,
                    "peak": peak_val,
                    "timestamp": peak_timestamp,
                    "label": "main"
                })

    # If no deviation found, return None
    if not all_deviated:
        return None

    # Build output HTML for this metric
    unit = config.get('unit', '')
    grafana_url = config.get('grafana', '')
    grafana_link = build_grafana_url(grafana_url, region, start_epoch_ms, end_epoch_ms) if grafana_url else grafana_url

    html_output = ""
    html_output += f"<p><strong>{metric_name} deviation detected</strong></p>\n"
    html_output += f"<p>Reference = {all_deviated[0]['peak']:.2f} {unit}</p>\n"
    html_output += "<ul>\n"

    for dev in all_deviated:
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

    # Build final region block
    grafana_base = "https://grafana-general.svc.talkdeskapp.com/goto/dfolpmd59gp34d?orgId=1"
    grafana_link = build_grafana_url(grafana_base, region, start_epoch_ms, end_epoch_ms) if region else grafana_base

    final_html = f'<p><a href="{grafana_link}">Grafana — RTPEngine {region}</a></p>\n'

    if has_deviation:
        final_html += all_html
    else:
        final_html += "<p>No deviation detected ✅</p>\n"

    print(final_html)

if __name__ == "__main__":
    main()
