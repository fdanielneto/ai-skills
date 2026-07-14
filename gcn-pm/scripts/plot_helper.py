#!/usr/bin/env python3
import sys
import json
import statistics
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from datetime import datetime

# render_chart(...) is called directly (in-process) by grafana_metrics.py and
# kibana_metrics.py. The __main__ block below is kept only for standalone
# debugging: plot_helper.py <title> <output_png_path> <x_label> <y_label> '<json_data>'
# json_data format: { "lines": [ { "label": "Instance 1", "points": [ {"x": "2026-06-15", "y": 123}, ... ] } ], "threshold": {"label": "Threshold", "value": 500} }

_DEFAULT_BAR_WIDTH_DAYS = 1.0 / 24  # 1 hour, used when there's < 2 points to space bars from

# Categorical palette + chart chrome from the dataviz skill's validated reference
# instance (references/palette.md, light mode — these charts are always rendered
# as static PNGs on a white Confluence page, never dark mode). Slot order is the
# CVD-safety mechanism (max-min adjacent ΔE), so keep it as-is when indexing.
PALETTE = ['#2a78d6', '#1baf7a', '#eda100', '#008300',
           '#4a3aa7', '#e34948', '#e87ba4', '#eb6834']
_THRESHOLD_COLOR = '#d03b3b'  # status "critical" red — deliberately distinct from PALETTE[5]
_SURFACE = '#fcfcfb'
_PRIMARY_INK = '#0b0b0b'
_SECONDARY_INK = '#52514e'
_MUTED_INK = '#898781'
_GRIDLINE = '#e1e0d9'
_AXIS_LINE = '#c3c2b7'

CHART_STYLE = {
    'font.family': 'sans-serif',
    'font.sans-serif': ['Segoe UI', 'Helvetica Neue', 'Arial', 'DejaVu Sans'],
    'axes.prop_cycle': plt.cycler(color=PALETTE),
    'axes.facecolor': _SURFACE,
    'figure.facecolor': _SURFACE,
    'axes.edgecolor': _AXIS_LINE,
    'axes.titlecolor': _PRIMARY_INK,
    'axes.titleweight': 'bold',
    'axes.titlesize': 13,
    'axes.labelcolor': _SECONDARY_INK,
    'axes.labelsize': 10,
    'xtick.color': _MUTED_INK,
    'ytick.color': _MUTED_INK,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'grid.color': _GRIDLINE,
    'grid.linewidth': 0.8,
    'legend.frameon': False,
    'legend.labelcolor': _SECONDARY_INK,
}


def render_chart(title, output_path, x_label, y_label, data, render_cfg=None):
    with plt.style.context(CHART_STYLE):
        _render_chart(title, output_path, x_label, y_label, data, render_cfg)


def _render_chart(title, output_path, x_label, y_label, data, render_cfg=None):
    render_cfg = render_cfg or {}
    draw_style = render_cfg.get('draw_style', 'line')
    lines = data.get('lines', [])

    parsed_lines = []
    for line in lines:
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
        parsed_lines.append((line.get('label'), x_vals, y_vals))

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    if draw_style in ('bars', 'points'):
        _render_bars(ax, parsed_lines)
    elif render_cfg.get('style') == 'state':
        _render_state(ax, parsed_lines)
    else:
        for label, x_vals, y_vals in parsed_lines:
            ax.plot(x_vals, y_vals, linestyle='-', label=label)

    threshold = data.get('threshold')
    if threshold:
        ax.axhline(y=threshold['value'], color=_THRESHOLD_COLOR, linestyle='--',
                    label=threshold.get('label', 'Threshold'))

    scale = render_cfg.get('scale')
    if scale == 'log':
        ax.set_yscale('log')
    y_min, y_max = render_cfg.get('min'), render_cfg.get('max')
    if y_min is not None or y_max is not None:
        ax.set_ylim(bottom=y_min, top=y_max)

    ax.set_title(title)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)

    # Auto-format dates on x-axis
    fig.autofmt_xdate()

    if len(lines) > 0 or threshold:
        ax.legend(loc='upper left', bbox_to_anchor=(1.02, 1), borderaxespad=0, fontsize='small')

    ax.grid(True)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close(fig)


_STATE_OFFSET = 0.01  # per-instance vertical spacing so overlapping up-lines stay perceptible


def _render_state(ax, parsed_lines):
    """Per-instance up/down (1=up, 0=down) step chart.

    Each series gets a distinct color and a tiny downward vertical offset
    (0.01 per series) so instances that are all up (flat at y=1) don't collapse
    into a single line — they read as a small stack just below 1, while still
    clearly being value=1. Rendered as steps so 1->0 / 0->1 transitions are sharp.
    """
    for i, (label, x_vals, y_vals) in enumerate(parsed_lines):
        offset = i * _STATE_OFFSET
        y_shifted = [y - offset for y in y_vals]
        ax.plot(x_vals, y_shifted, drawstyle='steps-post', linewidth=1.5,
                color=PALETTE[i % len(PALETTE)], label=label)


def _render_bars(ax, parsed_lines):
    """Grouped bar chart across parsed_lines = [(label, x_vals[datetime], y_vals), ...].

    x_vals are converted to matplotlib date numbers so bar width/offset can be
    computed numerically; ax.xaxis_date() restores date tick labels afterwards.
    """
    n = len(parsed_lines) or 1
    all_nums = sorted({mdates.date2num(x) for _label, x_vals, _y in parsed_lines
                        for x in x_vals if isinstance(x, datetime)})
    if len(all_nums) > 1:
        diffs = [b - a for a, b in zip(all_nums, all_nums[1:]) if b > a]
        base_width = statistics.median(diffs) * 0.8 if diffs else _DEFAULT_BAR_WIDTH_DAYS
    else:
        base_width = _DEFAULT_BAR_WIDTH_DAYS

    bar_width = base_width / n
    for i, (label, x_vals, y_vals) in enumerate(parsed_lines):
        x_nums = [mdates.date2num(x) if isinstance(x, datetime) else x for x in x_vals]
        offset = (i - (n - 1) / 2.0) * bar_width
        ax.bar([x + offset for x in x_nums], y_vals, width=bar_width, label=label)
    ax.xaxis_date()


def main():
    title = sys.argv[1]
    output_path = sys.argv[2]
    x_label = sys.argv[3]
    y_label = sys.argv[4]
    data = json.loads(sys.argv[5])
    render_cfg = json.loads(sys.argv[6]) if len(sys.argv) > 6 else None
    render_chart(title, output_path, x_label, y_label, data, render_cfg)


if __name__ == "__main__":
    main()
