# Metric Analysis Engine

This file defines the unified algorithm and Python script structure for fetching, detecting deviations, and charting metrics. Both `xcc-metrics.md` and `rtpengine-metrics.md` rely on this engine.

> **TOKEN DIET & AUTOMATION MANDATE**: 
> The LLM MUST NOT perform mathematical analysis, percentile calculations, or JSON parsing for metrics. All Prometheus evaluation has been offloaded to the Python script `scripts/grafana_analyzer.py`.
> The LLM's only job for these sections is to execute the script and embed its markdown output.

## 1. High-Resolution Analysis (Single Phase Fetch)

Because analysis is performed in Python, we no longer need the "Lazy Evaluation" or two-phase fetch. The script `grafana_analyzer.py` handles the large data arrays securely.

For every active metric defined in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`, the script will:
1. Execute a `queryType: range` via `grafana-mcp-prd:query_prometheus` spanning the full sprint.
2. Use a high-resolution step (e.g. `step: 300` for 5-minute intervals) to capture true peaks.
3. Process the entire timeseries in memory to detect deviations based on the mathematical rule defined in the YAML configuration.

### Deviation Rules Applied by the Script

Each metric defines a **floor** (an absolute hard trigger value) and a fallback statistical rule.

1. **Floor bypass** (checked first):  
   If any data point meets or exceeds the metric's floor, the metric is **flagged as deviating immediately**.
2. **Fallback statistical rule**:  
   If the floor was not breached, the script applies the metric's statistical deviation rule across the entire array.
   - **RATE / Spikes**: Median + 3×MAD (Median Absolute Deviation)
   - **RESOURCE / Stable**: 95th Percentile (P95) against a baseline threshold
   - **STATE / Gaps**: Detection of sustained 0s or gaps lasting > 5 minutes

## 2. Automated Chart Generation (PNG)

For each metric that deviates, `grafana_analyzer.py` automatically invokes `scripts/plot_helper.py` to generate static PNG charts.
* High-resolution charts are saved to the `output/` directory (e.g., `output/chart_<region>_<metric_id>.png`).
* If a metric requires a zoom window, the script slices the array in memory (`peak ± 30 mins`) and generates a second zoom PNG.

> NEVER use Native Confluence Chart Macros (`<ac:structured-macro ac:name="chart">`). They cause severe `StaleStateException` crashes. Only use the generated PNG attachments.

## 3. Script Output

The `grafana_analyzer.py` script outputs a fully formatted Confluence Storage / Markdown block.
It includes:
* The `Reference = N.NN <unit>` text.
* Bullet points for deviating instances (`* <instance>: peak <value> at <time>`).
* Inline image tags (`<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`) pointing to the generated PNGs.
* The parameterized Grafana link.

**Subagent Workflow:**
1. Run the script: `python3 scripts/grafana_analyzer.py <config_yaml> <start_date> <end_date> <region>`
2. Append the script's stdout directly to your local HTML/Markdown output file.
3. Move on to the next region. Do not second-guess the math or write manual metric bullets.
