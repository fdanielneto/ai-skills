#!/usr/bin/env python3
"""Phase-1 evidence gate: does replaying the Vouch cookie over plain HTTP
(no browser) authenticate against Kibana?

Usage: test_kibana_auth.py [start_date] [end_date]   (YYYY-MM-DD, default: last 2 days)

PASS = real Elasticsearch JSON (hits/aggregations present)
FAIL = SSO/login HTML (same fingerprint as the kibana-prd MCP failures)
"""
import json
import sys
from datetime import date, timedelta
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from kibana_auth import cookie_header

KIBANA = "https://kibana-logging.svc.talkdeskapp.com"
# /api/console/proxy is 404 on this Kibana (7.17.6) — /internal/search/es is
# the working endpoint (same one fetch_sbc_data.py uses)
SEARCH_PATH = "/internal/search/es"
INDEX = "logs-td-ribbonsbc-cdr*"


def a1_a3_query(start, end):
    # the real A-1/A-3 combined query from references/sbc-metrics.md
    return {
        "size": 0,
        "query": {"bool": {
            "must": [{"range": {"@timestamp": {
                "gte": f"{start}T00:00:00.000Z", "lte": f"{end}T23:59:59.999Z"}}}],
            "must_not": [{"match_phrase": {"Record Type.keyword": "START"}}],
        }},
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


def main():
    if len(sys.argv) >= 3:
        start, end = sys.argv[1], sys.argv[2]
    else:
        end = date.today().isoformat()
        start = (date.today() - timedelta(days=2)).isoformat()

    payload = {"params": {"index": INDEX, "body": a1_a3_query(start, end)}}
    req = Request(KIBANA + SEARCH_PATH,
                  data=json.dumps(payload).encode(),
                  method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("kbn-xsrf", "true")
    req.add_header("Cookie", cookie_header())

    try:
        resp = urlopen(req, timeout=60)
        body = resp.read().decode()
    except HTTPError as e:
        print(f"FAIL — HTTP {e.code}. Body first 500:\n{e.read().decode()[:500]}")
        sys.exit(1)

    if body.lstrip().startswith("<"):
        print(f"FAIL — HTTP {resp.status} returned HTML (SSO redirect), "
              f"{len(body)} chars. First 300:\n{body[:300]}")
        sys.exit(1)

    data = json.loads(body)
    data = data.get("rawResponse", data)  # /internal/search/es wraps the ES response
    if "aggregations" in data or "hits" in data:
        total = data.get("hits", {}).get("total", {})
        buckets = (data.get("aggregations", {})
                       .get("disconnect_reasons", {}).get("buckets", []))
        print(f"PASS — real ES JSON. hits.total={total}, "
              f"top disconnect buckets={[(b['key'], b['doc_count']) for b in buckets[:3]]}")
        sys.exit(0)

    print(f"FAIL — JSON but not an ES response. Keys: {list(data)[:10]}\n{body[:300]}")
    sys.exit(1)


if __name__ == "__main__":
    main()
