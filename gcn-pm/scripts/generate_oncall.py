#!/usr/bin/env python3
"""Generate the On-Call section (Status Review, On-Call Alarms, Post-Mortem)
plus Events Tracking: output/section_oncall.html, output/section_events_tracking.html.

Usage:
    generate_oncall.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> [--out DIR]

On-Call Alarms uses a real Playwright browser (the `playwright` package
directly — not the MCP tool, which only Claude subagents can call) against
the shared Chrome persistent profile (gcn-pm/.auth/profile, same SSO
identity as grafana_metrics.py/kibana_metrics.py `refresh`): navigate to
Jira Ops Alerts, filter rows by the sprint window via a MutationObserver
(handles lazy-loaded batches), screenshot, and embed as an attachment. Any
failure or timeout along that path falls back to the documented warning
panel (references/on-call.md, "Fallback — Playwright MCP unavailable") —
this is a successful, expected outcome, not a section failure.

Exit 0 with both files written (Playwright success or fallback both count).
Exit 1 only on a fatal error (fatal I/O error) — should not normally happen,
this section has no external auth dependency besides the browser.
"""
import os
import sys
import uuid
from datetime import datetime

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.normpath(os.path.join(SCRIPTS, ".."))
AUTH_DIR = os.path.join(SKILL_DIR, ".auth")
PROFILE_DIR = os.path.join(AUTH_DIR, "profile")

ONCALL_URL = ("https://talkdesk.atlassian.net/jira/ops/alerts?view=list&amp;"
              "query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22")
ONCALL_NAV_URL = ("https://talkdesk.atlassian.net/jira/ops/alerts?view=list&"
                   "query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22")

# Re-applies the sprint-window row filter on every lazy-load batch (MutationObserver),
# then waits for the row count to stabilise (1.5s stable, 8s max) — see
# references/on-call.md "Step 2 — Filter by sprint dates (resilient lazy-load filter)".
FILTER_JS = """() => {{
  const start = new Date('{start}T00:00:00');
  const end   = new Date('{end}T23:59:59');

  function applyFilter() {{
    const rows = [...document.querySelectorAll('table tbody tr')];
    let visible = 0;
    for (const r of rows) {{
      const raw = r.querySelector('td:nth-child(8)')?.textContent?.trim();
      const d = new Date(raw);
      if (isNaN(d))             {{ r.style.display = 'none'; continue; }}
      if (d < start || d > end) {{ r.style.display = 'none'; continue; }}
      r.style.display = '';
      visible++;
    }}
    return visible;
  }}

  const tbody = document.querySelector('table tbody');
  const obs = new MutationObserver(() => applyFilter());
  if (tbody) obs.observe(tbody, {{ childList: true, subtree: true }});

  return new Promise((resolve) => {{
    let last = -1, stableMs = 0;
    const t0 = Date.now();
    const tick = () => {{
      const n = document.querySelectorAll('table tbody tr').length;
      applyFilter();
      if (n === last) {{ stableMs += 250; }} else {{ stableMs = 0; last = n; }}
      if (stableMs >= 1500 || Date.now() - t0 >= 8000) {{
        obs.disconnect();
        resolve(applyFilter());
        return;
      }}
      setTimeout(tick, 250);
    }};
    tick();
  }});
}}"""


def _capture_oncall_alarms(start, end, outdir):
    """Real Playwright capture of the On-Call Alarms table, filtered to the
    sprint window. Returns the screenshot filename on success, None on any
    failure or timeout (caller renders the documented warning-panel fallback)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("WARN: playwright not installed — using fallback warning panel.", file=sys.stderr)
        return None

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                PROFILE_DIR, channel="chrome", headless=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(ONCALL_NAV_URL, wait_until="domcontentloaded", timeout=60000)

                # Auth guard: poll up to 30s for the URL to land on jira/ops/alerts.
                # Always wait before the first check too — like grafana_metrics.py's
                # _try_session, a client-side auth redirect can fire after
                # domcontentloaded, so an immediate check can pass prematurely.
                ok = False
                for _ in range(6):
                    page.wait_for_timeout(5000)
                    if "jira/ops/alerts" in page.url:
                        ok = True
                        break
                if not ok:
                    print("WARN: On-Call Alarms auth did not complete in 30s.", file=sys.stderr)
                    return None

                page.wait_for_selector("table tbody", timeout=15000)
                page.evaluate(FILTER_JS.format(start=start, end=end))

                fname = f"oncall-alerts-{start}_{end}.png"
                path = os.path.join(outdir, fname)
                page.screenshot(path=path)
                return fname
            finally:
                context.close()
    except Exception as e:
        print(f"WARN: On-Call Alarms Playwright capture failed: {e}", file=sys.stderr)
        return None


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


def oncall_section(start, end, outdir):
    shot = _capture_oncall_alarms(start, end, outdir)
    if shot:
        alarms_evidence = (f'<ac:image ac:align="center" ac:width="760">'
                            f'<ri:attachment ri:filename="{shot}"/></ac:image>')
    else:
        alarms_evidence = (
            '<ac:structured-macro ac:name="warning" ac:schema-version="1"><ac:rich-text-body>'
            "<p><em>Live alert data was not collected in this run (Playwright tool unavailable). "
            "See link above.</em></p></ac:rich-text-body></ac:structured-macro>")

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
        alarms_evidence,
        "<h1>Post-Mortem (last 90 days)</h1>",
        _info([
            "Link all relevant post-mortems to the meeting documentation for easy reference.",
            "Use insights from post-mortems to prevent similar incidents in the future.",
        ]),
        _blockcard(PM_HREF, PM_DS),
    ]
    path = os.path.join(outdir, "section_oncall.html")
    with open(path, "w") as f:
        f.write("".join(parts))
    print(f"  wrote {path}")

    rows = ["EMS Alarms Analysis", "Ribbon Licenses", "…", "", "", "", ""]
    table = ["<h1>Events Tracking</h1>", "<table><tbody>",
             "<tr><th>Checkpoints</th><th>Description</th><th>Action</th><th>Date</th></tr>"]
    for r in rows:
        table.append(f"<tr><td>{r}</td><td></td><td></td><td></td></tr>")
    table.append("</tbody></table>")
    path = os.path.join(outdir, "section_events_tracking.html")
    with open(path, "w") as f:
        f.write("".join(table))
    print(f"  wrote {path}")


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

    os.makedirs(outdir, exist_ok=True)
    oncall_section(start, end, outdir)


if __name__ == "__main__":
    main()
