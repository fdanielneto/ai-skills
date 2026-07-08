#!/usr/bin/env python3
import json
import os
import sys
import yaml
import subprocess
from datetime import datetime

# Helper functions to simulate Talkdesk's grafana-mcp-prd execution
def run_grafana_mcp(promql, start_time, end_time, step):
    """
    In the real environment, this invokes the MCP tool or an internal API.
    Since we are in a script, it would use an HTTP client or subprocess to call the CLI.
    For the sake of the skill definition, we define the structure.
    """
    # Mock data structure matching Prometheus API
    return {
        "status": "success",
        "data": {
            "resultType": "matrix",
            "result": []
        }
    }

def calculate_mad(values):
    if not values:
        return 0, 0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = sorted_vals[n//2] if n % 2 != 0 else (sorted_vals[n//2 - 1] + sorted_vals[n//2]) / 2.0
    
    deviations = [abs(x - median) for x in values]
    sorted_devs = sorted(deviations)
    mad = sorted_devs[n//2] if n % 2 != 0 else (sorted_devs[n//2 - 1] + sorted_devs[n//2]) / 2.0
    
    return median, mad

def analyze_metric(metric_name, config, start_epoch, end_epoch, region):
    deviated_instances = []
    chart_data = {"lines": [], "threshold": None}
    
    # 1. Fetch High-Res Data
    # Iterating over queries if it's a multiple series metric, or single promql
    queries = config.get('queries', {})
    if 'promql' in config:
        queries['Series'] = config['promql']
        
    for label, query in queries.items():
        if not query: continue
        
        # Replace template vars
        if region:
            query = query.replace('"$region"', f'"{region}"')
            
        # step=300 (5 minutes) for high resolution
        res = run_grafana_mcp(query, start_epoch, end_epoch, 300)
        
        for series in res.get('data', {}).get('result', []):
            instance = series.get('metric', {}).get('instance', 'unknown')
            values = [float(v[1]) for v in series.get('values', [])]
            if not values: continue
            
            peak_val = max(values)
            floor = config.get('floor')
            deviated = False
            
            # Floor Bypass
            if floor and str(floor).replace('.', '', 1).isdigit():
                if peak_val >= float(floor):
                    deviated = True
            
            # Fallback statistical
            if not deviated:
                median, mad = calculate_mad(values)
                if peak_val > (median + 3 * mad):
                    deviated = True
                    
            if deviated:
                deviated_instances.append({
                    "instance": instance,
                    "peak": peak_val,
                    "label": label
                })
                # Add to chart data
                # ... formatting logic for plot_helper.py
                
    if not deviated_instances:
        return None

    # 2. Chart Generation
    safe_name = metric_name.replace(" ", "_").replace("/", "_").lower()
    chart_filename = f"chart_{region}_{safe_name}.png"
    chart_path = os.path.join("output", chart_filename)
    
    # In a real run, we would call plot_helper.py via subprocess here
    # subprocess.run(["python3", "scripts/plot_helper.py", metric_name, chart_path, "Time", config.get('unit', ''), json.dumps(chart_data)])

    # 3. Format Confluence Output
    output = f"#### {metric_name}\n\n"
    output += f"[Grafana Dashboard]({config.get('grafana')})\n\n"
    output += f"Reference = {config.get('floor', 'N/A')} {config.get('unit', '')}\n\n"
    
    for d in deviated_instances:
        output += f"* {d['instance']}: peak {d['peak']:.2f} {config.get('unit', '')}\n"
        
    output += f"\n<ac:image ac:align=\"center\" ac:width=\"950\"><ri:attachment ri:filename=\"{chart_filename}\"/></ac:image>\n\n"
    
    return output


def main():
    if len(sys.argv) < 4:
        print("Usage: grafana_analyzer.py <config_yaml> <start_epoch> <end_epoch> [region]")
        sys.exit(1)
        
    config_file = sys.argv[1]
    start_epoch = int(sys.argv[2])
    end_epoch = int(sys.argv[3])
    region = sys.argv[4] if len(sys.argv) > 4 else None
    
    # Ensure output dir exists
    os.makedirs("output", exist_ok=True)
    
    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)
        
    final_markdown = ""
    for metric_name, cfg in config.items():
        if cfg.get('status') == 'active':
            result_md = analyze_metric(metric_name, cfg, start_epoch, end_epoch, region)
            if result_md:
                final_markdown += result_md
                
    if not final_markdown.strip():
        final_markdown = "No deviation detected ✅"
        
    print(final_markdown)

if __name__ == "__main__":
    main()
