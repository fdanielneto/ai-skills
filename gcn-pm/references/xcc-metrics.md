# XCC_Metrics — "XCC Metrics" section (its own section)

XCC == kamailio-sip-router (Kamailio). Standalone section (separate from RTP
Engine, per the requester's decision).

> SCOPE RULE (applies to the WHOLE section): only the role
> **`kamailio-edgerouter`** matters. In PromQL this is `role="edgerouter"`
> (the instances are named `kamailio-edgerouter-*`). IGNORE every other kamailio
> role (proxy, registrar, etc.) in all queries and analysis.

> DATA SOURCES: analyse ONLY the Grafana dashboards / panels and PromQL filters
> listed in the **Appendix: XCC Data Sources** below. Do not browse other dashboards or
> invent metrics. That section is the single source of truth for what to analyse.

---

> **TOKEN REDUCTION PIPELINE**: Do NOT process the metrics math here manually. The configuration is stored in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`. Use `scripts/grafana_analyzer.py` to evaluate the deviations. Only write about the metrics that `grafana_analyzer.py` flags as deviated.

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
>   ```xml
>   <ac:structured-macro ac:name="expand">
>     <ac:parameter ac:name="title">{region}</ac:parameter>
>     <ac:rich-text-body>
>       <p><em>Not analysed in this run (region filter active).</em></p>
>     </ac:rich-text-body>
>   </ac:structured-macro>
>   ```
>   NEVER use HTML `<details>` or `<summary>`. You MUST use `<ac:structured-macro ac:name="expand">` for all dropdowns.
>   No Prometheus queries are made for skipped regions.
> - The Host Details table is always built in full (single instant query — cheap).
>
> If NO region filter is given, all regions are analysed as normal.

Emit one expandable block per region (using `<ac:structured-macro ac:name="expand">`, NEVER `<details>`), iterating over the SAME region
set discovered for the Host Details table (every region with
`kamailio-edgerouter` instances — never a hardcoded list). Sort regions
consistently (e.g. by Ribbon grouping, then alphabetically); if a new region
shows up in the query, it automatically gets its own block.

For each region, the content is driven by the **Appendix: XCC Data Sources**
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

### Per-region analysis algorithm (consumes Appendix: XCC Data Sources)

> DATA SOURCE RULE: analyse ALL metrics listed in the **Appendix: XCC Data Sources**, in
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
1. For each metric M in the **Appendix: XCC Data Sources** (in section order):
   - If `status: active`: run Phase 1 (`queryType: instant`) via `grafana-mcp-prd:query_prometheus`.
     - **Floor bypass**: if `peak >= M.floor` (RATE), `P95 >= M.floor` (RESOURCE), or `value == 0` (STATE) → flag immediately, skip statistical check.
     - **Fallback**: if floor not breached, apply M's statistical rule (Median+3×MAD, P95 > threshold, IQR, etc.).
     - If either check passes, run Phase 2 (`queryType: range`, `step: 14400`) — EXCEPT for STATE metrics, which skip Phase 2.
   - If `status: reference`: link the Grafana panel; analyse visually if data
     collection is wired; otherwise include the link and skip automated check.
   - If M is within normal range (floor not breached AND statistical check passed) → **emit nothing for M**.
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
      reference line), and a zoom chart per spike event when applicable. Do NOT omit charts for failover/events counters even if classified as STATE; generate charts for them using `scripts/plot_helper.py` and upload as PNG;
   c. the metric's Grafana link from the datasources file.
4. If ALL metrics for a region are within normal range: the region block
   contains only the Grafana dashboard link. **Do not add any text.**

### GENERIC DEVIATION & CHART GENERATION

> **IMPORTANT**: See `references/metric-analysis-engine.md` for the single source of truth on how to fetch data, compute deviations dynamically (RATE vs RESOURCE vs STATE), and the full Python script to generate charts in batch.

Do NOT use the legacy 'treat everything like Error Rates' rule. Follow the engine's classification.

When the engine script outputs a deviating metric chart, proceed to Step 3.

#### Step 3 — Generate PNG Charts

You MUST use `scripts/plot_helper.py` to generate chart PNGs from the Phase 2 JSON.
Do NOT use Native Confluence Chart Macros.
1. Format the data into the JSON structure expected by `plot_helper.py`.
2. Generate the PNG.
3. Upload it as an attachment to the page.
4. Embed it using `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`.

---

## Rules
- Section scope is `role="edgerouter"` ONLY — never include other kamailio roles.
- Analyse ALL metrics in the **Appendix: XCC Data Sources** (active + reference),
  in section order. Do not add metrics from other sources. EVERY metric is
  processed with the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule.
- **FLOOR BYPASS**: Every metric defines a `floor` (hard trigger). If the Phase 1 value meets or exceeds the floor, the metric is flagged as deviating immediately without running the statistical rule (MAD/P95/IQR). Below the floor, the statistical rule still applies as fallback.
- **SILENCE RULE**: Publish only deviating metrics. Within deviating metrics, publish only deviating instances. If a region has zero deviations, emit only the region dashboard link.
- **FINDING FORMAT**: Each bullet = `<instance>: <metric/code> peak <value> <unit> at <timestamp>`. Never include AZ/instance-type annotations, threshold internals, or summaries for non-deviating instances.
- **GRAFANA LINKS**: Must be parameterized from the datasource `goto` URL.
- **FAIL-FAST RULE**: If any required data source returns an authentication error or is unreachable, return `[FATAL_AUTH_ERROR]` and a brief description. Do not generate warning panels.
- **IMAGE ALIGNMENT**: All `<ac:image>` tags MUST carry `ac:align="center" ac:width="950"`.
- **NO-TODO RULE**: Never emit fabricated values or TODO placeholders.
- **OUTPUT SCHEMA**: Emit only final section body content. Do not emit orchestration, publishing, rationale, or repeated rule text.
- Host Details: build from PromQL result with REAL values; NEVER emit `[TODO]`/placeholder cells.
  Run sprint-start vs sprint-end delta check; emit one-line notes AFTER the table for changes.
- Do not invent versions, instance types, values, dates, or deviations.
- For each deviating metric: emit the reference scalar AND a chart (overview + zoom per event).
  Charts: static PNG charts generated via `plot_helper.py` (see `references/metric-analysis-engine.md` §2). Do NOT use native Confluence Chart macros.

  STATE metrics: skip chart, text bullet only.
- Publish: Must use Confluence REST API with `representation: "storage"`. Never use Atlassian MCP tools for publishing.


---

# Appendix: XCC Data Sources — single source of truth for the XCC per-region analysis

This file lists EVERY metric the XCC section may analyse, and nothing else.
The section builder (`xcc-metrics.md`) must analyse ONLY what is registered here
— do not browse other dashboards or invent metrics.

## Global scope (applies to every entry)
- Role is always `role="edgerouter"` (kamailio-edgerouter).
- Region is injected as `region="$region"`.
- Default datasource is `prometheus`.
- Shared conventions (Grafana Link Format, Silence Rule, Deviation Policy,
  Datasource Conventions — including `$region` and `$__range` substitution):
  see the rules above.

## Status convention

- `status: active` — PromQL confirmed from Grafana source. Fully automated.
- `status: reference` — Grafana link available; PromQL TBD. Link included in
  report as a panel shortcut; automated analysis not yet wired.

## Per-metric entry schema

```
### <Metric display name>
- grafana: <Grafana panel/dashboard link>
- description: <what the panel shows>
- status: active | reference
- datasource: prometheus | mimir | mimir-ap
- promql: <PromQL expression using $region and role="edgerouter">
- deviation: <rule>
- unit: <e.g. %, Mb/s, count, err/s>
```

---

## Metrics to analyse

### Error Rates (Spikes) — by instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolortpdd2psd?orgId=1
- description: 4xx, 5xx, 6xx error rate — by XCC instance
- status: active
- datasource: prometheus
- promql (4 series; use `region="$region"` and `role="edgerouter"`):
  - A — TOTAL per instance:
      `sum by (instance) (rate(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[5m]))
     + sum by (instance) (rate(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[5m]))
     + sum by (instance) (rate(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - B — 4xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - C — 5xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - D — 6xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
- unit: SIP error replies / second
- deviation: type: RATE — Median + 3*MAD
- floor: 0.1 err/s

> PERFORMANCE CONSTRAINT: on `prometheus` via Grafana MCP, use 3600 s step for
> the global chart; finer step only for zoom windows (60 s step times out).

> Fleet aggregate variant: same queries without `by (instance)` — use `sum(...)`.
> Grafana link: https://grafana-general.svc.talkdeskapp.com/goto/dfolt1g447fuoe?orgId=1

### Custom Metrics Rates (Spikes) — by instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffoloqq16x1j4f?orgId=1
- description: Inbound/Outbound Invite rate, RTP Engine failure rate, SIP Rec call rate — by XCC instance
- status: active
- datasource: prometheus
- promql (6 series — all use `region="$region"`, `role="edgerouter"`, `service=~".*"`):
  - B — Emergency invites: `sum by (instance) (rate(kamailio_kamailio_emergency_invites_total{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - D — Inbound invites: `sum by (instance) (rate(kamailio_kamailio_inbound_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - M — Outbound off-net: `sum by (instance) (rate(kamailio_kamailio_outbound_offnet_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - N — Outbound on-net: `sum by (instance) (rate(kamailio_kamailio_outbound_onnet_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - O — RTPEngine failures: `sum by (instance) (rate(kamailio_rtpengine_connection_failure{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - P — SIP Rec calls: `sum by (instance) (rate(kamailio_siprec_calls{region="$region",role="edgerouter",service=~".*"}[5m]))`
- deviation: type: RATE — Median + 3*MAD
- floor:
  * B — Emergency invites: 1 event/s
  * D — Inbound invites: 30 events/s
  * M — Outbound off-net: 30 events/s
  * N — Outbound on-net: 30 events/s
  * O — RTPEngine failures: 0.1 events/s
  * P — SIP Rec calls: 10 events/s
- unit: events / second per instance

> Fleet aggregate variant: same metrics without `by (instance)` — use `sum(...)`.
> Grafana link: https://grafana-general.svc.talkdeskapp.com/goto/cfolpibqv60owf?orgId=1

### Infra Details — version and instance type
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpkul5sx6of?orgId=1
- description: XCC version and instance type — by XCC instance
- status: active
- datasource: prometheus
- promql: `count by (region, version, instance_type) (custom_metrics{role="edgerouter"})`
  (scoped: `count by (region, version, instance_type) (custom_metrics{region="$region",role=~"edgerouter"})`)
- deviation: N/A — used for Host Details table only.

### Kamailio Alive
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolplog4lu68a?orgId=1
- description: XCC alive stats — by XCC instance (up/down status)
- status: active
- datasource: prometheus
- promql: `up{region="$region",role="edgerouter",service="kamailio",stack="cpaas"}`
  (returns 1 = up, 0 = down, missing series = unreachable)
- deviation: flag any gap (value = 0 or series absent) lasting > 5 min.
- floor: 0
- unit: binary 0/1

### CPU Stats — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolpn2o21khsa?orgId=1
- description: XCC CPU stats — by XCC instance (user, system, iowait, guest)
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `service=~"edgerouter"`, `cpu="cpu-total"`):
  - A — User: `cpu_usage_user{region="$region",service=~"edgerouter",cpu="cpu-total"}`
  - B — System: `cpu_usage_system{region="$region",role=~"edgerouter",cpu="cpu-total"}`
  - C — IOWait: `cpu_usage_iowait{region="$region",role=~"edgerouter",cpu="cpu-total"}`
  - D — Guest: `cpu_usage_guest{region="$region",role=~"edgerouter",cpu="cpu-total"}`
- deviation: type: RESOURCE — P95 > 80%.
- floor:
  * A — User: 70%
  * B — System: 50%
  * C — IOWait: 25%
  * D — Guest: 50%
- unit: % CPU

### System Load — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolpnqqut43kf?orgId=1
- description: XCC system load (1 m, 5 m, 15 m) and CPU count — by XCC instance
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — 1-min load: `system_load1{region="$region",role=~"edgerouter"}`
  - B — 5-min load: `system_load5{region="$region",role=~"edgerouter"}`
  - C — 15-min load: `system_load15{region="$region",role=~"edgerouter"}`
  - D — CPU count: `system_n_cpus{region="$region",role=~"edgerouter"}`
- deviation: type: RESOURCE — P95 > (CPU count * 0.8)
- floor: CPU count × 1.2
- unit: load average (dimensionless)

### CPU Usage per Process — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolpogr88uf4a?orgId=1
- description: CPU usage per process (top-18) — by XCC instance
- status: active
- datasource: prometheus
- promql: `topk(18, sum(procstat_cpu_usage{region="$region",role=~"edgerouter"}) by (process_name,instance))`
- deviation: no alerting defined; flag top consumers when CPU is elevated.
- floor: 50% (any single process)
- unit: % CPU per process

### Memory Usage per Process — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolppd52cs8we?orgId=1
- description: Memory usage per process (top-18, RSS) — by XCC instance
- status: active
- datasource: prometheus
- promql: `topk(18, sum(procstat_memory_rss{region="$region",role=~"edgerouter"}) by (process_name,instance))`
- deviation: no alerting defined; flag clear stepwise increases.
- floor: 80% of system memory (RSS per process)
- unit: bytes (RSS)

### Memory Usage — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolpq2u5tlogc?orgId=1
- description: Memory breakdown (total, used, cached+buffered, free, swap used) — by XCC instance
- status: active
- datasource: prometheus
- promql (5 series; all scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — Total: `mem_total{region="$region",role=~"edgerouter"}`
  - B — Used: `mem_used{region="$region",role=~"edgerouter"}`
  - C — Cached+Buffered: `mem_cached{region="$region",role=~"edgerouter"} + mem_buffered{region="$region",role=~"edgerouter"}`
  - D — Free: `mem_free{region="$region",role=~"edgerouter"}`
  - E — Swap used: `mem_swap_total{region="$region",role=~"edgerouter"} - mem_swap_free{region="$region",role=~"edgerouter"}`
- deviation: type: RESOURCE — P95 > 80%
- floor: 60%
- unit: bytes

### Network I/O — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpqob1el8gb?orgId=1
- description: Network I/O in bits/s (receive and transmit) — by XCC instance
- status: active
- datasource: prometheus
- promql (2 series; both scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — RX: `irate(net_bytes_recv{region="$region",role=~"edgerouter"}[5m]) * 8`
  - B — TX: `irate(net_bytes_sent{region="$region",role=~"edgerouter"}[5m]) * 8`
- deviation: type: RESOURCE — P95
- floor: 1 Gb/s
- unit: bits/s

### Number of File Handles — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolprd4tknb4f?orgId=1
- description: Number of open file handles (system-wide) — by XCC instance
- status: active
- datasource: prometheus
- promql: `linux_sysctl_fs_file_nr{region="$region",role=~"edgerouter"}`
  (use the allocated series for deviation)
- deviation: sprint median + 2×IQR; alert if approaching system max
- floor: 75% of system max
- unit: count

### Disk Usage — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpryt5s4qod?orgId=1
- description: Disk usage percentage — by XCC instance
- status: active
- datasource: prometheus
- promql: `disk_used_percent{region="$region",role=~"edgerouter"}`
- deviation: flag when any mount exceeds 80 % used
- floor: 60%
- unit: %

### TCP Connection Counters
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolpwcjkj1tse?orgId=1
- description: TCP connection counters by type — by XCC instance
- status: active
- datasource: prometheus
- promql: `rate(kamailio_tcp_total{region="$region",role=~"edgerouter",type=~"(con_reset|con_timeout|connect_failed|connect_success|established|local_reject|passive_open|send_timeout|sendq_full)"}[5m]) * 1000`
- deviation: sprint median + 2×IQR per type; flag `connect_failed`, `con_reset`, `con_timeout` especially
- floor:
  * connect_failed: 100
  * con_timeout: 20
  * con_reset: 100
- unit: connections / s × 1000

### Core SHMem Max Used
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpwymc5f5se?orgId=1
- description: Kamailio core shared memory (max_used and total) — by XCC instance
- status: active
- datasource: prometheus
- promql: `kamailio_shm_bytes{region="$region",role=~"edgerouter",type=~"(max_used|total)"}`
- deviation: flag when max_used / total > 80 % or sustained increase trend
- floor: 80%
- unit: bytes

### RTPEngine Connection Failures
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpxknkh7gge?orgId=1
- description: RTPEngine connection failures (from Kamailio's perspective) — by XCC instance
- status: active
- datasource: prometheus
- promql: `rate(kamailio_rtpengine_connection_failure{region="$region",role=~"edgerouter"}[5m]) * 1000`
- deviation: type: RATE — Median + 3*MAD
- floor: 1 (failures/s × 1000)
- unit: failures/s × 1000

> NOTE: `$__range` in the following SIP Codes and Requests sections is a Grafana
> range variable. When executing via MCP, replace with `[N]s` (sprint duration in
> seconds). The result is the total count over the sprint, not a rate.

### Total 4xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq167odukgf?orgId=1
- description: Total 4xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: compare sprint total vs. baseline mean ± 2σ (baseline = 5 prior sprints)
- floor: 50000 (total over sprint)
- unit: count (total over sprint)

### 4xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolq22e3aneob?orgId=1
- description: 4xx breakdown by specific code (400–493) and SIP method
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_4xx_{method}` for by-method, `kamailio_core_rcv_replies_{NNN}` for by-code):
  - `sum(increase(kamailio_core_rcv_replies_4xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_4xx_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_400{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_486{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag individual codes/methods whose sprint total exceeds baseline mean + 2σ.
- floor: 5000 per code/method (total over sprint)
- unit: count per code/method (total over sprint)

### Total 5xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolq2od92arkc?orgId=1
- description: Total 5xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline mean ± 2σ (prior sprints)
- floor: 5000 (total over sprint)
- unit: count (total over sprint)

### 5xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq3iprnj7kc?orgId=1
- description: 5xx breakdown by SIP method (bye, cancel, invite, message, prack, refer, reg, update)
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_5xx_{method}`):
  - `sum(increase(kamailio_core_rcv_replies_5xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_5xx_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: cancel, message, prack, refer, reg, update)
- deviation: flag methods whose sprint total exceeds baseline mean + 2σ.
- floor: 500 per method (total over sprint)
- unit: count per method (total over sprint)

### Total 6xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq4bagu5moc?orgId=1
- description: Total 6xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline mean ± 2σ
- floor: 500 (total over sprint)
- unit: count (total over sprint)

### 6xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolq4z7oegowd?orgId=1
- description: 6xx breakdown by SIP method
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_6xx_{method}`):
  - `sum(increase(kamailio_core_rcv_replies_6xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: bye, cancel, message, prack, refer, reg, update)
- deviation: flag methods whose sprint total exceeds baseline mean + 2σ.
- floor: 50 per method (total over sprint)
- unit: count per method (total over sprint)

### Total Requests — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolq5kf4d98gb?orgId=1
- description: Total SIP requests over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_requests{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline median ± 2×IQR (median is more robust for daily-patterned data)
- floor: 5000000 (total over sprint)
- unit: count (total over sprint)

### Requests by Method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq6451xrswa?orgId=1
- description: SIP requests broken down by method (ACK, BYE, CANCEL, INFO, INVITE, MESSAGE, NOTIFY, OPTIONS, PRACK, PUBLISH, REFER, REGISTER, SUBSCRIBE, UPDATE)
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_requests_{method}`):
  - INVITE: `sum(increase(kamailio_core_rcv_requests_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - BYE: `sum(increase(kamailio_core_rcv_requests_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: ack, cancel, info, message, notify, options, prack, publish, refer, register, subscribe, update)
- deviation: per-method baseline median ± 2×IQR
- floor: 500000 per method (total over sprint)
- unit: count per method (total over sprint)

### Failover Metrics — combined overview
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq6x2h6cxsa?orgId=1
- description: All failover counters combined (backup_used, counter_expired, failure_tracked, force, proactive, quarantine_activated)
- status: active
- datasource: prometheus
- promql (6 series, all `sum(increase(...[$__range]))`):
  - A — Backup used: `sum(increase(kamailio_failover_backup_used{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - B — Counter expired: `sum(increase(kamailio_failover_counter_expired{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - C — Failure tracked: `sum(increase(kamailio_failover_failure_tracked{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - D — Force: `sum(increase(kamailio_failover_force{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - E — Proactive: `sum(increase(kamailio_failover_proactive{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - F — Quarantine activated: `sum(increase(kamailio_failover_quarantine_activated{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence during sprint (failover activity is always significant)
- floor: > 0
- unit: count over sprint

### Backup Used — by X-Header (customer)
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq7pb0a7eoc?orgId=1
- description: Backup path usage — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_backup_used{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any non-zero xheader entry
- floor: > 0
- unit: count over sprint per customer

### Counter Expired — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolq90hjb75sf?orgId=1
- description: Failover counter expiry events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_counter_expired{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag increases vs. baseline sprint
- floor: > 0
- unit: count over sprint per customer

### Failure Tracked — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolqanied4w0f?orgId=1
- description: Failures being tracked by the failover system — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_failure_tracked{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: mean ± 3σ; flag sustained elevation
- floor: > 10
- unit: count over sprint per customer

### Force Failover — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqctb9iepsf?orgId=1
- description: Forced failover events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_force{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence
- floor: > 0
- unit: count over sprint per customer

### Proactive Failover — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqdp04mw3kc?orgId=1
- description: Proactive failover events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_proactive{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any non-zero count
- floor: > 0
- unit: count over sprint per customer

### Quarantine Activated — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolqed5vcpogb?orgId=1
- description: Quarantine activation events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_quarantine_activated{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence
- floor: > 0
- unit: count over sprint per customer

### Top 5 High MOS — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolqf233b5kwf?orgId=1
- description: Top 5 customers / X-Headers with highest MOS scores (p50 over sprint)
- status: active
- datasource: prometheus
- promql: `topk(5, avg by (xheader) (quantile_over_time(0.5, (kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"}[$__range]))))`
- deviation: informational; flag only if top MOS values drop below 3.5
- floor: < 3.0
- unit: MOS (1–5 scale)

### Top 5 Low MOS — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqfsxbls00b?orgId=1
- description: Top 5 customers / X-Headers with lowest MOS scores (p50 over sprint)
- status: active
- datasource: prometheus
- promql: `bottomk(5, avg by (xheader) (quantile_over_time(0.5, (kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"}[$__range]))))`
- deviation: flag when lowest MOS < 3.0 or the number of low-MOS xheaders increases vs. baseline
- floor: < 2.5
- unit: MOS (1–5 scale)

### MOS Metrics Over Time
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolqgjev9slca?orgId=1
- description: MOS trend over time — fleet median for MOS avg/min/max and jitter/packetloss/rtt/samples
- status: active
- datasource: prometheus
- promql (fleet-level p50 using `quantile(0.5,...)`; multiple series):
  - A — MOS avg: `quantile(0.5, kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"} > 0)`
  - B — MOS avg jitter: `quantile(0.5, kamailio_mos_avg_jitter{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"} > 0)`
  - C — MOS avg packetloss: `quantile(0.5, kamailio_mos_avg_packetloss{...} > 0)`
  - D — MOS avg RTT: `quantile(0.5, kamailio_mos_avg_rtt{...} > 0)`
  - E — MOS avg samples: `quantile(0.5, kamailio_mos_avg_samples{...} > 0)`
  - F — MOS max: `quantile(0.5, kamailio_mos_max{...} > 0)`
  - G — MOS max jitter: `quantile(0.5, kamailio_mos_max_jitter{...} > 0)`
  - H — MOS max packetloss: `quantile(0.5, kamailio_mos_max_packetloss{...} > 0)`
  - I — MOS max RTT: `quantile(0.5, kamailio_mos_max_rtt{...} > 0)`
  - J — MOS min: `quantile(0.5, kamailio_mos_min{...} > 0)`
  - K — MOS min jitter: `quantile(0.5, kamailio_mos_min_jitter{...} > 0)`
  - L — MOS min packetloss: `quantile(0.5, kamailio_mos_min_packetloss{...} > 0)`
  - M — MOS min RTT: `quantile(0.5, kamailio_mos_min_rtt{...} > 0)`
- deviation: flag when fleet p50 MOS avg drops below 3.5 or decreases > 0.3 vs. baseline
- floor: < 3.0
- unit: MOS (1–5 scale)
