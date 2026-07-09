# SBC_Metrics — Executive Summary + Detailed data by Region (Calls)

This reference owns two consecutive parts of the page. The per-region **call
records** live here (not in a separate Calls reference) because the call data
comes from the SBC CDR logs.

Order on the page: **(A) Executive Summary → (B) Detailed data by Region**.
All region/Ribbon dropdowns are collapsed-by-default expand macros.

---

## DATA COLLECTION

### Source — Kibana (Elasticsearch via Playwright)

Call records live in `kibana-logging.svc.talkdeskapp.com`. Data collection is performed 
using the Playwright MCP to execute Elasticsearch `_search` queries against the `logs-td-ribbonsbc-cdr*` index or directly from the Kibana UI via screenshots and DOM extraction.

**Kibana Authentication via Playwright:**
Authentication must be handled exclusively via the `playwright_browser_navigate` tool.
1. Open the Kibana URL.
2. Attempt to fetch data or check if authentication is requested.
3. If authentication is requested, wait 10 seconds (`sleep 10`) and try again. Do this for a maximum of 2 retries.
4. If authentication still fails after retries, abort with `[FATAL_AUTH_ERROR]`.

### Region → SBC Map

Each sub-region corresponds to exactly **one SBC**. Filters in §B must use the 
**`Gateway Name.keyword`** (the SBC name), NOT `region.keyword` — because both LATAM SBCs share `sa-east-1`.

| Region             | Ribbon  | SBC name (`Gateway Name.keyword`) |
|--------------------|---------|-----------------------------------|
| EU-South-1         | EU      | `PRDEUS1RSBC`                     |
| EU-West-3          | EU      | `PRDEUW3RSBC`                     |
| US-East-1          | US      | `prduse1rsbc`                     |
| US-West-2          | US      | `prdusw2rsbc`                     |
| AP1 - Singapore    | APAC    | `PRDAPS1RSBC`                     |
| AP2 - Sydney       | APAC    | `PRDAPS2RSBC`                     |
| LATAM-AZ1 (São Paulo) | LATAM | `PRDSAE1RSBC1`                  |
| LATAM-AZ2 (São Paulo) | LATAM | `PRDSAE1RSBC2`                  |

### Collection rules

Execute the collection tasks below using the `playwright_browser_evaluate` tool to perform authenticated `fetch()` calls to the Kibana Proxy API from within the browser page, or extract from the DOM if necessary.

**CRITICAL: ISOLATION BY SUBAGENT**
To prevent context bloat, the orchestrator launches **one isolated subagent per task**. Each subagent should use Playwright to gather data for its specific assignment and write the final Confluence HTML/macro output to a local temporary file.

Wait for each subagent to execute its calls and return ONLY the final scalar value, Markdown table, or Confluence XML macro.

> PII rule: never fabricate CALL_IDs, account names, phone numbers or IPs.
> Keep raw identifiers redacted; use the dashboards as the source of truth.

---

## A. Executive Summary

A single heading (H1) that links to the Kibana overview dashboard:
**[Executive Summary](https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/97c532ef-3354-4392-a153-141a02816e90?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:'<START_SPRINT_DATE>T00:00:00.000Z',to:'<END_SPRINT_DATE>T23:59:59.000Z')))**

Immediately after the heading-link, emit **exactly one** plain sentence:

```
Total: <N> completed calls.
```

- `<N>` = total STOP-record call count for the sprint (collected from Kibana API).
- Use comma-separated thousands (e.g. `2,365,167`).

Then emit the following three content blocks **in this exact order**:
`A-1 table → A-3 table`. Each block is preceded by its own **H3 heading**.

---

### A-1. Total Call Attempts & Media Anchoring

Emit a visible **H3 heading**: `Total Call Attempts & Media Anchoring`

> Collection prompt: see § A-1 & A-3 below.

Render the resulting two-row table in storage format on the page.

---


### A-3. Call Disconnect Reason (all regions) — Top 10

> Collection prompt: see § A-1 & A-3 below.

Render the resulting table in storage format on the page.

---

## B. Detailed data by Region

1. Heading (H1): **Detailed data by Region**

2. Grouped by Ribbon (H2), in order: **Ribbon EU, Ribbon US, Ribbon APAC, Ribbon LATAM**.
   Region membership:
   - Ribbon EU   → EU-South-1, EU-West-3
   - Ribbon US   → US-East-1, US-West-2
   - Ribbon APAC → AP1 - Singapore, AP2 - Sydney
   - Ribbon LATAM→ LATAM-AZ1 (São Paulo), LATAM-AZ2 (São Paulo)

### B-1. Disconnect Codes by Region (4 mini-tables, 2+2 layout)

Rendered **once** at the top of §B, before any per-region dropdown.

Four mini-tables in two rows of two via `<ac:layout>` with `two_equal` sections.

Layout structure (storage format):
```xml
<ac:layout>
  <ac:layout-section ac:type="two_equal">
    <ac:layout-cell><!-- EU mini-table --></ac:layout-cell>
    <ac:layout-cell><!-- US mini-table --></ac:layout-cell>
  </ac:layout-section>
  <ac:layout-section ac:type="two_equal">
    <ac:layout-cell><!-- APAC mini-table --></ac:layout-cell>
    <ac:layout-cell><!-- LATAM mini-table --></ac:layout-cell>
  </ac:layout-section>
</ac:layout>
```

Each mini-table structure:
```
| <Ribbon Name>               |                    |   ← colspan=2 header row
|-----------------------------|--------------------| 
| Total calls (STOP)          | <count>            |
| <Reason Name> (<code>)      | <count> (<pct>%)   |
| …                           | …                  |
```

- First row spans both columns and shows the Ribbon name (e.g. **Ribbon EU**).
- Second row: `Total calls (STOP)` → total STOP count (no percentage).
- Remaining rows: one per disconnect code, ordered by count descending,
  `<Reason Name> (<code>)` → `<count> (<pct>%)`, pct = one decimal place.
- **Font size:** wrap each mini-table in `<div style="font-size: 0.85em;">…</div>`.

> Collection prompt: see § B-1 below.

---

### B-2. Per-SBC Call Attempts (Timeline Chart)

For **each of the 8 individual SBCs**, an expandable dropdown (sub-region name as title, e.g., "EU-South-1").

**CRITICAL**: You MUST run the query and generate the chart for EACH INDIVIDUAL SBC separately (8 total). The 'EU-South-1' dropdown should ONLY contain the chart for `PRDEUS1RSBC`. DO NOT group by Ribbon for this step.

Inside each dropdown:
1.  Run the B-2 ES query (see § B-2 below), then pipe the response into
    `python3 scripts/sbc_analyzer.py b2 <SBC_NAME>` (e.g. `PRDEUS1RSBC`).
2.  The script generates the PNG locally and prints the ready `<ac:image>` tag.
3.  Paste that tag directly — do not build the image tag by hand.

---

## Notes
- **IMAGE ALIGNMENT**: All `<ac:image>` tags MUST carry `ac:align="center" ac:width="950"`.
- **NO-TODO / FALLBACK**: Never fabricate values. If a required tool is genuinely unavailable, emit a warning macro only. Do not emit `[TODO]`.
- **FAIL-FAST RULE**: If the Kibana source returns an authentication error (like a Google OAuth login page) or is unreachable after Playwright auth retries, you MUST return exactly the string `[FATAL_AUTH_ERROR]`. Do not generate warning panels or XML macros.
- The Disconnect Codes by Region tables (§B-1) are placed at the top of §B, before the per-region dropdowns.
- Mirror example pages (IC260508 / IC260522) for per-Ribbon dashboard order.
# SBC Collection API Payloads

**Load this file when you are ready to collect SBC/Kibana data.**

Use Playwright's `browser_evaluate` to run a `fetch()` request against the authenticated session:
- **method:** `POST`
- **path:** `/api/console/proxy?path=logs-td-ribbonsbc-cdr*/_search&method=POST`
- **headers:** Ensure you pass `kbn-xsrf: true`.

**CRITICAL RULE FOR ALL SUBAGENTS:**
1. If the Playwright fetch returns an authentication error (like a Google OAuth login page) or is unreachable, you MUST return exactly the string `[FATAL_AUTH_ERROR]` along with a brief description. Do not generate warning panels or XML macros.
2. Otherwise, return ONLY the final Markdown table or Confluence XML macro requested. Do not return raw JSON responses or extra prose.

---

## A-1 & A-3. Total Call Attempts, Media Anchoring & Top 10 Disconnects (Combined)

Execute the following Elasticsearch JSON query (substitute `<START_SPRINT_DATE>` and `<END_SPRINT_DATE>`):

```json
{
  "size": 0,
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "<START_SPRINT_DATE>T00:00:00.000Z", "lte": "<END_SPRINT_DATE>T23:59:59.000Z" } } }
      ],
      "must_not": [
        { "match_phrase": { "Record Type.keyword": "START" } }
      ]
    }
  },
  "aggs": {
    "disconnect_reasons": {
      "terms": { "field": "Call Disconnect Reason.keyword", "size": 10 }
    },
    "media_anchoring": {
      "filter": {
        "bool": {
          "must": [
            { "match_phrase": { "Record Type.keyword": "STOP" } }
          ],
          "must_not": [
            { "match_phrase": { "Ingress Number of Audio Packets Received.keyword": "" } }
          ]
        }
      }
    }
  }
}
```

**Return format:**
Pipe the raw ES response into `python3 scripts/sbc_analyzer.py a1-a3`; paste
its stdout verbatim (it prints the A-1 table then the A-3 table, in order —
do NOT hand-compute counts or percentages). Note: A-3's "Top 10" may render
fewer than 10 rows — `sbc_analyzer.py` silently drops disconnect-reason
buckets under 0.5% of total (a deliberate token-saving filter); that's
expected, not a regression.

---


## B-1. Disconnect Codes by Ribbon (single combined query, all 4 Ribbons)

One query returns all four Ribbons at once via a `filters` aggregation (each
named filter matches that Ribbon's 2 SBCs from the Region → SBC Map above) —
avoids 4 separate round-trips.

```json
{
  "size": 0,
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "<START_SPRINT_DATE>T00:00:00.000Z", "lte": "<END_SPRINT_DATE>T23:59:59.000Z" } } }
      ],
      "must_not": [
        { "match_phrase": { "Record Type.keyword": "START" } }
      ]
    }
  },
  "aggs": {
    "ribbons": {
      "filters": {
        "filters": {
          "EU": { "bool": { "should": [
            { "match_phrase": { "Gateway Name.keyword": "PRDEUS1RSBC" } },
            { "match_phrase": { "Gateway Name.keyword": "PRDEUW3RSBC" } }
          ] } },
          "US": { "bool": { "should": [
            { "match_phrase": { "Gateway Name.keyword": "prduse1rsbc" } },
            { "match_phrase": { "Gateway Name.keyword": "prdusw2rsbc" } }
          ] } },
          "APAC": { "bool": { "should": [
            { "match_phrase": { "Gateway Name.keyword": "PRDAPS1RSBC" } },
            { "match_phrase": { "Gateway Name.keyword": "PRDAPS2RSBC" } }
          ] } },
          "LATAM": { "bool": { "should": [
            { "match_phrase": { "Gateway Name.keyword": "PRDSAE1RSBC1" } },
            { "match_phrase": { "Gateway Name.keyword": "PRDSAE1RSBC2" } }
          ] } }
        }
      },
      "aggs": {
        "reasons": {
          "terms": { "field": "Call Disconnect Reason.keyword", "size": 5 }
        }
      }
    }
  }
}
```

**Return format:**
Pipe the combined ES response into `python3 scripts/sbc_analyzer.py b1`;
paste its stdout verbatim — it already prints the complete `<ac:layout>`
with all four mini-tables in the 2+2 layout described above. Do not
hand-compute totals or percentages.

---

## B-2. Per-region Call Attempts (run once per SBC)

Substitute `<SBC_NAME>`.

```json
{
  "size": 0,
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "<START_SPRINT_DATE>T00:00:00.000Z", "lte": "<END_SPRINT_DATE>T23:59:59.000Z" } } },
        { "match_phrase": { "Gateway Name.keyword": "<SBC_NAME>" } }
      ],
      "must_not": [
        { "match_phrase": { "Record Type.keyword": "START" } }
      ]
    }
  },
  "aggs": {
    "timeline": {
      "date_histogram": {
        "field": "@timestamp",
        "fixed_interval": "1h",
        "format": "yyyy-MM-dd HH:mm"
      }
    }
  }
}
```

**Return format:**
Pipe the raw ES response into `python3 scripts/sbc_analyzer.py b2 <SBC_NAME>`;
it generates `output/sbc_timeline_<SBC_NAME>.png` and prints the ready
`<ac:image>` tag on stdout — paste that directly, do not build the chart JSON
or call `plot_helper.py` yourself.
