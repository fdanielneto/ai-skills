# GCN PM Help Card

Return the following code block verbatim when `/gcn-pm help` is invoked. Do not add commentary.

```
GCN Production Meeting builder — available runs

Usage:
  /gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
  /gcn-pm help

Section tokens (partial / block runs):
  status-review      → Status Review
  on-call-alarms     → On-Call Alarms
  post-mortem        → Post-Mortem (last 90 days)
  xcc-metrics        → XCC Metrics (Kamailio)
  rtpengine-metrics  → RTP Engine Metrics
  sbc-metrics        → Executive Summary + Detailed data by Region (SBC/calls)
  events-tracking    → Events Tracking
  all                → Full page (all sections — same as omitting section tokens)

Region tokens (filter for xcc-metrics / rtpengine-metrics):
  eu-south-1        ap-southeast-1
  eu-west-3         ap-southeast-2
  us-east-1         sa-east-1
  us-west-2         ca-central-1

  Omit region tokens to analyse all regions.
  Tokens are case-insensitive; - and _ are interchangeable.

Examples:
  /gcn-pm 2026-06-01 2026-06-14                           full page, all regions
  /gcn-pm 2026-06-01 2026-06-14 xcc-metrics               XCC only, all regions
  /gcn-pm 2026-06-01 2026-06-14 xcc-metrics eu-south-1    XCC, EU-South-1 only
  /gcn-pm 2026-06-01 2026-06-14 status-review post-mortem  two sections only
  /gcn-pm help                                             show this message
```
