#!/usr/bin/env python3
"""Generate the RTP Engine Metrics section: output/section_rtpengine.html.

Usage:
    generate_rtpengine.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> \\
        [region ...] [--out DIR]

Per-region deviation analysis via `grafana_metrics.py analyze` (P95/MAD/IQR +
floor bypass, chart generation) against config/rtp_metrics.yaml. No Host
Details table here — that's XCC-only (generate_xcc.py).

Exit 0 with section_rtpengine.html written on success. Exit 1 on fatal error
(dead Grafana session even after one refresh) — the orchestrator must not
publish.
"""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)

from regions import REGIONS, REGION_TOKENS  # noqa: E402


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
    start_ms, end_ms = epoch_ms(start), epoch_ms(end, end_of_day=True)
    parts = ["<h1>RTP Engine Metrics</h1>"]
    for display, token in REGIONS:
        if region_filter and token not in region_filter:
            parts.append(expand(display,
                "<p><em>Not analysed in this run (region filter active).</em></p>"))
            continue
        print(f"[RTPEngine] {token}...", file=sys.stderr)
        html = run([sys.executable, os.path.join(SCRIPTS, "grafana_metrics.py"), "analyze",
                    os.path.join(SKILL_DIR, "config", "rtp_metrics.yaml"),
                    str(start_ms), str(end_ms), token])
        parts.append(expand(display, html.strip()))
    print("[RTPEngine] done", file=sys.stderr)

    path = os.path.join(outdir, "section_rtpengine.html")
    with open(path, "w") as f:
        f.write("".join(parts))
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
