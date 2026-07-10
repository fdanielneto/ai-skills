#!/usr/bin/env python3
"""Assemble + publish the GCN PM page to Confluence via REST + storage representation.

Usage:
    confluence_publish.py <sprint_start> <sprint_end> [--message "..."] \\
        [--out DIR] [--no-publish]

Reads whichever of output/section_{oncall,xcc,rtpengine,sbc,events_tracking}.html
exist under --out (default gcn-pm/output), assembles the header table + Table
of Contents + sections in canonical order into output/page_full.html, uploads
any referenced PNG attachments, PUTs the full body to the fixed GCN PM Auto
Test page, and runs the post-publish verification gate.

--no-publish: assemble page_full.html and run verify() against it locally,
skipping the attachment upload and REST PUT (for standalone testing).

Single attempt only — on any failure, prints the error and exits non-zero. No
retries: retrying automatically is what caused the orchestrator loop this
script is meant to fix.
"""
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timedelta

BASE_URL = "https://talkdesk.atlassian.net/wiki"
PAGE_ID = "6568476792"
TITLE = "GCN PM Auto Test"
SECRETS_FILE = os.path.expanduser("~/.env.secrets")

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

SECTION_ORDER = ["section_oncall.html", "section_xcc.html", "section_rtpengine.html",
                 "section_sbc.html", "section_events_tracking.html"]


def load_credentials():
    username = os.environ.get("ATLASSIAN_USERNAME")
    token = os.environ.get("ATLASSIAN_API_TOKEN")
    if username and token:
        return username, token

    if os.path.exists(SECRETS_FILE):
        with open(SECRETS_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("ATLASSIAN_USERNAME="):
                    username = username or line.split("=", 1)[1].strip('"\'')
                elif line.startswith("ATLASSIAN_API_TOKEN="):
                    token = token or line.split("=", 1)[1].strip('"\'')

    if not username or not token:
        sys.exit(
            "ERROR: missing ATLASSIAN_USERNAME/ATLASSIAN_API_TOKEN "
            f"(checked env and {SECRETS_FILE})"
        )
    return username, token


def request(method, path, username, token, body=None):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    creds = f"{username}:{token}".encode()
    import base64

    req.add_header("Authorization", "Basic " + base64.b64encode(creds).decode())
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"ERROR: {method} {path} -> HTTP {e.code}: {e.read().decode()[:500]}")


def verify(storage_value):
    for m in re.finditer(r"data-datasource", storage_value):
        astart = storage_value.rfind("<a ", 0, m.start())
        # 100 chars comfortably fits `<p local-id="<uuid-v4>" />` (~53 chars) plus whitespace.
        pre = storage_value[max(0, astart - 100):astart]
        if "<p local-id=" not in pre:
            sys.exit("ERROR: verification failed — missing <p local-id/> before a datasource card")
    for tag in re.finditer(r"<ac:image[^>]*>", storage_value):
        if 'ac:align="center"' not in tag.group():
            sys.exit("ERROR: verification failed — ac:image not centered")


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
    found = False
    for name in SECTION_ORDER:
        path = os.path.join(outdir, name)
        if os.path.exists(path):
            found = True
            with open(path) as f:
                parts.append(f.read())
    if not found:
        sys.exit(f"ERROR: no section_*.html found under {outdir} — nothing to publish")

    full = os.path.join(outdir, "page_full.html")
    with open(full, "w") as f:
        f.write("".join(parts))
    print(f"  assembled {full}")
    return full


def upload_attachments(page_html_path):
    with open(page_html_path) as f:
        referenced = set(re.findall(r'ri:filename="([^"]+)"', f.read()))
    pngs = [p for p in glob.glob(os.path.join(SKILL_DIR, "output", "*.png"))
            if os.path.basename(p) in referenced]
    if not pngs:
        return
    print(f"uploading {len(pngs)} images...", file=sys.stderr)
    username, token = load_credentials()
    import base64
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


def main():
    argv = list(sys.argv[1:])
    outdir = os.path.join(SKILL_DIR, "output")
    if "--out" in argv:
        i = argv.index("--out")
        outdir = os.path.abspath(argv[i + 1])
        del argv[i:i + 2]
    no_publish = "--no-publish" in argv
    if no_publish:
        argv.remove("--no-publish")
    message = None
    if "--message" in argv:
        i = argv.index("--message")
        message = argv[i + 1]
        del argv[i:i + 2]

    if len(argv) < 2:
        sys.exit(f"Usage: {sys.argv[0]} <sprint_start> <sprint_end> [--message MSG] [--out DIR] [--no-publish]")
    sprint_start, sprint_end = argv[0], argv[1]
    message = message or f"gcn-pm run {sprint_start} to {sprint_end}"

    page = assemble(sprint_start, sprint_end, outdir)
    with open(page) as f:
        storage_value = f.read()

    if no_publish:
        verify(storage_value)
        print("OK (--no-publish): assembled + verified locally, skipped upload/PUT.")
        return

    upload_attachments(page)

    username, token = load_credentials()
    current = request("GET", f"/rest/api/content/{PAGE_ID}?expand=version", username, token)
    next_version = current["version"]["number"] + 1

    print(f"publishing version {next_version}...", file=sys.stderr)
    payload = {
        "version": {"number": next_version, "message": message},
        "type": "page",
        "title": TITLE,
        "body": {"storage": {"value": storage_value, "representation": "storage"}},
    }
    request("PUT", f"/rest/api/content/{PAGE_ID}", username, token, payload)

    published = request(
        "GET", f"/rest/api/content/{PAGE_ID}?expand=body.storage", username, token
    )
    verify(published["body"]["storage"]["value"])

    print(f"OK: published version {next_version} to {BASE_URL}/pages/viewpage.action?pageId={PAGE_ID}")


if __name__ == "__main__":
    main()
