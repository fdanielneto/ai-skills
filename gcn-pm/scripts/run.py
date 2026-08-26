#!/usr/bin/env python3
"""Single entry point for the /gcn-pm skill — runs every requested generator
then publishes once. See SKILL.md's RUN section.

Usage:
    run.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> [section ...] [region ...]

Section tokens (case-insensitive, -/_ interchangeable, aliases per SKILL.md):
  on-call, xcc-metrics, rtpengine-metrics, sbc-metrics, all (default: all)
Region tokens: any token in scripts/regions.py's REGION_TOKENS. Only applied
to xcc-metrics/rtpengine-metrics (the only region-aware generators); ignored
for on-call/sbc-metrics.

Sequence: wipe tmp/, write a run marker, run each requested generator in
order (fail-fast — abort immediately on the first non-zero exit, before
running the rest or publishing), then call confluence_publish.py once.
confluence_publish.py enforces its own completeness/freshness guardrails
before it will actually publish. tmp/ is cleaned only on full success, left
in place on any failure for debugging.

Single attempt only — no retries at this layer. Exit 0 only if every
requested generator AND the publish step exited 0.
"""
import os
import shutil
import subprocess
import sys
import time

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
TMP_DIR = os.path.join(SKILL_DIR, "tmp")
RUN_MARKER = os.path.join(TMP_DIR, ".run_marker")

sys.path.insert(0, SCRIPTS)
from regions import REGION_TOKENS  # noqa: E402

ALL_SECTIONS = ["on-call", "xcc-metrics", "rtpengine-metrics", "sbc-metrics"]

SECTION_ALIASES = {
    "on-call": "on-call", "on_call": "on-call", "ops": "on-call",
    "xcc-metrics": "xcc-metrics", "xcc_metrics": "xcc-metrics",
    "xcc": "xcc-metrics", "kamailio": "xcc-metrics",
    "rtpengine-metrics": "rtpengine-metrics", "rtpengine_metrics": "rtpengine-metrics",
    "rtpengine": "rtpengine-metrics", "rtp": "rtpengine-metrics",
    "sbc-metrics": "sbc-metrics", "sbc_metrics": "sbc-metrics",
    "sbc": "sbc-metrics", "calls": "sbc-metrics",
    "all": "all", "full": "all", "page": "all",
}

GENERATORS = {
    "on-call": "generate_oncall.py",
    "xcc-metrics": "generate_xcc.py",
    "rtpengine-metrics": "generate_rtpengine.py",
    "sbc-metrics": "generate_sbc.py",
}
REGION_AWARE = {"xcc-metrics", "rtpengine-metrics"}


def norm_token(tok):
    return tok.lower().replace("_", "-")


def parse_args(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    start, end = argv[0], argv[1]
    sections, regions = [], []
    for raw in argv[2:]:
        tok = norm_token(raw)
        if tok in SECTION_ALIASES:
            canon = SECTION_ALIASES[tok]
            if canon == "all":
                sections = list(ALL_SECTIONS)
            elif canon not in sections:
                sections.append(canon)
        elif tok in REGION_TOKENS:
            if tok not in regions:
                regions.append(tok)
        else:
            sys.exit(f"ERROR: unknown section/region token {raw!r}\n"
                     f"Valid sections: {sorted(set(SECTION_ALIASES.values()))}\n"
                     f"Valid regions: {sorted(REGION_TOKENS)}")
    if not sections:
        sections = list(ALL_SECTIONS)
    return start, end, sections, regions


def run(cmd, label):
    print(f"[run.py] {label}: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, cwd=SKILL_DIR)
    if result.returncode != 0:
        sys.exit(f"ERROR: {label} failed (exit {result.returncode}) — "
                 "aborting, nothing published.")


def main():
    start, end, sections, regions = parse_args(sys.argv[1:])

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    with open(RUN_MARKER, "w") as f:
        f.write(str(time.time()))

    for section in ALL_SECTIONS:
        if section not in sections:
            continue
        cmd = [sys.executable, os.path.join(SCRIPTS, GENERATORS[section]), start, end]
        if section in REGION_AWARE:
            cmd += regions
        run(cmd, section)

    run([sys.executable, os.path.join(SCRIPTS, "confluence_publish.py"), start, end],
        "publish")

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print("[run.py] OK — published, tmp/ cleaned.", file=sys.stderr)


if __name__ == "__main__":
    main()
