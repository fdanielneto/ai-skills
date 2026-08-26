#!/usr/bin/env python3
"""Run /gcn-pm's orchestrator, wait for the publish, then validate the
*live* published Confluence page for section/region completeness — all in
this script, so the caller never has to read the page body.

Usage:
    verify_publish.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> [section ...] [region ...]
    verify_publish.py --check-only <page_id> [section ...] [region ...]

Section/region tokens: identical vocabulary to /gcn-pm (see gcn-pm/SKILL.md).
Omit section tokens for a full-page run/check (all 4 sections).

--check-only skips running run.py entirely and validates an already-published
page id directly — useful for testing the validator or re-checking a page
without re-running the (slow, Grafana/Kibana/Playwright-backed) generators.

Prints exactly one final line to stdout:
    RESULT: PASS page=<id> url=<url> sections=<a,b,c> regions=8/8
    RESULT: FAIL stage=<run|parse|parse-args|auth|fetch|validate> ...

Exit code 0 on PASS, 1 on any FAIL. Never prints the page body.
"""
import os
import re
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.normpath(os.path.join(SCRIPTS_DIR, "..", ".."))
GCN_PM_SCRIPTS = os.path.join(REPO_ROOT, "gcn-pm", "scripts")

sys.path.insert(0, GCN_PM_SCRIPTS)
import run as run_mod  # noqa: E402
import confluence_publish as publish_mod  # noqa: E402
from regions import REGIONS  # noqa: E402

RUN_TIMEOUT_SECONDS = 1500  # 25 min

PUBLISH_OK_RE = re.compile(r"OK: (?:created|updated) page (\d+) -> (\S+)")

SECTION_HEADINGS = {
    "on-call": [
        r"<h1>Status Review</h1>",
        r"<h1>On-Call Alarms</h1>",
        r"<h1>Post-Mortem \(last 90 days\)</h1>",
        r"<h1>Events Tracking</h1>",
    ],
    "xcc-metrics": [r"<h1>XCC Metrics \(Kamailio\)</h1>"],
    "rtpengine-metrics": [r"<h1>RTP Engine Metrics</h1>"],
    "sbc-metrics": [
        r'<h1><a href="[^"]*">Executive Summary</a></h1>',
        r"<h1>Detailed data by Region</h1>",
    ],
}

# Fixed page order among the region-aware sections + their right-hand
# boundary (sbc-metrics), used only to slice the page so xcc/rtpengine
# region-title counts don't bleed into each other when both are present.
REGION_SLICE_ORDER = ["xcc-metrics", "rtpengine-metrics", "sbc-metrics"]
REGION_SLICE_START = {
    "xcc-metrics": SECTION_HEADINGS["xcc-metrics"][0],
    "rtpengine-metrics": SECTION_HEADINGS["rtpengine-metrics"][0],
    "sbc-metrics": SECTION_HEADINGS["sbc-metrics"][0],
}


def fail(stage, **fields):
    detail = " ".join(f"{k}={v!r}" for k, v in fields.items())
    print(f"RESULT: FAIL stage={stage} {detail}".rstrip())
    sys.exit(1)


def resolve_tokens(start, end, tokens):
    try:
        _, _, sections, regions = run_mod.parse_args([start, end, *tokens])
    except SystemExit as e:
        fail("parse-args", reason=str(e.code))
    return sections, regions


def run_and_publish(start, end, tokens):
    cmd = [sys.executable, os.path.join(GCN_PM_SCRIPTS, "run.py"), start, end, *tokens]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=RUN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        fail("run", reason=f"timed out after {RUN_TIMEOUT_SECONDS}s")
    if proc.returncode != 0:
        fail("run", exit=proc.returncode, stderr_tail=proc.stderr[-500:].strip())
    match = PUBLISH_OK_RE.search(proc.stdout)
    if not match:
        fail("parse", reason="page id not found in run.py output",
             stdout_tail=proc.stdout[-300:].strip())
    return match.group(1), match.group(2)


def fetch_page_html(page_id):
    try:
        username, token = publish_mod.load_credentials()
    except SystemExit as e:
        fail("auth", reason=str(e.code))
    try:
        published = publish_mod.request(
            "GET", f"/rest/api/content/{page_id}?expand=body.storage", username, token)
    except SystemExit as e:
        fail("fetch", page=page_id, reason=str(e.code))
    return published["body"]["storage"]["value"]


def region_slice(html, section):
    start_m = re.search(REGION_SLICE_START[section], html)
    if not start_m:
        return ""
    start = start_m.end()
    end = len(html)
    idx = REGION_SLICE_ORDER.index(section)
    for later in REGION_SLICE_ORDER[idx + 1:]:
        later_m = re.search(REGION_SLICE_START[later], html)
        if later_m:
            end = later_m.start()
            break
    return html[start:end]


def missing_regions_in(html_slice):
    titles = re.findall(r'<ac:parameter ac:name="title">([^<]*)</ac:parameter>', html_slice)
    return [display for display, _ in REGIONS
            if sum(1 for t in titles if t == display or t.startswith(display + " ")) != 1]


def validate(html, sections):
    missing_sections = []
    for section in sections:
        if not all(re.search(pat, html) for pat in SECTION_HEADINGS[section]):
            missing_sections.append(section)

    unexpected_sections = []
    for section in run_mod.ALL_SECTIONS:
        if section in sections:
            continue
        if any(re.search(pat, html) for pat in SECTION_HEADINGS[section]):
            unexpected_sections.append(section)

    missing_regions = {}
    checked = 0
    for section in sections:
        if section not in run_mod.REGION_AWARE:
            continue
        checked += 1
        missing = missing_regions_in(region_slice(html, section))
        if missing:
            missing_regions[section] = missing

    return missing_sections, unexpected_sections, missing_regions, checked


def main():
    argv = sys.argv[1:]
    if not argv:
        sys.exit(__doc__)

    if argv[0] == "--check-only":
        if len(argv) < 2:
            sys.exit(__doc__)
        page_id, tokens = argv[1], argv[2:]
        sections, _ = resolve_tokens("0000-01-01", "0000-01-01", tokens)
        url = f"{publish_mod.BASE_URL}/pages/viewpage.action?pageId={page_id}"
    else:
        if len(argv) < 2:
            sys.exit(__doc__)
        start, end, tokens = argv[0], argv[1], argv[2:]
        sections, _ = resolve_tokens(start, end, tokens)
        page_id, url = run_and_publish(start, end, tokens)

    html = fetch_page_html(page_id)
    missing_sections, unexpected_sections, missing_regions, checked = validate(html, sections)

    if missing_sections or unexpected_sections or missing_regions:
        fail("validate", page=page_id, url=url,
             missing_sections=missing_sections,
             unexpected_sections=unexpected_sections,
             missing_regions=missing_regions)

    region_summary = f"{checked * 8 - sum(len(v) for v in missing_regions.values())}/{checked * 8}" \
        if checked else "n/a"
    print(f"RESULT: PASS page={page_id} url={url} "
          f"sections={','.join(sections)} regions={region_summary}")


if __name__ == "__main__":
    main()
