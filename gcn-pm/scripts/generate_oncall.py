#!/usr/bin/env python3
"""Generate the On-Call section (Status Review, On-Call Alarms, Post-Mortem)
plus Events Tracking: tmp/section_oncall.html, tmp/section_events_tracking.html.

Usage:
    generate_oncall.py <sprint_start YYYY-MM-DD> <sprint_end YYYY-MM-DD> [--out DIR]
    generate_oncall.py refresh

On-Call Alarms uses a real Playwright browser (the `playwright` package
directly — not the MCP tool, which only Claude subagents can call) against
the shared Chrome persistent profile (gcn-pm/.auth/profile, same SSO
identity as grafana_metrics.py/kibana_metrics.py `refresh`): navigate to
Jira Ops Alerts, filter rows by the sprint window via a MutationObserver
(handles lazy-loaded batches), screenshot, and embed as an attachment. Any
failure or timeout along that path falls back to the warning panel below
("Fallback — Playwright MCP unavailable") — this is a successful, expected
outcome, not a section failure.

The `refresh` subcommand renews the Atlassian SSO session in the persistent
profile (headless — or opens a visible browser if the session is expired).

Exit 0 with both files written (Playwright success or fallback both count).
Exit 1 only on a fatal error (fatal I/O error) — should not normally happen,
this section has no external auth dependency besides the browser.
"""
import os
import stat
import sys
import time
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
# then waits for the row count to stabilise (1.5s stable, 8s max).
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


def _wait_for_auth(page, timeout_ms=30000):
    """Poll up to timeout_ms for the URL to land on jira/ops/alerts."""
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        page.wait_for_timeout(5000)
        if "jira/ops/alerts" in page.url:
            return True
    print(f"  last URL: {page.url[:120]}", file=sys.stderr)
    return False


def _ensure_session():
    """Ensure a valid Atlassian SSO session exists in the persistent profile.
    Tries headless first; falls back to a visible browser for interactive login.
    Returns True if a session is established, False otherwise."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chrome", headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(ONCALL_NAV_URL, wait_until="domcontentloaded", timeout=60000)
            if _wait_for_auth(page, 30000):
                return True
        finally:
            context.close()

        print("On-Call Alarms: headless session expired — "
              "opening browser for Atlassian login.", file=sys.stderr)
        context = p.chromium.launch_persistent_context(
            PROFILE_DIR, channel="chrome", headless=False)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(ONCALL_NAV_URL, wait_until="domcontentloaded", timeout=60000)
            print("Complete the Atlassian login in the browser window...", file=sys.stderr)
            return _wait_for_auth(page, 180000)
        finally:
            context.close()


def refresh():
    """Refresh Atlassian SSO session in the persistent profile."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.chmod(AUTH_DIR, stat.S_IRWXU)
    if _ensure_session():
        print("OK: Atlassian session valid.")
    else:
        sys.exit("ERROR: Atlassian login did not complete.")


def _capture_oncall_alarms(start, end, outdir):
    """Real Playwright capture of the On-Call Alarms table, filtered to the
    sprint window. Returns the screenshot filename on success, None on any
    failure or timeout (caller renders the documented warning-panel fallback)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("WARN: playwright not installed — using fallback warning panel.", file=sys.stderr)
        return None

    if not _ensure_session():
        print("WARN: On-Call Alarms auth did not complete.", file=sys.stderr)
        return None

    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                PROFILE_DIR, channel="chrome", headless=True)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(ONCALL_NAV_URL, wait_until="domcontentloaded", timeout=60000)
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


def _xml_escape(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _jira_macro(jql, columns, maximum_issues=50):
    """Classic Confluence storage-format Jira Issues macro. Renders as a
    real, live-updating table -- unlike the ADF smart-link "block card" this
    replaces, which only ever resolves client-side and did so unreliably
    (confirmed via a scratch-page test: no server/serverId parameter needed
    since Jira and Confluence share this cloud site)."""
    return ('<ac:structured-macro ac:name="jira" ac:schema-version="1">'
            f'<ac:parameter ac:name="jqlQuery">{_xml_escape(jql)}</ac:parameter>'
            f'<ac:parameter ac:name="columns">{columns}</ac:parameter>'
            f'<ac:parameter ac:name="maximumIssues">{maximum_issues}</ac:parameter>'
            '</ac:structured-macro>')


def _info(items):
    lis = "".join(f"<li><p>{i}</p></li>" for i in items)
    return ('<ac:structured-macro ac:name="info" ac:schema-version="1">'
            f'<ac:rich-text-body><ul>{lis}</ul></ac:rich-text-body></ac:structured-macro>')


STATUS_JQL = 'filter = "production-meetings-interconnect"'
STATUS_COLUMNS = "type,key,summary,status,parent,customfield_10007,assignee,created"

PM_JQL = ('project in (INCIDENT) and type in ("TD Incident") and assignee in '
          "(712020:e99666d8-42ea-4f69-be46-1d96262ac54e, 622745edb7e7c7007159b8df, "
          "712020:3a4c738b-581a-432c-a471-82d7e70c57f6, 5f9fde30632c620071778e2b, "
          "712020:d39b9372-96d2-4be1-98a0-e17ad4292a0c, 60380d934623c60069cfc0ea, "
          "61ead968e2261a0069580f6c, 61d89c7d90cfd20071343f62, 5fba1b20cbead500690e3ffd, "
          "603cac0581a8400068b23bcd, 712020:9baaf1c0-1a40-4795-92ca-f879f03a96fd) "
          "and created >= -90d ORDER BY created DESC")
PM_COLUMNS = "type,key,summary,status,priority,assignee,created"


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
        _jira_macro(STATUS_JQL, STATUS_COLUMNS),
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
        _jira_macro(PM_JQL, PM_COLUMNS),
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
    outdir = os.path.join(SKILL_DIR, "tmp")
    if "--out" in argv:
        i = argv.index("--out")
        outdir = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]

    if argv and argv[0] == "refresh":
        refresh()
        return

    if len(argv) < 2:
        sys.exit(__doc__)
    start, end = argv[0], argv[1]
    for d in (start, end):
        datetime.strptime(d, "%Y-%m-%d")

    os.makedirs(outdir, exist_ok=True)
    oncall_section(start, end, outdir)


if __name__ == "__main__":
    main()
