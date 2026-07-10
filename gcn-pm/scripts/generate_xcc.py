#!/usr/bin/env python3
"""Generate the XCC Metrics (Kamailio) section: output/section_xcc.html.

Usage:
    generate_xcc.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> \\
        [region ...] [--out DIR]

Two data sources, both plain HTTP (no browser except for `refresh`):
1. Per-region deviation analysis via `grafana_metrics.py analyze` (P95/MAD/IQR
   + floor bypass, chart generation) — same as the RTP Engine section.
2. Host Details table: a single instant PromQL query
   (`GrafanaHttpClient.query_prometheus(..., query_type="instant")`) listing
   version/instance-type per region, plus a sprint-start vs sprint-end delta
   check that adds one-line "rolling replacement" notes after the table.

Exit 0 with section_xcc.html written on success. Exit 1 on fatal error (dead
Grafana session even after one refresh) — the orchestrator must not publish.
"""
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)

from regions import REGIONS, REGION_TOKENS  # noqa: E402
from grafana_metrics import GrafanaHttpClient  # noqa: E402

HOST_DETAILS_EXPR = 'count by (region, version, instance_type) (custom_metrics{role="edgerouter"})'


def run(cmd, timeout=120):
    """Run a subprocess from the skill root; on Grafana 401 refresh once and retry."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1, cwd=SKILL_DIR,
                         env={**os.environ, "PYTHONUNBUFFERED": "1"})
    stderr_lines = []
    for line in p.stderr:
        stderr_lines.append(line)
        print(line, end='', file=sys.stderr)
    try:
        stdout, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        sys.exit(f"ERROR: {' '.join(cmd)} timed out after {timeout}s")
    if p.poll() != 0:
        stderr = ''.join(stderr_lines)
        if "401" in stderr and any("grafana_metrics.py" in part for part in cmd):
            print("Grafana session expired, refreshing...", file=sys.stderr)
            ret = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "grafana_metrics.py"), "refresh"],
                cwd=SKILL_DIR, text=True, timeout=240)
            if ret.returncode != 0:
                sys.exit("ERROR: Grafana session refresh failed.")
            print("Grafana session refreshed, retrying...", file=sys.stderr)
            return run(cmd, timeout=timeout)
        sys.exit(f"ERROR: {' '.join(cmd)} failed:\n{stderr[-2000:]}")
    return stdout


def epoch_ms(d, end_of_day=False):
    t = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        t += timedelta(days=1) - timedelta(milliseconds=1)
    return int(t.timestamp() * 1000)


def expand(title, body):
    return ('<ac:structured-macro ac:name="expand" ac:schema-version="1">'
            f'<ac:parameter ac:name="title">{title}</ac:parameter>'
            f'<ac:rich-text-body>{body}</ac:rich-text-body></ac:structured-macro>')


def _host_details_client():
    """One GrafanaHttpClient, refreshing the session once on a dead/expired cookie.

    GrafanaHttpClient() raises RuntimeError for an SSO/login-page response and
    a plain Exception for an HTTP error (e.g. 401) from the proxy — both mean
    the session needs a refresh, so both are caught here.
    """
    try:
        return GrafanaHttpClient()
    except Exception:
        print("Grafana session expired, refreshing...", file=sys.stderr)
        ret = subprocess.run(
            [sys.executable, os.path.join(SCRIPTS, "grafana_metrics.py"), "refresh"],
            cwd=SKILL_DIR, text=True, timeout=240)
        if ret.returncode != 0:
            return None
        try:
            return GrafanaHttpClient()
        except Exception:
            return None


def _instant_snapshot(client, time_s):
    """{region: (version, instance_type)} at a given instant, or {} on query failure."""
    try:
        res = client.query_prometheus("prometheus", HOST_DETAILS_EXPR, time_s, query_type="instant")
    except Exception as e:
        print(f"WARN: Host Details instant query failed: {e}", file=sys.stderr)
        return {}
    rows = {}
    for series in res.get("data", {}).get("result", []):
        m = series.get("metric", {})
        region = m.get("region")
        if region:
            rows[region] = (m.get("version", "?"), m.get("instance_type", "?"))
    return rows


def host_details_block(start_ms, end_ms):
    """XCC - Host Details expand block: current snapshot table + sprint delta notes.

    ponytail: per-region analysis below still iterates the static REGIONS list
    (regions.py), not this query's live region set — xcc-metrics.md calls for
    driving the per-region loop off the live discovery too, but that's a
    larger behavioral change to proven code, out of scope here. Revisit if a
    new edgerouter region shows up and the per-region loop needs to follow.
    """
    client = _host_details_client()
    if client is None:
        return expand("XCC - Host Details",
                       '<ac:structured-macro ac:name="warning" ac:schema-version="1">'
                       '<ac:rich-text-body><p><em>Grafana was unavailable for the Host '
                       'Details query.</em></p></ac:rich-text-body></ac:structured-macro>')

    now_s = int(time.time())
    current = _instant_snapshot(client, now_s)
    if not current:
        return expand("XCC - Host Details",
                       '<ac:structured-macro ac:name="warning" ac:schema-version="1">'
                       '<ac:rich-text-body><p><em>Grafana was unavailable for the Host '
                       'Details query.</em></p></ac:rich-text-body></ac:structured-macro>')

    rows = ["<table><tbody>", "<tr><th>XCC</th><th>Version</th><th>Instance Type</th></tr>"]
    for region in sorted(current):
        version, itype = current[region]
        rows.append(f"<tr><td>{region}</td><td>{version}</td><td>{itype}</td></tr>")
    rows.append("</tbody></table>")

    notes = []
    start_snap = _instant_snapshot(client, start_ms // 1000)
    end_snap = _instant_snapshot(client, end_ms // 1000)
    if start_snap and end_snap:
        for region in sorted(set(start_snap) & set(end_snap)):
            old, new = start_snap[region], end_snap[region]
            if old != new:
                notes.append(f"<p>Note: {region} had a rolling instance replacement "
                             f"during the sprint (({old[1]}, {old[0]}) → "
                             f"({new[1]}, {new[0]}))</p>")
    # else: delta check unavailable — table above still stands (per xcc-metrics.md).

    return expand("XCC - Host Details", "".join(rows) + "".join(notes))


def per_region_blocks(config_yaml, start, end, region_filter):
    start_ms, end_ms = epoch_ms(start), epoch_ms(end, end_of_day=True)
    parts = []
    for display, token in REGIONS:
        if region_filter and token not in region_filter:
            parts.append(expand(display,
                "<p><em>Not analysed in this run (region filter active).</em></p>"))
            continue
        print(f"[XCC] {token}...", file=sys.stderr)
        html = run([sys.executable, os.path.join(SCRIPTS, "grafana_metrics.py"), "analyze",
                    os.path.join(SKILL_DIR, "config", config_yaml),
                    str(start_ms), str(end_ms), token])
        parts.append(expand(display, html.strip()))
    print("[XCC] done", file=sys.stderr)
    return "".join(parts), start_ms, end_ms


def main():
    argv = list(sys.argv[1:])
    outdir = os.path.join(SKILL_DIR, "output")
    if "--out" in argv:
        i = argv.index("--out")
        outdir = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]
    if len(argv) < 2:
        sys.exit(__doc__)
    start, end = argv[0], argv[1]
    for d in (start, end):
        datetime.strptime(d, "%Y-%m-%d")
    region_filter = {t.lower().replace("_", "-") for t in argv[2:]}
    unknown = region_filter - REGION_TOKENS
    if unknown:
        sys.exit(f"Unknown region token(s): {sorted(unknown)}\nValid: {sorted(REGION_TOKENS)}")

    os.makedirs(outdir, exist_ok=True)
    region_html, start_ms, end_ms = per_region_blocks("xcc_metrics.yaml", start, end, region_filter)
    host_details = host_details_block(start_ms, end_ms)

    html = "<h1>XCC Metrics (Kamailio)</h1>" + host_details + region_html
    path = os.path.join(outdir, "section_xcc.html")
    with open(path, "w") as f:
        f.write(html)
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
