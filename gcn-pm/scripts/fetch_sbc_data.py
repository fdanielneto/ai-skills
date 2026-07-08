#!/usr/bin/env python3
"""Fetch B-2 timeline data for all 8 SBCs via Kibana internal search API.

Usage: fetch_sbc_data.py <start_date> <end_date>   (dates as YYYY-MM-DD)
"""
import json, sys, os, time, re
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# Canonical skill tmp dir, resolved from this script's location (profile-agnostic).
TMP = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp"))
KIBANA = "https://kibana-logging.svc.talkdeskapp.com"

SBCS = [
    "PRDEUS1RSBC", "PRDEUW3RSBC",
    "prduse1rsbc", "prdusw2rsbc",
    "PRDAPS1RSBC", "PRDAPS2RSBC",
    "PRDSAE1RSBC1", "PRDSAE1RSBC2",
]

# Get session cookie and CSRF token from cookie jar or env
SESSION = os.environ.get("KIBANA_SESSION")
COOKIE = os.environ.get("KIBANA_COOKIE", "")

def build_query_body(gte, lte):
    return {
        "params": {
            "index": "logs-td-ribbonsbc-cdr*",
            "body": {
                "query": {
                    "bool": {
                        "filter": [
                            {"range": {"@timestamp": {"gte": gte, "lte": lte}}}
                        ]
                    }
                },
                "size": 0,
                "aggs": {
                    "calls_over_time": {
                        "date_histogram": {
                            "field": "@timestamp",
                            "fixed_interval": "1h",
                            "min_doc_count": 0,
                            "extended_bounds": {"min": gte, "max": lte}
                        }
                    }
                }
            }
        }
    }

def fetch_sbc(name, query_body):
    q = json.loads(json.dumps(query_body))
    q["params"]["body"]["query"]["bool"]["filter"].append({"term": {"host.hostname": name}})
    
    data = json.dumps(q).encode()
    req = Request(f"{KIBANA}/internal/search/es", data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("kbn-xsrf", "true")
    if COOKIE:
        req.add_header("Cookie", COOKIE)
    if SESSION:
        req.add_header("Authorization", f"Bearer {SESSION}")
    
    try:
        resp = urlopen(req, timeout=60)
        raw = json.loads(resp.read().decode())
        if "rawResponse" not in raw:
            print(f"  WARN: no rawResponse for {name}, keys={list(raw.keys())}")
            return None
        
        agg = raw["rawResponse"].get("aggregations", {}).get("calls_over_time", {})
        buckets = agg.get("buckets", [])
        total = sum(b["doc_count"] for b in buckets)
        print(f"  {name}: {len(buckets)} buckets, {total} total calls")
        
        out = {
            "sbc": name,
            "buckets": [{"t": b["key_as_string"], "c": b["doc_count"]} for b in buckets]
        }
        safe = re.sub(r'[^a-zA-Z0-9]', '_', name)
        with open(f"{TMP}/timeline_{safe}.json", "w") as f:
            json.dump(out, f)
        return out
    except HTTPError as e:
        body = e.read().decode()[:500]
        print(f"  ERROR {name}: HTTP {e.code} - {body}")
        return None

def main():
    if len(sys.argv) < 3:
        print("Usage: fetch_sbc_data.py <start_date> <end_date>  (YYYY-MM-DD)", file=sys.stderr)
        sys.exit(1)

    start_date, end_date = sys.argv[1], sys.argv[2]
    gte = f"{start_date}T00:00:00.000Z"
    lte = f"{end_date}T23:59:59.999Z"
    query_body = build_query_body(gte, lte)

    os.makedirs(TMP, exist_ok=True)
    print(f"Window: {gte} .. {lte}  ->  {TMP}")
    for sbc in SBCS:
        print(f"Fetching {sbc}...")
        r = fetch_sbc(sbc, query_body)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
