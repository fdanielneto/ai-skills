#!/usr/bin/env python3
"""Publish the GCN PM page to Confluence via REST + storage representation.

Usage:
    confluence_publish.py <sprint_start> <sprint_end> <storage_html_path> [--message "..."]

Reads the fully-assembled Confluence Storage HTML body from
<storage_html_path>, PUTs it to the fixed GCN PM Auto Test page, and runs
the post-publish verification gate from references/publish.md. Single
attempt only — on any failure, prints the error and exits non-zero. No
retries: retrying automatically is what caused the orchestrator loop this
script is meant to fix.
"""
import json
import os
import re
import sys
import urllib.error
import urllib.request

BASE_URL = "https://talkdesk.atlassian.net/wiki"
PAGE_ID = "6568476792"
TITLE = "GCN PM Auto Test"
SECRETS_FILE = os.path.expanduser("~/.env.secrets")


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
        pre = storage_value[max(0, astart - 50):astart]
        if "<p local-id=" not in pre:
            sys.exit("ERROR: verification failed — missing <p local-id/> before a datasource card")
    for tag in re.finditer(r"<ac:image[^>]*>", storage_value):
        if 'ac:align="center"' not in tag.group():
            sys.exit("ERROR: verification failed — ac:image not centered")


def main():
    if len(sys.argv) < 4:
        sys.exit(f"Usage: {sys.argv[0]} <sprint_start> <sprint_end> <storage_html_path> [--message MSG]")

    sprint_start, sprint_end, html_path = sys.argv[1], sys.argv[2], sys.argv[3]
    message = f"gcn-pm run {sprint_start} to {sprint_end}"
    if "--message" in sys.argv:
        message = sys.argv[sys.argv.index("--message") + 1]

    if not os.path.exists(html_path):
        sys.exit(f"ERROR: storage HTML file not found: {html_path}")
    with open(html_path) as f:
        storage_value = f.read()

    username, token = load_credentials()

    current = request("GET", f"/rest/api/content/{PAGE_ID}?expand=version", username, token)
    next_version = current["version"]["number"] + 1

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
