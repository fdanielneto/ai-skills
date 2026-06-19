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
> section order. For metrics with `status: active`, run the PromQL and apply
> the deviation rule automatically. For metrics with `status: reference`, open
> the Grafana link and include it in the report only if a deviation is visible;
> skip the metric entirely if everything looks normal.

> SILENCE RULE (global — overrides everything else): **publish ONLY deviating
> metrics.** If a metric is within its normal range, emit nothing — no comment,
> no bullet, no "within parameters" note. This applies per metric, not per
> region. A region block with zero deviations contains only the Grafana
> dashboard link (one line); no "no anomalies" text is needed.

For each region R (scoped to `role="edgerouter", region="R"`):
1. For each metric M in `xcc-datasources.md` (in section order):
   - If `status: active`: run M's PromQL over the SPRINT window via
     `grafana-mcp-prd:query_prometheus`, apply M's deviation rule.
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

### GENERIC DEVIATION → REFERENCE SCALAR + CHART rule (applies to EVERY metric)

This is the core requirement: **every metric in `xcc-datasources.md` is treated
the same way the "Error Rates (Spikes)" metric is** — fetch the data, run the
metric's deviation rule, and when it deviates present the result as a
**reference scalar + a CHART** that shows the deviation. The Error Rates
algorithm below is the fully worked example of this rule; apply the same shape
to all other metrics:

- **Fetch**: run the metric's PromQL over the sprint (range query, 3600s step
  for the 2-day window; finer step only for zoom). Save the raw Prometheus JSON
  to `/tmp/*.json` and `json.load` it — never retype numbers.
- **Detect**: apply the metric's `deviation:` rule from the datasources file
  (rate → mean±3σ; resource → median+2×IQR; alive → gap >5min; absolute →
  >25% over baseline median). Only deviating series proceed.
- **Reference scalar** (emit before the chart, as plain text — NO table):
  `Reference = N.NN {unit}`
  (rate metrics → mean across all instances and all sprint timepoints; resource
  metrics → sprint median). This is the single number drawn on the chart.
- **Chart**: plot the metric over the sprint (one **solid** line per
  instance/series) with one **dotted** reference line for that metric (see
  SINGLE REFERENCE LINE — generalised below), plus a zoom chart per spike event.
  Embed via `ac:image` + `ri:attachment`. Name files
  `xcc-{region}-{metric-slug}-overview.png` and
  `xcc-{region}-{metric-slug}-zoom-{event}.png`.
- **Reference line (generalised)**: one scalar drawn as a **dotted** horizontal
  line on every chart of that metric = the metric's baseline (rate metrics →
  mean across all instances over the sprint; resource metrics → sprint median).
  Label it `Reference = N.NN {unit}`.
- **Silence**: non-deviating metrics produce no reference scalar, no chart, no text.

### CHART GENERATION algorithm — worked example: Error Rates (inline, no external scripts)

> This is the canonical worked example of the GENERIC rule above, kept verbatim
> because Error Rates is the most complex case (per error-code breakdown). Reuse
> its structure (fetch → detect → reference scalar → overview + zoom bar chart)
> for every other metric, adapting the breakdown dimension (instance, xheader,
> code, method, mount, process, …) to the metric.

> BREAK DOWN BY ERROR CODE — do NOT chart the accumulated total.
> The charts must show one line per (instance, error code). Use the per-code
> series B (4xx), C (5xx), D (6xx) from `xcc-datasources.md`, NOT the summed
> series A. Series A is used ONLY for the spike-detection scan; the charts and
> the spike attribution are per (instance, code).

Spike detection is done PER (instance, code): for each of the 9 series
(3 instances × {4xx,5xx,6xx}) compute mean, std, max, threshold = mean + 3σ,
and flag SPIKE when `max > threshold AND max >= 0.05`. This is used only to
decide WHICH series spiked and WHEN; it is NOT what the charts draw as the
reference line (see below).

> SINGLE REFERENCE LINE — there is exactly ONE reference value, drawn on EVERY
> chart (global and every zoom). It is the MEAN of the error rate across ALL
> instances over the sprint (mean of the total/series-A across all instances and
> all sprint timepoints — one scalar, e.g. ~0.32 err/s). Draw it as one **dotted**
> red horizontal line labelled "Reference = N.NN". Do NOT draw per-series
> mean+3σ lines on the charts.

> REPORT ONLY DEVIATIONS — in the page TEXT, list only (instance, code) series
> that actually spiked. Do NOT write bullets for codes/series within parameters
> (e.g. never "6xx: negligible, no spike"). The GLOBAL chart still draws ALL
> codes and instances (completeness); the omission is in the prose only.

Produce these charts:

  CHART 1 — GLOBAL overview. ALWAYS the full sprint window, ALL instances, ALL
            error codes, 1h step. ONE figure, single axis, one **solid** line per
            (instance, code) — colour = instance, all lines solid regardless of
            code. Plus one **dotted** red reference line. (6xx lines hugging
            zero is expected and fine.)

  CHART(S) 2…N — ZOOM, one per spike EVENT (a code's spike, or a cluster of
            simultaneous spikes). When the spike is a 4xx, 5xx, or 6xx error
            rate event, the zoom chart is a **bar chart** showing customer
            attribution:
            - **X axis**: account / xheader (one bar per customer)
            - **Y axis**: Error codes count (total count of the spiked code
              during the spike window, aggregated per xheader)
            Fetch the attribution data using the per-xheader PromQL for that
            code over the spike window, e.g.:
            `sum by (xheader) (increase(kamailio_core_rcv_replies_{Nxx}{region="$region",role="edgerouter",service=~".*"}[<spike_window_seconds>s]))`
            Sort bars descending by count. Add a title: "{code} spike attribution
            — {region} · {spike_window_start}–{spike_window_end} UTC".
            One zoom bar chart per spiked code (4xx, 5xx, 6xx).

  ZOOM WINDOW (for attribution query): window = [peak_START − 30 min, peak_END + 30 min].
  The 30-min trailing margin is measured from when the peak ENDS (returns toward
  baseline), NOT from the peak moment — otherwise the elevated tail gets cut.
  Compute the elevated span from the fine data:
   - Single sustained spike (e.g. the 5xx event): expand left/right from the
     global peak while max-across-instances stays above an elevated level
     (~the spike threshold), giving [start, end]; window = [start−30m, end+30m].
   - Several spread sub-peaks of one code (e.g. 4xx peaking at different times
     per instance): take the FIRST and LAST crossing of the elevated level
     across the event; window = [first−30m, last+30m]. One zoom covers all the
     spread peaks of that code.
  Typical eu-south-1 result: 5xx event ~08:54–10:03 → window ~08:24–10:33;
  4xx spread event ~10:10–14:44 → window ~09:40–15:14.

#### Step 1 — Fetch data

For the GLOBAL chart, run the per-code series (B=4xx, C=5xx, D=6xx) as RANGE
queries over the full sprint at 3600s step (the confirmed-working step for the
2-day window — see PERFORMANCE CONSTRAINT in `xcc-datasources.md`). One query
per code; each returns one value-series per instance.

For each ZOOM bar chart, run the per-xheader attribution query for the spiked
code over the spike window (computed above):
```
sum by (xheader) (increase(kamailio_core_rcv_replies_{Nxx}{region="$region",role="edgerouter",service=~".*"}[<spike_window_s>s]))
```
This returns one scalar per xheader — the total count of that error code
attributed to each customer during the spike. Note that 1h sampling aliases
sub-hour peaks — the fine attribution query will show higher counts than the 1h
global; report both (e.g. "1h peak 1.16 @ 09:00, attribution window total: 1234 errors").

#### Step 2 — Generate PNGs inline via bash_tool

Ensure matplotlib is available: `pip install matplotlib --break-system-packages -q`

Write the Python to /tmp and run it. To avoid transcription errors on the large
arrays, SAVE each Prometheus JSON result verbatim to a /tmp/*.json file and have
the script `json.load` them (do not retype numbers into the script).
Structure:
- Compute the single reference: mean of (4xx+5xx+6xx) across all instances and
  all sprint timepoints → one scalar.
- GLOBAL chart: single axis, one **solid** line per (instance, code) over the
  full sprint (colour = instance, `linestyle="-"` for all lines), plus one
  **dotted** red reference line (`ax.axhline(REF, color="red", linestyle=":",
  linewidth=1.2, label=f"Reference = {REF:.3f} err/s")`).
- ZOOM chart(s): one **bar chart** per spiked code, showing customer attribution.
  X axis = xheader (sorted descending by count), Y axis = error code count
  (total during the spike window). No reference line on bar charts.
Always VERIFY each PNG by reading it back before uploading.

Illustrative skeleton (the real version carries the fetched per-code dicts):

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime, io

# --- Chart 1: sprint overview, all instances, all codes (solid lines) ---
fig, ax = plt.subplots(figsize=(11, 4))
for (inst, code), vals in series_by_inst_code.items():
    xs = [datetime.datetime.utcfromtimestamp(t) for t in timestamps_3600s]
    ax.plot(xs, vals, linestyle="-", linewidth=1.2,
            label=f"{inst.replace('kamailio-edgerouter-', '')} {code}")
ax.axhline(REF, color="red", linestyle=":", linewidth=1.2,
           label=f"Reference = {REF:.3f} err/s")
ax.set_title(
    f"Error Rates (4xx+5xx+6xx) — {region}  ·  sprint {sprint_start}–{sprint_end}\n"
    f"source: Prometheus  kamailio_core_rcv_replies_{{4xx|5xx|6xx}}"
    f"{{role=edgerouter}}  (xconnect_dashboard panel-800)",
    fontsize=9)
ax.set_ylabel("err/s"); ax.set_xlabel("UTC time")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H"))
ax.xaxis.set_major_locator(mdates.HourLocator(interval=4))
plt.xticks(rotation=30, ha="right")
ax.legend(fontsize=7, ncol=4); ax.grid(alpha=0.3)
fig.tight_layout()
buf1 = io.BytesIO()
fig.savefig(buf1, format="png", dpi=150)
buf1.seek(0)
plt.close(fig)

# --- Chart 2: zoom bar chart — attribution by xheader (one per spiked code) ---
# xheader_counts: dict {xheader: count} from the per-xheader attribution query
xheaders_sorted = sorted(xheader_counts, key=lambda x: xheader_counts[x], reverse=True)
counts_sorted = [xheader_counts[h] for h in xheaders_sorted]
fig, ax = plt.subplots(figsize=(11, 4))
ax.bar(range(len(xheaders_sorted)), counts_sorted, color="steelblue")
ax.set_xticks(range(len(xheaders_sorted)))
ax.set_xticklabels(xheaders_sorted, rotation=45, ha="right", fontsize=8)
ax.set_xlabel("Account / X-Header")
ax.set_ylabel("Error codes (count)")
ax.set_title(
    f"{spike_code} spike attribution — {region}\n"
    f"{spike_window_start} – {spike_window_end} UTC",
    fontsize=9)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
buf2 = io.BytesIO()
fig.savefig(buf2, format="png", dpi=150)
buf2.seek(0)
plt.close(fig)
```

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
  processed with the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule (fetch →
  detect → reference scalar + chart for deviating series) — not only the Error
  Rates metric.
- **SILENCE RULE**: publish ONLY deviating metrics AND deviating instances.
  Metrics within normal range are completely omitted — no bullet, no "within
  parameters" comment, no mention. Instances within normal range are completely
  omitted — no bullet, not even a "no issue" note. A region with zero deviations
  shows only its Grafana link.
- **FINDING FORMAT**: follow the FINDING FORMAT rule above for every bullet.
  Each bullet = `<instance>: <metric/code> peak <value> <unit> at <timestamp>`.
  No AZ/type tags. No threshold values. No editorial commentary.
- **GRAFANA LINKS**: use the GRAFANA LINK FORMAT rule for every per-region
  Grafana link — append `&var-region=<region>&from=<ms>&to=<ms>`.
- Host Details: build the table from the PromQL result with the REAL returned
  values; never screenshot it and NEVER emit `[TODO]`/placeholder cells. If the
  Grafana MCP is unavailable, emit a warning panel instead of an empty table.
  After building the table, run the sprint-start vs sprint-end delta check and
  emit brief one-line notes as paragraphs AFTER the table for any detected
  version/instance_type change; if no change detected, emit nothing. Never put
  notes inside table rows.
- Do not invent versions, instance types, values, dates, or deviations.
- For each deviating metric, emit the reference scalar (`Reference = N.NN unit`)
  AND a chart that shows the deviation (overview + zoom per event). No deviation
  tables. This applies to all metrics, generalising the Error Rates example.
- Chart generation: matplotlib via bash_tool (no get_panel_image).
  - All data lines (instances, error codes, series): **solid** (`linestyle="-"`).
  - Reference line: always **dotted** (`linestyle=":", color="red"`), labelled
    `Reference = N.NN {unit}`.
  - For Error Rates: global chart shows one solid line per (instance, code);
    zoom charts are **bar charts** (X = account/xheader, Y = error codes count).
  - For other metrics: global chart = full sprint + all series (solid lines,
    single axis). Zoom window = [peak_start−30m, peak_END+30m].
  - Spike detection picks which series deviated. Report only deviating series in
    the prose. Verify each PNG before upload. Save raw JSON to /tmp and
    json.load it (no retyping). Upload via
    `mcp__atlassian__confluence_upload_attachments` (Desktop) or REST +
    `$ATLASSIAN_API_TOKEN` (POST .../child/attachment) and embed via
    `ac:image`+`ri:attachment` (storage) — NOT ADF mediaSingle/data-id.
  - Embed charts with **no caption** — no surrounding `<p><em>…</em></p>` label.
  - **All embedded images MUST use `ac:align="center" ac:width="950"` — never
    omit `ac:align="center"` or the image will be left-aligned in Confluence.**
