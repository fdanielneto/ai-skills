# RTPEngine_Metrics — "RTP Engine Metrics" section (its own section)

Per the requester's decision, RTP Engine is a **standalone section**, separate
from XCC/Kamailio. This reference owns its own heading and its own per-region
dropdowns, rendered immediately AFTER the "XCC Metrics" section.

> DATA SOURCES: analyse ONLY the Grafana panels and metrics listed in
> `references/rtpengine-datasources.md`. Do not browse other dashboards or
> invent metrics. That file is the single source of truth.

> SILENCE RULE (global): **publish ONLY deviating metrics.** If a metric is
> within its normal range, emit nothing — no comment, no bullet, no "within
> parameters" note. This applies per metric. A region block with zero
> deviations contains only the Grafana dashboard link (one line).

## Structure (in order)

1. Heading (H1): **RTP Engine Metrics**

2. **Per-region blocks**, one per region, same order as the XCC section:
   EU-South-1, EU-West-3, US-East-1, US-West-2, AP1 - Singapore, AP2 - Sydney,
   SA-East-1, CA-Central-1. Use an expandable dropdown (Confluence expand macro)
   per region, collapsed by default.

   > REGION FILTER: if the invocation included one or more region tokens, only
   > the filtered region(s) are analysed. Other regions render as a minimal
   > collapsed block: `<em>Not analysed in this run (region filter active).</em>`

   Each block skeleton:
   ```
   [Grafana — RTPEngine <Region>](<parameterized Grafana URL — see GRAFANA LINK FORMAT>)

   <bold issue-group heading for each deviating metric group>
     * <minimal finding bullet — see FINDING FORMAT>
      [chart image embedded via ac:image ac:align="center" + ri:attachment — no caption]
   ```
   If NO metrics deviated: the block contains only the Grafana dashboard link.

### GRAFANA LINK FORMAT (mandatory for every per-region Grafana link)

When emitting a Grafana link for a per-region block, build a **parameterized
URL** by appending the region variable and sprint timestamps to the `goto` base
URL from the datasources file:

```
<base_goto_url>&var-region=<region>&from=<sprint_start_epoch_ms>&to=<sprint_end_epoch_ms>
```

Example — eu-south-1, sprint 2026-06-16 to 2026-06-17:
```
https://grafana-general.svc.talkdeskapp.com/goto/dfolpmd59gp34d?orgId=1&var-region=eu-south-1&from=1750032000000&to=1750118400000
```

Convert sprint dates to Unix epoch milliseconds (YYYY-MM-DDT00:00:00Z).

The link text must identify both the metric and the region, e.g.:
`[Grafana — RTPEngine EU-South-1 Alive](<parameterized URL>)`

### FINDING FORMAT (mandatory for every per-region deviation bullet)

When a metric deviates:
1. Emit `Reference = N.NN <unit>` as plain text above the bullets (one line).
2. For each deviating **instance** (omit instances within normal range —
   no mention, no bullet, not even a "no issue" note):
   ```
   * <instance>: <metric> peak <value> <unit> at <YYYY-MM-DDTHH:MMZ>
   ```
3. **Strip** from bullets:
   - AZ / instance-type annotations (no `(AZ-c)`, `(c5.large)`, etc.)
   - Threshold values (no `median+2×IQR`, no `mean+3σ threshold`, no percentages)
   - Non-deviating instance summaries (no "zero throughout sprint",
     "unaffected", "within normal range" per-instance notes)
   - Trailing `OK — … within normal range` lines when the block has deviations
   - Editorial commentary: no "likely cause", no "consistent with", no
     correlation sentences
4. Metric group heading must be short and factual — metric + date only.

## Per-region analysis algorithm (consumes rtpengine-datasources.md)

> SILENCE RULE: publish ONLY deviating metrics. If a metric is within normal
> range, emit nothing for that metric. If ALL metrics are within range for a
> region, the block contains only the Grafana link.

For each region R:
1. For each metric M in `references/rtpengine-datasources.md` (in section order):
   - If `status: active`: run M's PromQL, apply M's deviation rule.
   - If `status: reference`: include the Grafana link; analyse visually if data
     is available; otherwise skip automated check.
   - If M is within normal range → **emit nothing for M**.
2. Group deviating metrics under bold issue-group headings, e.g.:
   - **RTPEngine alive gap on <date>** (instance went down)
   - **CPU / Load pressure on <date>** (resource deviation)
   - **Media sessions spike on <date>** (abnormal session count)
   - **Transcoding sessions increase on <date>**
   - **No data until <date>** (series missing)
3. For each flagged metric, emit `Reference = N.NN {unit}` (plain text, NO
   table) and a **chart** that shows the deviation, plus the Grafana link —
   following the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule below.
4. If ALL metrics for a region are within normal range: emit only the Grafana
   dashboard link. **Do not add any text.**

### GENERIC DEVIATION → REFERENCE SCALAR + CHART rule (applies to EVERY metric)

Every metric in `rtpengine-datasources.md` is processed exactly like the worked
"Error Rates (Spikes)" example in `xcc-metrics.md` — fetch the data, run the
metric's deviation rule, and when it deviates present a **reference scalar +
a CHART**:

- **Fetch**: run the metric's PromQL over the sprint (range query, 3600s step;
  finer step only for zoom). Save the raw Prometheus JSON to `/tmp/*.json` and
  `json.load` it — never retype numbers.
- **Detect**: apply the metric's `deviation:` rule from the datasources file
  (rate/count → mean±3σ; resource → median+2×IQR; alive → gap >5min; session
  counts → median+2×IQR or stepwise change). Only deviating series proceed.
- **Reference scalar** (emit before the chart, as plain text — NO table):
  `Reference = N.NN {unit}`
  (rate/count metrics → sprint mean; resource/session metrics → sprint median).
- **Chart**: plot the metric over the sprint with one **solid** line per
  instance/series, plus one **dotted** reference line = the metric's sprint
  baseline (rate → mean; resource/session → median). Embed via `ac:image ac:align="center"` +
  `ri:attachment`. Name files `rtpengine-{region}-{metric-slug}-overview.png`
  and `rtpengine-{region}-{metric-slug}-zoom-{event}.png`. Generate PNGs with
  matplotlib via bash_tool; verify each PNG before upload.
  - All data lines: **solid** (`linestyle="-"`).
  - Reference line: **dotted** (`linestyle=":", color="red"`,
    `label=f"Reference = {REF:.3f} {unit}"`).
- **Silence**: non-deviating metrics produce no reference scalar, no chart, no text.

## Issue-group headings (bold) — RTP-Engine-driven shapes
(Emit ONLY when the deviation exists; never invent or pre-fill these.)
- **RTPEngine alive gap on <date>** — instance was unreachable
- **CPU Stats RTP Engine spikes on <date>**
- **Load pressure on <date>** (load average exceeded threshold)
- **Memory pressure on <date>**
- **Media sessions spikes on <date>**
  - sub-bullet: describe the call behaviour (e.g. long-duration / stuck calls)
    when visible — keep as a placeholder; do NOT invent account names, CALL_IDs
    or numbers.
- **Transcoding sessions increase on <date>**
- **RTPEngine connection failures on <date>** (from Kamailio's perspective)
- **No data until <date>** (when the RTPEngine series is missing)

## RTP Engine metric groups owned by THIS section
(Full details — Grafana links, PromQL, deviation rules — in `rtpengine-datasources.md`)

- **Alive Stats**: RTPEngine Alive
- **Infra Details**: CPU Stats, System Load, Memory Usage, Network I/O
- **Media Details**: Media Ports, Media Sessions (by region), Media Sessions by
  Instance, Transcoding Media Sessions

## Rules
- This section is RTP Engine ONLY; Kamailio/XCC content stays in the XCC section.
- Analyse ALL metrics in `references/rtpengine-datasources.md` (active +
  reference). EVERY metric is processed with the GENERIC DEVIATION → REFERENCE
  SCALAR + CHART rule (fetch → detect → reference scalar + chart for deviating
  series), exactly like the Error Rates worked example in `xcc-metrics.md`.
- **SILENCE RULE**: publish ONLY deviating metrics AND deviating instances.
  Metrics within normal range are completely omitted — no bullet, no comment,
  no mention. Instances within normal range are completely omitted — no bullet,
  not even a "no issue" note.
- **FINDING FORMAT**: follow the FINDING FORMAT rule above for every bullet.
  Each bullet = `<instance>: <metric> peak <value> <unit> at <timestamp>`.
  No AZ/type tags. No threshold values. No editorial commentary.
- **GRAFANA LINKS**: use the GRAFANA LINK FORMAT rule for every per-region
  Grafana link — append `&var-region=<region>&from=<ms>&to=<ms>`.
- Do not invent values, goto URLs, instance names, or session counts.
- For each deviating metric, emit `Reference = N.NN {unit}` (as plain text,
  NO table) AND a chart that shows the deviation (overview + zoom per event).
  - All data lines: **solid** (`linestyle="-"`).
  - Reference line: **dotted** (`linestyle=":", color="red"`), labelled
    `Reference = N.NN {unit}`.
  Generate charts via matplotlib (bash_tool), save raw JSON to /tmp and
  json.load it, and embed via `ac:image ac:align="center"`+`ri:attachment` (storage format) —
  **with no caption** (no surrounding `<p><em>…</em></p>` label).
  **Always set `ac:align="center" ac:width="950"` on every `<ac:image>` tag — omitting
  `ac:align="center"` causes left-alignment in Confluence.**
  Upload attachments via the Atlassian MCP upload tool or REST
  `.../child/attachment` with `$ATLASSIAN_API_TOKEN`.
- If the Grafana MCP is unavailable, emit a warning panel for the section rather
  than `[TODO]` placeholders.
