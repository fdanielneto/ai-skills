#!/usr/bin/env python3
"""Fetch SBC CDR data (A-1/A-3, B-1, B-2) from Kibana over plain HTTP.

Auth: the Vouch session cookie maintained by kibana_auth.py (refresh with
`python3 kibana_auth.py refresh` when this script reports an auth error).
No browser is involved here — validated by test_kibana_auth.py.

Usage: fetch_sbc_data.py <start_date> <end_date> [a1-a3|b1|b2|all]   (dates YYYY-MM-DD)

Writes raw Elasticsearch responses (unwrapped, ready to pipe into
sbc_analyzer.py) to gcn-pm/tmp/:
  sbc_a1a3.json, sbc_b1.json, sbc_b2_<SBC>.json
"""
import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from kibana_auth import cookie_header

TMP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp"))
KIBANA = "https://kibana-logging.svc.talkdeskapp.com"
SEARCH_PATH = "/internal/search/es"  # /api/console/proxy is 404 on this Kibana (7.17.6)
INDEX = "logs-td-ribbonsbc-cdr*"

SBCS = [
    "PRDEUS1RSBC", "PRDEUW3RSBC",
    "prduse1rsbc", "prdusw2rsbc",
    "PRDAPS1RSBC", "PRDAPS2RSBC",
    "PRDSAE1RSBC1", "PRDSAE1RSBC2",
]

RIBBONS = {
    "EU": ["PRDEUS1RSBC", "PRDEUW3RSBC"],
    "US": ["prduse1rsbc", "prdusw2rsbc"],
    "APAC": ["PRDAPS1RSBC", "PRDAPS2RSBC"],
    "LATAM": ["PRDSAE1RSBC1", "PRDSAE1RSBC2"],
}


def _base_query(gte, lte):
    return {"bool": {
        "must": [{"range": {"@timestamp": {"gte": gte, "lte": lte}}}],
        "must_not": [{"match_phrase": {"Record Type.keyword": "START"}}],
    }}


def a1_a3_body(gte, lte):
    return {
        "size": 0,
        "query": _base_query(gte, lte),
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


def b1_body(gte, lte):
    filters = {
        ribbon: {"bool": {"should": [
            {"match_phrase": {"Gateway Name.keyword": sbc}} for sbc in sbcs
        ]}}
        for ribbon, sbcs in RIBBONS.items()
    }
    return {
        "size": 0,
        "query": _base_query(gte, lte),
        "aggs": {"ribbons": {
            "filters": {"filters": filters},
            "aggs": {"reasons": {"terms": {
                "field": "Call Disconnect Reason.keyword", "size": 5}}},
        }},
    }


def b2_body(gte, lte, sbc):
    body = {
        "size": 0,
        "query": _base_query(gte, lte),
        "aggs": {"timeline": {"date_histogram": {
            "field": "@timestamp",
            "fixed_interval": "1h",
            "format": "yyyy-MM-dd HH:mm",
        }}},
    }
    body["query"]["bool"]["must"].append(
        {"match_phrase": {"Gateway Name.keyword": sbc}})
    return body


def search(body):
    """POST the ES body via Kibana's internal search API; return the raw ES response."""
    payload = {"params": {"index": INDEX, "body": body}}
    req = Request(KIBANA + SEARCH_PATH, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("kbn-xsrf", "true")
    req.add_header("Cookie", cookie_header())
    try:
        resp = urlopen(req, timeout=60)
        text = resp.read().decode()
    except HTTPError as e:
        sys.exit(f"ERROR: HTTP {e.code} from Kibana: {e.read().decode()[:300]}")
    if text.lstrip().startswith("<"):
        sys.exit("ERROR: Kibana returned an SSO/login page — session expired. "
                 "Run: python3 gcn-pm/scripts/kibana_auth.py refresh")
    data = json.loads(text)
    if "rawResponse" not in data:
        sys.exit(f"ERROR: unexpected response, keys={list(data)[:10]}")
    return data["rawResponse"]


def _save(name, data):
    path = os.path.join(TMP, name)
    with open(path, "w") as f:
        json.dump(data, f)
    return path


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    start, end = sys.argv[1], sys.argv[2]
    mode = sys.argv[3] if len(sys.argv) > 3 else "all"
    gte = f"{start}T00:00:00.000Z"
    lte = f"{end}T23:59:59.999Z"

    os.makedirs(TMP, exist_ok=True)
    print(f"Window: {gte} .. {lte}  ->  {TMP}")

    if mode in ("a1-a3", "all"):
        raw = search(a1_a3_body(gte, lte))
        total = raw.get("hits", {}).get("total", {})
        print(f"  a1-a3: hits.total={total} -> {_save('sbc_a1a3.json', raw)}")

    if mode in ("b1", "all"):
        raw = search(b1_body(gte, lte))
        ribbons = raw.get("aggregations", {}).get("ribbons", {}).get("buckets", {})
        counts = {k: v.get("doc_count") for k, v in ribbons.items()}
        print(f"  b1: {counts} -> {_save('sbc_b1.json', raw)}")

    if mode in ("b2", "all"):
        for sbc in SBCS:
            raw = search(b2_body(gte, lte, sbc))
            buckets = raw.get("aggregations", {}).get("timeline", {}).get("buckets", [])
            total = sum(b["doc_count"] for b in buckets)
            print(f"  b2 {sbc}: {len(buckets)} buckets, {total} calls "
                  f"-> {_save(f'sbc_b2_{sbc}.json', raw)}")
            time.sleep(0.3)


if __name__ == "__main__":
    main()
