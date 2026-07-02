# XCC Data Sources — single source of truth for the XCC per-region analysis

This file lists EVERY metric the XCC section may analyse, and nothing else.
The section builder (`xcc-metrics.md`) must analyse ONLY what is registered here
— do not browse other dashboards or invent metrics.

## Global scope (applies to every entry)
- Role is always `role="edgerouter"` (kamailio-edgerouter).
- Region is injected as `region="$region"`.
- Default datasource is `prometheus`.
- Shared conventions (Grafana Link Format, Silence Rule, Deviation Policy,
  Datasource Conventions — including `$region` and `$__range` substitution):
  see `references/common-patterns.md`.

## Status convention

- `status: active` — PromQL confirmed from Grafana source. Fully automated.
- `status: reference` — Grafana link available; PromQL TBD. Link included in
  report as a panel shortcut; automated analysis not yet wired.

## Per-metric entry schema

```
### <Metric display name>
- grafana: <Grafana panel/dashboard link>
- description: <what the panel shows>
- status: active | reference
- datasource: prometheus | mimir | mimir-ap
- promql: <PromQL expression using $region and role="edgerouter">
- deviation: <rule>
- unit: <e.g. %, Mb/s, count, err/s>
```

---

## Metrics to analyse

### Error Rates (Spikes) — by instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolortpdd2psd?orgId=1
- description: 4xx, 5xx, 6xx error rate — by XCC instance
- status: active
- datasource: prometheus
- promql (4 series; use `region="$region"` and `role="edgerouter"`):
  - A — TOTAL per instance:
      `sum by (instance) (rate(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[5m]))
     + sum by (instance) (rate(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[5m]))
     + sum by (instance) (rate(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - B — 4xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - C — 5xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - D — 6xx only: `sum by (instance) (rate(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[5m]))`
- unit: SIP error replies / second
- deviation: per (instance, code) — SPIKE if max > mean + 3σ AND max ≥ 0.05 err/s
  (mean and σ computed over the full sprint window for each series individually).

> PERFORMANCE CONSTRAINT: on `prometheus` via Grafana MCP, use 3600 s step for
> the global chart; finer step only for zoom windows (60 s step times out).

> Fleet aggregate variant: same queries without `by (instance)` — use `sum(...)`.
> Grafana link: https://grafana-general.svc.talkdeskapp.com/goto/dfolt1g447fuoe?orgId=1

### Custom Metrics Rates (Spikes) — by instance
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffoloqq16x1j4f?orgId=1
- description: Inbound/Outbound Invite rate, RTP Engine failure rate, SIP Rec call rate — by XCC instance
- status: active
- datasource: prometheus
- promql (6 series — all use `region="$region"`, `role="edgerouter"`, `service=~".*"`):
  - B — Emergency invites: `sum by (instance) (rate(kamailio_kamailio_emergency_invites_total{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - D — Inbound invites: `sum by (instance) (rate(kamailio_kamailio_inbound_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - M — Outbound off-net: `sum by (instance) (rate(kamailio_kamailio_outbound_offnet_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - N — Outbound on-net: `sum by (instance) (rate(kamailio_kamailio_outbound_onnet_invites{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - O — RTPEngine failures: `sum by (instance) (rate(kamailio_rtpengine_connection_failure{region="$region",role="edgerouter",service=~".*"}[5m]))`
  - P — SIP Rec calls: `sum by (instance) (rate(kamailio_siprec_calls{region="$region",role="edgerouter",service=~".*"}[5m]))`
- deviation: mean ± 3σ per instance over sprint window; floor TBD per metric.
- unit: events / second per instance

> Fleet aggregate variant: same metrics without `by (instance)` — use `sum(...)`.
> Grafana link: https://grafana-general.svc.talkdeskapp.com/goto/cfolpibqv60owf?orgId=1

### Infra Details — version and instance type
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpkul5sx6of?orgId=1
- description: XCC version and instance type — by XCC instance
- status: active
- datasource: prometheus
- promql: `count by (region, version, instance_type) (custom_metrics{role="edgerouter"})`
  (scoped: `count by (region, version, instance_type) (custom_metrics{region="$region",role=~"edgerouter"})`)
- deviation: N/A — used for Host Details table only.

### Kamailio Alive
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolplog4lu68a?orgId=1
- description: XCC alive stats — by XCC instance (up/down status)
- status: active
- datasource: prometheus
- promql: `up{region="$region",role="edgerouter",service="kamailio",stack="cpaas"}`
  (returns 1 = up, 0 = down, missing series = unreachable)
- deviation: flag any gap (value = 0 or series absent) lasting > 5 min.
- unit: binary 0/1

### CPU Stats — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolpn2o21khsa?orgId=1
- description: XCC CPU stats — by XCC instance (user, system, iowait, guest)
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `service=~"edgerouter"`, `cpu="cpu-total"`):
  - A — User: `cpu_usage_user{region="$region",service=~"edgerouter",cpu="cpu-total"}`
  - B — System: `cpu_usage_system{region="$region",role=~"edgerouter",cpu="cpu-total"}`
  - C — IOWait: `cpu_usage_iowait{region="$region",role=~"edgerouter",cpu="cpu-total"}`
  - D — Guest: `cpu_usage_guest{region="$region",role=~"edgerouter",cpu="cpu-total"}`
- deviation: sprint median; flag sustained A+B > 80 % or median + 2×IQR.
- unit: % CPU

### System Load — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolpnqqut43kf?orgId=1
- description: XCC system load (1 m, 5 m, 15 m) and CPU count — by XCC instance
- status: active
- datasource: prometheus
- promql (4 series; all scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — 1-min load: `system_load1{region="$region",role=~"edgerouter"}`
  - B — 5-min load: `system_load5{region="$region",role=~"edgerouter"}`
  - C — 15-min load: `system_load15{region="$region",role=~"edgerouter"}`
  - D — CPU count: `system_n_cpus{region="$region",role=~"edgerouter"}`
- deviation: sprint median + 2×IQR for each load average (normalize by CPU count).
- unit: load average (dimensionless)

### CPU Usage per Process — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolpogr88uf4a?orgId=1
- description: CPU usage per process (top-18) — by XCC instance
- status: active
- datasource: prometheus
- promql: `topk(18, sum(procstat_cpu_usage{region="$region",role=~"edgerouter"}) by (process_name,instance))`
- deviation: no alerting defined; flag top consumers when CPU is elevated.
- unit: % CPU per process

### Memory Usage per Process — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolppd52cs8we?orgId=1
- description: Memory usage per process (top-18, RSS) — by XCC instance
- status: active
- datasource: prometheus
- promql: `topk(18, sum(procstat_memory_rss{region="$region",role=~"edgerouter"}) by (process_name,instance))`
- deviation: no alerting defined; flag clear stepwise increases.
- unit: bytes (RSS)

### Memory Usage — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolpq2u5tlogc?orgId=1
- description: Memory breakdown (total, used, cached+buffered, free, swap used) — by XCC instance
- status: active
- datasource: prometheus
- promql (5 series; all scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — Total: `mem_total{region="$region",role=~"edgerouter"}`
  - B — Used: `mem_used{region="$region",role=~"edgerouter"}`
  - C — Cached+Buffered: `mem_cached{region="$region",role=~"edgerouter"} + mem_buffered{region="$region",role=~"edgerouter"}`
  - D — Free: `mem_free{region="$region",role=~"edgerouter"}`
  - E — Swap used: `mem_swap_total{region="$region",role=~"edgerouter"} - mem_swap_free{region="$region",role=~"edgerouter"}`
- deviation: sprint median; flag when mem_used / mem_total > 80 % or median + 2×IQR.
- unit: bytes

### Network I/O — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpqob1el8gb?orgId=1
- description: Network I/O in bits/s (receive and transmit) — by XCC instance
- status: active
- datasource: prometheus
- promql (2 series; both scoped to `region="$region"`, `role=~"edgerouter"`):
  - A — RX: `irate(net_bytes_recv{region="$region",role=~"edgerouter"}[5m]) * 8`
  - B — TX: `irate(net_bytes_sent{region="$region",role=~"edgerouter"}[5m]) * 8`
- deviation: sprint median + 2×IQR for each direction.
- unit: bits/s

### Number of File Handles — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolprd4tknb4f?orgId=1
- description: Number of open file handles (system-wide) — by XCC instance
- status: active
- datasource: prometheus
- promql: `linux_sysctl_fs_file_nr{region="$region",role=~"edgerouter"}`
  (use the allocated series for deviation)
- deviation: sprint median + 2×IQR; alert if approaching system max.
- unit: count

### Disk Usage — Kamailio
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpryt5s4qod?orgId=1
- description: Disk usage percentage — by XCC instance
- status: active
- datasource: prometheus
- promql: `disk_used_percent{region="$region",role=~"edgerouter"}`
- deviation: flag when any mount exceeds 80 % used.
- unit: %

### TCP Connection Counters
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolpwcjkj1tse?orgId=1
- description: TCP connection counters by type — by XCC instance
- status: active
- datasource: prometheus
- promql: `rate(kamailio_tcp_total{region="$region",role=~"edgerouter",type=~"(con_reset|con_timeout|connect_failed|connect_success|established|local_reject|passive_open|send_timeout|sendq_full)"}[5m]) * 1000`
- deviation: sprint median + 2×IQR per type; flag `connect_failed`, `con_reset`, `con_timeout` especially.
- unit: connections / s × 1000

### Core SHMem Max Used
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolpwymc5f5se?orgId=1
- description: Kamailio core shared memory (max_used and total) — by XCC instance
- status: active
- datasource: prometheus
- promql: `kamailio_shm_bytes{region="$region",role=~"edgerouter",type=~"(max_used|total)"}`
- deviation: flag when max_used / total > 80 % or sustained increase trend.
- unit: bytes

### RTPEngine Connection Failures
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolpxknkh7gge?orgId=1
- description: RTPEngine connection failures (from Kamailio's perspective) — by XCC instance
- status: active
- datasource: prometheus
- promql: `rate(kamailio_rtpengine_connection_failure{region="$region",role=~"edgerouter"}[5m]) * 1000`
- deviation: flag any sustained non-zero failure rate (mean ± 3σ; floor = 0.001).
- unit: failures/s × 1000

> NOTE: `$__range` in the following SIP Codes and Requests sections is a Grafana
> range variable. When executing via MCP, replace with `[N]s` (sprint duration in
> seconds). The result is the total count over the sprint, not a rate.

### Total 4xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq167odukgf?orgId=1
- description: Total 4xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_4xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: compare sprint total vs. baseline mean ± 2σ (baseline = 5 prior sprints).
- unit: count (total over sprint)

### 4xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolq22e3aneob?orgId=1
- description: 4xx breakdown by specific code (400–493) and SIP method
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_4xx_{method}` for by-method, `kamailio_core_rcv_replies_{NNN}` for by-code):
  - `sum(increase(kamailio_core_rcv_replies_4xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_4xx_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_400{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_486{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag individual codes/methods whose sprint total exceeds baseline mean + 2σ.
- unit: count per code/method (total over sprint)

### Total 5xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolq2od92arkc?orgId=1
- description: Total 5xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_5xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline mean ± 2σ (prior sprints).
- unit: count (total over sprint)

### 5xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq3iprnj7kc?orgId=1
- description: 5xx breakdown by SIP method (bye, cancel, invite, message, prack, refer, reg, update)
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_5xx_{method}`):
  - `sum(increase(kamailio_core_rcv_replies_5xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - `sum(increase(kamailio_core_rcv_replies_5xx_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: cancel, message, prack, refer, reg, update)
- deviation: flag methods whose sprint total exceeds baseline mean + 2σ.
- unit: count per method (total over sprint)

### Total 6xx — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq4bagu5moc?orgId=1
- description: Total 6xx replies over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_replies_6xx{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline mean ± 2σ.
- unit: count (total over sprint)

### 6xx Detailed — by error code and method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolq4z7oegowd?orgId=1
- description: 6xx breakdown by SIP method
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_replies_6xx_{method}`):
  - `sum(increase(kamailio_core_rcv_replies_6xx_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: bye, cancel, message, prack, refer, reg, update)
- deviation: flag methods whose sprint total exceeds baseline mean + 2σ.
- unit: count per method (total over sprint)

### Total Requests — global
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolq5kf4d98gb?orgId=1
- description: Total SIP requests over the sprint window — all XCC instances aggregated
- status: active
- datasource: prometheus
- promql: `sum(increase(kamailio_core_rcv_requests{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: baseline median ± 2×IQR (median is more robust for daily-patterned data).
- unit: count (total over sprint)

### Requests by Method
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq6451xrswa?orgId=1
- description: SIP requests broken down by method (ACK, BYE, CANCEL, INFO, INVITE, MESSAGE, NOTIFY, OPTIONS, PRACK, PUBLISH, REFER, REGISTER, SUBSCRIBE, UPDATE)
- status: active
- datasource: prometheus
- promql (pattern: `kamailio_core_rcv_requests_{method}`):
  - INVITE: `sum(increase(kamailio_core_rcv_requests_invite{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - BYE: `sum(increase(kamailio_core_rcv_requests_bye{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - (same pattern for: ack, cancel, info, message, notify, options, prack, publish, refer, register, subscribe, update)
- deviation: per-method baseline median ± 2×IQR.
- unit: count per method (total over sprint)

### Failover Metrics — combined overview
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolq6x2h6cxsa?orgId=1
- description: All failover counters combined (backup_used, counter_expired, failure_tracked, force, proactive, quarantine_activated)
- status: active
- datasource: prometheus
- promql (6 series, all `sum(increase(...[$__range]))`):
  - A — Backup used: `sum(increase(kamailio_failover_backup_used{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - B — Counter expired: `sum(increase(kamailio_failover_counter_expired{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - C — Failure tracked: `sum(increase(kamailio_failover_failure_tracked{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - D — Force: `sum(increase(kamailio_failover_force{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - E — Proactive: `sum(increase(kamailio_failover_proactive{region="$region",role="edgerouter",service=~".*"}[$__range]))`
  - F — Quarantine activated: `sum(increase(kamailio_failover_quarantine_activated{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence during sprint (failover activity is always significant).
- unit: count over sprint

### Backup Used — by X-Header (customer)
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/ffolq7pb0a7eoc?orgId=1
- description: Backup path usage — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_backup_used{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any non-zero xheader entry.
- unit: count over sprint per customer

### Counter Expired — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolq90hjb75sf?orgId=1
- description: Failover counter expiry events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_counter_expired{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag increases vs. baseline sprint.
- unit: count over sprint per customer

### Failure Tracked — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/dfolqanied4w0f?orgId=1
- description: Failures being tracked by the failover system — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_failure_tracked{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: mean ± 3σ; flag sustained elevation.
- unit: count over sprint per customer

### Force Failover — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqctb9iepsf?orgId=1
- description: Forced failover events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_force{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence.
- unit: count over sprint per customer

### Proactive Failover — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqdp04mw3kc?orgId=1
- description: Proactive failover events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_proactive{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any non-zero count.
- unit: count over sprint per customer

### Quarantine Activated — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/bfolqed5vcpogb?orgId=1
- description: Quarantine activation events — per customer X-Header
- status: active
- datasource: prometheus
- promql: `sum by (xheader) (increase(kamailio_failover_quarantine_activated{region="$region",role="edgerouter",service=~".*"}[$__range]))`
- deviation: flag any occurrence.
- unit: count over sprint per customer

### Top 5 High MOS — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/efolqf233b5kwf?orgId=1
- description: Top 5 customers / X-Headers with highest MOS scores (p50 over sprint)
- status: active
- datasource: prometheus
- promql: `topk(5, avg by (xheader) (quantile_over_time(0.5, (kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"}[$__range]))))`
- deviation: informational; flag only if top MOS values drop below 3.5.
- unit: MOS (1–5 scale)

### Top 5 Low MOS — by X-Header
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/afolqfsxbls00b?orgId=1
- description: Top 5 customers / X-Headers with lowest MOS scores (p50 over sprint)
- status: active
- datasource: prometheus
- promql: `bottomk(5, avg by (xheader) (quantile_over_time(0.5, (kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"}[$__range]))))`
- deviation: flag when lowest MOS < 3.0 or the number of low-MOS xheaders increases vs. baseline.
- unit: MOS (1–5 scale)

### MOS Metrics Over Time
- grafana: https://grafana-general.svc.talkdeskapp.com/goto/cfolqgjev9slca?orgId=1
- description: MOS trend over time — fleet median for MOS avg/min/max and jitter/packetloss/rtt/samples
- status: active
- datasource: prometheus
- promql (fleet-level p50 using `quantile(0.5,...)`; multiple series):
  - A — MOS avg: `quantile(0.5, kamailio_mos_avg{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"} > 0)`
  - B — MOS avg jitter: `quantile(0.5, kamailio_mos_avg_jitter{region="$region",role="edgerouter",service=~".*",account_id=~".*",xheader=~".*"} > 0)`
  - C — MOS avg packetloss: `quantile(0.5, kamailio_mos_avg_packetloss{...} > 0)`
  - D — MOS avg RTT: `quantile(0.5, kamailio_mos_avg_rtt{...} > 0)`
  - E — MOS avg samples: `quantile(0.5, kamailio_mos_avg_samples{...} > 0)`
  - F — MOS max: `quantile(0.5, kamailio_mos_max{...} > 0)`
  - G — MOS max jitter: `quantile(0.5, kamailio_mos_max_jitter{...} > 0)`
  - H — MOS max packetloss: `quantile(0.5, kamailio_mos_max_packetloss{...} > 0)`
  - I — MOS max RTT: `quantile(0.5, kamailio_mos_max_rtt{...} > 0)`
  - J — MOS min: `quantile(0.5, kamailio_mos_min{...} > 0)`
  - K — MOS min jitter: `quantile(0.5, kamailio_mos_min_jitter{...} > 0)`
  - L — MOS min packetloss: `quantile(0.5, kamailio_mos_min_packetloss{...} > 0)`
  - M — MOS min RTT: `quantile(0.5, kamailio_mos_min_rtt{...} > 0)`
- deviation: flag when fleet p50 MOS avg drops below 3.5 or decreases > 0.3 vs. baseline.
- unit: MOS (1–5 scale)
