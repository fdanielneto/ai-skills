# Metric Analysis Engine

This file defines the unified algorithm and Python script structure for fetching, detecting deviations, and charting metrics. Both `xcc-metrics.md` and `rtpengine-metrics.md` rely on this engine to avoid redundancy.

## 1. Metric Classification
Every metric in the datasources files falls into one of three categories, which determines how deviation is calculated:

* **RATE metrics** (e.g., Error Rates, Invites, Failures): Bursty by nature.
  * **Deviation Rule:** Use `Median + 3 × MAD` (Median Absolute Deviation) or a predefined fixed threshold (e.g., > 0.05 err/s). Do not use `Mean + 3σ` as large spikes skew the mean and standard deviation.
* **RESOURCE metrics** (e.g., CPU, Memory, Disk, Load): Generally stable or cyclic.
  * **Deviation Rule:** Use percentile thresholds (e.g., `P95 > threshold` or `P99 > threshold`) or fixed values (e.g., `> 80%`). Do not use `Median + 2 × IQR` as stable resources have tiny IQRs, causing false positives.
* **STATE / COUNT metrics** (e.g., Alive, Session Counts): 
  * **Deviation Rule:** For Alive, flag any gap (value = 0 or missing series) > 5 mins. For Sessions, use `P95` or a stepwise change detection (leak detection).

## 2. Python Script Template (Batch Processing)
To maximize efficiency, generate a SINGLE Python script per region that parses the JSON payloads (fetched via `grafana-mcp-prd:query_prometheus` and saved to `/tmp/`), processes all active metrics in batch, calculates deviations, and generates the charts.

```python
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import datetime, io, sys

def calculate_mad(data):
    median = np.median(data)
    mad = np.median(np.abs(data - median))
    # Add a tiny epsilon to avoid zero MAD for completely flat lines
    return median, mad if mad > 0 else 0.001

def process_metric(metric_name, json_path, metric_type, unit, region, sprint_start, sprint_end, floor_val=0.0):
    with open(json_path, 'r') as f:
        payload = json.load(f)
    
    # Ensure there is data
    if 'data' not in payload or not payload['data']['result']:
        return None
        
    all_values = []
    series_data = {}
    
    for result in payload['data']['result']:
        # Extract instance name or other identifier
        metric_labels = result['metric']
        instance = metric_labels.get('instance', metric_labels.get('xheader', 'aggregate'))
        values = result['values']
        
        y_vals = [float(v[1]) for v in values]
        x_vals = [datetime.datetime.utcfromtimestamp(v[0]) for v in values]
        all_values.extend(y_vals)
        series_data[instance] = (x_vals, y_vals)
    
    if not all_values: return None
        
    deviations = []
    threshold = 0
    
    # Dynamic Deviation Logic
    if metric_type == "RATE":
        median, mad = calculate_mad(all_values)
        threshold = median + (3 * mad)
        threshold = max(threshold, floor_val)
        for inst, (xs, ys) in series_data.items():
            if max(ys) > threshold:
                deviations.append(inst)
                
    elif metric_type == "RESOURCE":
        threshold = np.percentile(all_values, 95)
        # For percentages, we might use a fixed 80% threshold instead if specified
        if unit == "%" and floor_val > 0:
            threshold = max(threshold, floor_val)
        for inst, (xs, ys) in series_data.items():
            if max(ys) > threshold:
                deviations.append(inst)
                
    elif metric_type == "STATE":
        # Custom logic for alive gaps or session counts
        threshold = np.percentile(all_values, 95)
        deviations = list(series_data.keys()) # Simplified, replace with specific check
    
    if not deviations:
        return None # Silence Rule: Do not chart if no deviation
        
    # Generate Chart
    fig, ax = plt.subplots(figsize=(11, 4))
    
    for inst in deviations:
        xs, ys = series_data[inst]
        ax.plot(xs, ys, linestyle="-", linewidth=1.2, label=inst)
        
    # Plot dotted line for the ACTUAL THRESHOLD that was breached
    ax.axhline(threshold, color="red", linestyle=":", linewidth=1.2, label=f"Threshold = {threshold:.2f} {unit}")
    
    ax.set_title(f"{metric_name} — {region} · {sprint_start}–{sprint_end}", fontsize=9)
    ax.set_ylabel(unit)
    ax.set_xlabel("UTC time")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H"))
    ax.legend(fontsize=7, ncol=4)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    
    chart_slug = metric_name.lower().replace(' ', '-')
    chart_path = f"/tmp/{region}-{chart_slug}-overview.png"
    fig.savefig(chart_path, format="png", dpi=150)
    plt.close(fig)
    return chart_path
```

## 3. Zoom Window Logic (Simplified)
For any metric event that requires a zoom chart (e.g., error attribution):
* Find the absolute peak timestamp across all instances for that event.
* The zoom window is fixed: `[peak_timestamp - 30 minutes, peak_timestamp + 30 minutes]`.

## 4. Reporting the Findings
For each metric that deviated and produced a chart:
* Print the reference scalar (the threshold breached): `Threshold breached = N.NN {unit}`.
* Create a minimal bullet point per instance: `* <instance>: <metric> peak <value> <unit> at <YYYY-MM-DDTHH:MMZ>`.
* Embed the chart using `ac:image` + `ri:attachment` (NO caption).
* Include the parameterized Grafana link.
