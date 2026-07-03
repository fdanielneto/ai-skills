# SBC Collection API Payloads

**Load this file when you are ready to collect SBC/Kibana data via the API.**

Instead of browser automation, use `kibana-prd_execute_kb_api` with:
- **method:** `POST`
- **path:** `/api/console/proxy?path=logs-td-ribbonsbc-cdr*/_search&method=POST`

**CRITICAL RULE FOR ALL SUBAGENTS:**
Return ONLY the final Markdown table or Confluence XML macro requested. Do not return raw JSON responses or extra prose.

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

**Extraction Logic:**
1. `TOTAL_CALL_ATTEMPTS` = `hits.total.value`
2. `TOTAL_MEDIA_ANCHORING_CALLS` = `aggregations.media_anchoring.doc_count`
3. Disconnect Top 10 = `aggregations.disconnect_reasons.buckets`

**Return format:**
Return two distinct blocks.
First, a Markdown table for A-1:
```markdown
| Metric                              | Value                          |
|-------------------------------------|--------------------------------|
| Total Call Attempts (all)           | <TOTAL_CALL_ATTEMPTS>          |
| Total Media Anchoring Calls (all)   | <TOTAL_MEDIA_ANCHORING_CALLS>  |
```

Second, a Markdown table for A-3:
```markdown
| Metric | Value |
|--------|-------|
| Total calls (STOP) | <TOTAL_CALL_ATTEMPTS> |
| <Reason 1> | <count> (<pct>%) |
| <Reason 2> | <count> (<pct>%) |
```
*(pct = count / TOTAL_CALL_ATTEMPTS * 100, one decimal place)*

---

## A-2. Call Disconnect Reason (excluding 16) — Pie Chart Macro

Execute this query:

```json
{
  "size": 0,
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "<START_SPRINT_DATE>T00:00:00.000Z", "lte": "<END_SPRINT_DATE>T23:59:59.000Z" } } }
      ],
      "must_not": [
        { "match_phrase": { "Record Type.keyword": "START" } },
        { "match_phrase": { "Call Disconnect Reason.keyword": "16" } }
      ]
    }
  },
  "aggs": {
    "reasons": {
      "terms": { "field": "Call Disconnect Reason.keyword", "size": 20 }
    }
  }
}
```

**Return format:**
Return a Native Confluence Pie Chart macro mapping the `aggregations.reasons.buckets` array:

```xml
<ac:structured-macro ac:name="chart">
  <ac:parameter ac:name="type">pie</ac:parameter>
  <ac:parameter ac:name="title">Call Disconnect Reason (excluding 16)</ac:parameter>
  <ac:parameter ac:name="dataOrientation">vertical</ac:parameter>
  <ac:parameter ac:name="width">600</ac:parameter>
  <ac:parameter ac:name="height">400</ac:parameter>
  <ac:rich-text-body>
    <table>
      <tbody>
        <tr><th>Reason</th><th>Count</th></tr>
        <!-- One row per bucket -->
        <tr><td><bucket.key></td><td><bucket.doc_count></td></tr>
      </tbody>
    </table>
  </ac:rich-text-body>
</ac:structured-macro>
```

---

## B-1. Disconnect Codes by Ribbon (run once per Ribbon)

Substitute `<SBC_A>`, `<SBC_B>` based on the Ribbon mapping.

```json
{
  "size": 0,
  "query": {
    "bool": {
      "must": [
        { "range": { "@timestamp": { "gte": "<START_SPRINT_DATE>T00:00:00.000Z", "lte": "<END_SPRINT_DATE>T23:59:59.000Z" } } },
        {
          "bool": {
            "should": [
              { "match_phrase": { "Gateway Name.keyword": "<SBC_A>" } },
              { "match_phrase": { "Gateway Name.keyword": "<SBC_B>" } }
            ]
          }
        }
      ],
      "must_not": [
        { "match_phrase": { "Record Type.keyword": "START" } }
      ]
    }
  },
  "aggs": {
    "reasons": {
      "terms": { "field": "Call Disconnect Reason.keyword", "size": 5 }
    }
  }
}
```

**Extraction Logic:**
1. Total calls for Ribbon = `hits.total.value`
2. Top 5 Reasons = `aggregations.reasons.buckets`

**Return format:**
A Markdown table:
```markdown
| Metric | Value |
|--------|-------|
| Total calls (STOP) | <Ribbon_Total_Calls> |
| <Reason 1> | <count> (<pct>%) |
```

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
        "calendar_interval": "1d",
        "format": "yyyy-MM-dd"
      }
    }
  }
}
```

**Return format:**
A Native Confluence Line Chart macro mapping the `aggregations.timeline.buckets` array:

```xml
<ac:structured-macro ac:name="chart">
  <ac:parameter ac:name="type">line</ac:parameter>
  <ac:parameter ac:name="title">Call Attempts</ac:parameter>
  <ac:parameter ac:name="timeSeries">true</ac:parameter>
  <ac:parameter ac:name="dataOrientation">vertical</ac:parameter>
  <ac:parameter ac:name="width">800</ac:parameter>
  <ac:parameter ac:name="height">350</ac:parameter>
  <ac:parameter ac:name="dateFormat">yyyy-MM-dd</ac:parameter>
  <ac:rich-text-body>
    <table>
      <tbody>
        <tr><th>Date</th><th><SBC_NAME></th></tr>
        <!-- One row per bucket -->
        <tr><td><bucket.key_as_string></td><td><bucket.doc_count></td></tr>
      </tbody>
    </table>
  </ac:rich-text-body>
</ac:structured-macro>
```
