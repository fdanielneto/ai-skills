#!/usr/bin/env python3
"""Standalone test harness for the gcn-pm skill — exercises the real data
pipelines of each section without Claude Code or subagents.

Usage:
    test_skill.py <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> \\
        [section ...] [region ...] [--no-publish] [--out DIR]

Sections (same tokens/aliases as SKILL.md): on-call, xcc-metrics,
rtpengine-metrics, sbc-metrics, all (default: all).
Regions only affect xcc-metrics / rtpengine-metrics.

--no-publish: build the HTML locally (output/section_*.html + page_full.html)
but skip the Confluence upload/PUT.

Data access: Grafana via grafana_analyzer.py (mcp-remote), Kibana via
fetch_sbc_data.py (plain HTTP; session cookie from kibana_auth.py — run
`kibana_auth.py refresh` first if expired). The On-Call Alarms screenshot
needs a live browser and is rendered as the documented warning fallback here.
"""
import glob
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
SCRIPTS = os.path.join(SKILL_DIR, "scripts")

SECTION_ALIASES = {
    "on-call": ("on-call", "on_call", "ops"),
    "xcc-metrics": ("xcc-metrics", "xcc_metrics", "xcc", "kamailio"),
    "rtpengine-metrics": ("rtpengine-metrics", "rtpengine_metrics", "rtpengine", "rtp"),
    "sbc-metrics": ("sbc-metrics", "sbc_metrics", "sbc", "calls"),
    "all": ("all", "full", "page"),
}
CANONICAL_ORDER = ["on-call", "xcc-metrics", "rtpengine-metrics", "sbc-metrics"]

REGIONS = [  # (display name, region token) — order from SKILL.md
    ("EU-South-1", "eu-south-1"),
    ("EU-West-3", "eu-west-3"),
    ("US-East-1", "us-east-1"),
    ("US-West-2", "us-west-2"),
    ("AP1 - Singapore", "ap-southeast-1"),
    ("AP2 - Sydney", "ap-southeast-2"),
    ("SA-East-1", "sa-east-1"),
    ("CA-Central-1", "ca-central-1"),
]
REGION_TOKENS = {tok for _, tok in REGIONS}

RIBBON_SBCS = [  # (ribbon, [(sub-region, SBC name)]) — from sbc-metrics.md
    ("Ribbon EU", [("EU-South-1", "PRDEUS1RSBC"), ("EU-West-3", "PRDEUW3RSBC")]),
    ("Ribbon US", [("US-East-1", "prduse1rsbc"), ("US-West-2", "prdusw2rsbc")]),
    ("Ribbon APAC", [("AP1 - Singapore", "PRDAPS1RSBC"), ("AP2 - Sydney", "PRDAPS2RSBC")]),
    ("Ribbon LATAM", [("LATAM-AZ1 (São Paulo)", "PRDSAE1RSBC1"),
                      ("LATAM-AZ2 (São Paulo)", "PRDSAE1RSBC2")]),
]


# ---------- helpers ----------

def run(cmd, **kw):
    """Run a subprocess from the skill root; die loudly on failure."""
    r = subprocess.run(cmd, cwd=SKILL_DIR, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit(f"ERROR: {' '.join(cmd)} failed:\n{r.stderr[-2000:]}")
    if r.stderr.strip():
        print(r.stderr.strip(), file=sys.stderr)
    return r.stdout


def epoch_ms(d, end_of_day=False):
    t = datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if end_of_day:
        t += timedelta(days=1) - timedelta(milliseconds=1)
    return int(t.timestamp() * 1000)


def ordinal_date(d):
    """2026-05-07 -> 'May 07th' (zero-padded, as on the example pages)."""
    dt = datetime.strptime(d, "%Y-%m-%d")
    day = dt.day
    suffix = "th" if 11 <= day % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{dt.strftime('%B')} {day:02d}{suffix}"


def expand(title, body):
    return ('<ac:structured-macro ac:name="expand" ac:schema-version="1">'
            f'<ac:parameter ac:name="title">{title}</ac:parameter>'
            f'<ac:rich-text-body>{body}</ac:rich-text-body></ac:structured-macro>')


def md_to_html(md):
    """Convert sbc_analyzer's markdown output (### headings + 2-col tables) to storage HTML."""
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


# ---------- section handlers ----------

def grafana_section(config_yaml, heading, start, end, region_filter, out_file, outdir):
    start_ms, end_ms = epoch_ms(start), epoch_ms(end, end_of_day=True)
    parts = [f"<h1>{heading}</h1>"]
    for display, token in REGIONS:
        if region_filter and token not in region_filter:
            parts.append(expand(display,
                "<p><em>Not analysed in this run (region filter active).</em></p>"))
            continue
        print(f"  {heading}: analysing {token}...")
        html = run([sys.executable, os.path.join(SCRIPTS, "grafana_analyzer.py"),
                    os.path.join(SKILL_DIR, "config", config_yaml),
                    str(start_ms), str(end_ms), token])
        parts.append(expand(display, html.strip()))
    _write(outdir, out_file, "".join(parts))


def sbc_section(start, end, outdir):
    print("  sbc-metrics: fetching Kibana data (plain HTTP)...")
    run([sys.executable, os.path.join(SCRIPTS, "fetch_sbc_data.py"), start, end, "all"])

    with open(os.path.join(SKILL_DIR, "tmp", "sbc_a1a3.json")) as f:
        total = json.load(f)["hits"]["total"]
        total = total["value"] if isinstance(total, dict) else total

    a1a3_md = run([sys.executable, os.path.join(SCRIPTS, "sbc_analyzer.py"),
                   "a1-a3", "tmp/sbc_a1a3.json"])
    b1_html = run([sys.executable, os.path.join(SCRIPTS, "sbc_analyzer.py"),
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
            img_tag = run([sys.executable, os.path.join(SCRIPTS, "sbc_analyzer.py"),
                           "b2", sbc, f"tmp/sbc_b2_{sbc}.json"])
            parts.append(expand(sub_region, img_tag.strip()))
    _write(outdir, "section_sbc.html", "".join(parts))


ONCALL_URL = ("https://talkdesk.atlassian.net/jira/ops/alerts?view=list&amp;"
              "query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22")


def _blockcard(href, datasource):
    return (f'<p local-id="{uuid.uuid4()}" />'
            f'<a href="{href}" data-layout="full-width" local-id="{uuid.uuid4()}"'
            f' data-card-appearance="block" data-datasource="{datasource}">{href}</a>'
            f'<p local-id="{uuid.uuid4()}" />')


def _info(items):
    lis = "".join(f"<li><p>{i}</p></li>" for i in items)
    return ('<ac:structured-macro ac:name="info" ac:schema-version="1">'
            f'<ac:rich-text-body><ul>{lis}</ul></ac:rich-text-body></ac:structured-macro>')


# data-datasource values verbatim from references/on-call.md (entity-encoded JSON)
STATUS_DS = "{&quot;id&quot;: &quot;d8b75300-dfda-4519-b6cd-e49abbd50401&quot;, &quot;parameters&quot;: {&quot;cloudId&quot;: &quot;66f0204c-1684-409c-b644-8cac70022a54&quot;, &quot;jql&quot;: &quot;filter = \\&quot;production-meetings-interconnect\\&quot;&quot;}, &quot;views&quot;: [{&quot;type&quot;: &quot;table&quot;, &quot;properties&quot;: {&quot;columns&quot;: [{&quot;key&quot;: &quot;issuetype&quot;}, {&quot;key&quot;: &quot;key&quot;, &quot;width&quot;: 88}, {&quot;key&quot;: &quot;summary&quot;, &quot;width&quot;: 471}, {&quot;key&quot;: &quot;status&quot;}, {&quot;key&quot;: &quot;parent&quot;}, {&quot;key&quot;: &quot;customfield_10007&quot;, &quot;width&quot;: 109}, {&quot;key&quot;: &quot;assignee&quot;, &quot;width&quot;: 114}, {&quot;key&quot;: &quot;created&quot;}]}}]}"
STATUS_HREF = "https://talkdesk.atlassian.net/issues/?jql=filter%20%3D%20%22production-meetings-interconnect%22"

PM_DS = "{&quot;id&quot;: &quot;d8b75300-dfda-4519-b6cd-e49abbd50401&quot;, &quot;parameters&quot;: {&quot;cloudId&quot;: &quot;66f0204c-1684-409c-b644-8cac70022a54&quot;, &quot;jql&quot;: &quot;project in (INCIDENT) and type in (\\&quot;TD Incident\\&quot;) and assignee in (712020:e99666d8-42ea-4f69-be46-1d96262ac54e, 622745edb7e7c7007159b8df, 712020:3a4c738b-581a-432c-a471-82d7e70c57f6, 5f9fde30632c620071778e2b, 712020:d39b9372-96d2-4be1-98a0-e17ad4292a0c, 60380d934623c60069cfc0ea, 61ead968e2261a0069580f6c, 61d89c7d90cfd20071343f62, 5fba1b20cbead500690e3ffd, 603cac0581a8400068b23bcd, 712020:9baaf1c0-1a40-4795-92ca-f879f03a96fd) and created &gt;= -90d ORDER BY created DESC&quot;}, &quot;views&quot;: [{&quot;type&quot;: &quot;table&quot;, &quot;properties&quot;: {&quot;columns&quot;: [{&quot;key&quot;: &quot;issuetype&quot;}, {&quot;key&quot;: &quot;key&quot;, &quot;width&quot;: 88}, {&quot;key&quot;: &quot;summary&quot;, &quot;width&quot;: 471}, {&quot;key&quot;: &quot;status&quot;}, {&quot;key&quot;: &quot;priority&quot;}, {&quot;key&quot;: &quot;assignee&quot;, &quot;width&quot;: 114}, {&quot;key&quot;: &quot;created&quot;}]}}]}"
PM_HREF = "https://talkdesk.atlassian.net/issues/?jql=project%20in%20(INCIDENT)%20and%20type%20in%20(%22TD%20Incident%22)%20and%20assignee%20in%20(712020%3Ae99666d8-42ea-4f69-be46-1d96262ac54e%2C%20622745edb7e7c7007159b8df%2C%20712020%3A3a4c738b-581a-432c-a471-82d7e70c57f6%2C%205f9fde30632c620071778e2b%2C%20712020%3Ad39b9372-96d2-4be1-98a0-e17ad4292a0c%2C%2060380d934623c60069cfc0ea%2C%2061ead968e2261a0069580f6c%2C%2061d89c7d90cfd20071343f62%2C%205fba1b20cbead500690e3ffd%2C%20603cac0581a8400068b23bcd%2C%20712020%3A9baaf1c0-1a40-4795-92ca-f879f03a96fd)%20and%20created%20%3E%3D%20-90d%20ORDER%20BY%20created%20DESC"


def oncall_section(outdir):
    parts = [
        "<h1>Status Review</h1>",
        _info([
            "Review the status of all Ops Improvement Action items from last meetings at the beginning of the meeting.",
            "Assign clear ownership for each item and set due dates.",
            "Track the age of Ops Improvement Action items to prioritise older, unresolved tasks.",
        ]),
        _blockcard(STATUS_HREF, STATUS_DS),
        "<h1>On-Call Alarms</h1>",
        ('<ac:structured-macro ac:name="info" ac:schema-version="1"><ac:rich-text-body><ul>'
         "<li>Review both paged and non-paged alarms for accuracy and effectiveness.<ul>"
         "<li>Include on-call team members in the meeting and actively seek their input, especially regarding recent paged events.</li>"
         "<li>Use their feedback to improve alarms, runbooks, and processes for managing incidents.</li>"
         "</ul></li>"
         "<li>Analyze the false positive rate of alarms and take steps to improve their quality.</li>"
         "<li>Update runbooks based on on-call feedback and alarm effectiveness.</li>"
         "</ul></ac:rich-text-body></ac:structured-macro>"),
        f'<p><a href="{ONCALL_URL}">{ONCALL_URL}</a></p>',
        # harness has no browser: documented fallback from on-call.md
        ('<ac:structured-macro ac:name="warning" ac:schema-version="1"><ac:rich-text-body>'
         "<p><em>Live alert data was not collected in this run (Playwright tool unavailable). "
         "See link above.</em></p></ac:rich-text-body></ac:structured-macro>"),
        "<h1>Post-Mortem (last 90 days)</h1>",
        _info([
            "Link all relevant post-mortems to the meeting documentation for easy reference.",
            "Use insights from post-mortems to prevent similar incidents in the future.",
        ]),
        _blockcard(PM_HREF, PM_DS),
    ]
    _write(outdir, "section_oncall.html", "".join(parts))

    rows = ["EMS Alarms Analysis", "Ribbon Licenses", "…", "", "", "", ""]
    table = ["<h1>Events Tracking</h1>", "<table><tbody>",
             "<tr><th>Checkpoints</th><th>Description</th><th>Action</th><th>Date</th></tr>"]
    for r in rows:
        table.append(f"<tr><td>{r}</td><td></td><td></td><td></td></tr>")
    table.append("</tbody></table>")
    _write(outdir, "section_events_tracking.html", "".join(table))


# ---------- assembly + publish ----------

def _write(outdir, name, html):
    path = os.path.join(outdir, name)
    with open(path, "w") as f:
        f.write(html)
    print(f"  wrote {path}")


def assemble(start, end, outdir):
    meeting = (datetime.strptime(end, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    parts = [
        "<table><tbody>",
        f"<tr><th>Date</th><td>{ordinal_date(meeting)}</td></tr>",
        f"<tr><th>Timeframe</th><td>{ordinal_date(start)} to {ordinal_date(end)}</td></tr>",
        "</tbody></table>",
        expand("Table of Contents",
               '<ac:structured-macro ac:name="toc" ac:schema-version="1"/>'),
    ]
    for name in ["section_oncall.html", "section_xcc.html", "section_rtpengine.html",
                 "section_sbc.html", "section_events_tracking.html"]:
        path = os.path.join(outdir, name)
        if os.path.exists(path):
            with open(path) as f:
                parts.append(f.read())
    full = os.path.join(outdir, "page_full.html")
    with open(full, "w") as f:
        f.write("".join(parts))
    print(f"  assembled {full}")
    return full


def upload_attachments(page_html_path):
    sys.path.insert(0, SCRIPTS)
    from confluence_publish import BASE_URL, PAGE_ID, load_credentials
    import base64
    import urllib.request

    with open(page_html_path) as f:
        referenced = set(re.findall(r'ri:filename="([^"]+)"', f.read()))
    pngs = [p for p in glob.glob(os.path.join(SKILL_DIR, "output", "*.png"))
            if os.path.basename(p) in referenced]
    if not pngs:
        return
    username, token = load_credentials()
    auth = "Basic " + base64.b64encode(f"{username}:{token}".encode()).decode()
    for p in pngs:
        fname = os.path.basename(p)
        boundary = uuid.uuid4().hex
        with open(p, "rb") as f:
            content = f.read()
        body = ((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                 f'filename="{fname}"\r\nContent-Type: image/png\r\n\r\n').encode()
                + content + f"\r\n--{boundary}--\r\n".encode())
        # PUT = create-or-update by filename (POST 400s on duplicates)
        req = urllib.request.Request(
            f"{BASE_URL}/rest/api/content/{PAGE_ID}/child/attachment",
            data=body, method="PUT")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        req.add_header("X-Atlassian-Token", "no-check")
        req.add_header("Authorization", auth)
        try:
            urllib.request.urlopen(req, timeout=120)
            print(f"  uploaded attachment {fname}")
        except urllib.error.HTTPError as e:
            sys.exit(f"ERROR: attachment {fname} -> HTTP {e.code}: {e.read().decode()[:300]}")


# ---------- CLI ----------

def parse_args(argv):
    flags = {"publish": True, "outdir": os.path.join(SKILL_DIR, "output")}
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

    if "on-call" in sections:
        oncall_section(outdir)
    if "xcc-metrics" in sections:
        grafana_section("xcc_metrics.yaml", "XCC Metrics (Kamailio)",
                        start, end, regions, "section_xcc.html", outdir)
    if "rtpengine-metrics" in sections:
        grafana_section("rtp_metrics.yaml", "RTP Engine Metrics",
                        start, end, regions, "section_rtpengine.html", outdir)
    if "sbc-metrics" in sections:
        sbc_section(start, end, outdir)

    page = assemble(start, end, outdir)

    if not flags["publish"]:
        print("Done (--no-publish): inspect the HTML files above.")
        return
    upload_attachments(page)
    out = run([sys.executable, os.path.join(SCRIPTS, "confluence_publish.py"),
               start, end, page, "--message", f"test_skill.py run {start}..{end}"])
    print(out.strip())


if __name__ == "__main__":
    main()
