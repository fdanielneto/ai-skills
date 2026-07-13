#!/usr/bin/env python3
"""Regression harness for the gcn-pm skill — runs the real generate_*.py +
confluence_publish.py pipeline via subprocess (the same invocation
SKILL.md's bash dispatcher uses) and reports pass/fail per step.

Usage:
    test_skill.py <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> \\
        [section ...] [region ...] [--no-publish] [--out DIR]

Sections (same tokens/aliases as SKILL.md): on-call, xcc-metrics,
rtpengine-metrics, sbc-metrics, all (default: all).
Regions only affect xcc-metrics / rtpengine-metrics.

--no-publish: build tmp/section_*.html + page_full.html and verify
locally, skip the Confluence upload/PUT (passed through to
confluence_publish.py --no-publish).
"""
import glob
import os
import subprocess
import sys
from datetime import datetime

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)

from regions import REGION_TOKENS  # noqa: E402

SECTION_ALIASES = {
    "on-call": ("on-call", "on_call", "ops"),
    "xcc-metrics": ("xcc-metrics", "xcc_metrics", "xcc", "kamailio"),
    "rtpengine-metrics": ("rtpengine-metrics", "rtpengine_metrics", "rtpengine", "rtp"),
    "sbc-metrics": ("sbc-metrics", "sbc_metrics", "sbc", "calls"),
    "all": ("all", "full", "page"),
}
CANONICAL_ORDER = ["on-call", "xcc-metrics", "rtpengine-metrics", "sbc-metrics"]

# script, takes_region_args
GENERATORS = {
    "on-call": ("generate_oncall.py", False),
    "xcc-metrics": ("generate_xcc.py", True),
    "rtpengine-metrics": ("generate_rtpengine.py", True),
    "sbc-metrics": ("generate_sbc.py", False),
}


def run(cmd, timeout=180):
    """Run a subprocess from the skill root; stream stderr live, capture stdout."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, bufsize=1, cwd=SKILL_DIR,
                         env={**os.environ, "PYTHONUNBUFFERED": "1"})
    for line in p.stderr:
        print(line, end='', file=sys.stderr)
    try:
        stdout, _ = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        return 1, f"ERROR: {' '.join(cmd)} timed out after {timeout}s"
    return p.poll(), stdout


def parse_args(argv):
    flags = {"publish": True, "outdir": os.path.join(SKILL_DIR, "tmp")}
    if "--no-publish" in argv:
        argv.remove("--no-publish")
        flags["publish"] = False
    if "--out" in argv:
        i = argv.index("--out")
        flags["outdir"] = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]

    if len(argv) < 2:
        sys.exit(__doc__)
    start, end = argv[0], argv[1]
    for d in (start, end):
        datetime.strptime(d, "%Y-%m-%d")  # validate

    sections, regions = set(), set()
    for tok in argv[2:]:
        t = tok.lower().replace("_", "-")
        canonical = next((c for c, aliases in SECTION_ALIASES.items()
                          if t in [a.replace("_", "-") for a in aliases]), None)
        if canonical:
            sections.add(canonical)
        elif t in REGION_TOKENS:
            regions.add(t)
        else:
            sys.exit(f"Unknown token: {tok}\nSections: {list(SECTION_ALIASES)}\n"
                     f"Regions: {sorted(REGION_TOKENS)}")
    if not sections or "all" in sections:
        sections = set(CANONICAL_ORDER)
    return start, end, sections, regions, flags


def main():
    start, end, sections, regions, flags = parse_args(sys.argv[1:])
    outdir = flags["outdir"]
    os.makedirs(outdir, exist_ok=True)
    for stale in glob.glob(os.path.join(outdir, "section_*.html")) + \
            glob.glob(os.path.join(outdir, "page_full.html")):
        os.remove(stale)  # each run's page contains ONLY that run's sections
    print(f"Run: {start}..{end} sections={sorted(sections)} regions={sorted(regions) or 'all'}")

    for section in CANONICAL_ORDER:
        if section not in sections:
            continue
        script, takes_region = GENERATORS[section]
        cmd = [sys.executable, os.path.join(SCRIPTS, script), start, end, "--out", outdir]
        if takes_region:
            cmd += sorted(regions)
        rc, _ = run(cmd)
        if rc != 0:
            sys.exit(f"FAIL: {script} exited {rc}")
        print(f"OK: {script}")

    publish_cmd = [sys.executable, os.path.join(SCRIPTS, "confluence_publish.py"),
                   start, end, "--out", outdir]
    if not flags["publish"]:
        publish_cmd.append("--no-publish")
    rc, out = run(publish_cmd)
    if rc != 0:
        sys.exit(f"FAIL: confluence_publish.py exited {rc}")
    print(out.strip())
    print("OK: confluence_publish.py")


if __name__ == "__main__":
    main()
