# Metric Analysis Engine

This file defines the unified algorithm and Python script structure for fetching, detecting deviations, and charting metrics. Both `xcc-metrics.md` and `rtpengine-metrics.md` rely on this engine.

> **TOKEN DIET & AUTOMATION MANDATE**: 
> The LLM MUST NOT perform mathematical analysis, percentile calculations, or JSON parsing for metrics. All Prometheus evaluation has been offloaded to the Python script `scripts/grafana_metrics.py analyze`.
> The LLM's only job for these sections is to execute the script and embed its markdown output.

## 1. High-Resolution Analysis (Single Phase Fetch)

Because analysis is performed in Python, we no longer need the "Lazy Evaluation" or two-phase fetch. The script `grafana_metrics.py` (subcommand `analyze`) handles the large data arrays securely.

For every active metric defined in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`, the script will:
1. Execute a `queryType: range` via its in-process `GrafanaHttpClient.query_prometheus()` (plain HTTP against Grafana's Prometheus datasource proxy, Vouch cookie auth) spanning the full sprint.
2. Use a high-resolution step (e.g. `step: 300` for 5-minute intervals) to capture true peaks.
3. Process the entire timeseries in memory to detect deviations based on the mathematical rule defined in the YAML configuration.

### Deviation Rules Applied by the Script

Each metric may define a **floor** (an absolute hard trigger value, via the
`floor_value`/`floor_op` YAML fields) and a fallback statistical rule.

1. **Floor bypass** (checked first):
   If any data point crosses the metric's floor (`floor_op: gte|gt` — value
   too HIGH; `floor_op: lt` — value too LOW, e.g. MOS), the metric is
   **flagged as deviating immediately**, without waiting for the statistical
   rule. Currently wired up in `config/xcc_metrics.yaml` only — see that
   file for which metrics have a numeric floor and which are left
   statistical-only (formula/cross-series floors like "CPU count × 1.2"
   aren't parsed automatically). `config/rtp_metrics.yaml` has no floor
   values defined yet.
2. **Fallback statistical rule**:
   If the floor was not breached (or the metric has no floor), the script
   applies the metric's statistical deviation rule across the entire array,
   dispatched by keyword in the `deviation:` field:
   - **RATE / Spikes**: Median + 3×MAD (Median Absolute Deviation)
   - **RESOURCE / Stable**: 95th Percentile (P95) against a baseline threshold
   - **STATE / Gaps**: sustained-zero or IQR-jump detection
   - Free-text `deviation:` rules that contain none of those keywords are
     never statistically flagged — their floor (if any) is their only
     detection mechanism; otherwise their data is still fetched and their
     Grafana link still published, just never auto-flagged.

## 2. Chart Generation (PNG)

For each metric that deviates and is **not** STATE-type, `grafana_metrics.py`
calls `plot_helper.render_chart()` in-process to generate static PNG
charts — STATE metrics are blanket-skipped (text bullets only).
* High-resolution charts are saved to the `output/` directory
  (e.g., `output/chart_<region>_<metric_slug>.png`), one solid line per
  deviated instance plus a dotted red "Reference" threshold line.
* A second zoom PNG (`..._zoom.png`, suffix `_zoom`) is generated around the
  primary deviated series' peak timestamp (`± 30 min`), skipped silently if
  the sliced window has fewer than 3 points.
* Chart generation failures are non-fatal: a `WARN:` is printed to stderr and
  the metric's text bullets are still emitted without an image tag.

> NEVER use Native Confluence Chart Macros (`<ac:structured-macro ac:name="chart">`). They cause severe `StaleStateException` crashes. Only use the generated PNG attachments.

## 3. Script Output

The `grafana_metrics.py analyze` subcommand outputs a fully formatted Confluence Storage / Markdown block.
It includes:
* The `Reference = N.NN <unit>` text.
* Bullet points for deviating instances (`* <instance>: peak <value> at <time>`).
* Inline image tags (`<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`) pointing to the generated PNGs.
* The parameterized Grafana link.

**Subagent Workflow:**
1. Run the script: `python3 scripts/grafana_metrics.py analyze <config_yaml> <start_date> <end_date> <region>`
2. Append the script's stdout directly to your local HTML/Markdown output file.
3. Move on to the next region. Do not second-guess the math or write manual metric bullets.
