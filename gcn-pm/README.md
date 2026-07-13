# GCN Production Meeting — Metrics Pipeline

## YAML Config Reference

### Metric entry fields

```yaml
Kamailio Alive:
  status: active            # active | inactive — skip metric if inactive
  datasource: prometheus    # datasource type (only prometheus today)
  deviation: STATE          # STATE | RATE | RESOURCE — detection strategy
  data_view: list           # chart | chart_not_zoom | list | table — output format
  panel_id: 22              # Grafana panel id (for unit extraction + live queries)
  expr: up{...}             # PromQL expression (overrides panel's live expression)
  floor_value: 1            # expected normal value
  floor_op: <               # < | > | <= | >= — breach condition
  description: "..."        # human-readable label
```

### `deviation` modes

| Mode | Detection | Use case |
|------|-----------|----------|
| `STATE` | `floor_value` + `floor_op` only | Binary up/down metrics |
| `RATE` | Median + 3×MAD spike detection | Call rates, error rates |
| `RESOURCE` | P95 > `deviation_threshold` (default 80) | CPU, memory, SHMEM |

### `data_view` modes

| Value | Chart overview | Chart zoom | Output format |
|-------|:--------------:|:----------:|---------------|
| `chart` (default) | ✅ | ✅ | `<ul>` + chart + zoom |
| `chart_not_zoom` | ✅ | ❌ | `<ul>` + chart, no zoom |
| `list` | ❌ | ❌ | `<ul>` only |
| `table` | ❌ | ❌ | `<table>` (Instance / Value / Timestamp) |

### Fields by priority

| Field | Purpose | When needed |
|-------|---------|-------------|
| `expr` | PromQL query | Always, unless you want to pull from Grafana panel live |
| `panel_id` | Grafana panel for unit + live query fallback | Needed for unit extraction; optional if `expr` is set |
| `dashboard` | Override `defaults.dashboard` per metric | Only if a metric lives in a different dashboard |

If `expr` is omitted, the tool fetches the PromQL expression live from the Grafana panel specified by `panel_id` + `defaults.dashboard`.

### Dashboard link

The top-level Grafana link in the HTML output is built from:

```yaml
defaults:
  dashboard: xconnect_dashboard_v3  # uid, used for all metrics unless overridden
```

Plus the first active metric's `panel_id`.

## Detection logic

### STATE (binary)

```
min(values) < floor_value  (when floor_op is '<' or '<=')
max(values) > floor_value  (when floor_op is '>' or '>=')
```

The `peak` reported is:
- `min(points)` when `floor_op` is `<` / `<=` (captures the actual zero/violation)
- `max(points)` when `floor_op` is `>` / `>=`

### RATE (spike)

```
max(values) > median(values) + 3 * MAD(values)
```

### RESOURCE (high utilization)

```
P95(values) > deviation_threshold
```

## CLI usage

```bash
# Refresh Grafana session cookie (one-time or when expired)
python3 scripts/grafana_metrics.py refresh

# Analyze one region
python3 scripts/grafana_metrics.py analyze config/xcc_metrics.yaml \
  <start_epoch_ms> <end_epoch_ms> eu-south-1

# Analyze all regions (generates Confluence HTML section)
python3 scripts/generate_xcc.py 2026-06-29 2026-07-12
python3 scripts/generate_rtpengine.py 2026-06-29 2026-07-12
```

Epoch milliseconds converter:

```python
from datetime import datetime, timezone
start = int(datetime(2026, 6, 29, tzinfo=timezone.utc).timestamp() * 1000)
end = int(datetime(2026, 7, 12, 23, 59, 59, tzinfo=timezone.utc).timestamp() * 1000)
```
