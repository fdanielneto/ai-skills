# RTPEngine_Metrics — "RTP Engine Metrics" section (its own section)

Per the requester's decision, RTP Engine is a **standalone section**, separate
from XCC/Kamailio. This reference owns its own heading and its own per-region
dropdowns, rendered immediately AFTER the "XCC Metrics" section.

> DATA SOURCES: analyse ONLY the Grafana panels and metrics listed in
> the **Appendix: RTPEngine Data Sources** below. Do not browse other dashboards or
> invent metrics. That section is the single source of truth.

> SILENCE RULE (global): **publish ONLY deviating metrics.** If a metric is
> within its normal range, emit nothing — no comment, no bullet, no "within
> parameters" note. This applies per metric. A region block with zero
> deviations contains only the Grafana dashboard link (one line).

> **TOKEN REDUCTION PIPELINE**: Do NOT process the metrics math here manually. The configuration is stored in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`. Use `scripts/grafana_analyzer.py` to evaluate the deviations. Only write about the metrics that `grafana_analyzer.py` flags as deviated.

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

## Per-region analysis algorithm (consumes Appendix: RTPEngine Data Sources)

> SILENCE RULE (UPDATED): **Publish only deviating metrics.** If a metric is within normal range, emit nothing for that metric. If ALL metrics are within range for a region, the block contains the Grafana link followed by: `No deviation detected ✅`.

For each region R:
1. For each metric M in the **Appendix: RTPEngine Data Sources** (in section order):
   - If `status: active`: you MUST use the Two-Phase Fetch (Instant Phase 1, Range Phase 2) as strictly defined in `metric-analysis-engine.md`.
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
   table) and a **chart** that shows the deviation (skip chart for STATE metrics), plus the Grafana link —
   following the GENERIC DEVIATION → REFERENCE SCALAR + CHART rule below.
4. If ALL metrics for a region are within normal range: emit only the Grafana
   dashboard link. **Do not add any text.**

### GENERIC DEVIATION → REFERENCE SCALAR + CHART rule
### GENERIC DEVIATION & CHART GENERATION

**CRITICAL**: You MUST use the `bash` tool to execute `scripts/grafana_analyzer.py` for each region, passing the `rtp_metrics.yaml` config. The script will handle fetching data, detecting deviations, generating PNGs, and outputting the exact HTML snippet.

Example: `python3 scripts/grafana_analyzer.py /path/to/rtp_metrics.yaml 2026-06-10 2026-06-28 eu-south-1`

Your job is to run this script for each region and place its output inside the correct expandable block.

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
(Full details — Grafana links, PromQL, deviation rules — in the **Appendix: RTPEngine Data Sources**)

- **Alive Stats**: RTPEngine Alive
- **Infra Details**: CPU Stats, System Load, Memory Usage, Network I/O
- **Media Details**: Media Ports, Media Sessions (by region), Media Sessions by
  Instance, Transcoding Media Sessions

## Rules
- This section is RTP Engine ONLY; Kamailio/XCC content stays in the XCC section.
- Analyse ALL metrics in the **Appendix: RTPEngine Data Sources** (active +
  reference). EVERY metric is processed with the GENERIC DEVIATION → REFERENCE
  SCALAR + CHART rule (see `references/metric-analysis-engine.md`).
- **SILENCE RULE**: Publish only deviating metrics. Within deviating metrics, publish only deviating instances. If a region has zero deviations, emit only the region dashboard link.
- **FINDING FORMAT**: Each bullet = `<instance>: <metric> peak <value> <unit> at <timestamp>`. Never include AZ/instance-type annotations, threshold internals, or summaries for non-deviating instances.
- **GRAFANA LINKS**: Must be parameterized from the datasource `goto` URL.
- **FAIL-FAST RULE**: If any required data source returns an authentication error or is unreachable, return `[FATAL_AUTH_ERROR]` and a brief description. Do not generate warning panels.
- **IMAGE ALIGNMENT**: All `<ac:image>` tags MUST carry `ac:align="center" ac:width="950"`.
- **NO-TODO RULE**: Never emit fabricated values or TODO placeholders.
- **OUTPUT SCHEMA**: Emit only final section body content. Do not emit orchestration, publishing, rationale, or repeated rule text.
- Do not invent values, goto URLs, instance names, or session counts.
- For each deviating metric: emit `Reference = N.NN {unit}` (plain text, NO table)
  AND a chart that shows the deviation (overview + zoom per event). STATE metrics: skip chart, text bullet only.
  Charts: static PNG charts generated via `plot_helper.py` (see `references/metric-analysis-engine.md` §2). Do NOT use native Confluence Chart macros.
- Publish: Must use Confluence REST API with `representation: "storage"`. Never use Atlassian MCP tools for publishing.


---

# Appendix: RTPEngine Data Sources — single source of truth for the RTPEngine per-region analysis

This file lists EVERY metric the RTPEngine section may analyse, and nothing else.
The section builder (`rtpengine-metrics.md`) must analyse ONLY what is registered
here — do not browse other dashboards or invent metrics.

## Global scope (applies to every entry)
- Service: `rtpengine` instances — `instance=~"rtpengine-edge-.*"`. Never mix
  with kamailio roles.
- Region: injected per region as `region="$region"`.
- Windows: SPRINT = [sprint_start, sprint_end]; BASELINE = 5 days before
  sprint_start (for deviation comparison).
- Default Prometheus datasourceUid: `prometheus`
  (alternatives: `mimir` = ae504r5d0usjkb, `mimir-ap` for APAC).
- **Grafana region variable**: `var-region` — append to `goto` URLs when
  building per-region parameterized links (see GRAFANA LINK FORMAT in
  `rtpengine-metrics.md`).

## DEVIATION POLICY — global, applies to every metric in this file

**Only publish findings for metrics that deviated from the normal pattern.
For metrics within the normal range: complete silence — no comment, no bullet,
no "within parameters" note, no "no deviation" line.**

**Per-instance silence rule**: within a deviating metric, omit ANY instance
that is within normal range — no bullet, no "within range" note, no mention of
that instance at all. Only instances that actually exceeded the deviation
threshold appear in the report.

Deviation detection method (choose per metric type):
- **Rate / count metrics** (connection failures, session counts):
  mean ± 3σ over the sprint window. Flag when
  `max > mean + 3σ  AND  max ≥ minimum_floor`.
- **Resource metrics** (CPU, memory, load, network I/O):
  use the sprint **median** as baseline (more robust than mean to transient
  spikes). Flag when any sustained 30-min window average exceeds
  `median + 2 × IQR`, or when a stepwise change is visually clear.
- **Alive / up metrics**: flag any gap (value = 0 or series missing) lasting
  more than 5 consecutive minutes.
- **Session / media counts**: use sprint median; flag when max exceeds
  `median + 2 × IQR` or when a stepwise change suggests stuck/leaked sessions.

When no deviation is detected for a metric: **emit nothing** — the metric is
absent from the published report entirely.
When no deviation is detected for ANY metric in a region: the region's expand
block contains only the word "OK" and below the Grafana dashboard link (one line). No extra text.

## Status convention

- `status: active` — PromQL confirmed from Grafana source. Fully automated.
- `status: reference` — Grafana link available; PromQL TBD. Link included in
  report as a panel shortcut; automated analysis not yet wired.

## PromQL conventions in this file

- `$region` is replaced at runtime with the target region value.
- `instance=~"rtpengine-edge-.*"` selects all RTPEngine instances dynamically.
  Do NOT hardcode instance names.
- `$__range` = Grafana dashboard time range variable. When executing via MCP,
  replace with `[N]s` (sprint duration in seconds).

## Per-metric entry schema

```
### <Metric display name>
- grafana: <Grafana panel/dashboard link>
- description: <what the panel shows>
- purpose: <when/why to look at this>
- status: active | reference
- datasource: prometheus | mimir | mimir-ap
- promql: <PromQL expression using $region and role="edgerouter">
- deviation: <rule>
- unit: <e.g. %, Mb/s, count, err/s>
```

---

## Metrics to analyse

### ── Section: Alive Stats ─────────────────────────────────────────────────────

### RTPEngine Alive
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolpmd59gp34d?orgId=1
- description: RTPEngine alive stats — by RTPEngine instance (up/down via uptime seconds)
- purpose: verify all RTPEngine instances are up; flag any gap in aliveness
- status: active
- datasource: prometheus
- promql: `sgn(rtpengine_uptime_seconds{region="$region",instance=~"rtpengine-edge-.*",service=~".*"})`
  (returns 1 when instance has uptime > 0; 0 or absent = down/unreachable)
- deviation: flag any gap (result = 0 or series absent) lasting > 5 min.
- unit: binary 0/1

### ── Section: Infra Details — RTPEngine ──────────────────────────────────────

### CPU Stats — RTPEngine
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolptd75jklce?orgId=1
- description: CPU stats (user, system, iowait, guest) — by RTPEngine instance
- purpose: detect CPU pressure on RTPEngine instances; correlate with media session load
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `instance=~"rtpengine-edge.*"`, `cpu="cpu-total"`):
  - A — User: `cpu_usage_user{region="$region",instance=~"rtpengine-edge.*",cpu="cpu-total"}`
  - B — System: `cpu_usage_system{region="$region",instance=~"rtpengine-edge.*",cpu="cpu-total"}`
  - C — IOWait: `cpu_usage_iowait{region="$region",instance=~"rtpengine-edge.*",cpu="cpu-total"}`
  - D — Guest: `cpu_usage_guest{region="$region",instance=~"rtpengine-edge.*",cpu="cpu-total"}`
- deviation: type: RESOURCE — P95 > 80%.
- unit: % CPU

### System Load — RTPEngine
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpty78t4hsa?orgId=1
- description: System load (1 m, 5 m, 15 m) and CPU count — by RTPEngine instance
- purpose: detect load spikes that may affect media processing
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `instance=~"rtpengine-edge.*"`):
  - A — 1-min load: `system_load1{region="$region",instance=~"rtpengine-edge.*"}`
  - B — 5-min load: `system_load5{region="$region",instance=~"rtpengine-edge.*"}`
  - C — 15-min load: `system_load15{region="$region",instance=~"rtpengine-edge.*"}`
  - D — CPU count: `system_n_cpus{region="$region",instance=~"rtpengine-edge.*"}`
- deviation: type: RESOURCE — P95 > (CPU count * 0.8).
- unit: load average (dimensionless)

### Memory Usage — RTPEngine
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolpuk8l260wc?orgId=1
- description: Memory breakdown (total, used, cached+buffered, free, swap used) — by RTPEngine instance
- purpose: detect memory pressure or leaks in RTPEngine processes
- status: active
- datasource: prometheus
- promql (5 series; all scoped to `region="$region"`, `instance=~"rtpengine-edge.*"`):
  - A — Total: `mem_total{region="$region",instance=~"rtpengine-edge.*"}`
  - B — Used: `mem_used{region="$region",instance=~"rtpengine-edge.*"}`
  - C — Cached+Buffered: `mem_cached{region="$region",instance=~"rtpengine-edge.*"} + mem_buffered{region="$region",instance=~"rtpengine-edge.*"}`
  - D — Free: `mem_free{region="$region",instance=~"rtpengine-edge.*"}`
  - E — Swap used: `mem_swap_total{region="$region",instance=~"rtpengine-edge.*"} - mem_swap_free{region="$region",instance=~"rtpengine-edge.*"}`
- deviation: type: RESOURCE — P95 > 80%.
- unit: bytes

### Network I/O — RTPEngine
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpv3s713pca?orgId=1
- description: Network I/O in bits/s (receive and transmit) — by RTPEngine instance
- purpose: detect unusual media traffic volume; correlate with session counts
- status: active
- datasource: prometheus
- promql (2 series; both scoped to `region="$region"`, `instance=~"rtpengine-edge.*"`):
  - A — RX: `irate(net_bytes_recv{region="$region",instance=~"rtpengine-edge.*"}[5m]) * 8`
  - B — TX: `irate(net_bytes_sent{region="$region",instance=~"rtpengine-edge.*"}[5m]) * 8`
- deviation: type: RESOURCE — P95.
- unit: bits/s

### ── Section: RTPEngine Media Details ───────────────────────────────────────

### Media Ports
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpybilo2kga?orgId=1
- description: RTPEngine media port usage (used, free, total) for public interface — all RTPEngine instances aggregated
- purpose: detect port exhaustion or unusual port allocation patterns
- status: active
- datasource: prometheus
- promql (3 series; all summed, scoped to `region="$region"`, `instance=~"rtpengine-edge.*"`, `name="pub"`):
  - A — Used: `sum(rtpengine_ports_used{region="$region",instance=~"rtpengine-edge.*",name="pub"}) by (name)`
  - B — Free: `sum(rtpengine_ports_free{region="$region",instance=~"rtpengine-edge.*",name="pub"}) by (name)`
  - C — Total: `sum(rtpengine_ports{region="$region",instance=~"rtpengine-edge.*",name="pub"}) by (name)`
- deviation: type: RESOURCE — used / total > 80%.
- unit: count (ports)

### Media Sessions — by region
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolpyyq6pam8b?orgId=1
- description: RTPEngine active media sessions (type=own) — aggregated by region and service
- purpose: detect session count anomalies — sudden drops (call drops) or stuck sessions (leaks)
- status: active
- datasource: prometheus
- promql: `sum(rtpengine_sessions{type="own",region="$region",instance=~"rtpengine-edge.*",service=~".*"}) by (region,service)`
- deviation: type: STATE — flag sustained zero or monotonic increase (leak).
- unit: count (sessions)

### Media Sessions by Instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpzjae43cwb?orgId=1
- description: RTPEngine active media sessions (type=own) — per RTPEngine instance
- purpose: detect per-instance imbalances or individual instance anomalies
- status: active
- datasource: prometheus
- promql: `rtpengine_sessions{type="own",region="$region",instance=~"rtpengine-edge.*",service=~".*"}`
- deviation: type: STATE — flag if one instance diverges significantly.
- unit: count (sessions)

### Transcoding Media Sessions — by region
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolq07ux3400f?orgId=1
- description: RTPEngine transcoding sessions — aggregated by region
- purpose: detect unexpected transcoding load (transcoding is CPU-heavy; spikes impact capacity)
- status: active
- datasource: prometheus
- promql: `sum(rtpengine_transcoded_media{region="$region",instance=~"rtpengine-edge.*"}) by (region)`
- deviation: sprint median + 2×IQR; any sustained increase is noteworthy if transcoding is not expected.
- unit: count (transcoding sessions)
