#!/usr/bin/env python3
"""Generate the SBC Metrics section (Executive Summary + Detailed data):
output/section_sbc.html.

Usage:
    generate_sbc.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> [--out DIR]

Fetches Kibana CDR data via `kibana_metrics.py fetch`/`analyze` (plain HTTP)
for a1-a3 (executive summary), b1 (region table) and b2 (per-SBC timeline
chart, one per ribbon/sub-region).

Exit 0 with section_sbc.html written on success. Exit 1 on fatal error (dead
Kibana session, missing fetch output) — the orchestrator must not publish.
"""
import json
import os
import subprocess
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)

from regions import RIBBON_SBCS  # noqa: E402


def run(cmd, timeout=120):
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
        if any("kibana_metrics.py" in part for part in cmd) and ("401" in stderr or "session expired" in stderr):
            print("Kibana session expired, refreshing...", file=sys.stderr)
            ret = subprocess.run(
                [sys.executable, os.path.join(SCRIPTS, "kibana_metrics.py"), "refresh"],
                cwd=SKILL_DIR, text=True, timeout=240)
            if ret.returncode != 0:
                sys.exit("ERROR: Kibana session refresh failed.")
            print("Kibana session refreshed, retrying...", file=sys.stderr)
            return run(cmd, timeout=timeout)
        sys.exit(f"ERROR: {' '.join(cmd)} failed:\n{stderr[-2000:]}")
    return stdout


def expand(title, body):
    return ('<ac:structured-macro ac:name="expand" ac:schema-version="1">'
            f'<ac:parameter ac:name="title">{title}</ac:parameter>'
            f'<ac:rich-text-body>{body}</ac:rich-text-body></ac:structured-macro>')


def md_to_html(md):
    """Convert kibana_metrics.py analyze's markdown output (### headings + 2-col tables) to storage HTML."""
    out, rows = [], []

    def flush():
        if not rows:
            return
        html = ["<table><tbody>"]
        html.append("<tr>" + "".join(f"<th>{c}</th>" for c in rows[0]) + "</tr>")
        for r in rows[1:]:
            html.append("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>")
        html.append("</tbody></table>")
        out.append("".join(html))
        rows.clear()

    for line in md.splitlines():
        line = line.strip()
        if line.startswith("### "):
            flush()
            out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if not all(set(c) <= set("-: ") for c in cells):  # skip separator row
                rows.append(cells)
        else:
            flush()
    flush()
    return "".join(out)


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

    os.makedirs(outdir, exist_ok=True)

    print("  sbc-metrics: fetching Kibana data (plain HTTP)...")
    run([sys.executable, os.path.join(SCRIPTS, "kibana_metrics.py"), "fetch", start, end, "all"])

    with open(os.path.join(SKILL_DIR, "tmp", "sbc_a1a3.json")) as f:
        total = json.load(f)["hits"]["total"]
        total = total["value"] if isinstance(total, dict) else total

    a1a3_md = run([sys.executable, os.path.join(SCRIPTS, "kibana_metrics.py"), "analyze",
                   "a1-a3", "tmp/sbc_a1a3.json"])
    b1_html = run([sys.executable, os.path.join(SCRIPTS, "kibana_metrics.py"), "analyze",
                   "b1", "tmp/sbc_b1.json"])

    dash = ("https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/"
            "97c532ef-3354-4392-a153-141a02816e90?_g=(filters:!(),refreshInterval:"
            f"(pause:!t,value:0),time:(from:'{start}T00:00:00.000Z',to:'{end}T23:59:59.000Z'))")
    parts = [
        f'<h1><a href="{dash}">Executive Summary</a></h1>',
        f"<p>Total: {total:,} completed calls.</p>",
        md_to_html(a1a3_md),
        "<h1>Detailed data by Region</h1>",
        b1_html.strip(),
    ]
    for ribbon, sbcs in RIBBON_SBCS:
        parts.append(f"<h2>{ribbon}</h2>")
        for sub_region, sbc in sbcs:
            print(f"  sbc-metrics: chart {sbc}...")
            img_tag = run([sys.executable, os.path.join(SCRIPTS, "kibana_metrics.py"), "analyze",
                           "b2", sbc, f"tmp/sbc_b2_{sbc}.json"])
            parts.append(expand(sub_region, img_tag.strip()))

    path = os.path.join(outdir, "section_sbc.html")
    with open(path, "w") as f:
        f.write("".join(parts))
    print(f"  wrote {path}")


if __name__ == "__main__":
    main()
