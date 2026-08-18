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
  analyze <config_yaml> <start_epoch_ms> <end_epoch_ms> [region] [--metric slug[,slug...]] [--debug]
                                 Query every active metric in config_yaml over
                                 plain HTTP (Grafana's Prometheus datasource
                                 proxy), detect deviations (P95/floor bypass,
                                 or for SPIKE metrics a day-of-week x hour-of-day
                                 seasonal baseline — see build_seasonal_baseline;
                                 baseline history is cached incrementally under
                                 gcn-pm/.baseline_cache/), render PNG charts, and
                                 print the Confluence Storage HTML snippet.
                                 --debug prints the bucket/threshold that gated
                                 each flagged SPIKE series to stderr.

Data-path code (analyze) must only ever call cookie_header() / `read` — never
drive a browser or prompt for login itself; that's `refresh`'s job alone.
"""
import hashlib
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
from regions import REGION_TOKENS


class GrafanaHTTPError(Exception):
    """HTTP error from the Grafana proxy/dashboard API, carrying the actual
    status code so callers can branch on 404/401 instead of string-matching."""
    def __init__(self, status_code, message):
        self.status_code = status_code
        super().__init__(message)


SKILL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
AUTH_DIR = os.path.join(SKILL_DIR, ".auth")
PROFILE_DIR = os.path.join(AUTH_DIR, "profile")
COOKIE_FILE = os.path.join(AUTH_DIR, "grafana_vouch_cookie.txt")
OUTPUT_DIR = os.path.join(SKILL_DIR, "tmp")
BASELINE_CACHE_DIR = os.path.join(SKILL_DIR, ".baseline_cache")

# SPIKE seasonal baseline model defaults (see build_seasonal_baseline).
BASELINE_WEEKS_DEFAULT = 8      # minimum history before a bucket is "trusted"
MAX_BASELINE_WEEKS = 26         # cache prune cap (~6 months)
BAND_K_DEFAULT = 4.0            # confidence-band multiplier on bucket MAD
MIN_BUCKET_SAMPLES = 20         # below this, fall back to the series' global stats
MAD_FLOOR_FRACTION = 0.10       # mad_eff floor: 10% of the expected level
MAD_ABS_FLOOR = 0.05            # mad_eff floor: absolute minimum (metric units)

DEBUG_SEASONAL = False          # set by `analyze --debug`; prints bucket stats for flagged SPIKE series

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
            raise GrafanaHTTPError(e.code, f"grafana: HTTP {e.code}: {e.read().decode()[:300]}")

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

    Returns {"data": {"resultType": ..., "result": [...]}, "failed_ranges": [(start_s, end_s), ...]}.

    Per-query failures fall back to an empty result (preserves prior behaviour);
    a dead endpoint is caught earlier at client handshake in main(), which raises.
    Failed chunks are reported back via "failed_ranges" so incremental callers
    (fetch_baseline_points_cached) can avoid marking that span as fetched.
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

    # Grafana interval macros: panels extracted via panel_id embed these in
    # range-vectors (e.g. rate(...[$__rate_interval])). The datasource proxy does
    # not expand them, so the literal '$' reaches Prometheus and fails parsing.
    # Resolve them from `step`. Order matters: replace the more specific *_ms and
    # rate_interval variants before $__interval, otherwise $__interval matches the
    # shared prefix inside $__interval_ms / $__rate_interval.
    #
    # rate_interval is floored at 900s (not just 4*step): confirmed live against
    # the Thanos-backed datasource that samples older than ~1 week (outside raw
    # retention) are spaced further apart than the raw scrape interval, so a
    # 240s (4*step) window finds fewer than the 2 samples rate() needs and
    # silently returns empty — even though the counter has data. 600s was the
    # empirically-confirmed minimum that recovered data; 900s adds margin.
    rate_interval_s = max(4 * step, 900)
    promql = (
        promql.replace("$__rate_interval_ms", str(rate_interval_s * 1000))
        .replace("$__interval_ms", str(step * 1000))
        .replace("$__rate_interval", f"{rate_interval_s}s")
        .replace("$__interval", f"{step}s")
    )

    # Merge key = frozenset of (label, value) pairs, so series with identical
    # labels across chunks are grouped without a dependency on result order.
    merged = {}
    failed_ranges = []

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
            failed_ranges.append((chunk_start, chunk_end))
            chunk_start = chunk_end
            continue

        for series in res.get("data", {}).get("result", []):
            key = frozenset(series.get("metric", {}).items())
            if key not in merged:
                merged[key] = {"metric": series["metric"], "values": []}
            merged[key]["values"].extend(series.get("values", []))

        chunk_start = chunk_end

    if not merged:
        return {"data": {"resultType": "matrix", "result": []}, "failed_ranges": failed_ranges}

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

    return {"data": {"resultType": "matrix", "result": result}, "failed_ranges": failed_ranges}


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


def detect_deviation_spike(values):
    """Rate/spike metrics: flag if max > median + 3*MAD.
    Returns (flagged, peak_val, spike_threshold)."""
    if not values:
        return False, 0, 0
    peak_val = max(values)
    median, mad = calculate_mad(values)
    threshold = median + (3 * mad)
    return peak_val > threshold, peak_val, threshold


def _eta_squared(points, group_key_fn):
    """Fraction of total variance in points' values explained by group_key_fn(ts).
    Used only to report which seasonality (daily vs weekly) dominates — not a
    gating input."""
    if not points:
        return 0.0
    values = [v for _, v in points]
    grand_mean = sum(values) / len(values)
    ss_total = sum((v - grand_mean) ** 2 for v in values)
    if ss_total == 0:
        return 0.0
    groups = {}
    for ts, v in points:
        groups.setdefault(group_key_fn(ts), []).append(v)
    ss_between = sum(len(g) * (sum(g) / len(g) - grand_mean) ** 2 for g in groups.values())
    return ss_between / ss_total


def _linreg_slope(xs, ys):
    """Least-squares slope of ys over xs. Pure Python (no numpy)."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    return num / den if den else 0.0


def build_seasonal_baseline(points, baseline_weeks=BASELINE_WEEKS_DEFAULT):
    """Build a day-of-week x hour-of-day baseline model from raw
    (epoch_seconds, value) baseline-window points for ONE series.

    Returns None if points is empty, else:
      {"buckets": {(weekday, hour): {"median":, "mad":, "n":}},
       "global": {"median":, "mad":, "n":, "p50":, "p90":, "p95":, "p99":, "cv": float|None},
       "trend_slope":, "baseline_end_ts":,
       "dominant_seasonality": "daily"|"weekly",
       "seasonality_strength": {"weekly": eta2, "daily": eta2}}
    """
    if not points:
        return None

    values = [v for _, v in points]
    median, mad = calculate_mad(values)
    global_stats = {
        "median": median, "mad": mad, "n": len(values),
        "p50": calculate_percentile(values, 50),
        "p90": calculate_percentile(values, 90),
        "p95": calculate_percentile(values, 95),
        "p99": calculate_percentile(values, 99),
        # Robust CV = MAD/median (consistent with this file's MAD-based spread
        # vocabulary; classic stdev/mean is not robust to the bursty, skewed
        # traffic these SPIKE metrics exhibit). None when median is ~0 to avoid
        # a meaningless/huge ratio.
        "cv": (mad / median) if median >= 1e-6 else None,
    }

    buckets_raw = {}
    for ts, v in points:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        buckets_raw.setdefault((dt.weekday(), dt.hour), []).append(v)
    buckets = {}
    for key, vals in buckets_raw.items():
        b_median, b_mad = calculate_mad(vals)
        buckets[key] = {"median": b_median, "mad": b_mad, "n": len(vals)}

    # Trend: linear regression of daily median values across the baseline window.
    daily_values = {}
    for ts, v in points:
        daily_values.setdefault(int(ts // 86400), []).append(v)
    day_keys = sorted(daily_values)
    if day_keys:
        day0 = day_keys[0]
        xs = [k - day0 for k in day_keys]
        ys = [calculate_mad(daily_values[k])[0] for k in day_keys]
        trend_slope = _linreg_slope(xs, ys)
    else:
        trend_slope = 0.0

    weekly_eta2 = _eta_squared(points, lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).weekday())
    daily_eta2 = _eta_squared(points, lambda ts: datetime.fromtimestamp(ts, tz=timezone.utc).hour)

    return {
        "buckets": buckets,
        "global": global_stats,
        "trend_slope": trend_slope,
        "baseline_end_ts": max(ts for ts, _ in points),
        "dominant_seasonality": "weekly" if weekly_eta2 > daily_eta2 else "daily",
        "seasonality_strength": {"weekly": weekly_eta2, "daily": daily_eta2},
    }


def seasonal_upper_bound(model, target_ts, k=BAND_K_DEFAULT):
    """(expected, upper_bound, lower_bound) at target_ts (epoch seconds), using
    the model's (weekday, hour) bucket, falling back to the series' global
    stats when the bucket has too few samples (MIN_BUCKET_SAMPLES)."""
    dt = datetime.fromtimestamp(target_ts, tz=timezone.utc)
    bucket = model["buckets"].get((dt.weekday(), dt.hour))
    if bucket and bucket["n"] >= MIN_BUCKET_SAMPLES:
        median, mad = bucket["median"], bucket["mad"]
    else:
        median, mad = model["global"]["median"], model["global"]["mad"]

    days = (target_ts - model["baseline_end_ts"]) / 86400.0
    # Clamped at 0: these are rate/count metrics (structurally non-negative).
    # An unbounded trend extrapolation over sparse/noisy daily medians (e.g. a
    # thin "global" fallback when the bucket has too few baseline samples) can
    # otherwise drag expected — and therefore upper — negative, which would
    # flag every non-negative peak regardless of magnitude.
    expected = max(0.0, median + model["trend_slope"] * days)
    # Floor mad_eff so a near-zero-variance bucket can't collapse the band to
    # ~0 (the exact degenerate-MAD failure mode the flat median+3*MAD test had).
    mad_eff = max(mad, expected * MAD_FLOOR_FRACTION, MAD_ABS_FLOOR)
    upper = expected + k * mad_eff
    lower = max(0.0, expected - k * mad_eff)
    return expected, upper, lower


def detect_deviation_seasonal(peak_val, peak_ts, model, k=BAND_K_DEFAULT):
    """Returns (flagged, upper_bound). (False, 0) if model is None (no baseline
    history for this series — floor_value remains the sole backstop, same as
    today's behavior when there's no signal)."""
    if model is None:
        return False, 0
    _expected, upper, _lower = seasonal_upper_bound(model, peak_ts, k)
    return peak_val > upper, upper


def _debug_seasonal_line(model, peak_ts, k):
    """One-line summary of the bucket/threshold that gated a SPIKE decision,
    for `analyze --debug` (used to calibrate band_k/MAD_ABS_FLOOR against real data)."""
    dt = datetime.fromtimestamp(peak_ts, tz=timezone.utc)
    bucket = model["buckets"].get((dt.weekday(), dt.hour))
    if bucket and bucket["n"] >= MIN_BUCKET_SAMPLES:
        source, n, median, mad = "bucket", bucket["n"], bucket["median"], bucket["mad"]
    else:
        source, n = "global", model["global"]["n"]
        median, mad = model["global"]["median"], model["global"]["mad"]
    expected, upper, _lower = seasonal_upper_bound(model, peak_ts, k)
    mad_eff = max(mad, expected * MAD_FLOOR_FRACTION, MAD_ABS_FLOOR)
    return (f"weekday={dt.weekday()} hour={dt.hour} source={source} n={n} "
            f"median={median:.3f} mad={mad:.3f} mad_eff={mad_eff:.3f} "
            f"expected={expected:.3f} upper={upper:.3f} k={k}")


def _series_key(metric_labels):
    """Stable, JSON-friendly key for a Prometheus label set (used for the
    on-disk baseline cache)."""
    return json.dumps(sorted((metric_labels or {}).items()), sort_keys=True)


def _key_to_metric(key):
    return dict(json.loads(key))


def _cache_path(section, metric_slug_str, region, sub_label=None):
    tag = f"{section}_{metric_slug_str}_{region or 'all'}"
    if sub_label:
        tag += f"_{slugify(sub_label)}"
    return os.path.join(BASELINE_CACHE_DIR, f"{tag}.json")


def load_baseline_cache(path):
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def save_baseline_cache(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp_path = path + '.tmp'
    with open(tmp_path, 'w') as f:
        json.dump(data, f)
    os.replace(tmp_path, path)  # atomic — survives a mid-write interruption


def fetch_baseline_points_cached(client, cache_path, promql, baseline_start_ms, baseline_end_ms,
                                  region=None, max_weeks=MAX_BASELINE_WEEKS):
    """Like query_prometheus, but persists raw points to a local JSON cache
    (cache_path) and only fetches the gap between what's cached and
    [baseline_start_ms, baseline_end_ms]. Grows the cache incrementally across
    runs (pruned to max_weeks) instead of re-fetching the full window every time.

    Coverage is tracked via explicit "covered_start_s"/"covered_end_s" boundaries
    (the contiguous span actually confirmed fetched), NOT inferred from the min/max
    timestamp of the data itself — a chunk that fails mid-fetch (see query_prometheus's
    failed_ranges) must not let a later, successful chunk's timestamps push the
    boundary past the gap, or the gap is never retried on subsequent runs.

    Returns {"data": {"resultType": "matrix", "result": [{"metric":, "values": [[ts, val], ...]}, ...]},
             "failed_ranges": [(start_s, end_s), ...]}
    """
    promql_hash = hashlib.sha256(promql.encode('utf-8')).hexdigest()[:16]
    cache = load_baseline_cache(cache_path)
    if cache is None or cache.get("promql_hash") != promql_hash:
        cache = {"promql_hash": promql_hash, "series": {}}  # stale/missing/query changed -> fresh

    series_points_by_key = {
        key: [(float(p[0]), float(p[1])) for p in pts]
        for key, pts in cache.get("series", {}).items()
    }
    # None on a first-time/stale cache, and on any cache predating this field —
    # those are treated as cold (one full refetch, then normal incremental
    # behavior resumes; existing_ts dedup below means no data is lost).
    covered_start_s = cache.get("covered_start_s")
    covered_end_s = cache.get("covered_end_s")
    baseline_start_s = baseline_start_ms // 1000

    fetch_ranges = []  # (side, range_start_ms, range_end_ms)
    if covered_start_s is None and covered_end_s is None:
        fetch_ranges.append(("cold", baseline_start_ms, baseline_end_ms))
    else:
        if covered_end_s is not None and covered_end_s * 1000 < baseline_end_ms:
            fetch_ranges.append(("forward", covered_end_s * 1000, baseline_end_ms))
        if covered_start_s is not None and baseline_start_s < covered_start_s:
            fetch_ranges.append(("backward", baseline_start_ms, covered_start_s * 1000))

    all_failed_ranges = []
    for side, range_start_ms, range_end_ms in fetch_ranges:
        if range_start_ms >= range_end_ms:
            continue
        res = query_prometheus(client, promql, range_start_ms, range_end_ms, region)
        for series in res.get('data', {}).get('result', []):
            key = _series_key(series.get('metric', {}))
            pts = series_points_by_key.setdefault(key, [])
            existing_ts = {p[0] for p in pts}
            for ts, val in series.get('values', []):
                try:
                    ts_f, val_f = float(ts), float(val)
                except (TypeError, ValueError):
                    continue
                if ts_f not in existing_ts:
                    pts.append((ts_f, val_f))
                    existing_ts.add(ts_f)

        failed = res.get('failed_ranges') or []
        all_failed_ranges.extend(failed)
        range_start_s, range_end_s = range_start_ms // 1000, range_end_ms // 1000
        # Only the portion contiguous with the anchor edge is trustworthy —
        # a failure stops the boundary right there instead of skipping past it.
        if side in ("cold", "forward"):
            trusted_end_s = min(f[0] for f in failed) if failed else range_end_s
            covered_end_s = trusted_end_s if covered_end_s is None else max(covered_end_s, trusted_end_s)
            if side == "cold":
                covered_start_s = range_start_s
        else:  # backward
            trusted_start_s = max(f[1] for f in failed) if failed else range_start_s
            covered_start_s = trusted_start_s if covered_start_s is None else min(covered_start_s, trusted_start_s)

    cutoff_s = baseline_end_ms // 1000 - max_weeks * 7 * 24 * 3600
    result = []
    series_out = {}
    for key, pts in series_points_by_key.items():
        pruned = sorted(p for p in pts if p[0] >= cutoff_s)
        if not pruned:
            continue
        series_out[key] = pruned
        result.append({"metric": _key_to_metric(key), "values": [[p[0], p[1]] for p in pruned]})

    if covered_start_s is not None:
        covered_start_s = max(covered_start_s, cutoff_s)

    all_out_ts = [p[0] for pts in series_out.values() for p in pts]
    save_baseline_cache(cache_path, {
        "promql_hash": promql_hash,
        "series": {key: [[p[0], p[1]] for p in pts] for key, pts in series_out.items()},
        "min_ts": min(all_out_ts) if all_out_ts else None,
        "max_ts": max(all_out_ts) if all_out_ts else None,
        "covered_start_s": covered_start_s,
        "covered_end_s": covered_end_s,
    })

    return {"data": {"resultType": "matrix", "result": result}, "failed_ranges": all_failed_ranges}


def detect_deviation(deviation_rule, values, deviation_threshold=None):
    """Returns (flagged, value_at_risk, decision_threshold).
    SPIKE uses a statistical test on the values themselves.
    All other types fall through to floor-only (caller handles RESOURCE
    baseline detection separately when deviation_threshold is set)."""
    if not values:
        return False, 0, 0
    rule = (deviation_rule or '').upper()
    if 'SPIKE' in rule:
        return detect_deviation_spike(values)
    return False, max(values), 0  # STATE / RESOURCE / free-text → floor only


_SIZE_UNIT_MULTIPLIERS = {
    'kb': 1_000, 'mb': 1_000_000, 'gb': 1_000_000_000, 'tb': 1_000_000_000_000,
}
_HUMAN_VALUE_RE = re.compile(r'^([+-]?\d+(?:\.\d+)?)\s*([a-zA-Z%]*)$')


def parse_human_value(value):
    """Accepts a raw number (int/float/None, passed through unchanged) or a
    human-readable string like '2GB', '50MB', '60%', '300%' and returns the
    plain number the rest of the pipeline already expects: bytes for size
    suffixes (decimal/SI: kb/mb/gb/tb), and the bare number for '%' (no /100
    here — callers dividing by a ceiling/percentage apply the /100 themselves,
    matching how raw deviation_threshold/floor_value numbers work today)."""
    if value is None or isinstance(value, (int, float)):
        return value
    if not isinstance(value, str):
        return value
    match = _HUMAN_VALUE_RE.match(value.strip())
    if not match:
        raise ValueError(f"cannot parse human-readable value: {value!r}")
    number, unit = float(match.group(1)), match.group(2).lower()
    if unit in ('', '%'):
        return number
    if unit in _SIZE_UNIT_MULTIPLIERS:
        return number * _SIZE_UNIT_MULTIPLIERS[unit]
    raise ValueError(f"unknown unit {unit!r} in human-readable value: {value!r}")


_FLOOR_ENTRY_MISSING = object()  # sentinel: metric has 'series_floor' but no
                                  # entry for this sub_label


def _resolve_region_floor(region_floor_map, region, floor_value, floor_op):
    """Apply an optional 'region_floor: {token: {value, op}}' override on top
    of an already-resolved (floor_value, floor_op) pair. Sparse and opt-in:
    a region with no entry (or no map at all) passes the default through
    unchanged, so most metrics/regions never need this key at all."""
    if not region_floor_map:
        return parse_human_value(floor_value), floor_op
    unknown = set(region_floor_map) - REGION_TOKENS
    if unknown:
        raise ValueError(
            f"region_floor has unknown region token(s) {sorted(unknown)!r} — "
            f"must be one of {sorted(REGION_TOKENS)!r}")
    if region not in region_floor_map:
        return parse_human_value(floor_value), floor_op
    override = region_floor_map[region]
    if not isinstance(override, dict) or 'value' not in override:
        raise ValueError(
            f"region_floor entry for {region!r} must be "
            f"{{value: ...}} or {{value: ..., op: ...}}, got {override!r}")
    return parse_human_value(override['value']), override.get('op', floor_op)


def resolve_ceiling(ceiling_cfg, region=None):
    """Resolve a metric-level 'ceiling' into a tagged (kind, value) pair used by
    RESOURCE deviation (deviation_threshold = percentage of this ceiling):

      - absent / falsy      -> ('none', None)
      - {series: <key>}     -> ('series', <slugified key>)  point-by-point per
                               instance against that panel series (per-region
                               values come from the series itself)
      - {value: <n>, ...}   -> ('scalar', <float>)  a manual capacity, with an
                               optional nested 'region_floor: {token: {value}}'
                               override applied for `region` exactly like a
                               metric floor (same global-default + per-region
                               behavior the user asked for).

    'series' and 'value' are mutually exclusive; 'series' cannot carry a region
    override (it already provides real per-region/per-instance values)."""
    if not ceiling_cfg:
        return ('none', None)
    if not isinstance(ceiling_cfg, dict):
        raise ValueError(f"ceiling must be a mapping, got {ceiling_cfg!r}")
    has_series, has_value = 'series' in ceiling_cfg, 'value' in ceiling_cfg
    if has_series == has_value:
        raise ValueError("ceiling must have exactly one of 'series' or 'value'")
    if has_series:
        if ceiling_cfg.get('region_floor'):
            raise ValueError("ceiling.series cannot carry a 'region_floor' override — "
                             "the series already provides per-region values")
        series_key = ceiling_cfg['series']
        if not isinstance(series_key, str) or not series_key.strip():
            raise ValueError(f"ceiling.series must be a non-empty series key, got {series_key!r}")
        return ('series', slugify(series_key))
    # scalar capacity with an optional per-region override. Same global-default +
    # per-region shape as region_floor, but value-only (a ceiling has no op).
    value = ceiling_cfg['value']
    region_map = ceiling_cfg.get('region_floor')
    if region_map:
        unknown = set(region_map) - REGION_TOKENS
        if unknown:
            raise ValueError(
                f"ceiling region_floor has unknown region token(s) {sorted(unknown)!r} — "
                f"must be one of {sorted(REGION_TOKENS)!r}")
        override = region_map.get(region)
        if override is not None:
            if not isinstance(override, dict) or 'value' not in override:
                raise ValueError(
                    f"ceiling region_floor entry for {region!r} must be {{value: ...}}, "
                    f"got {override!r}")
            value = override['value']
    return ('scalar', parse_human_value(value))


def resolve_series_floor_entry(config, sub_label, floor_value, floor_op, region=None):
    """Resolve the (floor_value, floor_op) pair for one sub-query.

    No 'series_floor' key: single scalar floor for the whole metric — returns
    the metric-level (floor_value, floor_op), unless an optional metric-level
    'region_floor: {token: {value, op}}' overrides it for this region.

    'series_floor' key present: per-series floor is mandatory, keyed by
    normalize_series_key(sub_label) (e.g. CPU Stats' iowait vs system/guest,
    which need very different scales). 'null' disables the floor for that
    series entirely (regardless of region — a disabled series stays disabled
    everywhere); {value, op} sets both explicitly, and that entry may itself
    carry a 'region_floor' map for series whose baseline diverges by region.
    There is no silent fallback to the metric-level floor here — that's what
    let a series like Memory Usage's 'free' silently inherit a floor_op that
    could never fire for it. A sub_label with no entry returns
    (_FLOOR_ENTRY_MISSING, None, None) so the caller can warn and skip just that
    series instead of guessing.

    Returns a 3-tuple (floor_value, floor_op, ceiling_ref). ceiling_ref is the
    slugified key of a sibling series when the entry uses 'of' or 'ceiling'
    (e.g. {value: 10%, op: '<', of: total} → alert if this series < 10% of
    'total', point-by-point per instance); None otherwise. In that case
    floor_value carries the percentage, not an absolute floor."""
    series_floor = config.get('series_floor')
    if series_floor is None:
        v, o = _resolve_region_floor(config.get('region_floor'), region, floor_value, floor_op)
        return v, o, None
    key = normalize_series_key(sub_label)
    if key not in series_floor:
        return _FLOOR_ENTRY_MISSING, None, None
    entry = series_floor[key]
    if entry is None:
        return None, '>', None  # disabled; op is unused since check_floor short-circuits on None
    if not isinstance(entry, dict) or 'value' not in entry or 'op' not in entry:
        raise ValueError(
            f"series_floor entry for {key!r} must be null or "
            f"{{value: ..., op: ...}}, got {entry!r}")
    ceiling_key = entry.get('ceiling') or entry.get('of')
    if ceiling_key is not None:
        if not isinstance(ceiling_key, str) or not ceiling_key.strip():
            raise ValueError(
                f"series_floor entry for {key!r} has invalid "
                f"'ceiling'/'of': {ceiling_key!r}")
        raw_val = entry['value']
        if 'unit' in entry:
            unit = entry['unit']
            raw_val = f"{raw_val}{unit}" if unit and unit != '%' else raw_val
        v, o = _resolve_region_floor(entry.get('region_floor'), region, raw_val, entry['op'])
        return v, o, slugify(ceiling_key)
    v, o = _resolve_region_floor(entry.get('region_floor'), region, entry['value'], entry['op'])
    return v, o, None


def check_floor(floor_value, floor_op, values):
    if floor_value is None or not values:
        return False
    if floor_op == '<':
        return min(values) < floor_value
    if floor_op == '>':
        return max(values) > floor_value
    if floor_op == '<=':
        return min(values) <= floor_value
    if floor_op == '>=':
        return max(values) >= floor_value
    return max(values) >= floor_value  # >= (default)


def check_ceiling_relative(points, op, pct, ceiling_map):
    """Point-by-point per-instance check of a series against a ceiling series:
    at each timestamp compute value/ceiling*100 and keep the worst ratio in the
    `op` direction (max for '>'/'>=', min for '<'/'<='), then compare it to `pct`.

    `ceiling_map` is {ts: ceiling_value} for the matching instance. Points with
    no aligned ceiling value, or a non-positive ceiling, are skipped (no
    divide-by-zero). Returns (flagged, breach_ts, breach_val, ref_at_breach),
    where ref_at_breach = ceiling_at_breach * pct/100 is the decision boundary at
    the worst point (a sensible chart reference line even when the ceiling drifts)."""
    if pct is None or not ceiling_map:
        return False, None, None, 0
    lower = op in ('<', '<=')
    worst = None  # (ratio, ts, val, ceil)
    for ts, val in points:
        ceil = ceiling_map.get(ts)
        if ceil is None or ceil <= 0:
            continue
        ratio = val / ceil * 100.0
        if worst is None or (ratio < worst[0] if lower else ratio > worst[0]):
            worst = (ratio, ts, val, ceil)
    if worst is None:
        return False, None, None, 0
    ratio, ts, val, ceil = worst
    if op == '<':
        flagged = ratio < pct
    elif op == '<=':
        flagged = ratio <= pct
    elif op == '>=':
        flagged = ratio >= pct
    else:  # '>'
        flagged = ratio > pct
    return flagged, ts, val, ceil * pct / 100.0


def build_ceiling_index(client, resolved_queries, ceiling_keys, start_ms, end_ms, region):
    """For each referenced ceiling key, locate the matching sub-query (by
    normalize_series_key), query it once, and index its points by instance:
    {key: {instance_key: {ts: value}}}. Raises ValueError if a key matches no
    sub-query in the metric (config points at a series the panel doesn't produce)."""
    index = {}
    for key in ceiling_keys:
        promql = next((q for sl, q in resolved_queries if normalize_series_key(sl) == key), None)
        if promql is None:
            raise ValueError(
                f"ceiling reference {key!r} matches no series/sub-query in this metric")
        res = query_prometheus(client, promql, start_ms, end_ms, region)
        inst_map = {}
        for series in res.get('data', {}).get('result', []):
            pts = series_points(series)
            if not pts:
                continue
            metric = series.get('metric', {})
            inst = metric.get('instance') or series_label(metric)
            inst_map.setdefault(inst, {}).update({ts: v for ts, v in pts})
        index[key] = inst_map
    return index


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


def format_value(value, unit):
    if not unit:
        return f"{value:.2f}"
    u = unit.lower()
    is_rate = 'ps' in u or '/s' in u
    is_bit = unit == 'bps'
    if u in ('bytes', 'byte', 'b', 'decbytes', 'decbyte',
             'bps', 'decbps',
             'bytes/s', 'bytes/sec', 'b/s'):
        base = 'b' if is_bit else 'B'
        for suf, div in [('G', 1e9), ('M', 1e6), ('K', 1e3)]:
            if abs(value) >= div:
                return f"{value/div:.2f} {suf}{base}{'/s' if is_rate else ''}"
        return f"{value:.2f} {unit}"
    if u in ('percent', '%', 'percentunit'):
        return f"{value:.2f}{'%' if u != 'percentunit' else ''}"
    return f"{value:.2f} {unit}"


def build_grafana_url(base_url, region, start_ms, end_ms):
    """Build parameterized Grafana URL."""
    return f"{base_url}&var-region={region}&from={start_ms}&to={end_ms}"


def resolve_grafana_url(dashboard_uid, panel_id, region, start_ms, end_ms):
    """Build a full Grafana panel URL from dashboard uid + panel id."""
    params = urlencode({"orgId": 1, "viewPanel": f"panel-{panel_id}",
                        "var-region": region, "from": start_ms, "to": end_ms})
    return f"{GRAFANA_ORIGIN}/d/{dashboard_uid}/{dashboard_uid}?{params}"


def slugify(text):
    """lowercase, non-alphanumeric -> underscore (matches existing chart_<region>_<slug>.png convention)."""
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def normalize_series_key(sub_label):
    """'B — System' -> 'system'; None/'' -> ''. Used to match a sub_label
    against a metric's per-series 'series_overrides' YAML keys."""
    if not sub_label:
        return ''
    return slugify(SUBQUERY_KEY.sub('', sub_label))


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


def slice_zoom(points, start_ts, end_ts):
    """Points within [start_ts, end_ts]."""
    return [(ts, v) for ts, v in points if start_ts <= ts <= end_ts]


def fill_state_gaps(deviated):
    """For up/down state series where 'down' is a gap (no sample), insert an
    explicit 0.0 at every grid timestamp an instance is missing.

    The grid is the union of all instances' timestamps in the group (the query
    step grid). This turns down states into a 0 line so 1->0 (terminate) and
    0->1 (start) transitions render as visible steps instead of vanishing.
    Mutates and returns `deviated` with each dev['points'] gap-filled + sorted.
    """
    grid = sorted({ts for dev in deviated for ts, _ in dev['points']})
    if not grid:
        return deviated
    for dev in deviated:
        present = {ts: val for ts, val in dev['points']}
        dev['points'] = [(ts, present.get(ts, 0.0)) for ts in grid]
    return deviated


def fill_prometheus_gaps(result):
    """Pre-detection gap fill for state metrics. Prometheus doesn't emit 0
    when a target is down — it stops emitting samples. This fills in 0.0 at
    every union-grid timestamp a series is missing so check_floor(min < 1)
    can detect down instances. Mutates result in place."""
    series_list = result.get('data', {}).get('result', [])
    if not series_list:
        return
    all_ts = set()
    for series in series_list:
        for ts, _ in series_points(series):
            all_ts.add(ts)
    if not all_ts:
        return
    grid = sorted(all_ts)
    for series in series_list:
        present = {}
        for ts_str, val_str in series.get('values', []):
            present[float(ts_str)] = val_str
        filled = []
        for ts in grid:
            if ts in present:
                filled.append([str(ts), present[ts]])
            else:
                filled.append([str(ts), "0"])
        series['values'] = filled


def summarize_state_transitions(points):
    """List individual terminated(1→0) / started(0→1) events in a gap-filled
    up/down series. Returns [(event_type, timestamp_s), ...] in chronological
    order. Empty list = no transitions (all-up)."""
    events = []
    prev_up = None
    for ts, val in points:
        up = val >= 0.5
        if prev_up is not None and up != prev_up:
            events.append(('terminated' if not up else 'started', ts))
        prev_up = up
    return events


def generate_chart(title, out_path, unit, payload, render_cfg=None):
    """Render via plot_helper.render_chart(). Never raises: a broken chart
    must not fail the metric."""
    try:
        plot_helper.render_chart(title, out_path, "Time", unit, payload, render_cfg)
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
                # legendFormat is a Grafana frontend template (e.g. "{{instance}} -
                # X Rate"), normally resolved per-series by Grafana's UI using each
                # series' own labels. This script bypasses that UI and uses the
                # label as a single group-level sub_label shared by every series in
                # the group, so an unresolved {{...}} token would be meaningless
                # (and misleading) here — strip it rather than leave it literal.
                label = re.sub(r'\{\{.*?\}\}', '', label).strip().lstrip('-–').strip()
                label = label or t.get("refId", "?")  # legendFormat was only a template token
                sub_label = (f"{t.get('refId', '?')} — {label}"
                             if label != t.get("refId", "?") else "")
                queries.append((sub_label, t["expr"]))
            return queries
    raise KeyError(f"panel {panel_id} not found")


def extract_panel_field_config(dashboard_json, panel_id):
    """Extract (unit, render_cfg) from a Grafana panel's fieldConfig, so the
    generated PNG can mirror the panel's own chart type and axis config.

    render_cfg = {"draw_style", "scale", "min", "max"}, pulled from
    fieldConfig.defaults.custom.drawStyle/scaleDistribution and defaults.min/max.
    Returns ("", {}) if the panel isn't found.
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
            defaults = p.get("fieldConfig", {}).get("defaults", {})
            custom = defaults.get("custom", {})
            render_cfg = {
                "draw_style": custom.get("drawStyle", "line"),
                "scale": custom.get("scaleDistribution", {}).get("type", "linear"),
                "min": defaults.get("min"),
                "max": defaults.get("max"),
            }
            return defaults.get("unit", ""), render_cfg
    return "", {}


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


def _build_informational_table(client, queries, metric_name,
                                start_epoch_ms, end_epoch_ms,
                                region, section):
    """data_view: table with no deviation/floor rules.

    Collect every series returned by PromQL, group them by their
    significant label-set (excluding infra-only labels like region,
    __name__, job, stack, team), render a Confluence HTML table, and
    detect label-value transitions (version, instance_type, etc.)
    across the sprint.
    """
    print(f"  building informational table for {section} {metric_name}",
          file=sys.stderr)

    # collate: frozenset(label items) -> {labels, first_ts, last_ts, values}
    groups = {}
    for _sub_label, promql in queries:
        res = query_prometheus(client, promql, start_epoch_ms,
                               end_epoch_ms, region)
        for series in res.get('data', {}).get('result', []):
            points = series_points(series)
            if not points:
                continue
            labels = series.get('metric', {})
            sig = {k: v for k, v in labels.items()
                   if k not in ('region', '__name__', 'job', 'stack', 'team')}
            key = frozenset(sig.items())
            first_ts = points[0][0]
            last_ts = points[-1][0]
            vals = [v for _, v in points]
            avg_val = sum(vals) / len(vals)

            if key not in groups:
                groups[key] = {
                    "labels": sig,
                    "first_ts": first_ts,
                    "last_ts": last_ts,
                    "avg_val": avg_val,
                }
            else:
                g = groups[key]
                g["first_ts"] = min(g["first_ts"], first_ts)
                g["last_ts"] = max(g["last_ts"], last_ts)
                g["avg_val"] = (g["avg_val"] + avg_val) / 2

    if not groups:
        return None

    sorted_entries = sorted(groups.values(), key=lambda e: e["first_ts"])
    sample = sorted_entries[0]["labels"]
    columns = list(sample.keys())

    html = f"<p><strong>{metric_name}</strong></p>\n<table>"
    html += "<tr>"
    for col in columns:
        html += f"<th>{col}</th>"
    html += "<th>Avg Count</th><th>Active From</th><th>Active To</th></tr>\n"
    for e in sorted_entries:
        html += "<tr>"
        for col in columns:
            html += f"<td>{e['labels'].get(col, '')}</td>"
        html += f"<td>{e['avg_val']:.0f}</td>"
        html += f"<td>{format_timestamp(e['first_ts'])}</td>"
        html += f"<td>{format_timestamp(e['last_ts'])}</td></tr>\n"
    html += "</table>\n"

    if len(sorted_entries) > 1:
        transition_ts = format_timestamp(sorted_entries[0]["last_ts"])
        first = sorted_entries[0]
        for col in columns:
            old_val = first["labels"].get(col, "")
            new_val = sorted_entries[-1]["labels"].get(col, "")
            if old_val != new_val:
                html += (f'<p><strong>{col} changed</strong>: '
                         f'{old_val} → {new_val} at {transition_ts}</p>\n')

    return html


def analyze_metric(client, metric_name, config, start_epoch_ms, end_epoch_ms,
                   region, section="xcc", defaults=None, failures=None, baseline_warnings=None):
    """Analyze one metric and return HTML for its deviated series (or None).

    Query source, in priority order:
    1. an explicit `expr:` in the YAML (single query, or legacy A/B/C… keys
       for configs not yet migrated) — used as-is.
    2. otherwise, live sub-queries fetched from the metric's Grafana panel
       (config['panel_id'] + defaults['dashboard']).
    Each query result is grouped under the metric's deviation rule; sub-query
    results are labelled by their key so the reader sees which dimension
    (e.g. "A — 4xx only") deviated.

    `failures` (optional list, appended in place): 404/401/"panel not found"
    errors resolving config['panel_id'] are recorded here instead of just
    being logged, so the caller can render a visible warning — the data is
    unreliable for that metric and deviation detection is skipped for it
    (queries stays empty below, so this function returns None before the
    detection loop ever runs).

    `baseline_warnings` (optional list, appended in place): for SPIKE metrics,
    if this run's baseline-history fetch hit any Prometheus/HTTP errors, an
    entry is recorded here instead of only logging to stderr — seasonal
    deviation detection is degraded (falls back to floor-only) for the
    affected series until the gap is backfilled on a later run.
    """
    print(f"  checking {section} {metric_name} deviation", file=sys.stderr)

    # Expand unified `threshold:` block into legacy fields (floor_value,
    # floor_op, ceiling, deviation_threshold) so the rest of the pipeline
    # needs no changes.  Handles:
    #   STATE:  {value: 1, op: "<"}  → deviation: STATE, floor_value: 1, floor_op: <
    #   RESOURCE (ceiling-relative): {value: 40, unit: "%", op: ">", ceiling: 100}
    #            → deviation: RESOURCE, ceiling: {value: 100}, deviation_threshold: 40
    #   RESOURCE (absolute floor):   {value: 2.5, op: ">"}
    #            → deviation: RESOURCE, floor_value: 2.5, floor_op: >
    # Metrics with series_floor or SPIKE keep their current fields unchanged
    # (threshold block is ignored for them).
    threshold = config.get('threshold')
    if threshold and isinstance(threshold, dict):
        value = threshold.get('value')
        op = threshold.get('op', '>=')
        ceiling_val = threshold.get('ceiling')
        unit = threshold.get('unit', '')
        # Reconstruct a string like "1MB" so parse_human_value() converts to
        # bytes.  % and bare numbers are passed as-is (parse_human_value treats
        # them identically to int/float).
        raw = f"{value}{unit}" if unit and unit != '%' else value
        if ceiling_val is not None:
            config['ceiling'] = {'value': ceiling_val}
            config['deviation_threshold'] = raw if isinstance(raw, str) else value
            config['deviation'] = 'RESOURCE'
            config.pop('floor_value', None)
            config.pop('floor_op', None)
        elif value == 1 and op == '<':
            config['deviation'] = config.get('deviation', 'STATE')
            config['floor_value'] = 1
            config['floor_op'] = '<'
        else:
            config['deviation'] = config.get('deviation', 'RESOURCE')
            config['floor_value'] = raw
            config['floor_op'] = op

    deviation_rule = config.get('deviation', '')
    deviation_threshold = parse_human_value(config.get('deviation_threshold'))
    floor_value = parse_human_value(config.get('floor_value'))
    floor_op = config.get('floor_op', '>=')
    ceiling_kind, ceiling_ref = resolve_ceiling(config.get('ceiling'), region)
    is_state = 'STATE' in deviation_rule
    is_spike = 'SPIKE' in deviation_rule.upper()
    # RESOURCE deviation is ceiling-relative: 'deviation_threshold' is a percentage
    # of the metric's 'ceiling' (a manual capacity or a panel series), evaluated on
    # the current window — no historical baseline. It needs both to mean anything.
    is_resource = ('RESOURCE' in deviation_rule.upper()
                   and deviation_threshold is not None
                   and ceiling_kind != 'none')
    if ('RESOURCE' in deviation_rule.upper() and deviation_threshold is not None
            and ceiling_kind == 'none'):
        print(f"WARN: {section} {metric_name}: RESOURCE deviation_threshold set but no "
              f"'ceiling' defined — ignoring threshold, running floor-only", file=sys.stderr)
    baseline_weeks = config.get('baseline_weeks', BASELINE_WEEKS_DEFAULT)
    band_k = config.get('band_k', BAND_K_DEFAULT)
    baseline_start_ms = start_epoch_ms - baseline_weeks * 7 * 24 * 3600 * 1000
    baseline_end_ms = start_epoch_ms
    metric_slug = slugify(metric_name)
    data_view = config.get('data_view', 'chart')

    # Save the original sprint-end before capping so the overview chart's
    # x-axis can span the full sprint window even when data starts mid-sprint.
    sprint_end_ms = end_epoch_ms
    # Cap end_epoch_ms to now — never query Prometheus for future data.
    # Without this cap, step timestamps extend past current time (up to
    # end-of-day). At those steps, different instances may have slightly
    # different last scrape timestamps, creating false 1→0 transitions
    # when fill_prometheus_gaps fills missing grid timestamps with 0.
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if end_epoch_ms > now_ms:
        end_epoch_ms = now_ms

    # Resolve dashboard uid + panel
    panel_id = config.get('panel_id')
    dashboard_uid = config.get('dashboard') or (defaults or {}).get('dashboard', '')

    # Extract Y-axis unit + render config (chart type/axis) from Grafana panel metadata
    unit = ''
    render_cfg = {}
    if dashboard_uid and panel_id is not None:
        try:
            unit, render_cfg = extract_panel_field_config(client.get_dashboard(dashboard_uid), panel_id)
        except Exception:
            pass

    # YAML-level render config overrides (min, max, draw_style)
    render_overrides = config.get('render')
    if render_overrides:
        render_cfg = {**render_cfg, **render_overrides}
    # STATE metrics always use state-style charts (gap-fill, step plot,
    # transition-based reporting). Auto-derive from deviation so YAML
    # doesn't need redundant `render: {style: state}`.
    if 'STATE' in config.get('deviation', '').upper():
        render_cfg.setdefault('style', 'state')
    # 'state' style = per-instance up/down chart (down gap-filled to 0, no
    # reference line, transition-based reporting instead of peak framing).
    chart_style = render_cfg.get('style')

    # Build the list of (sub-label, promql) to run.
    queries = []
    main = config.get('expr') or config.get('promql', '')
    if isinstance(main, str) and main.strip():
        queries.append((None, main))
    for key, val in config.items():
        if isinstance(key, str) and SUBQUERY_KEY.match(key) and isinstance(val, str) and val.strip():
            queries.append((key, val))

    if not queries:
        if dashboard_uid and panel_id is not None:
            try:
                dashboard = client.get_dashboard(dashboard_uid)
                queries = extract_panel_queries(dashboard, panel_id)
            except (GrafanaHTTPError, KeyError) as e:
                reason = (f"HTTP {e.status_code}" if isinstance(e, GrafanaHTTPError)
                          else "panel not found")
                print(f"WARN: {section} {metric_name}: could not resolve panel queries "
                      f"from panel {panel_id}: {e}", file=sys.stderr)
                if failures is not None and (
                        reason == "panel not found"
                        or (isinstance(e, GrafanaHTTPError) and e.status_code in (404, 401))):
                    failures.append({
                        "metric": metric_name, "panel_id": panel_id,
                        "dashboard": dashboard_uid, "reason": reason,
                    })
            except Exception as e:
                print(f"WARN: {section} {metric_name}: could not resolve panel queries "
                      f"from panel {panel_id}: {e}", file=sys.stderr)
        else:
            queries = resolve_panel_queries(client, config.get('grafana', ''),
                                            metric_name, section)

    if not queries:
        print(f"  skipping {section} {metric_name}: no expr and no resolvable "
              f"Grafana panel", file=sys.stderr)
        return None

    # Resolve Grafana template variables ($service, $instance, etc.) from the
    # dashboard.  These are NOT Prometheus query-language features — they are
    # Grafana dashboard variables that the frontend resolves client-side before
    # sending the query to the datasource.  The script bypasses the frontend, so
    # we must resolve them ourselves.
    #
    # Variables set to "All" (includeAll=True, no current selection) expand to
    # the regex `.*` in Grafana's `=~` matcher.  Variables with a fixed
    # selection use the selected value verbatim.  $region is already resolved
    # separately by query_prometheus(), so it is left alone here.
    template_vars = {}
    if dashboard_uid:
        try:
            dash = client.get_dashboard(dashboard_uid)
            for tv in dash.get('dashboard', {}).get('templating', {}).get('list', []):
                name = tv.get('name')
                if not name or name == 'region':
                    continue
                current = tv.get('current') or {}
                text = current.get('text')
                if text and text != 'All' and text != ['All']:
                    template_vars[name] = '|'.join(str(v) for v in (text if isinstance(text, list) else [text]))
                else:
                    template_vars[name] = '.*'  # "All" = match everything
        except Exception:
            pass  # template vars are optional; individual queries may fail

    # Apply template variable resolution to every query before any execution
    resolved_queries = []
    for sub_label, promql in queries:
        for var_name, var_value in template_vars.items():
            promql = promql.replace(f'${var_name}', var_value)
        resolved_queries.append((sub_label, promql))

    # Informational table: no deviation/floor rules, collect ALL series with labels
    if data_view == 'table' and not deviation_rule and floor_value is None and not config.get('series_floor'):
        return _build_informational_table(client, resolved_queries, metric_name,
                                          start_epoch_ms, end_epoch_ms,
                                          region, section)

    # Ceiling references (metric-level series ceiling + per-series 'of'/'ceiling')
    # need the referenced series' points, indexed by instance, before we can
    # evaluate the dependent series against them. Built once, one extra query per
    # referenced ceiling. Scalar ceilings need no query (constant capacity).
    ceiling_keys = set()
    if ceiling_kind == 'series':
        ceiling_keys.add(ceiling_ref)
    for _entry in (config.get('series_floor') or {}).values():
        if isinstance(_entry, dict):
            _ck = _entry.get('ceiling') or _entry.get('of')
            if _ck:
                ceiling_keys.add(slugify(_ck))
    ceiling_index = (build_ceiling_index(client, resolved_queries, ceiling_keys,
                                         start_epoch_ms, end_epoch_ms, region)
                     if ceiling_keys else {})

    groups = []  # (sub_label, [ {instance, peak, timestamp, points} ])
    for sub_label, promql in resolved_queries:
        sub_key = normalize_series_key(sub_label)
        # Per-series floor override: a single floor (value AND direction) is
        # often not viable across sub-series with very different baseline
        # scales or breach directions (e.g. Memory Usage's 'free' needs '<'
        # while the rest of the metric needs '>') — see 'series_floor' in the
        # metric's YAML config. Resolved before querying so a missing entry
        # is caught without spending a Prometheus call on it.
        eff_floor_value, eff_floor_op, entry_ceiling_ref = resolve_series_floor_entry(
            config, sub_label, floor_value, floor_op, region=region)

        # Decide this series' effective check(s):
        #   abs_floor_*     -> absolute floor via check_floor (None = no floor)
        #   ser_ceiling_*   -> point-by-point ratio vs a ceiling series
        #   scalar_boundary -> absolute boundary from a scalar (manual) ceiling
        abs_floor_value, abs_floor_op = eff_floor_value, eff_floor_op
        ser_ceiling_ref = ser_ceiling_pct = None
        ser_ceiling_op = '>'
        scalar_boundary = None
        is_ceiling_series = (ceiling_kind == 'series' and sub_key == ceiling_ref)
        entry_missing = eff_floor_value is _FLOOR_ENTRY_MISSING

        if entry_ceiling_ref is not None:
            # Per-series 'ceiling'/'of': the entry value is a percentage of that series.
            ser_ceiling_ref, ser_ceiling_pct, ser_ceiling_op = (
                entry_ceiling_ref, eff_floor_value, eff_floor_op)
            abs_floor_value, abs_floor_op = None, '>'
        elif entry_missing:
            # No per-series entry. Inherit the metric-level ceiling default for a
            # RESOURCE metric (below); otherwise keep the strict skip behavior.
            if not (is_resource and not is_ceiling_series):
                print(f"WARN: {section} {metric_name}: sub-query {sub_label!r} "
                      f"(key {sub_key!r}) has no series_floor entry — skipping "
                      f"deviation detection for this series", file=sys.stderr)
                continue
            abs_floor_value, abs_floor_op = None, '>'

        # Metric-level ceiling default: applies to a non-ceiling series that has
        # no explicit ceiling override of its own — either a missing series_floor
        # entry, or a metric with no series_floor block at all. An explicit
        # {value, op} or null entry overrides it (as region_floor overrides a
        # metric default).
        if (is_resource and not is_ceiling_series and ser_ceiling_ref is None
                and (entry_missing or config.get('series_floor') is None)):
            if ceiling_kind == 'series':
                ser_ceiling_ref, ser_ceiling_pct, ser_ceiling_op = (
                    ceiling_ref, deviation_threshold, '>')
            elif ceiling_kind == 'scalar':
                scalar_boundary = ceiling_ref * deviation_threshold / 100.0

        print(f"  querying data to {section} {metric_name}", file=sys.stderr)
        res = query_prometheus(client, promql, start_epoch_ms, end_epoch_ms, region)
        if chart_style == 'state':
            fill_prometheus_gaps(res)

        # SPIKE: build a per-series seasonal baseline model (day-of-week x
        # hour-of-day median/MAD) from a local, incrementally-updated cache of
        # baseline_weeks..now history, used for seasonal bounds. RESOURCE no
        # longer uses any baseline — it is ceiling-relative on the current window.
        baseline_models = {}
        pooled_model = None
        if is_spike:
            cache_path = _cache_path(section, metric_slug, region, sub_label)
            baseline_res = fetch_baseline_points_cached(
                client, cache_path, promql, baseline_start_ms, baseline_end_ms, region,
            )
            baseline_failed = baseline_res.get('failed_ranges') or []
            if baseline_failed and baseline_warnings is not None:
                baseline_warnings.append({
                    "metric": metric_name, "sub_label": sub_label, "region": region,
                    "chunks_failed": len(baseline_failed),
                })
            all_baseline_points = []
            for series in baseline_res.get('data', {}).get('result', []):
                bpoints = series_points(series)
                if not bpoints:
                    continue
                key = frozenset(series.get('metric', {}).items())
                baseline_models[key] = build_seasonal_baseline(bpoints, baseline_weeks)
                all_baseline_points.extend(bpoints)
            if all_baseline_points:
                pooled_model = build_seasonal_baseline(all_baseline_points, baseline_weeks)

        deviated = []
        all_series_data = []  # (instance_label, points, flagged)
        for series in res.get('data', {}).get('result', []):
            points = series_points(series)
            if not points:
                continue
            values = [v for _, v in points]
            # Peak direction follows whichever check drives this series: for a
            # lower-end op (<, ≤) use min to capture the actual violation;
            # otherwise use max (traditional peak).
            active_op = ser_ceiling_op if ser_ceiling_ref else abs_floor_op
            if active_op in ('<', '<='):
                peak_ts, peak_val = min(points, key=lambda p: p[1])
            else:
                peak_ts, peak_val = max(points, key=lambda p: p[1])

            flagged_floor = check_floor(abs_floor_value, abs_floor_op, values)

            # Ceiling-relative check (metric series ceiling or per-series 'ceiling'/'of').
            flagged_ceiling = False
            ceil_threshold = 0
            if ser_ceiling_ref is not None:
                metric_labels = series.get('metric', {})
                inst = metric_labels.get('instance') or series_label(metric_labels)
                cmap = ceiling_index.get(ser_ceiling_ref, {}).get(inst)
                if cmap is None:
                    print(f"WARN: {section} {metric_name}: {sub_label!r} instance "
                          f"{inst!r} has no matching {ser_ceiling_ref!r} ceiling series "
                          f"— skipping ceiling check", file=sys.stderr)
                else:
                    flagged_ceiling, b_ts, b_val, ceil_threshold = check_ceiling_relative(
                        points, ser_ceiling_op, ser_ceiling_pct, cmap)
                    if flagged_ceiling:
                        peak_ts, peak_val = b_ts, b_val
            elif scalar_boundary is not None:
                flagged_ceiling = max(values) > scalar_boundary
                ceil_threshold = scalar_boundary

            flagged_dev = False
            dev_threshold = 0
            model = None
            if is_spike:
                key = frozenset(series.get('metric', {}).items())
                model = baseline_models.get(key) or pooled_model
                flagged_dev, dev_threshold = detect_deviation_seasonal(peak_val, peak_ts, model, band_k)
            elif not is_resource:
                flagged_dev, _, dev_threshold = detect_deviation(deviation_rule, values, deviation_threshold)

            flagged = flagged_floor or flagged_ceiling or flagged_dev
            all_series_data.append((series_label(series.get('metric', {})), points, flagged))
            # Reference threshold: the actual decision boundary that triggered.
            if flagged_floor and abs_floor_value is not None:
                ref_threshold = abs_floor_value
            elif flagged_ceiling and ceil_threshold:
                ref_threshold = ceil_threshold
            elif flagged_dev and dev_threshold:
                ref_threshold = dev_threshold
            else:
                ref_threshold = peak_val  # fallback (should not happen when flagged)
            if flagged:
                if is_spike and DEBUG_SEASONAL and model is not None:
                    print(f"  DEBUG spike {section} {metric_name} "
                          f"{series_label(series.get('metric', {}))}: "
                          f"{_debug_seasonal_line(model, peak_ts, band_k)}", file=sys.stderr)
                deviated.append({
                    "instance": series_label(series.get('metric', {})),
                    "peak": peak_val,
                    "timestamp": peak_ts,
                    "points": points,
                    "threshold": ref_threshold,
                    "op": active_op,
                })
        if deviated:
            groups.append((sub_label, deviated, all_series_data))

    seen = set()
    deduped = []
    for sub_label, deviated, all_series_data in groups:
        key = frozenset((d["instance"], round(d["peak"], 2), round(d["timestamp"] or 0, 0)) for d in deviated)
        if key not in seen:
            seen.add(key)
            deduped.append((sub_label, deviated, all_series_data))
        else:
            print(f"  dedup {section} {metric_name}: {sub_label!r} matches previous group", file=sys.stderr)
    groups = deduped

    if not groups:
        print(f"  done {section} {metric_name} (no deviation)", file=sys.stderr)
        return None

    print(f"  building {section} {metric_name}", file=sys.stderr)

    html_output = ""
    for sub_label, deviated, all_series_data in groups:
        display_label = SUBQUERY_KEY.sub('', sub_label).strip() if sub_label else ''
        title = metric_name if not display_label else f"{metric_name} — {display_label}"

        if chart_style == 'state':
            # Up/down state: gap-fill down=0, report transitions (not a "peak").
            fill_state_gaps(deviated)
            if not any(
                event == 'terminated'
                for dev in deviated
                for event, _ in summarize_state_transitions(dev['points'])
            ):
                print(f"  no restart/terminate for {section} {metric_name}, skipping chart",
                      file=sys.stderr)
                continue
            html_output += f"<p><strong>{title} — instance up/down</strong></p>\n"
            html_output += '<ul>\n'
            for dev in deviated:
                events = summarize_state_transitions(dev['points'])
                if events:
                    li_content = f'{dev["instance"]}:'
                    for event, ts in events:
                        ts_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime('%b %d, %H:%M')
                        li_content += f'<br>  {event} - {ts_str}'
                    html_output += f'  <li>{li_content}</li>\n'
                else:
                    html_output += f'  <li>{dev["instance"]}: up (stable)</li>\n'
            html_output += '</ul>\n'
        else:
            reference = deviated[0].get('threshold', deviated[0]['peak'])
            html_output += f"<p><strong>{title} deviation detected</strong></p>\n"
            html_output += f"<p>Reference = {format_value(reference, unit)}</p>\n"
            if data_view == 'table':
                html_output += '<table><tr><th>Instance</th><th>Value</th><th>Timestamp (UTC)</th></tr>\n'
                for dev in deviated:
                    timestamp_str = format_timestamp(dev['timestamp']) if dev['timestamp'] else "N/A"
                    html_output += f'<tr><td>{dev["instance"]}</td><td>{format_value(dev["peak"], unit)}</td><td>{timestamp_str}</td></tr>\n'
                html_output += '</table>\n'
            else:
                html_output += '<ul>\n'
                for dev in deviated:
                    timestamp_str = format_timestamp(dev['timestamp']) if dev['timestamp'] else "N/A"
                    val_text = format_value(dev["peak"], unit)
                    if dev.get("op", ">") in ('<', '<='):
                        html_output += f'  <li>{dev["instance"]}: {val_text} at {timestamp_str}</li>\n'
                    else:
                        html_output += f'  <li>{dev["instance"]}: peak {val_text} at {timestamp_str}</li>\n'
                html_output += '</ul>\n'

        if data_view == 'list' or data_view == 'table':
            continue

        group_slug = metric_slug if not sub_label else f"{metric_slug}_{slugify(sub_label)}"
        region_tag = region or "all"

        overview_payload = {
            "lines": [{"label": label, "points": format_points(pts), "deviated": flagged}
                      for label, pts, flagged in all_series_data],
        }
        if chart_style != 'state':
            # State charts have no meaningful reference line (down=0, up=1).
            overview_payload["threshold"] = {"label": "Reference", "value": reference}
        overview_path = os.path.join(OUTPUT_DIR, f"chart_{region_tag}_{group_slug}.png")
        overview_cfg = {**render_cfg} if render_cfg else {}
        overview_cfg['x_min'] = datetime.fromtimestamp(start_epoch_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
        overview_cfg['x_max'] = datetime.fromtimestamp(sprint_end_ms / 1000, tz=timezone.utc).strftime('%Y-%m-%d %H:%M')
        if generate_chart(title, overview_path, unit, overview_payload, overview_cfg):
            html_output += (
                f'<ac:image ac:align="center" ac:width="950">'
                f'<ri:attachment ri:filename="{os.path.basename(overview_path)}"/></ac:image>\n'
            )

            # Zoom chart: only for full chart mode. Window spans from the
            # earliest to the latest deviated instance's own peak (+ margin),
            # not just the first instance's — otherwise instances whose peak
            # lands far from deviated[0]'s get silently dropped from the zoom
            # even though they're clearly visible (and flagged) in the overview.
            # For STATE metrics, transitions are used instead of dev['timestamp']
            # (which is the min value point and lands at the sprint boundary
            # for gap-filled instances that started mid-sprint).
            if data_view == 'chart':
                margin_s = 7200  # 2h margin
                if chart_style == 'state':
                    zoom_timestamps = [
                        ts for dev in deviated
                        for _, ts in summarize_state_transitions(dev['points'])
                    ]
                    if not zoom_timestamps:
                        continue
                else:
                    zoom_timestamps = [dev['timestamp'] for dev in deviated]
                zoom_start = min(zoom_timestamps) - margin_s
                zoom_end = max(zoom_timestamps) + margin_s
                zoom_lines = []
                for label, pts, flagged in all_series_data:
                    zoomed = slice_zoom(pts, zoom_start, zoom_end)
                    if len(zoomed) >= 3:
                        zoom_lines.append({"label": label, "points": format_points(zoomed), "deviated": flagged})
                if zoom_lines:
                    zoom_payload = {"lines": zoom_lines}
                    if chart_style != 'state':
                        zoom_payload["threshold"] = {"label": "Reference", "value": reference}
                    zoom_path = os.path.join(OUTPUT_DIR, f"chart_{region_tag}_{group_slug}_zoom.png")
                    if generate_chart(f"{title} (zoom)", zoom_path, unit, zoom_payload, render_cfg):
                        html_output += (
                            f'<ac:image ac:align="center" ac:width="950">'
                            f'<ri:attachment ri:filename="{os.path.basename(zoom_path)}"/></ac:image>\n'
                        )

    # Empty when every group was skipped (e.g. state metric with no terminate):
    # treat as no deviation so the caller renders nothing for this metric.
    return html_output or None


def metric_slug(name):
    """Canonical token for a metric name: lowercase, non-alnum → '-', collapsed.
    e.g. 'Error Rates (Spikes) - By Instance' → 'error-rates-spikes-by-instance'."""
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', name.lower())).strip('-')


def load_metric_slugs(config_file):
    """{slug: metric_name} for every active metric in config_file. Used by the
    generators to validate --metric tokens and list valid slugs on error."""
    with open(config_file, 'r') as f:
        cfg = yaml.safe_load(f) or {}
    return {metric_slug(k): k for k, v in cfg.items()
            if isinstance(v, dict) and v.get('status') == 'active'}


def analyze(config_file, start_epoch_ms, end_epoch_ms, region=None, metric_filter=None):
    """Run the full fetch + deviation-detection + chart pipeline for every
    active metric in config_file. Returns the Confluence Storage HTML block.

    metric_filter: optional set of metric slugs (see metric_slug); when given,
    only matching metrics are analysed."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    defaults = config.pop('defaults', {}) if isinstance(config, dict) else {}

    all_html = ""
    has_deviation = False
    failures = []
    baseline_warnings = []

    # One client/session per invocation, reused across all metrics.
    # A dead endpoint raises here (FAIL-FAST) instead of masking as "no deviation".
    section = "xcc" if "xcc" in os.path.basename(config_file).lower() else "rtpengine"
    client = GrafanaHttpClient()
    try:
        for metric_name, cfg in config.items():
            if isinstance(cfg, dict) and cfg.get('status') == 'active':
                if metric_filter and metric_slug(metric_name) not in metric_filter:
                    continue
                result = analyze_metric(client, metric_name, cfg, start_epoch_ms, end_epoch_ms,
                                        region, section, defaults, failures, baseline_warnings)
                if result:
                    all_html += result
                    has_deviation = True
    finally:
        client.close()

    # Build final region block. Section + base link derive from the config.
    section = "RTPEngine" if "rtp" in os.path.basename(config_file).lower() else "XCC"
    dashboard_uid = defaults.get('dashboard', '')
    first_panel_id = next(
        (c.get('panel_id') for c in config.values()
         if isinstance(c, dict) and c.get('status') == 'active' and c.get('panel_id')),
        None,
    )
    if dashboard_uid and first_panel_id is not None and region:
        grafana_link = resolve_grafana_url(dashboard_uid, first_panel_id, region,
                                           start_epoch_ms, end_epoch_ms)
    elif dashboard_uid:
        grafana_link = f"{GRAFANA_ORIGIN}/d/{dashboard_uid}/{dashboard_uid}"
    else:
        grafana_base = next(
            (c.get('grafana') for c in config.values()
             if isinstance(c, dict) and c.get('status') == 'active' and c.get('grafana')),
            GRAFANA_ORIGIN,
        )
        grafana_link = build_grafana_url(grafana_base, region, start_epoch_ms, end_epoch_ms) if region else grafana_base

    final_html = f'<p><a href="{grafana_link}">Grafana — {section} {region}</a></p>\n'

    if failures:
        final_html += (
            '<ac:structured-macro ac:name="warning" ac:schema-version="1">'
            '<ac:rich-text-body>'
            f'<p><strong>⚠ {len(failures)} metric(s) could not be retrieved — '
            'data unreliable, deviation detection skipped for these.</strong></p>'
            '<table><tr><th>Metric</th><th>Panel ID</th><th>Dashboard</th><th>Reason</th></tr>'
        )
        for f in failures:
            final_html += (
                f'<tr><td>{f["metric"]}</td><td>{f["panel_id"]}</td>'
                f'<td>{f["dashboard"]}</td><td>{f["reason"]}</td></tr>'
            )
        final_html += '</table></ac:rich-text-body></ac:structured-macro>\n'

    if baseline_warnings:
        final_html += (
            '<ac:structured-macro ac:name="note" ac:schema-version="1">'
            '<ac:rich-text-body>'
            f'<p><strong>ℹ {len(baseline_warnings)} SPIKE metric series had incomplete '
            'baseline history fetches — seasonal deviation detection is degraded '
            '(floor-only) for these until the gap is backfilled on a later run.</strong></p>'
            '<table><tr><th>Metric</th><th>Sub-query</th><th>Region</th><th>Chunks failed</th></tr>'
        )
        for w in baseline_warnings:
            final_html += (
                f'<tr><td>{w["metric"]}</td><td>{w["sub_label"] or ""}</td>'
                f'<td>{w["region"] or ""}</td><td>{w["chunks_failed"]}</td></tr>'
            )
        final_html += '</table></ac:rich-text-body></ac:structured-macro>\n'

    if has_deviation:
        final_html += all_html
    elif failures:
        final_html += "<p>No deviation detected in the metrics that could be retrieved.</p>\n"
    else:
        final_html += "<p>No deviation detected ✅</p>\n"

    if failures:
        final_html = f"<!-- PANEL_ERRORS:{len(failures)} -->\n" + final_html

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
        global DEBUG_SEASONAL
        argv = sys.argv[2:]
        metric_filter = None
        if "--metric" in argv:
            i = argv.index("--metric")
            metric_filter = {s for s in argv[i + 1].split(",") if s}
            del argv[i:i + 2]
        if "--debug" in argv:
            argv.remove("--debug")
            DEBUG_SEASONAL = True
        if len(argv) < 3:
            sys.exit("Usage: grafana_metrics.py analyze <config_yaml> <start_epoch_ms> "
                     "<end_epoch_ms> [region] [--metric slug[,slug...]] [--debug]")
        config_file = argv[0]
        start_epoch_ms = int(argv[1])
        end_epoch_ms = int(argv[2])
        region = argv[3] if len(argv) > 3 else None
        try:
            print(analyze(config_file, start_epoch_ms, end_epoch_ms, region, metric_filter))
        except Exception as e:
            sys.exit(f"Error: {e}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
