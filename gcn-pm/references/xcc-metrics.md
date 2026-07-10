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

> **TOKEN REDUCTION PIPELINE**: Do NOT process the metrics math here manually. The configuration is stored in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`. Use `scripts/grafana_metrics.py analyze` to evaluate the deviations. Only write about the metrics that it flags as deviated.

### DATA COLLECTION / Grafana auth

Grafana (`grafana-general.svc.talkdeskapp.com`) is queried over **plain
HTTP** via `scripts/grafana_metrics.py`'s in-process `GrafanaHttpClient` —
no MCP, no browser per query. Auth is a Vouch SSO session cookie kept in
`gcn-pm/.auth/grafana_vouch_cookie.txt` (gitignored, chmod 600), maintained
by the same script's `refresh` subcommand. A browser (Playwright, persistent
Chrome profile shared with `kibana_metrics.py`) is used **only** by
`grafana_metrics.py refresh` to obtain/renew that cookie — never per query.
Same pattern as Kibana; see `references/sbc-metrics.md` §DATA COLLECTION for
the full rationale.

**Authentication procedure:**
1. Run `scripts/grafana_metrics.py analyze` (or the direct query) as normal.
2. If it reports an expired/missing session, run
   `python3 scripts/grafana_metrics.py refresh` once, then retry.
3. If authentication still fails after the refresh, abort with
   `[FATAL_AUTH_ERROR]` (see FAIL-FAST RULE below) — do not generate warning
   panels or retry in a loop.

## Structure (in order)

### H1: XCC Metrics

### Sub-section A — "XCC - Host Details" (expandable, collapsed)

An expandable block titled **XCC - Host Details** containing ONE table with one
row per region.

#### Data fetch (most performant — chosen over rendering the Grafana view)
Run a single INSTANT PromQL query via `scripts/grafana_metrics.py`'s
`GrafanaHttpClient.query_prometheus(..., query_type="instant")` and read the
labels off each returned series — no browser, no per-host series to dedupe:

```
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
> NEVER emit `[TODO]` or `[TODO]`-style placeholder cells. If Grafana returns an
> auth error (session cookie expired — see DATA COLLECTION / Grafana auth
> below), run `python3 scripts/grafana_metrics.py refresh` once and retry. If it
> still fails, emit a single `warning` panel for the whole sub-section stating
> Grafana was unavailable — do not publish an empty/`[TODO]` table.

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
> section order. For metrics with `status: active`, fetching, deviation detection
> (floor-bypass + statistical rule), and chart generation are handled entirely by
> `scripts/grafana_metrics.py analyze` — see "GENERIC DEVIATION & CHART GENERATION" below;
> just run the script. For metrics with `status: reference`, open the Grafana link
> and include it in the report only if a deviation is visible; skip the metric
> entirely if everything looks normal.

> SILENCE RULE (UPDATED): **Publish only deviating metrics.** If a metric is within its normal range, emit nothing. If ALL metrics for a region are within normal range, the region block contains the Grafana dashboard link followed by: `No deviation detected ✅`.

For each region R (scoped to `role="edgerouter", region="R"`):
1. Run `scripts/grafana_metrics.py analyze` for region R (see "GENERIC DEVIATION & CHART
   GENERATION" below) — it fetches every `status: active` metric, applies
   floor-bypass then the statistical rule, and emits ready-to-embed HTML
   (reference scalar, finding bullets, chart `<ac:image>` tags for non-STATE
   deviations) for every metric that deviated.
2. For `status: reference` metrics: link the Grafana panel; analyse visually if
   data collection is wired; otherwise include the link and skip automated check.
3. Group the metrics that deviated under bold issue-group headings, e.g.:
   - **XCC <version> deploy on <date> causing spikes:**
   - **Different pattern/increase <date> (as previously seen every 2w)**
   - **No data until <date>**
   - **<Metric> spike (<value>) on <date>**
   - **CPU/Memory/Load pressure on <date>** (for resource metric deviations)
4. If ALL metrics for a region are within normal range: the region block
   contains only the Grafana dashboard link. **Do not add any text.**

### GENERIC DEVIATION & CHART GENERATION

> **IMPORTANT**: See `references/metric-analysis-engine.md` for the single source of truth on how the script fetches data, computes deviations dynamically (RATE vs RESOURCE vs STATE), applies floor-bypass, and generates charts.

**CRITICAL**: You MUST use the `bash` tool to execute `scripts/grafana_metrics.py analyze` for each region. The script handles fetching data, detecting deviations, generating PNG charts (overview + zoom, STATE metrics excluded), and outputting the exact HTML snippet.

The script takes **epoch milliseconds**, not dates — convert first (e.g. `date -j -f "%Y-%m-%dT%H:%M:%S" "2026-06-10T00:00:00" +%s000`).

Example: `python3 scripts/grafana_metrics.py analyze /path/to/xcc_metrics.yaml 1781049600000 1782691199000 eu-south-1`

Your job is to run this script for each region and place its output inside the correct expandable block. Do not second-guess the math or write manual metric bullets.

---

## Rules
- Section scope is `role="edgerouter"` ONLY — never include other kamailio roles.
- Analyse ALL metrics in the **Appendix: XCC Data Sources** (active + reference),
  in section order. Do not add metrics from other sources. EVERY metric is
  processed with the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule.
- **FLOOR BYPASS**: Metrics with a numeric `floor_value` in `config/xcc_metrics.yaml` are flagged as deviating immediately if any point crosses it, without running the statistical rule (MAD/P95/IQR). Below the floor (or for metrics with no `floor_value`), the statistical rule still applies as fallback.
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

Full definitions (PromQL, deviation rule, floor, unit) live in
`config/xcc_metrics.yaml` — that file is what `scripts/grafana_metrics.py analyze`
actually reads; this table is a human-readable index only.

| Metric | Description | Status |
|---|---|---|
| Error Rates (Spikes) — by instance | 4xx, 5xx, 6xx error rate — by XCC instance | active |
| Custom Metrics Rates (Spikes) — by instance | Inbound/Outbound Invite rate, RTP Engine failure rate, SIP Rec call rate — by XCC instance | active |
| Infra Details — version and instance type | XCC version and instance type — by XCC instance | active |
| Kamailio Alive | XCC alive stats — by XCC instance (up/down status) | active |
| CPU Stats — Kamailio | XCC CPU stats — by XCC instance (user, system, iowait, guest) | active |
| System Load — Kamailio | XCC system load (1 m, 5 m, 15 m) and CPU count — by XCC instance | active |
| CPU Usage per Process — Kamailio | CPU usage per process (top-18) — by XCC instance | active |
| Memory Usage per Process — Kamailio | Memory usage per process (top-18, RSS) — by XCC instance | active |
| Memory Usage — Kamailio | Memory breakdown (total, used, cached+buffered, free, swap used) — by XCC instance | active |
| Network I/O — Kamailio | Network I/O in bits/s (receive and transmit) — by XCC instance | active |
| Number of File Handles — Kamailio | Number of open file handles (system-wide) — by XCC instance | active |
| Disk Usage — Kamailio | Disk usage percentage — by XCC instance | active |
| TCP Connection Counters | TCP connection counters by type — by XCC instance | active |
| Core SHMem Max Used | Kamailio core shared memory (max_used and total) — by XCC instance | active |
| RTPEngine Connection Failures | RTPEngine connection failures (from Kamailio's perspective) — by XCC instance | active |
| Total 4xx — global | Total 4xx replies over the sprint window — all XCC instances aggregated | active |
| 4xx Detailed — by error code and method | 4xx breakdown by specific code (400–493) and SIP method | active |
| Total 5xx — global | Total 5xx replies over the sprint window — all XCC instances aggregated | active |
| 5xx Detailed — by error code and method | 5xx breakdown by SIP method (bye, cancel, invite, message, prack, refer, reg, update) | active |
| Total 6xx — global | Total 6xx replies over the sprint window — all XCC instances aggregated | active |
| 6xx Detailed — by error code and method | 6xx breakdown by SIP method | active |
| Total Requests — global | Total SIP requests over the sprint window — all XCC instances aggregated | active |
| Requests by Method | SIP requests broken down by method (ACK, BYE, CANCEL, INFO, INVITE, MESSAGE, NOTIFY, OPTIONS, PRACK, PUBLISH, REFER, REGISTER, SUBSCRIBE, UPDATE) | active |
| Failover Metrics — combined overview | All failover counters combined (backup_used, counter_expired, failure_tracked, force, proactive, quarantine_activated) | active |
| Backup Used — by X-Header (customer) | Backup path usage — per customer X-Header | active |
| Counter Expired — by X-Header | Failover counter expiry events — per customer X-Header | active |
| Failure Tracked — by X-Header | Failures being tracked by the failover system — per customer X-Header | active |
| Force Failover — by X-Header | Forced failover events — per customer X-Header | active |
| Proactive Failover — by X-Header | Proactive failover events — per customer X-Header | active |
| Quarantine Activated — by X-Header | Quarantine activation events — per customer X-Header | active |
| Top 5 High MOS — by X-Header | Top 5 customers / X-Headers with highest MOS scores (p50 over sprint) | active |
| Top 5 Low MOS — by X-Header | Top 5 customers / X-Headers with lowest MOS scores (p50 over sprint) | active |
| MOS Metrics Over Time | MOS trend over time — fleet median for MOS avg/min/max and jitter/packetloss/rtt/samples | active |

Metric names above match `config/xcc_metrics.yaml` keys exactly — look a
metric up there for its PromQL, `deviation:` rule, `floor`/`floor_value`, and
`unit`. Sub-query breakdowns (the `A —`/`B —` series within a metric) are
also in the YAML, keyed the same way.
