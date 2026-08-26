#!/usr/bin/env python3
"""Populate .baseline_cache/ for all XCC metrics across all regions.

Usage:
    python3 scripts/populate_cache.py <sprint_start> <sprint_end> [regions...]

If no regions are specified, runs for all 8 regions.
Examples:
    python3 scripts/populate_cache.py 2026-07-07 2026-07-22
    python3 scripts/populate_cache.py 2026-07-07 2026-07-22 us-east-1 eu-west-3
"""
import os
import subprocess
import sys
from datetime import datetime, timezone

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
sys.path.insert(0, SCRIPTS)

from regions import REGIONS, REGION_TOKENS
from grafana_metrics import load_metric_slugs


def epoch_ms(dt):
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


def main():
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        sys.exit(1)

    start_dt = datetime.strptime(sys.argv[1], "%Y-%m-%d")
    end_dt = datetime.strptime(sys.argv[2], "%Y-%m-%d")
    start_ms = epoch_ms(start_dt)
    end_ms = epoch_ms(end_dt)

    requested_regions = sys.argv[3:] or [tok for _, tok in REGIONS]
    unknown = set(requested_regions) - REGION_TOKENS
    if unknown:
        print(f"Unknown region(s): {sorted(unknown)}. Valid: {sorted(REGION_TOKENS)}",
              file=sys.stderr)
        sys.exit(1)

    config = os.path.join(SKILL_DIR, "config", "xcc_metrics.yaml")
    metric_slugs = load_metric_slugs(config)
    active_slugs = sorted(metric_slugs)

    print(f"Baseline window: baseline_weeks=8 before {sys.argv[1]}",
          file=sys.stderr)
    print(f"Regions: {requested_regions}", file=sys.stderr)
    print(f"Active metrics: {len(active_slugs)} — {active_slugs}", file=sys.stderr)
    print(file=sys.stderr)

    for display, token in REGIONS:
        if token not in requested_regions:
            continue
        print(f"[{token}] Analyzing all active metrics...", file=sys.stderr)
        cmd = [
            sys.executable,
            os.path.join(SCRIPTS, "grafana_metrics.py"),
            "analyze",
            config,
            str(start_ms),
            str(end_ms),
            token,
        ]
        result = subprocess.run(
            cmd,
            cwd=SKILL_DIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        # Print stderr (progress messages) and discard stdout (HTML output)
        for line in result.stderr.splitlines():
            print(f"  {line}", file=sys.stderr)
        if result.returncode != 0:
            print(f"  FAILED (exit {result.returncode})", file=sys.stderr)
            # Print last lines of stderr for context
            err_lines = result.stderr.strip().splitlines()
            for line in err_lines[-10:]:
                print(f"  ! {line}", file=sys.stderr)
        else:
            print(f"  OK", file=sys.stderr)
        print(file=sys.stderr)

    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
