# XCC_Metrics — "XCC Metrics" section (its own section)

XCC == kamailio-sip-router (Kamailio). Standalone section (separate from RTP
Engine, per the requester's decision).

> SCOPE RULE (applies to the WHOLE section): only the role
> **`kamailio-edgerouter`** matters. In PromQL this is `role="edgerouter"`
> (the instances are named `kamailio-edgerouter-*`). IGNORE every other kamailio
> role (proxy, registrar, etc.) in all queries and analysis.

> DATA SOURCES: analyse ONLY the Grafana dashboards / panels and PromQL filters
> listed in `references/xcc-datasources.md`. Do not browse other dashboards or
> invent metrics. That file is the single source of truth for what to analyse.

---

## Structure (in order)

### H1: XCC Metrics

### Sub-section A — "XCC - Host Details" (expandable, collapsed)

An expandable block titled **XCC - Host Details** containing ONE table with one
row per region.

#### Data fetch (most performant — chosen over rendering the Grafana view)
Run a single INSTANT PromQL query via the Grafana MCP and read the labels off
each returned series — no browser, no per-host series to dedupe:

```
tool:   grafana-mcp-prd:query_prometheus
datasourceUid: prometheus
queryType:     instant
endTime:       now
expr:          count by (region, version, instance_type) (custom_metrics{role="edgerouter"})
```

Each result series carries the three labels needed. Map them to the columns:

| Column          | Source label    | Example     |
|-----------------|-----------------|-------------|
| **XCC**         | `region`        | eu-south-1  |
| **Version**     | `version`       | xcc-v5.0.2  |
| **Instance Type** | `instance_type` | c5.xlarge |

Build one table row per series, sorted by region. Do NOT add other columns and
do NOT take a screenshot — the table is built from the query result directly.

> MANDATORY: this table must contain the REAL values returned by the query
> (e.g. `xcc-v5.0.2` / `c5.xlarge`), exactly as it did in the working v37 run.
> NEVER emit `[TODO]` or `[TODO]`-style placeholder cells. If the Grafana MCP is
> unavailable, emit a single `warning` panel for the whole sub-section stating
> the Grafana MCP was unavailable — do not publish an empty/`[TODO]` table.

#### Detecting version / instance-type changes during the sprint

After building the table, run two additional instant PromQL queries — one at
`sprint_start` and one at `sprint_end` — using the same expression:

```
count by (region, version, instance_type) (custom_metrics{role="edgerouter"})
```

Compare the `(version, instance_type)` pair for each region between the two
snapshots. If they differ, a rolling replacement or deploy occurred during the
sprint. In that case, add a **brief one-line note as a paragraph AFTER the
table** (never as a table row or interleaved between region rows):

```
Note: <region> had a rolling instance replacement during the sprint (<old> → <new>) at 2026-XX-XX XXhXXm UTC
```

Rules for the note:
- One note per change event (version change and/or instance_type change).
- Combine both if they co-occur: `(<old_type>, <old_version>) → (<new_type>, <new_version>)`.
- The timestamp is the approximate midpoint of the sprint when the series label
  changed (use the sprint_start query vs sprint_end query to bound it; if
  a finer timestamp is not available, write `during the sprint` without a time).
- If no change is detected for a region: **no note at all** — complete silence.
- If the Grafana MCP is unavailable for the second query, skip the delta check
  silently (the table is still published from the first query).
- Notes are plain paragraphs rendered AFTER the complete table — never inside
  it or between rows.

REGION SET (used by the WHOLE section): the set of regions is whatever this
query returns — i.e. every region that currently has `kamailio-edgerouter`
instances. Never hardcode it. If edgerouters appear in a new region later, that
region is automatically included (both here and in the per-region sub-sections).
At the time of writing the query returns 8 regions (incl. `ca-central-1`), but
always use the live result, not this number.

### Sub-sections B…N — one expandable per region

> REGION FILTER: if the invocation included one or more region tokens
> (e.g. `/gcn-pm ... xcc-metrics eu-south-1`), then:
> - Only the filtered region(s) are analysed (spike detection + charts).
> - Every other region renders as a minimal collapsed expand block:
>   ```html
>   <details><summary>{region}</summary>
>   <p><em>Not analysed in this run (region filter active).</em></p>
>   </details>
>   ```
>   No Prometheus queries are made for skipped regions.
> - The Host Details table is always built in full (single instant query — cheap).
>
> If NO region filter is given, all regions are analysed as normal.

Emit one expandable block per region (collapsed), iterating over the SAME region
set discovered for the Host Details table (every region with
`kamailio-edgerouter` instances — never a hardcoded list). Sort regions
consistently (e.g. by Ribbon grouping, then alphabetically); if a new region
shows up in the query, it automatically gets its own block.

For each region, the content is driven by `references/xcc-datasources.md`
(see "Per-region analysis algorithm" below). Each block contains:
- A **parameterized** link to the region's Grafana dashboard (see GRAFANA LINK
  FORMAT below)
- Bold issue-group headings for any deviation found this sprint
- Minimal finding bullets (see FINDING FORMAT below) under each heading
- A chart image embedded via `ac:image` + `ri:attachment` for each deviating metric

### GRAFANA LINK FORMAT (mandatory for every per-region Grafana link)

When emitting a Grafana link for a per-region block, build a **parameterized
URL** by appending the region variable and sprint timestamps to the `goto` base
URL from the datasources file:

```
<base_goto_url>&var-region=<region>&from=<sprint_start_epoch_ms>&to=<sprint_end_epoch_ms>
```

Example — eu-south-1, sprint 2026-06-16 to 2026-06-17:
```
https://grafana-general.svc.talkdeskapp.com/goto/cfolortpdd2psd?orgId=1&var-region=eu-south-1&from=1750032000000&to=1750118400000
```

Convert sprint dates to Unix epoch milliseconds (YYYY-MM-DDT00:00:00Z).

The link text must identify both the metric and the region, e.g.:
`[Grafana — xConnect EU-South-1 Error Rates (by instance)](<parameterized URL>)`

### FINDING FORMAT (mandatory for every per-region deviation bullet)

When a metric deviates:
1. Emit `Reference = N.NN <unit>` as plain text above the bullets (one line).
2. For each deviating **instance** (omit instances that are within normal range —
   no mention, no bullet, not even a "within range" note):
   ```
   * <instance>: <metric/error-code> peak <value> <unit> at <YYYY-MM-DDTHH:MMZ>
   ```
3. **Strip** from bullets:
   - AZ / instance-type annotations (no `(AZ-c)`, `(c5.large)`, etc.)
   - Threshold values (no `mean+3σ threshold …`, no `median+2×IQR`, no `+37.6%`)
   - Instance count summaries for non-deviating instances (no "zero throughout
     sprint", "unaffected", "within baseline range")
   - Trailing `OK — Kamailio Alive, CPU, Memory … within normal range` lines
     when the region block has deviating metrics (already covered by SILENCE rule)
   - Editorial commentary: no "business hours", no "fleet-wide", no "likely
     cause", no correlation sentences
4. Metric group heading must be short and factual — metric + date only. No
   editorializing.

### Per-region analysis algorithm (consumes xcc-datasources.md)

> DATA SOURCE RULE: analyse ALL metrics listed in `xcc-datasources.md`, in
> section order. For metrics with `status: active`, you MUST use the Two-Phase Fetch 
> (Instant Phase 1, Range Phase 2) as strictly defined in `metric-analysis-engine.md`.
> For metrics with `status: reference`, open the Grafana link and include it in the report 
> only if a deviation is visible; skip the metric entirely if everything looks normal.

> SILENCE RULE (global — overrides everything else): **publish ONLY deviating
> metrics.** If a metric is within its normal range, emit nothing — no comment,
> no bullet, no "within parameters" note. This applies per metric, not per
> region. A region block with zero deviations contains only the Grafana
> dashboard link (one line); no "no anomalies" text is needed.

For each region R (scoped to `role="edgerouter", region="R"`):
1. For each metric M in `xcc-datasources.md` (in section order):
   - If `status: active`: run Phase 1 (`queryType: instant`) via `grafana-mcp-prd:query_prometheus`.
     If a threshold is breached, run Phase 2 (`queryType: range`, `step: 3600`).
   - If `status: reference`: link the Grafana panel; analyse visually if data
     collection is wired; otherwise include the link and skip automated check.
   - If M is within normal range → **emit nothing for M**.
2. Group the metrics that deviated under bold issue-group headings, e.g.:
   - **XCC <version> deploy on <date> causing spikes:**
   - **Different pattern/increase <date> (as previously seen every 2w)**
   - **No data until <date>**
   - **<Metric> spike (<value>) on <date>**
   - **CPU/Memory/Load pressure on <date>** (for resource metric deviations)
3. For each flagged metric, render (following the GENERIC DEVIATION →
   REFERENCE SCALAR + CHART rule below):
   a. the **reference scalar** as plain text (`Reference = N.NN {unit}`);
   b. a **chart** of that metric over the sprint (solid data lines, dotted
      reference line), and a zoom chart per spike event when applicable;
   c. the metric's Grafana link from the datasources file.
4. If ALL metrics for a region are within normal range: the region block
   contains only the Grafana dashboard link. **Do not add any text.**

### GENERIC DEVIATION & CHART GENERATION

> **IMPORTANT**: See `references/metric-analysis-engine.md` for the single source of truth on how to fetch data, compute deviations dynamically (RATE vs RESOURCE vs STATE), and the full Python script to generate charts in batch.

Do NOT use the legacy 'treat everything like Error Rates' rule. Follow the engine's classification.

When the engine script outputs a deviating metric chart, proceed to Step 3.

#### Step 3 — Save PNGs and upload via MCP attachment tool

Save each chart buffer to a temp file, then upload using the
`mcp__atlassian__confluence_upload_attachments` MCP tool (no token needed):

Save one PNG per chart to /tmp/ — the global plus one per zoom cluster, e.g.:
`xcc-{region}-overview.png`, `xcc-{region}-zoom-5xx.png`,
`xcc-{region}-zoom-4xx.png` (name zooms by the code/cluster they show).

Then call `mcp__atlassian__confluence_upload_attachments` with:
- `content_id`: the page ID (e.g. "6568476792")
- `file_paths`: comma-separated list of every chart path
- `comment`: `"XCC error rate charts — {region} sprint {sprint_start}–{sprint_end}"`
- `minor_edit`: true

> NOTE (Claude Desktop): Do NOT use requests/REST API for upload — it requires
> CONFLUENCE_TOKEN which is not available there. The MCP tool handles auth.
> NOTE (Claude Code fallback): if `mcp__atlassian__confluence_upload_attachments`
> is NOT present (it isn't in the Claude Code MCP set), upload via the REST
> attachment endpoint using `$ATLASSIAN_API_TOKEN` and embed each chart with a
> plain `<img src="https://<site>/wiki/download/attachments/{pageId}/{file}">`
> when publishing with `contentFormat: "html"`. This is an invocation-layer
> workaround only — the canonical spec stays MCP upload + `ac:image`.

#### Step 4 — Embed in the region's expand block (storage format)

Reference the uploaded files by filename using the Confluence storage format
`ac:image` + `ri:attachment` macro — no attachment ID needed, just the filename.
Embed charts **with no caption** (omit the surrounding `<p><em>…</em></p>` label):

```xml
<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="xcc-{region}-overview.png"/>
</ac:image>

<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="xcc-{region}-zoom-5xx.png"/>
</ac:image>

<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="xcc-{region}-zoom-4xx.png"/>
</ac:image>
```
(Emit one zoom block per spike code found — codes/counts are data-driven.)

> NOTE: The ADF `mediaSingle` / `data-id` format used in previous iterations
> is incompatible with storage format HTML. Always use `ac:image` + `ri:attachment`
> when the page uses `content_format: "storage"`.

---

## Rules
- Section scope is `role="edgerouter"` ONLY — never include other kamailio roles.
- Analyse ALL metrics in `references/xcc-datasources.md` (active + reference),
  in section order. Do not add metrics from other sources. EVERY metric is
  processed with the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule.
- **SILENCE RULE**: see `references/common-patterns.md`.
- **FINDING FORMAT**: see `references/common-patterns.md`.
  Each bullet = `<instance>: <metric/code> peak <value> <unit> at <timestamp>`.
- **GRAFANA LINKS**: see `references/common-patterns.md`.
- Host Details: build from PromQL result with REAL values; NEVER emit `[TODO]`/placeholder cells.
  Run sprint-start vs sprint-end delta check; emit one-line notes AFTER the table for changes.
- Do not invent versions, instance types, values, dates, or deviations.
- For each deviating metric: emit the reference scalar AND a chart (overview + zoom per event).
  Charts: matplotlib via bash_tool. All data lines solid (`linestyle="-"`). Reference line dotted
  (`linestyle=":", color="red"`). No caption on embedded images.
- Image alignment: see `references/common-patterns.md` — Image Alignment Rule.
- No-TODO / fallback: see `references/common-patterns.md` — No-TODO Rule.
- Publish: see `references/common-patterns.md` — Storage-Only Publish Rule.
