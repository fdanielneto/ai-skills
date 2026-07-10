#!/usr/bin/env python3
"""Vouch SSO session bootstrap for kibana-logging.svc.talkdeskapp.com.

Two modes:
  kibana_auth.py refresh   Launch Chrome (persistent profile under gcn-pm/.auth/profile),
                           navigate to Kibana, export the Vouch cookies to
                           gcn-pm/.auth/vouch_cookie.txt (chmod 600).
                           Headless if the profile already has a live session;
                           opens a visible window for the one-time Google login otherwise.
  kibana_auth.py read      Print the saved Cookie header value (non-zero exit if missing).

Data-path scripts must only ever call cookie_header() / `read` — never drive
a browser or prompt for login themselves.
"""
import os
import stat
import sys

AUTH_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".auth"))
PROFILE_DIR = os.path.join(AUTH_DIR, "profile")
COOKIE_FILE = os.path.join(AUTH_DIR, "vouch_cookie.txt")

KIBANA_ORIGIN = "https://kibana-logging.svc.talkdeskapp.com"
KIBANA_URL = KIBANA_ORIGIN + "/app/home"


def cookie_header():
    """Return the saved Cookie header value, or raise with refresh instructions."""
    try:
        with open(COOKIE_FILE) as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"No Kibana session cookie at {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/kibana_auth.py refresh"
        )
    if not value:
        raise RuntimeError(
            f"Empty cookie file {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/kibana_auth.py refresh"
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


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "refresh":
        refresh()
    elif mode == "read":
        try:
            print(cookie_header())
        except RuntimeError as e:
            sys.exit(f"{e}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
