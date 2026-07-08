# Metric Analysis Engine

This file defines the unified algorithm and Python script structure for fetching, detecting deviations, and charting metrics. Both `xcc-metrics.md` and `rtpengine-metrics.md` rely on this engine.

> COST REDUCTION MANDATE (TOKEN DIET):
> Never fetch full timeseries data for all metrics. Raw 5-minute resolution JSON payloads for a 14-day sprint consume millions of tokens and exhaust the budget.

## 1. Lazy Evaluation Algorithm (Two-Phase Fetch)

To prevent massive JSON ingest, data collection MUST follow a two-phase approach.

### Phase 1: Server-Side Aggregation (Instant Query)
For every active metric, execute a single `queryType: instant` at `endTime: <sprint_end>`.
Delegate the calculation to the Prometheus server using the sprint duration (e.g., `14d`) in the over-time function.

Each metric defines a **floor** — an absolute hard trigger value. Phase 1 follows a two-step flow:

1. **Floor bypass** (checked first):  
   If the Phase 1 value meets or exceeds the metric's floor, the metric is **flagged as deviating immediately** — the statistical check is skipped.  
2. **Fallback estatístico** (only if floor was not breached):  
   Apply the metric's statistical deviation rule (Median + 3×MAD, P95 > threshold, IQR, etc.).

| Type | Phase 1 query | Floor bypass condition | Fallback statistical rule |
|---|---|---|---|
| **RATE** (Bursty) | `max_over_time( (<original_promql>)[14d:5m] )` | `peak >= floor` → immediate flag | Median + 3×MAD |
| **RESOURCE** (Stable) | `quantile_over_time(0.95, (<original_promql>)[14d:5m] )` | `P95 >= floor` → immediate flag | P95 > defined threshold % |
| **STATE** (Gaps/Leaks) | `min_over_time( (<original_promql>)[14d:5m] )` or `delta(...)` | `value == 0` or gap → immediate flag | gap duration > 5 min |

> Floor bypass overrides the fallback entirely. If the floor is breached, the metric proceeds directly to Phase 2 (charts) without running MAD, P95 comparison, IQR, or any other statistical rule.

*Only metrics that breach either their floor or their statistical rule proceed to Phase 2.*

### Phase 2: Downsampled Fetch (Range Query) - ONLY for deviating metrics
For the few metrics that actually deviated in Phase 1, you must fetch the timeseries to plot the chart.
You MUST enforce severe downsampling to keep the JSON small:
* Execute a `queryType: range` via `grafana-mcp-prd:query_prometheus`.
* **STATE METRICS EXCEPTIONS**: For strict binary states (like "Alive" 0/1), skip Phase 2. BUT for Failover metrics, Session counts, or other counters classified as STATE, you MUST run Phase 2 and generate a chart using `plot_helper.py`.
* **MANDATORY DOWNSAMPLING**: You MUST set `step: 14400` (4 hours). Never omit the `step` parameter. This reduces 4000 points to 84 points per series.
* **PEAK PRESERVATION**: Because a 4-hour step hides short spikes, you MUST wrap the Phase 2 query in `max_over_time( (<original_promql>)[4h:5m] )`. This ensures the 4-hour data points still reflect the true peak of that window.
* **INSTANCE FILTERING**: Do not download data for healthy instances. Inject a regex filter for ONLY the instances that deviated in Phase 1. E.g., if only `xcc-1` and `xcc-3` deviated, append `{instance=~"xcc-1|xcc-3"}` to the PromQL.

## 2. Generate Static PNG Charts (replaces Native Confluence Macros)

> NEVER use Native Confluence Chart Macros (`<ac:structured-macro ac:name="chart">`). They cause severe `StaleStateException` crashes in Atlassian backend.

For each deviating metric, you MUST use `scripts/plot_helper.py` to generate a static PNG chart.
1. Format your Phase 2 JSON into the expected payload:
   ```json
   {
     "lines": [
       {
         "label": "<INSTANCE_1>",
         "points": [ {"x": "2026-06-15 10:00", "y": 12.3}, {"x": "2026-06-15 14:00", "y": 14.5} ]
       }
     ],
     "threshold": {"label": "Threshold", "value": 10.0}
   }
   ```
2. Call `scripts/plot_helper.py "<TITLE>" "/tmp/chart_output.png" "Date" "<UNIT>" '<json_payload>'`
3. Upload `/tmp/chart_output.png` as an attachment to the Confluence page.
4. Inline the image in your HTML output:
   `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="chart_output.png"/></ac:image>`

## 3. Zoom Window Logic
For metrics that require a zoom chart:
* Find the peak timestamp from the Phase 2 rows (max value across deviating instances).
* Filter rows to `[peak_timestamp - 30 min, peak_timestamp + 30 min]`.
* Emit a second chart macro with the same structure, title suffix `— zoom <YYYY-MM-DDTHH:MMZ>`.

## 4. Reporting the Findings
For each metric that deviated and produced a chart:
* Emit `Reference = N.NN <unit>` as plain text (one line).
* Emit one bullet per deviating instance: `* <instance>: <metric> peak <value> <unit> at <YYYY-MM-DDTHH:MMZ>`.
* Inline the chart macro(s) immediately after the bullets (NO caption, NO surrounding paragraph).
* Include the parameterized Grafana link.
