---
name: gcn-pm
description: >
  Builds the GCN Production Meeting Confluence page (Status Review, On-Call
  Alarms, Post-Mortem, XCC Metrics, RTP Engine Metrics, Executive Summary +
  Calls, Events Tracking) and publishes it under the Notes page in Fábio Neto's
  personal Confluence space. MANUAL-ONLY skill: use this ONLY when the user explicitly
  runs the `/gcn-pm` command, or explicitly asks to "generate / build the GCN
  production meeting page". Do NOT trigger proactively, and do NOT trigger for
  general questions about Confluence, Grafana, Kibana, SIP, call metrics, or
  production meetings — only on the explicit invocation above.
  Usage: /gcn-pm SPRINT-START SPRINT-END [section...] [region...] (dates as YYYY-MM-DD).
  Omit section/region for the full page.
  Examples:
    /gcn-pm 2026-06-01 2026-06-02 xcc-metrics              (XCC, all regions)
    /gcn-pm 2026-06-01 2026-06-02 xcc-metrics eu-south-1   (XCC, one region only)
---

# GCN Production Meeting — Page Builder (Orchestrator)

This skill assembles a single Confluence page that mirrors the existing
UCInterconnect "Production Meeting" pages (reference example:
`IC260522`), and publishes it into Fábio Neto's personal space.

This file is the ORCHESTRATOR. It is intentionally thin: it defines the page
skeleton, the section order, the shared anchors (regions, URLs, publish target)
and then delegates the **structure of each section** to one reference file. Each
reference owns exactly one section of the final page.

> SCOPE — DATA COLLECTION IS MANDATORY (NOT structure-only)
> This skill must produce a page filled with REAL collected data, exactly like
> the reference run that worked (page 6568476792, version 37). For every section
> that has a wired data source, you MUST actually query it and render the result:
> - Status Review / Post-Mortem: emit the LIVE Jira datasource tables (storage
>   blockCard — see those references). Never a plain-text paragraph stand-in.
> - XCC - Host Details: run the instant PromQL and fill the table with the real
>   region / version / instance_type values. Never `[TODO]`.
> - XCC, RTP Engine, SBC per-region blocks: run EVERY metric registered in the
>   matching datasources file, detect deviations, and for each deviating metric
>   render a deviation table + a chart (see the per-region algorithm in each
>   reference). A region with no deviations shows only its Grafana/Kibana link.
>
> PLACEHOLDERS ARE ALLOWED ONLY IN TWO CASES:
> 1. Customer PII (CALL_IDs, account names, dialed/diversion phone numbers, IPs):
>    never fabricate — keep redacted placeholders and point to the dashboard.
 > 2. A required tool is genuinely unavailable in this environment (e.g. Playwright
 >    for Kibana/SBC CDR data, or the Grafana MCP): emit the documented warning
 >    panel for that section and the dashboard link — never invented values. As
 >    soon as the tool IS available, collect the data; do not fall back to `[TODO]`.
 >    Note: for the SBC section, Playwright is needed for CDR data; if unavailable
 >    emit the documented warning panel and the dashboard link.
>
> Any `[TODO: run analysis ...]` style text in the published page is a BUG — it
> means the data step was skipped. The only acceptable "no data" states are the
> two cases above.

## ACTIVATION

This skill is manual. Only proceed when the user explicitly invokes it
(`/gcn-pm ...`) or explicitly asks to build the GCN production meeting page.

## ARGUMENTS

```
/gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
```

- `sprint-start`, `sprint-end` (required): the sprint window (ISO dates). These
  fill the header table (Date/Timeframe); they do NOT affect the page title,
  which is FIXED (see PUBLISH TARGET).
- `section ...` (optional): one or more SECTION TOKENS. When present, run in
  **partial / block mode** and render ONLY those sections; when absent, render
  the FULL page (all 7 sections).
- `region ...` (optional): one or more REGION TOKENS. Only meaningful for the
  metric sections (`xcc-metrics`, `rtpengine-metrics`). When present, analyse
  **only the specified region(s)**; when absent, analyse all regions.

Parsing rule: after the two dates, classify each remaining token in order:
1. Matches a known **section token** (table below) → add to section list.
2. Matches a known **region token** (table below) → add to region filter.
3. Matches neither → stop and ask the user to clarify rather than guessing.

If invoked without dates, ask once:

```
Please provide the sprint window:
  /gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
```

## REGION TOKENS

Case-insensitive; `-` and `_` are interchangeable.

| Token            | Ribbon  |
|------------------|---------|
| `eu-south-1`     | EU      |
| `eu-west-3`      | EU      |
| `us-east-1`      | US      |
| `us-west-2`      | US      |
| `ap-southeast-1` | APAC    |
| `ap-southeast-2` | APAC    |
| `sa-east-1`      | LATAM   |
| `ca-central-1`   | (other) |

When a region filter is active:
- **Host Details table**: always built from the full instant PromQL query
  (all regions, one cheap call — no reason to skip it).
- **Per-region analysis**: ONLY the filtered region(s) are queried and rendered.
  Other regions appear as a one-line entry:
  `<p><em>Not analysed in this run (region filter active).</em></p>`
  This keeps the page structure intact while making the run fast.

Unknown region → don't guess; list the valid region tokens and ask.

## SECTION TOKENS (for partial / block runs)

Case-insensitive; `-` and `_` are interchangeable. Each token maps to exactly
one reference (one page section). Accepted aliases:

| Canonical token      | Reference file                     | Aliases                                  |
|----------------------|------------------------------------|------------------------------------------|
| `status-review`      | `references/status-review.md`      | status_review, status                    |
| `on-call-alarms`     | `references/on-call-alarms.md`     | on_call_alarms, on-call, oncall, alarms  |
| `post-mortem`        | `references/post-mortem.md`        | post_mortem, postmortem                  |
| `xcc-metrics`        | `references/xcc-metrics.md`        | xcc_metrics, xcc, kamailio               |
| `rtpengine-metrics`  | `references/rtpengine-metrics.md`  | rtpengine_metrics, rtpengine, rtp        |
| `sbc-metrics`        | `references/sbc-metrics.md`        | sbc_metrics, sbc, calls                  |
| `events-tracking`    | `references/events-tracking.md`    | events_tracking, events                  |
| `all`                | (all of the above)                 | full, page                               |

Unknown token → don't guess; list the valid tokens and ask which one was meant.

## RUN MODES

Every run — full OR block — produces a page that contains ONLY the section(s)
of THAT run. The page is wiped and rebuilt from scratch on each run; it does
NOT accumulate sections across runs.

**Full run** (no section tokens): the rebuilt page = header table + TOC + all 7
sections, in canonical order.

**Block / partial run** (one or more section tokens, e.g.
`/gcn-pm 2026-06-01 2026-06-02 status-review`): the rebuilt page = header table +
TOC + ONLY the requested section(s), in canonical order. Anything that was on
the page before this run is gone — running `status-review` leaves a page with
just Status Review; a later run with `events-tracking` leaves a page with just
Events Tracking (Status Review is no longer there).

Publish algorithm (same for both modes — see PUBLISH TARGET for the "delete &
recreate" semantics and the connector limitation):

1. Build the full body for THIS run (header + TOC + this run's sections only).
2. Locate the single fixed-title page under Notes.
3. If it exists → REPLACE its ENTIRE body with the freshly built body (this
   clears every previously-present section). If it does not exist → CREATE it.
4. The header's Date/Timeframe always reflect THIS run's window.

Because each run fully rebuilds the page, section order is always canonical and
there is never a stale or duplicated section.

This makes the page buildable incrementally, one block at a time, while a full
run regenerates everything at once. The canonical section order is always
preserved regardless of the order blocks are run in.

## SECTION → REFERENCE MAP

The page is composed of these sections, IN THIS ORDER. Read the matching
reference file for the exact structure of each section before authoring it.

| # | Page section                          | Reference file                       | Requested name    |
|---|---------------------------------------|--------------------------------------|-------------------|
| 0 | Header table + Table of Contents      | (this file — see below)              | —                 |
| 1 | Status Review                         | `references/status-review.md`        | Status_Review     |
| 2 | On-Call Alarms                        | `references/on-call-alarms.md`       | On-Call_Alarms    |
| 3 | Post-Mortem (last 90 days)            | `references/post-mortem.md`          | Post-Mortem       |
| 4 | XCC Metrics (Kamailio)                | `references/xcc-metrics.md`          | XCC_Metrics       |
| 5 | RTP Engine Metrics                    | `references/rtpengine-metrics.md`    | RTPEngine_Metrics |
| 6 | Executive Summary + Detailed data by Region   | `references/sbc-metrics.md` | SBC_Metrics |
| 7 | Events Tracking                       | `references/events-tracking.md`      | Events_Tracking   |

Notes on the two intentional design decisions (confirmed with the requester):
- **XCC_Metrics and RTPEngine_Metrics are TWO SEPARATE sections** (this diverges
  on purpose from the example page, which combined them under one
  "Kamailio/RTP Engine Metrics" heading). `xcc-metrics.md` owns a standalone
  "XCC Metrics" section (heading + XCC host-details table + per-region Kamailio
  blocks). `rtpengine-metrics.md` owns its OWN standalone "RTP Engine Metrics"
  section (its own heading + per-region RTP Engine blocks), rendered right after.
- **The call records ("Detailed data by Region") live inside SBC_Metrics**,
  because the per-region call data comes from the SBC CDR logs.
  `sbc-metrics.md` therefore owns Executive Summary + Detailed data by Region
  (calls). There is no separate SBC Ribbon section.

## STEP 0 — HEADER TABLE + TABLE OF CONTENTS (owned here)

At the very top of the page body, emit:

1. A 2-row header table:

   | Date      | <meeting date — the day after sprint end>     |
   | Timeframe | <sprint start> to <sprint end>                |

   Date format follows the example (e.g. "May 21st", "May 07th to May 20th").

2. A Table of Contents: the Confluence **Índice / Table of Contents** macro,
   collapsed by default (an expand macro wrapping the TOC is acceptable). If the
   authoring format can't express the macro, omit the TOC rather than faking it.

Then emit the section(s) selected by this run, in canonical order: all 7 for a
full run, or only the requested token(s) for a block run. Each section is
authored per its reference file.

## REGIONS & RIBBON GROUPINGS (shared anchors)

Per-region order used by the metrics sections (XCC §4 and RTP Engine §5):
```
EU-South-1      → eu-south-1
EU-West-3       → eu-west-3
US-East-1       → us-east-1
US-West-2       → us-west-2
AP1 - Singapore → ap-southeast-1
AP2 - Sydney    → ap-southeast-2
SA-East-1       → sa-east-1
CA-Central-1    → ca-central-1
```

When a **region filter** is active (one or more region tokens passed), the metric
sections follow these rules:
- Host Details table: always built from the full instant query (all regions).
- Filtered region(s): full analysis — spike detection + charts + publish.
- All other regions: render a single collapsed expand block with one line:
  `<em>Not analysed in this run (region filter active).</em>`
  No Prometheus queries are made for skipped regions.

Ribbon groupings used by SBC_Metrics (§6: Detailed data by Region):
```
Ribbon EU    → EU-South-1, EU-West-3
Ribbon US    → US-East-1, US-West-2
Ribbon APAC  → AP1 - Singapore, AP2 - Sydney
Ribbon LATAM → LATAM-AZ1 (São Paulo), LATAM-AZ2 (São Paulo)
```

## PUBLISH TARGET (mandatory)

Publish the assembled page to Confluence with the Atlassian tools:

- Space: `~622745edb7e7c7007159b8df` (Fábio Neto — personal space),
  numeric `spaceId` = `3406136357`.
- Parent page: **Notes**, `pageId` = `3541107151`
  (`https://talkdesk.atlassian.net/wiki/spaces/~622745edb7e7c7007159b8df/pages/3541107151/Notes`).
- `cloudId`: `talkdesk.atlassian.net` (hostname works; if it fails, resolve via
  `getAccessibleAtlassianResources`).
- Title (FIXED — mandatory): the page is ALWAYS titled exactly `GCN PM Auto Test`,
  regardless of run mode (full or block) or sprint window. There is only ever
  ONE such page; sprint-specific detail lives only in the body (header table).
## DELETE & RECREATE (every run starts from a clean page)

Each run must end with the page showing ONLY that run's sections — as if the
page had been deleted and recreated. Implement it like this:

1. Find the existing page titled exactly `GCN PM Auto Test` under Notes
   (`getPagesInConfluenceSpace` with `spaceId=3406136357`, `title` filter, or
   search the personal space).
2. Build the brand-new body for this run (header + TOC + this run's sections
   only).
3. Reset the page by replacing its ENTIRE body, via the **Confluence REST API
   with `representation: "storage"`** (see CONTENT FORMAT below — this is the
   ONLY supported publish path). The full-body overwrite clears every
   previously-present section and keeps the same `pageId`/URL so links stay
   stable. If the page does NOT exist → CREATE it once via the same REST API.

> CONNECTOR LIMITATION — no hard delete. There is NO delete/trash endpoint, and
> the page status stays `current`. The full-body overwrite is the faithful
> equivalent of delete+recreate: the page is fully cleared and rebuilt from this
> run's sections, with nothing left over from prior runs.

> DO NOT publish with the Atlassian MCP tools `updateConfluencePage` /
> `createConfluencePage`. Those tools only accept `contentFormat` of
> `html | markdown | adf` — they CANNOT emit `storage`. Publishing through them
> silently degrades the page: the Jira datasource blockCards (Status Review /
> Post-Mortem live tables) collapse to plain paragraphs, the TOC macro becomes a
> bullet list, and `expand` / `ac:image` macros are mangled. This is exactly the
> v38 regression. Always publish via REST + storage instead (next section).

Never create a second/duplicate page, and never append dates or sprint ids to
the title — the title is always exactly `GCN PM Auto Test`.

## CONTENT FORMAT — MANDATORY: REST API + storage format only

**Publish ONLY via the Confluence REST API with `representation: "storage"`.**
Never use `atlas_doc_format` (ADF), never publish via the Atlassian MCP page
tools (they cannot emit storage — see the warning in DELETE & RECREATE above).

Reason: the page mixes three feature types that only coexist cleanly in storage
format — chart images (`ac:image`), Jira datasource tables (blockCard) and
panels (`ac:structured-macro`). In ADF/html these conflict (media-aware mode)
or degrade (blockCard → plain text), which is what broke v38.

In storage format all required features are available without conflicts:

| Feature | Storage format equivalent |
|---------|--------------------------|
| Info/warning panel | `<ac:structured-macro ac:name="info\|note\|warning">` |
| Jira datasource blockCard | `<p local-id="UUID"/>`<br>`<a data-card-appearance="block" local-id="UUID" data-datasource="{...}">`<br>`<p local-id="UUID"/>` |
| Expand/accordion | `<ac:structured-macro ac:name="expand">` |
| Attachment image | `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>` |
| TOC macro | `<ac:structured-macro ac:name="toc">` inside an expand |

### Editor-native blockCard structure (MANDATORY — never omit)

Every Jira datasource blockCard (Status Review + Post-Mortem) MUST be wrapped
with empty self-closing paragraphs carrying fresh `local-id` UUIDs:

```html
<p local-id="<uuid-pre>" />
<a href="..." data-layout="full-width" local-id="<uuid-card>"
   data-card-appearance="block" data-datasource="{...}">...</a>
<p local-id="<uuid-post>" />
```

Without these wrappers the storage→ADF parser does not register the `<a>` as a
top-level `blockCard` node — the Custom Jira Charts app "fails to get context"
and renders a blank for all users (confirmed root cause, v46 regression, fixed
v47). Generate **3 fresh UUID v4s** per card per run. Attribute order on `<a>`
must be `href, data-layout, local-id, data-card-appearance, data-datasource`.

### Post-publish verification gate (MANDATORY — every run)

After the PUT (`representation: "storage"`), immediately GET the page storage
and assert:

```python
# Pseudo-code — run after every PUT
storage = GET /rest/api/content/6568476792?expand=body.storage
assert storage.count('data-datasource') == 2,  "FAIL: datasource cards missing"
for m in re.finditer(r'data-datasource', storage):
    astart = storage.rfind('<a ', 0, m.start())
    pre    = storage[max(0, astart-50):astart]
    assert '<p local-id=' in pre, "FAIL: missing <p local-id/> before card"
for tag in re.finditer(r'<ac:image[^>]*>', storage):
    assert 'ac:align="center"' in tag.group(), "FAIL: image not centered"
```

If any assertion fails: report the specific failure, do NOT mark the run as
successful, and either fix and re-PUT or surface the error to the user.

### Canonical publish path (REST + storage)

Auth uses the environment variables `$ATLASSIAN_USERNAME` and
`$ATLASSIAN_API_TOKEN` (both present in this environment). Base URL:
`https://talkdesk.atlassian.net/wiki`.

1. Read current version number:
   `GET /rest/api/content/6568476792?expand=version`
2. Update (overwrite whole body) with the next version number:
   ```
   PUT /rest/api/content/6568476792
   Content-Type: application/json
   {
     "version": { "number": <current+1>, "message": "<run description>" },
     "type": "page",
     "title": "GCN PM Auto Test",
     "body": { "storage": { "value": "<full storage HTML>", "representation": "storage" } }
   }
   ```
   Use `curl -u "$ATLASSIAN_USERNAME:$ATLASSIAN_API_TOKEN"`. Write the storage
   body to a temp file and reference it from the JSON payload (build the payload
   with a small Python/jq step) to avoid shell-escaping issues with the large
   HTML and the embedded `data-datasource` JSON.

Chart/screenshot PNGs are uploaded as attachments to the same page id
(`6568476792`) before the PUT, then embedded via `ac:image` + `ri:attachment`.
Upload via the REST attachment endpoint
(`POST /rest/api/content/6568476792/child/attachment`, `X-Atlassian-Token: no-check`)
with the same `$ATLASSIAN_API_TOKEN` when the Atlassian MCP upload tool is not
available.

The `gcn_pm_storage.py` helper (session temp directory) implements this PUT;
keep it as the canonical implementation and always send `representation:
"storage"`.

## FINAL OUTPUT

After publishing, report back:
- ✅ Page rebuilt (state the run mode: full run or block run)
- 🧩 Which section(s) this run rendered — and note that all other sections were
  cleared (the page now contains only this run's sections)
- 📊 Which metrics/regions deviated and got a chart + table this run
- 📄 The page URL
- ⚠️ Any section that fell back to a warning panel because a required tool
  (Playwright / Grafana MCP) was unavailable — never report `[TODO]` as a normal
  outcome; if a wired data source produced no data, say why.
