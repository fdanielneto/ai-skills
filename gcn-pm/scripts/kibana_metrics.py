#!/usr/bin/env python3
"""Kibana/Elasticsearch pipeline for gcn-pm: auth, fetch, aggregation, charts.

Subcommands:
  refresh                        Vouch SSO bootstrap (Playwright). Launches Chrome
                                  (persistent profile under gcn-pm/.auth/profile,
                                  shared with grafana_metrics.py — same SSO identity),
                                  navigates to Kibana, exports the Vouch cookies to
                                  gcn-pm/.auth/vouch_cookie.txt (chmod 600).
                                  Headless if the profile already has a live
                                  session; opens a visible window for the
                                  one-time Google login otherwise.
  read                            Print the saved Cookie header value
                                  (non-zero exit if missing).
  fetch <start> <end> [a1-a3|b1|b2|all]
                                  Fetch SBC CDR data (A-1/A-3, B-1, B-2) from
                                  Kibana over plain HTTP (dates YYYY-MM-DD).
                                  Writes raw Elasticsearch responses to
                                  gcn-pm/tmp/: sbc_a1a3.json, sbc_b1.json,
                                  sbc_b2_<SBC>.json.
  analyze a1-a3|b1 [json_file]   Aggregate + format a fetched response as
                                  Markdown (a1-a3) or Confluence HTML (b1).
                                  Reads json_file, or stdin if omitted.
  analyze b2 <SBC_NAME> [json_file]
                                  Render the per-SBC call-attempts timeline
                                  as a PNG chart and print the ready-to-embed
                                  <ac:image> tag.

Data-path code (fetch/analyze) must only ever call cookie_header() / `read` —
never drive a browser or prompt for login itself; that's `refresh`'s job alone.
"""
import json
import os
import stat
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import plot_helper

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AUTH_DIR = os.path.join(SKILL_DIR, ".auth")
PROFILE_DIR = os.path.join(AUTH_DIR, "profile")
COOKIE_FILE = os.path.join(AUTH_DIR, "vouch_cookie.txt")
TMP = os.path.join(SKILL_DIR, "tmp")
OUTPUT_DIR = os.path.join(SKILL_DIR, "output")

KIBANA_ORIGIN = "https://kibana-logging.svc.talkdeskapp.com"
KIBANA_URL = KIBANA_ORIGIN + "/app/home"
SEARCH_PATH = "/internal/search/es"  # /api/console/proxy is 404 on this Kibana (7.17.6)
INDEX = "logs-td-ribbonsbc-cdr*"

SBCS = [
    "PRDEUS1RSBC", "PRDEUW3RSBC",
    "prduse1rsbc", "prdusw2rsbc",
    "PRDAPS1RSBC", "PRDAPS2RSBC",
    "PRDSAE1RSBC1", "PRDSAE1RSBC2",
]

RIBBONS = {
    "EU": ["PRDEUS1RSBC", "PRDEUW3RSBC"],
    "US": ["prduse1rsbc", "prdusw2rsbc"],
    "APAC": ["PRDAPS1RSBC", "PRDAPS2RSBC"],
    "LATAM": ["PRDSAE1RSBC1", "PRDSAE1RSBC2"],
}


# ==================== auth ====================

def cookie_header():
    """Return the saved Cookie header value, or raise with refresh instructions."""
    try:
        with open(COOKIE_FILE) as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"No Kibana session cookie at {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/kibana_metrics.py refresh"
        )
    if not value:
        raise RuntimeError(
            f"Empty cookie file {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/kibana_metrics.py refresh"
        )
    return value


def _export_cookies(context):
    # every cookie the browser would send to the Kibana origin
    # (VouchCookie on .svc.talkdeskapp.com + Kibana's own sid, etc.)
    cookies = context.cookies(KIBANA_ORIGIN)
    if not cookies:
        return False
    header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    os.makedirs(AUTH_DIR, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    with open(COOKIE_FILE, "w") as f:
        f.write(header + "\n")
    os.chmod(COOKIE_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
    print(f"Saved {', '.join(c['name'] for c in cookies)} -> {COOKIE_FILE}")
    return True


def _try_session(headless):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chrome", headless=headless)
        page = context.pages[0] if context.pages else context.new_page()
        page.goto(KIBANA_URL, wait_until="domcontentloaded", timeout=60000)
        # success = the redirect chain lands back on the exact Kibana host;
        # oauth.svc.talkdeskapp.com (the login page) must NOT count
        if headless:
            page.wait_for_timeout(5000)  # allow Vouch redirect chain to settle
            ok = page.url.startswith(KIBANA_ORIGIN) and _export_cookies(context)
        else:
            print("Complete the Google login in the browser window...")
            ok = False
            for _ in range(36):  # max ~3 min
                page.wait_for_timeout(5000)
                if page.url.startswith(KIBANA_ORIGIN) and _export_cookies(context):
                    ok = True
                    break
        context.close()
        return ok


def refresh():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    if _try_session(headless=True):
        return
    print("Headless session expired/absent — opening browser for login.")
    if not _try_session(headless=False):
        sys.exit("Login did not complete; no Vouch cookie captured.")


# ==================== fetch ====================

def _base_query(gte, lte):
    return {"bool": {
        "must": [{"range": {"@timestamp": {"gte": gte, "lte": lte}}}],
        "must_not": [{"match_phrase": {"Record Type.keyword": "START"}}],
    }}


def a1_a3_body(gte, lte):
    return {
        "size": 0,
        "query": _base_query(gte, lte),
        "aggs": {
            "disconnect_reasons": {"terms": {
                "field": "Call Disconnect Reason.keyword", "size": 10}},
            "media_anchoring": {"filter": {"bool": {
                "must": [{"match_phrase": {"Record Type.keyword": "STOP"}}],
                "must_not": [{"match_phrase": {
                    "Ingress Number of Audio Packets Received.keyword": ""}}],
            }}},
        },
    }


def b1_body(gte, lte):
    filters = {
        ribbon: {"bool": {"should": [
            {"match_phrase": {"Gateway Name.keyword": sbc}} for sbc in sbcs
        ]}}
        for ribbon, sbcs in RIBBONS.items()
    }
    return {
        "size": 0,
        "query": _base_query(gte, lte),
        "aggs": {"ribbons": {
            "filters": {"filters": filters},
            "aggs": {"reasons": {"terms": {
                "field": "Call Disconnect Reason.keyword", "size": 5}}},
        }},
    }


def b2_body(gte, lte, sbc):
    body = {
        "size": 0,
        "query": _base_query(gte, lte),
        "aggs": {"timeline": {"date_histogram": {
            "field": "@timestamp",
            "fixed_interval": "1h",
            "format": "yyyy-MM-dd HH:mm",
        }}},
    }
    body["query"]["bool"]["must"].append(
        {"match_phrase": {"Gateway Name.keyword": sbc}})
    return body


def search(body):
    """POST the ES body via Kibana's internal search API; return the raw ES response."""
    payload = {"params": {"index": INDEX, "body": body}}
    req = Request(KIBANA_ORIGIN + SEARCH_PATH, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("kbn-xsrf", "true")
    req.add_header("Cookie", cookie_header())
    try:
        resp = urlopen(req, timeout=60)
        text = resp.read().decode()
    except HTTPError as e:
        sys.exit(f"ERROR: HTTP {e.code} from Kibana: {e.read().decode()[:300]}")
    if text.lstrip().startswith("<"):
        sys.exit("ERROR: Kibana returned an SSO/login page — session expired. "
                  "Run: python3 gcn-pm/scripts/kibana_metrics.py refresh")
    data = json.loads(text)
    if "rawResponse" not in data:
        sys.exit(f"ERROR: unexpected response, keys={list(data)[:10]}")
    return data["rawResponse"]


def _save(name, data):
    path = os.path.join(TMP, name)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def fetch(start, end, mode="all"):
    gte = f"{start}T00:00:00.000Z"
    lte = f"{end}T23:59:59.999Z"

    os.makedirs(TMP, exist_ok=True)
    print(f"Window: {gte} .. {lte}  ->  {TMP}")

    if mode in ("a1-a3", "all"):
        print(f"  kibana: a1-a3...", file=sys.stderr)
        raw = search(a1_a3_body(gte, lte))
        total = raw.get("hits", {}).get("total", {})
        print(f"  a1-a3: hits.total={total} -> {_save('sbc_a1a3.json', raw)}")

    if mode in ("b1", "all"):
        print(f"  kibana: b1...", file=sys.stderr)
        raw = search(b1_body(gte, lte))
        ribbons = raw.get("aggregations", {}).get("ribbons", {}).get("buckets", {})
        counts = {k: v.get("doc_count") for k, v in ribbons.items()}
        print(f"  b1: {counts} -> {_save('sbc_b1.json', raw)}")

    if mode in ("b2", "all"):
        print(f"  kibana: b2 ({len(SBCS)} SBCs)...", file=sys.stderr)
        for sbc in SBCS:
            raw = search(b2_body(gte, lte, sbc))
            buckets = raw.get("aggregations", {}).get("timeline", {}).get("buckets", [])
            total = sum(b["doc_count"] for b in buckets)
            print(f"  b2 {sbc}: {len(buckets)} buckets, {total} calls "
                  f"-> {_save(f'sbc_b2_{sbc}.json', raw)}")
            time.sleep(0.3)


# ==================== analysis ====================

def format_number(n):
    return f"{n:,}"


def analyze_a1_a3(raw_data):
    total = raw_data['hits']['total']
    if isinstance(total, dict):
        total = total['value']

    media = raw_data.get('aggregations', {}).get('media_anchoring', {}).get('doc_count', 0)
    buckets = raw_data.get('aggregations', {}).get('disconnect_reasons', {}).get('buckets', [])

    lines = []
    lines.append("### A-1. Total Call Attempts & Media Anchoring")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total Call Attempts (all) | {format_number(total)} |")
    lines.append(f"| Total Media Anchoring Calls (all) | {format_number(media)} |")
    lines.append("")
    lines.append("### A-3. Call Disconnect Reason (all regions) — Top 10")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Total calls (STOP) | {format_number(total)} |")
    for b in buckets:
        count = b['doc_count']
        pct = (count / total * 100) if total > 0 else 0
        if pct >= 0.5:  # ignore reasons under 0.5% (saves tokens downstream)
            lines.append(f"| {b['key']} | {format_number(count)} ({pct:.1f}%) |")
    return "\n".join(lines)


def analyze_b1(raw_data):
    REASON_MAP = {
        "16": "Normal call clearing",
        "41": "Temporary failure",
        "1": "Unallocated (unassigned) number",
        "17": "User busy",
        "31": "Normal, unspecified",
        "18": "No user responding",
        "102": "Recovery on timer expiry",
        "20": "Subscriber absent",
        "21": "Call rejected",
        "19": "No answer from user (user alerted)",
    }

    ribbon_buckets = raw_data.get('aggregations', {}).get('ribbons', {}).get('buckets', {})

    def make_table(ribbon_key, title):
        data = ribbon_buckets.get(ribbon_key, {})
        total = data.get('doc_count', 0)
        buckets = data.get('reasons', {}).get('buckets', [])

        html = []
        html.append('<div style="font-size: 0.85em;">')
        html.append('  <table>')
        html.append('    <thead>')
        html.append('      <tr>')
        html.append(f'        <th colspan="2"><strong>{title}</strong></th>')
        html.append('      </tr>')
        html.append('    </thead>')
        html.append('    <tbody>')
        html.append('      <tr>')
        html.append('        <td>Total calls (STOP)</td>')
        html.append(f'        <td>{format_number(total)}</td>')
        html.append('      </tr>')
        for b in buckets:
            code = b['key']
            count = b['doc_count']
            name = REASON_MAP.get(code, f"Code {code}")
            pct = (count / total * 100) if total > 0 else 0
            html.append('      <tr>')
            html.append(f'        <td>{name} ({code})</td>')
            html.append(f'        <td>{format_number(count)} ({pct:.1f}%)</td>')
            html.append('      </tr>')
        html.append('    </tbody>')
        html.append('  </table>')
        html.append('</div>')
        return '\n'.join(html)

    out = ["<ac:layout>"]
    out.append('  <ac:layout-section ac:type="two_equal">')
    out.append('    <ac:layout-cell>')
    out.append(make_table("EU", "Ribbon EU"))
    out.append('    </ac:layout-cell>')
    out.append('    <ac:layout-cell>')
    out.append(make_table("US", "Ribbon US"))
    out.append('    </ac:layout-cell>')
    out.append('  </ac:layout-section>')
    out.append('  <ac:layout-section ac:type="two_equal">')
    out.append('    <ac:layout-cell>')
    out.append(make_table("APAC", "Ribbon APAC"))
    out.append('    </ac:layout-cell>')
    out.append('    <ac:layout-cell>')
    out.append(make_table("LATAM", "Ribbon LATAM"))
    out.append('    </ac:layout-cell>')
    out.append('  </ac:layout-section>')
    out.append('</ac:layout>')
    return "\n".join(out)


def analyze_b2(raw_data, sbc_name):
    """Per-SBC call attempts timeline -> PNG + ready-to-embed <ac:image> tag."""
    print(f"  sbc chart: {sbc_name}...", file=sys.stderr)
    buckets = raw_data.get('aggregations', {}).get('timeline', {}).get('buckets', [])
    payload = {
        "lines": [{
            "label": sbc_name,
            "points": [{"x": b.get('key_as_string', ''), "y": b.get('doc_count', 0)} for b in buckets],
        }]
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"sbc_timeline_{sbc_name}.png")
    try:
        plot_helper.render_chart(f"Call Attempts — {sbc_name}", out_path, "Time", "calls", payload)
    except Exception as e:
        sys.exit(f"ERROR: chart generation failed for {sbc_name}: {e}")

    return f'<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="{os.path.basename(out_path)}"/></ac:image>'


# ==================== CLI ====================

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)

    mode = sys.argv[1]

    if mode == "refresh":
        refresh()
        return

    if mode == "read":
        try:
            print(cookie_header())
        except RuntimeError as e:
            sys.exit(f"{e}")
        return

    if mode == "fetch":
        if len(sys.argv) < 4:
            sys.exit("Usage: kibana_metrics.py fetch <start_date> <end_date> [a1-a3|b1|b2|all]")
        start, end = sys.argv[2], sys.argv[3]
        fetch_mode = sys.argv[4] if len(sys.argv) > 4 else "all"
        fetch(start, end, fetch_mode)
        return

    if mode == "analyze":
        if len(sys.argv) < 3:
            sys.exit("Usage: kibana_metrics.py analyze <a1-a3|b1|b2> [SBC_NAME] [json_file]")
        submode = sys.argv[2]

        if submode == "b2":
            if len(sys.argv) < 4:
                sys.exit("Usage: kibana_metrics.py analyze b2 <SBC_NAME> [json_file]")
            sbc_name = sys.argv[3]
            if len(sys.argv) > 4:
                with open(sys.argv[4], 'r') as f:
                    raw_data = json.load(f)
            else:
                raw_data = json.load(sys.stdin)
            print(analyze_b2(raw_data, sbc_name))
            return

        if len(sys.argv) > 3:
            with open(sys.argv[3], 'r') as f:
                raw_data = json.load(f)
        else:
            raw_data = json.load(sys.stdin)

        if submode == "a1-a3":
            print(analyze_a1_a3(raw_data))
        elif submode == "b1":
            print(analyze_b1(raw_data))
        else:
            sys.exit(f"Unknown analyze mode: {submode}")
        return

    sys.exit(__doc__)


if __name__ == "__main__":
    main()
