#!/usr/bin/env python3
import sys
import json
import matplotlib.pyplot as plt
from datetime import datetime

# render_chart(...) is called directly (in-process) by grafana_metrics.py and
# kibana_metrics.py. The __main__ block below is kept only for standalone
# debugging: plot_helper.py <title> <output_png_path> <x_label> <y_label> '<json_data>'
# json_data format: { "lines": [ { "label": "Instance 1", "points": [ {"x": "2026-06-15", "y": 123}, ... ] } ], "threshold": {"label": "Threshold", "value": 500} }


def render_chart(title, output_path, x_label, y_label, data):
    plt.figure(figsize=(10, 4))

    for line in data.get('lines', []):
        x_vals = []
        y_vals = []
        for pt in line.get('points', []):
            x_str = pt['x']
            # try parsing as yyyy-MM-dd or yyyy-MM-dd HH:mm
            try:
                if ' ' in x_str:
                    x_val = datetime.strptime(x_str, '%Y-%m-%d %H:%M')
                else:
                    x_val = datetime.strptime(x_str, '%Y-%m-%d')
            except ValueError:
                x_val = x_str  # fallback to string
            x_vals.append(x_val)
            y_vals.append(pt['y'])
        plt.plot(x_vals, y_vals, linestyle='-', label=line.get('label'))

    threshold = data.get('threshold')
    if threshold:
        plt.axhline(y=threshold['value'], color='r', linestyle='--', label=threshold.get('label', 'Threshold'))

    plt.title(title)
    plt.xlabel(x_label)
    plt.ylabel(y_label)

    # Auto-format dates on x-axis
    plt.gcf().autofmt_xdate()

    if len(data.get('lines', [])) > 0 or threshold:
        plt.legend()

    plt.grid(True, linestyle='--', alpha=0.7)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()


def main():
    title = sys.argv[1]
    output_path = sys.argv[2]
    x_label = sys.argv[3]
    y_label = sys.argv[4]
    data = json.loads(sys.argv[5])
    render_chart(title, output_path, x_label, y_label, data)


if __name__ == "__main__":
    main()
