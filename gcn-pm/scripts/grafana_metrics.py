#!/usr/bin/env python3
"""Grafana/Prometheus pipeline for gcn-pm: auth, fetch, deviation analysis, charts.

Subcommands:
  refresh                       Vouch SSO bootstrap (Playwright). Launches Chrome
                                 (persistent profile under gcn-pm/.auth/profile,
                                 shared with kibana_metrics.py — same SSO identity),
                                 navigates to Grafana, exports the Vouch cookies to
                                 gcn-pm/.auth/grafana_vouch_cookie.txt (chmod 600).
                                 Headless if the profile already has a live session;
                                 opens a visible window for the one-time Google
                                 login otherwise.
  read                           Print the saved Cookie header value (non-zero
                                 exit if missing).
  analyze <config_yaml> <start_epoch_ms> <end_epoch_ms> [region]
                                 Query every active metric in config_yaml over
                                 plain HTTP (Grafana's Prometheus datasource
                                 proxy), detect deviations (P95/MAD/IQR + floor
                                 bypass), render PNG charts, and print the
                                 Confluence Storage HTML snippet.

Data-path code (analyze) must only ever call cookie_header() / `read` — never
drive a browser or prompt for login itself; that's `refresh`'s job alone.
"""
import json
import os
import re
import stat
import sys
import time
import yaml
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import plot_helper

SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AUTH_DIR = os.path.join(SKILL_DIR, ".auth")
PROFILE_DIR = os.path.join(AUTH_DIR, "profile")
COOKIE_FILE = os.path.join(AUTH_DIR, "grafana_vouch_cookie.txt")
OUTPUT_DIR = os.path.join(SKILL_DIR, "output")

GRAFANA_ORIGIN = "https://grafana-general.svc.talkdeskapp.com"
GRAFANA_URL = GRAFANA_ORIGIN + "/"
PROXY_RANGE_PATH = "/api/datasources/proxy/uid/{uid}/api/v1/query_range"
PROXY_INSTANT_PATH = "/api/datasources/proxy/uid/{uid}/api/v1/query"

# Sub-query keys look like "A — User", "B — 4xx only" (single letter, space, dash).
SUBQUERY_KEY = re.compile(r'^[A-Z] [—\-]')

# Direct dashboard URLs only: https://.../d/{uid}/{slug}?...&viewPanel=panel-N
# (or viewPanel=N on older Grafana). /goto/ short-links are not resolved here —
# they must be replaced with their canonical /d/{uid}/... form in the YAML first.
_GRAFANA_DASHBOARD_RE = re.compile(r'/d/([^/]+)/')
_GRAFANA_PANEL_RE = re.compile(r'viewPanel=(?:panel-)?(\d+)')


# ==================== auth ====================

def cookie_header():
    """Return the saved Cookie header value, or raise with refresh instructions."""
    try:
        with open(COOKIE_FILE) as f:
            value = f.read().strip()
    except FileNotFoundError:
        raise RuntimeError(
            f"No Grafana session cookie at {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/grafana_metrics.py refresh"
        )
    if not value:
        raise RuntimeError(
            f"Empty cookie file {COOKIE_FILE} — "
            "run: python3 gcn-pm/scripts/grafana_metrics.py refresh"
        )
    return value


def _export_cookies(context):
    # every cookie the browser would send to the Grafana origin
    # (VouchCookie on .svc.talkdeskapp.com + Grafana's own session, etc.)
    cookies = context.cookies(GRAFANA_ORIGIN)
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
        page.goto(GRAFANA_URL, wait_until="domcontentloaded", timeout=60000)
        # success = the redirect chain lands back on the exact Grafana host;
        # oauth.svc.talkdeskapp.com (the login page) must NOT count
        if headless:
            page.wait_for_timeout(5000)  # allow Vouch redirect chain to settle
            ok = page.url.startswith(GRAFANA_ORIGIN) and _export_cookies(context)
        else:
            print("Complete the Google login in the browser window...")
            ok = False
            for _ in range(36):  # max ~3 min
                page.wait_for_timeout(5000)
                if page.url.startswith(GRAFANA_ORIGIN) and _export_cookies(context):
                    ok = True
                    break
        context.close()
        return ok


def refresh():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.chmod(AUTH_DIR, 0o700)
    if _try_session(headless=True):
        try:
            GrafanaHttpClient()
            return
        except Exception:
            print("Saved cookie invalid for API calls, retrying with visible browser...", file=sys.stderr)
    print("Headless session expired/absent — opening browser for login.")
    if not _try_session(headless=False):
        sys.exit("Login did not complete; no Vouch cookie captured.")
    try:
        GrafanaHttpClient()
    except Exception as e:
        sys.exit(f"Login completed but API validation failed: {e}")


# ==================== HTTP client ====================

class GrafanaHttpClient:
    def __init__(self, origin=GRAFANA_ORIGIN, timeout=60):
        self.origin = origin
        self.timeout = timeout
        self._dashboard_cache = {}
        self._verify_session()

    def _verify_session(self):
        """Eagerly probe the session so a dead/expired cookie raises here, in
        the caller's constructor line — not silently inside the per-query
        try/except in analyze_metric()'s query_prometheus() wrapper, which
        would otherwise turn an auth failure into a false 'no deviation'
        result for every metric (violates the FAIL-FAST rule)."""
        now = int(time.time())
        self._get(PROXY_RANGE_PATH.format(uid="prometheus"),
                  {"query": "up", "start": now - 60, "end": now, "step": 60})

    @staticmethod
    def _fmt_time(t):
        """Prometheus query_range wants Unix epoch seconds."""
        if isinstance(t, (int, float)):
            return int(t)
        raise TypeError(f"expected epoch seconds, got {t!r}")

    def get_dashboard(self, uid):
        """GET /api/dashboards/uid/{uid} → full dashboard JSON, cached per client
        instance so multiple metrics pointing at the same dashboard only fetch once."""
        if uid not in self._dashboard_cache:
            self._dashboard_cache[uid] = self._get_json(f"/api/dashboards/uid/{uid}", {})
        return self._dashboard_cache[uid]

    def query_prometheus(self, datasource_uid, expr, end_time, query_type="instant",
                          start_time=None, step=None):
        """Query Prometheus via Grafana's datasource proxy.

        Returns {"data": {"resultType": ..., "result": [...]}} so callers can do
        res["data"]["result"]. Raises RuntimeError on auth/session failure,
        Exception on any other HTTP/Prometheus error.
        """
        end_s = self._fmt_time(end_time)
        if query_type == "range":
            start_s = self._fmt_time(start_time)
            params = {"query": expr, "start": start_s, "end": end_s, "step": step or 60,
                      "dedup": "true", "max_source_resolution": "auto"}
            return {"data": self._get(PROXY_RANGE_PATH.format(uid=datasource_uid), params)}
        params = {"query": expr, "time": end_s, "dedup": "true", "max_source_resolution": "auto"}
        return {"data": self._get(PROXY_INSTANT_PATH.format(uid=datasource_uid), params)}

    def _get_json(self, path, params):
        """Auth'd GET, SSO-page detection, JSON parse — shared by every endpoint
        (Prometheus proxy, dashboard API), each of which validates its own shape."""
        url = f"{self.origin}{path}?{urlencode(params)}"
        req = Request(url, method="GET")
        req.add_header("Accept", "application/json")
        req.add_header("Cookie", cookie_header())
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            resp = urlopen(req, timeout=self.timeout)
            body = resp.read().decode()
        except HTTPError as e:
            raise Exception(f"grafana: HTTP {e.code}: {e.read().decode()[:300]}")

        if body.lstrip().startswith("<"):
            raise RuntimeError(
                "ERROR: Grafana returned an SSO/login page — session expired. "
                "Run: python3 gcn-pm/scripts/grafana_metrics.py refresh"
            )

        return json.loads(body)

    def _get(self, path, params):
        data = self._get_json(path, params)
        if data.get("status") != "success" or "result" not in data.get("data", {}):
            raise Exception(f"grafana proxy: unexpected response, keys={list(data)[:10]}")
        return data["data"]

    def close(self):
        """No subprocess/connection to tear down — kept as a no-op so
        analyze()'s `finally: client.close()` needs no change."""
        pass


# ==================== analysis ====================

def query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region=None, datasource_uid="prometheus"):
    """
    Query Prometheus via the shared Grafana HTTP client (range query).
    Splits long time ranges into weekly chunks to stay under Grafana's
    11 000 points-per-timeseries limit while keeping 1-minute resolution.

    Returns {"data": {"resultType": ..., "result": [...]}}.

    Per-query failures fall back to an empty result (preserves prior behaviour);
    a dead endpoint is caught earlier at client handshake in main(), which raises.
    """
    if region:
        promql = promql.replace("$region", region)

    step = 60
    start_s = start_epoch_ms // 1000
    end_s = end_epoch_ms // 1000
    chunk_size = 10900 * step  # ~7.57 days

    # Grafana dashboard macro: substitute the total sprint window duration.
    if "$__range" in promql:
        promql = promql.replace("$__range", f"{end_s - start_s}s")

    # Merge key = frozenset of (label, value) pairs, so series with identical
    # labels across chunks are grouped without a dependency on result order.
    merged = {}

    total_chunks = max(1, (end_s - start_s + chunk_size - 1) // chunk_size)
    chunk_i = 0
    chunk_start = start_s
    while chunk_start < end_s:
        chunk_i += 1
        chunk_end = min(chunk_start + chunk_size, end_s)
        print(f"    chunk {chunk_i}/{total_chunks}", file=sys.stderr)
        try:
            res = client.query_prometheus(
                datasource_uid, promql, chunk_end,
                query_type="range", start_time=chunk_start, step=step,
            )
        except Exception as e:
            print(f"WARN: query failed for {region or 'aggregated'} ({chunk_start}..{chunk_end}): {e}", file=sys.stderr)
            chunk_start = chunk_end
            continue

        for series in res.get("data", {}).get("result", []):
            key = frozenset(series.get("metric", {}).items())
            if key not in merged:
                merged[key] = {"metric": series["metric"], "values": []}
            merged[key]["values"].extend(series.get("values", []))

        chunk_start = chunk_end

    if not merged:
        return {"data": {"resultType": "matrix", "result": []}}

    result = []
    for key, entry in merged.items():
        seen = set()
        deduped = []
        for ts, val in entry["values"]:
            if ts not in seen:
                seen.add(ts)
                deduped.append([ts, val])
        entry["values"] = deduped
        result.append({"metric": dict(entry["metric"]), "values": entry["values"]})

    return {"data": {"resultType": "matrix", "result": result}}


def calculate_percentile(values, p):
    """Calculate p-th percentile (0-100)."""
    if not values:
        return 0
    sorted_vals = sorted(values)
    idx = int((p / 100.0) * (len(sorted_vals) - 1))
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


def calculate_mad(values):
    """Calculate median and median absolute deviation."""
    if not values:
        return 0, 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = sorted_vals[n//2] if n % 2 != 0 else (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2.0

    deviations = [abs(x - median) for x in values]
    sorted_devs = sorted(deviations)
    mad = sorted_devs[n//2] if n % 2 != 0 else (sorted_devs[n//2 - 1] + sorted_devs[n//2]) / 2.0

    return median, mad


def calculate_iqr(values):
    """Calculate Q1, Q3, and IQR."""
    if len(values) < 4:
        return 0, 0, 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    q1_idx = n // 4
    q3_idx = (3 * n) // 4
    q1 = sorted_vals[q1_idx]
    q3 = sorted_vals[q3_idx]
    return q1, q3, q3 - q1


def detect_deviation_resource(metric_name, values, threshold_pct=95):
    """Resource metrics: flag if P95 exceeds threshold."""
    if not values:
        return False, 0
    p95 = calculate_percentile(values, threshold_pct)
    return p95 > 80, p95  # hardcoded 80% as example threshold


def detect_deviation_spike(values):
    """Rate/spike metrics: flag if max > median + 3*MAD."""
    if not values:
        return False, 0
    peak_val = max(values)
    median, mad = calculate_mad(values)
    threshold = median + (3 * mad)
    return peak_val > threshold, peak_val


def detect_deviation_state(values):
    """State metrics: flag a jump above median + 2*IQR, or sustained zeros (>50%)."""
    if not values:
        return False, 0
    peak_val = max(values)
    q1, q3, iqr = calculate_iqr(values)
    median = sorted(values)[len(values) // 2]
    if iqr > 0 and peak_val > median + (2 * iqr):
        return True, peak_val
    if sum(1 for v in values if v == 0) > len(values) * 0.5:
        return True, 0
    return False, peak_val


def detect_deviation(deviation_rule, values):
    """Dispatch on the metric's declared deviation type.

    Free-text/baseline rules (no RESOURCE/RATE/STATE keyword) are not
    auto-detected — they need a historical baseline we don't have here — so
    they never false-flag; their data is still fetched and their Grafana link
    published.
    """
    if not values:
        return False, 0
    if 'RESOURCE' in deviation_rule:
        return detect_deviation_resource(None, values)
    if 'RATE' in deviation_rule or 'Spike' in deviation_rule:
        return detect_deviation_spike(values)
    if 'STATE' in deviation_rule:
        return detect_deviation_state(values)
    return False, max(values)


def check_floor(floor_value, floor_op, values):
    """Floor bypass: flag immediately if any point crosses the metric's hard
    floor, without waiting for the statistical rule. `floor_op` picks the
    relevant extreme: gte/gt metrics are bad when a value is too HIGH (check
    max), lt metrics (e.g. MOS) are bad when a value is too LOW (check min).
    """
    if floor_value is None or not values:
        return False
    if floor_op == 'lt':
        return min(values) < floor_value
    if floor_op == 'gt':
        return max(values) > floor_value
    return max(values) >= floor_value  # gte (default)


def series_label(metric):
    """Human label for a series: prefer instance, then a name-ish label."""
    for key in ('instance', 'name', 'metric', 'xheader', '__name__'):
        if metric.get(key):
            return metric[key]
    return 'aggregated'


def series_points(series):
    """Return [(ts, value), ...] for either a range (values) or instant (value) series."""
    raw = series.get('values')
    if raw is None and series.get('value'):
        raw = [series['value']]
    points = []
    for ts, val in (raw or []):
        try:
            points.append((float(ts), float(val)))
        except (ValueError, TypeError):
            continue
    return points


def format_timestamp(epoch_s):
    """Convert a Prometheus timestamp (Unix epoch seconds) to ISO format."""
    return datetime.fromtimestamp(float(epoch_s), tz=timezone.utc).strftime('%Y-%m-%dT%H:%MZ')


def build_grafana_url(base_url, region, start_ms, end_ms):
    """Build parameterized Grafana URL."""
    return f"{base_url}&var-region={region}&from={start_ms}&to={end_ms}"


def slugify(text):
    """lowercase, non-alphanumeric -> underscore (matches existing chart_<region>_<slug>.png convention)."""
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def format_points(points):
    """[(epoch_s, val), ...] -> plot_helper's expected [{"x": "YYYY-MM-DD HH:MM", "y": val}, ...].

    plot_helper's parser only accepts a bare date or '%Y-%m-%d %H:%M' (space,
    not ISO 'T'/'Z') — feeding it anything else silently falls back to a string
    x-axis.
    """
    return [
        {"x": datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%Y-%m-%d %H:%M'), "y": val}
        for ts, val in points
    ]


def slice_zoom(points, center_ts, window_s=1800):
    """Points within center_ts +/- window_s (default 30 min)."""
    return [(ts, v) for ts, v in points if center_ts - window_s <= ts <= center_ts + window_s]


def generate_chart(title, out_path, unit, payload):
    """Render via plot_helper.render_chart(). Never raises: a broken chart
    must not fail the metric."""
    try:
        plot_helper.render_chart(title, out_path, "Time", unit, payload)
        return True
    except Exception as e:
        print(f"WARN: chart generation failed for '{title}': {e}", file=sys.stderr)
        return False


def parse_grafana_url(url):
    """Extract (dashboard_uid, panel_id) from a direct Grafana dashboard URL
    (.../d/{uid}/{slug}?...&viewPanel=panel-N or ...viewPanel=N).

    Returns (uid, None) if there's no viewPanel, or (None, None) if this isn't
    a direct dashboard URL at all (e.g. a /goto/ short-link — those are not
    resolved here, see module docstring).
    """
    m = _GRAFANA_DASHBOARD_RE.search(url or '')
    if not m:
        return None, None
    uid = m.group(1)
    panel_m = _GRAFANA_PANEL_RE.search(url)
    return uid, (int(panel_m.group(1)) if panel_m else None)


def extract_panel_queries(dashboard_json, panel_id):
    """[(sub_label, expr), ...] for the panel with id == panel_id, from its
    targets[]. sub_label is "{refId} — {legendFormat or refId}", matching the
    "A — 4xx only" convention SUBQUERY_KEY/analyze_metric already expect.

    Recurses into row panels (panels[].panels[]) since Grafana nests panels
    under collapsed rows. Raises KeyError if no panel with that id exists.
    """
    def walk(items):
        for p in items:
            if p.get("type") == "row" and "panels" in p:
                yield from walk(p["panels"])
            else:
                yield p

    panels = dashboard_json.get("dashboard", {}).get("panels", [])
    for p in walk(panels):
        if p.get("id") == panel_id:
            queries = []
            for t in p.get("targets", []):
                if not t.get("expr"):
                    continue
                label = t.get("legendFormat") or t.get("refId", "?")
                queries.append((f"{t.get('refId', '?')} — {label}", t["expr"]))
            return queries
    raise KeyError(f"panel {panel_id} not found")


def resolve_panel_queries(client, grafana_url, metric_name, section):
    """(sub_label, promql) pairs fetched live from the metric's Grafana panel,
    or [] if the URL isn't a resolvable direct dashboard link (goto short-link,
    no viewPanel, or the panel/dashboard lookup fails) — caller falls back to
    an explicit `promql:` in that case, or skips the metric with a warning."""
    uid, panel_id = parse_grafana_url(grafana_url)
    if not uid or panel_id is None:
        return []
    try:
        dashboard = client.get_dashboard(uid)
        return extract_panel_queries(dashboard, panel_id)
    except Exception as e:
        print(f"WARN: {section} {metric_name}: could not resolve panel queries "
              f"from {grafana_url}: {e}", file=sys.stderr)
        return []


def analyze_metric(client, metric_name, config, start_epoch_ms, end_epoch_ms, region, section="xcc"):
    """Analyze one metric and return HTML for its deviated series (or None).

    Query source, in priority order:
    1. an explicit `promql:` in the YAML (single query, or legacy A/B/C… keys
       for configs not yet migrated) — used as-is, unchanged behaviour.
    2. otherwise, live sub-queries fetched from the metric's Grafana panel
       (config['grafana'] must be a direct .../d/{uid}/...&viewPanel=N URL,
       not a /goto/ short-link — see parse_grafana_url).
    Each query result is grouped under the metric's deviation rule; sub-query
    results are labelled by their key so the reader sees which dimension
    (e.g. "A — 4xx only") deviated.
    """
    print(f"  checking {section} {metric_name} deviation", file=sys.stderr)
    deviation_rule = config.get('deviation', '')
    unit = config.get('unit', '')
    floor_value = config.get('floor_value')
    floor_op = config.get('floor_op', 'gte')
    is_state = 'STATE' in deviation_rule

    # Build the list of (sub-label, promql) to run.
    queries = []
    main = config.get('promql', '')
    if isinstance(main, str) and main.strip():
        queries.append((None, main))
    for key, val in config.items():
        if isinstance(key, str) and SUBQUERY_KEY.match(key) and isinstance(val, str) and val.strip():
            queries.append((key, val))

    if not queries:
        queries = resolve_panel_queries(client, config.get('grafana', ''), metric_name, section)

    if not queries:
        print(f"  skipping {section} {metric_name}: no promql and no resolvable "
              f"Grafana panel", file=sys.stderr)
        return None

    groups = []  # (sub_label, [ {instance, peak, timestamp, points} ])
    for sub_label, promql in queries:
        print(f"  querying data to {section} {metric_name}", file=sys.stderr)
        res = query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region)
        deviated = []
        for series in res.get('data', {}).get('result', []):
            points = series_points(series)
            if not points:
                continue
            values = [v for _, v in points]
            peak_ts, peak_val = max(points, key=lambda p: p[1])
            # Floor bypass short-circuits the statistical rule (checked first).
            flagged = check_floor(floor_value, floor_op, values) or detect_deviation(deviation_rule, values)[0]
            if flagged:
                deviated.append({
                    "instance": series_label(series.get('metric', {})),
                    "peak": peak_val,
                    "timestamp": peak_ts,
                    "points": points,
                })
        if deviated:
            groups.append((sub_label, deviated))

    if not groups:
        print(f"  done {section} {metric_name} (no deviation)", file=sys.stderr)
        return None

    print(f"  building {section} {metric_name}", file=sys.stderr)
    metric_slug = slugify(metric_name)

    html_output = ""
    for sub_label, deviated in groups:
        title = metric_name if not sub_label else f"{metric_name} — {sub_label}"
        reference = deviated[0]['peak']
        html_output += f"<p><strong>{title} deviation detected</strong></p>\n"
        html_output += f"<p>Reference = {reference:.2f} {unit}</p>\n"
        html_output += "<ul>\n"
        for dev in deviated:
            timestamp_str = format_timestamp(dev['timestamp']) if dev['timestamp'] else "N/A"
            html_output += f"  <li>{dev['instance']}: peak {dev['peak']:.2f} {unit} at {timestamp_str}</li>\n"
        html_output += "</ul>\n"

        # STATE metrics never get a chart (blanket-skip; matches rtpengine-metrics.md's
        # existing rule, resolves xcc-metrics.md's line 198 vs 240 contradiction).
        if is_state:
            continue

        group_slug = metric_slug if not sub_label else f"{metric_slug}_{slugify(sub_label)}"
        region_tag = region or "all"

        overview_payload = {
            "lines": [{"label": dev["instance"], "points": format_points(dev["points"])} for dev in deviated],
            "threshold": {"label": "Reference", "value": reference},
        }
        overview_path = os.path.join(OUTPUT_DIR, f"chart_{region_tag}_{group_slug}.png")
        if generate_chart(title, overview_path, unit, overview_payload):
            html_output += (
                f'<ac:image ac:align="center" ac:width="950">'
                f'<ri:attachment ri:filename="{os.path.basename(overview_path)}"/></ac:image>\n'
            )

            # Zoom chart: peak +/- 30 min around the primary (first) deviated series' event.
            center_ts = deviated[0]['timestamp']
            zoom_lines = []
            for dev in deviated:
                zoomed = slice_zoom(dev['points'], center_ts)
                if len(zoomed) >= 3:
                    zoom_lines.append({"label": dev["instance"], "points": format_points(zoomed)})
            if zoom_lines:
                zoom_payload = {"lines": zoom_lines, "threshold": {"label": "Reference", "value": reference}}
                zoom_path = os.path.join(OUTPUT_DIR, f"chart_{region_tag}_{group_slug}_zoom.png")
                if generate_chart(f"{title} (zoom)", zoom_path, unit, zoom_payload):
                    html_output += (
                        f'<ac:image ac:align="center" ac:width="950">'
                        f'<ri:attachment ri:filename="{os.path.basename(zoom_path)}"/></ac:image>\n'
                    )

    return html_output


def analyze(config_file, start_epoch_ms, end_epoch_ms, region=None):
    """Run the full fetch + deviation-detection + chart pipeline for every
    active metric in config_file. Returns the Confluence Storage HTML block."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    all_html = ""
    has_deviation = False

    # One client/session per invocation, reused across all metrics.
    # A dead endpoint raises here (FAIL-FAST) instead of masking as "no deviation".
    section = "xcc" if "xcc" in os.path.basename(config_file).lower() else "rtpengine"
    client = GrafanaHttpClient()
    try:
        for metric_name, cfg in config.items():
            if cfg.get('status') == 'active':
                result = analyze_metric(client, metric_name, cfg, start_epoch_ms, end_epoch_ms, region, section)
                if result:
                    all_html += result
                    has_deviation = True
    finally:
        client.close()

    # Build final region block. Section + base link derive from the config
    # (was hardcoded to RTPEngine, which mislabelled XCC runs).
    section = "RTPEngine" if "rtp" in os.path.basename(config_file).lower() else "XCC"
    grafana_base = next(
        (cfg.get('grafana') for cfg in config.values()
         if isinstance(cfg, dict) and cfg.get('status') == 'active' and cfg.get('grafana')),
        "https://grafana-general.svc.talkdeskapp.com",
    )
    grafana_link = build_grafana_url(grafana_base, region, start_epoch_ms, end_epoch_ms) if region else grafana_base

    final_html = f'<p><a href="{grafana_link}">Grafana — {section} {region}</a></p>\n'

    if has_deviation:
        final_html += all_html
    else:
        final_html += "<p>No deviation detected ✅</p>\n"

    return final_html


# ==================== CLI ====================

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "refresh":
        refresh()
    elif mode == "read":
        try:
            print(cookie_header())
        except RuntimeError as e:
            sys.exit(f"{e}")
    elif mode == "analyze":
        if len(sys.argv) < 5:
            sys.exit("Usage: grafana_metrics.py analyze <config_yaml> <start_epoch_ms> <end_epoch_ms> [region]")
        config_file = sys.argv[2]
        start_epoch_ms = int(sys.argv[3])
        end_epoch_ms = int(sys.argv[4])
        region = sys.argv[5] if len(sys.argv) > 5 else None
        try:
            print(analyze(config_file, start_epoch_ms, end_epoch_ms, region))
        except Exception as e:
            sys.exit(f"Error: {e}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
