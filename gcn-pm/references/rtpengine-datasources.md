# RTPEngine Data Sources — single source of truth for the RTPEngine per-region analysis

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
- deviation: sprint median; flag sustained A+B > 80 % or median + 2×IQR.
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
- deviation: sprint median + 2×IQR for each load average.
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
- deviation: sprint median; flag when mem_used / mem_total > 80 % or median + 2×IQR.
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
- deviation: sprint median + 2×IQR for each direction.
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
- deviation: flag when used / total > 80 % or sprint median + 2×IQR.
- unit: count (ports)

### Media Sessions — by region
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolpyyq6pam8b?orgId=1
- description: RTPEngine active media sessions (type=own) — aggregated by region and service
- purpose: detect session count anomalies — sudden drops (call drops) or stuck sessions (leaks)
- status: active
- datasource: prometheus
- promql: `sum(rtpengine_sessions{type="own",region="$region",instance=~"rtpengine-edge.*",service=~".*"}) by (region,service)`
- deviation: sprint median + 2×IQR; also flag sustained zero (full outage) or monotonic increase without matching decrease (session leak).
- unit: count (sessions)

### Media Sessions by Instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpzjae43cwb?orgId=1
- description: RTPEngine active media sessions (type=own) — per RTPEngine instance
- purpose: detect per-instance imbalances or individual instance anomalies
- status: active
- datasource: prometheus
- promql: `rtpengine_sessions{type="own",region="$region",instance=~"rtpengine-edge.*",service=~".*"}`
- deviation: per-instance sprint median + 2×IQR; flag if one instance diverges significantly from peers.
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
