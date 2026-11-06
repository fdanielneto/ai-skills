#!/usr/bin/env python3
"""Credential resolution for the gcn-pm data sources.

Unattended / remote runs authenticate with tokens from the environment. When
the token variable is unset, callers fall back to the Vouch cookie file written
by the interactive Playwright `refresh` flow (local use only).

Secret values are never logged or placed in exception messages; only variable
and file names are.
"""
import os
from typing import NamedTuple

GRAFANA_TOKEN_ENV = "GRAFANA_TOKEN"        # Grafana service-account token (Bearer)
KIBANA_API_KEY_ENV = "KIBANA_API_KEY"      # Elasticsearch API key, base64 "id:key" (ApiKey)
ATLASSIAN_USERNAME_ENV = "ATLASSIAN_USERNAME"
ATLASSIAN_TOKEN_ENV = "ATLASSIAN_API_TOKEN"

SECRETS_FILE = os.path.expanduser("~/.env.secrets")


class MissingCredentials(RuntimeError):
    """No usable credential was found for a service."""


class Auth(NamedTuple):
    headers: dict
    # True only for the cookie flow: an expired session can be renewed by
    # launching Playwright. Token auth cannot be renewed in-process, so callers
    # must not attempt a browser refresh (there is no browser on a remote runner).
    refreshable: bool


def _env(name):
    value = os.environ.get(name, "").strip()
    return value or None


def _read_cookie(cookie_file, refresh_hint):
    try:
        with open(cookie_file) as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise MissingCredentials(f"No session cookie at {cookie_file} — run: {refresh_hint}")
    if not value:
        raise MissingCredentials(f"Empty cookie file {cookie_file} — run: {refresh_hint}")
    return value


def resolve(token_env, scheme, cookie_file, refresh_hint):
    """Token from `token_env` as `Authorization: <scheme> <token>`, else the cookie file."""
    token = _env(token_env)
    if token:
        return Auth({"Authorization": f"{scheme} {token}"}, refreshable=False)
    try:
        cookie = _read_cookie(cookie_file, refresh_hint)
    except MissingCredentials as e:
        raise MissingCredentials(f"{e} (or set {token_env})") from None
    return Auth({"Cookie": cookie}, refreshable=True)


def grafana(cookie_file, refresh_hint):
    return resolve(GRAFANA_TOKEN_ENV, "Bearer", cookie_file, refresh_hint)


def kibana(cookie_file, refresh_hint):
    return resolve(KIBANA_API_KEY_ENV, "ApiKey", cookie_file, refresh_hint)


def _from_secrets_file(path, names):
    found = {}
    if not os.path.exists(path):
        return found
    with open(path) as f:
        for line in f:
            line = line.strip()
            for name in names:
                if line.startswith(name + "="):
                    found[name] = line.split("=", 1)[1].strip("\"'")
    return found


def atlassian_credentials(secrets_file=SECRETS_FILE):
    """(username, api_token) for Confluence/Jira Basic auth: environment first,
    then `secrets_file`. Raises MissingCredentials naming only the variables."""
    names = (ATLASSIAN_USERNAME_ENV, ATLASSIAN_TOKEN_ENV)
    values = {n: _env(n) for n in names}
    if not all(values.values()):
        from_file = _from_secrets_file(secrets_file, names)
        values = {n: values[n] or from_file.get(n) for n in names}
    if not all(values.values()):
        raise MissingCredentials(
            f"missing {ATLASSIAN_USERNAME_ENV}/{ATLASSIAN_TOKEN_ENV} "
            f"(checked env and {secrets_file})")
    return values[ATLASSIAN_USERNAME_ENV], values[ATLASSIAN_TOKEN_ENV]
