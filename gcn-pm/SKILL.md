---
name: gcn-pm
description: >
  Builds the GCN Production Meeting Confluence page (Status Review, On-Call
  Alarms, Post-Mortem, XCC Metrics, RTP Engine Metrics, Executive Summary +
  Calls, Events Tracking) and publishes it under the Notes page in Fábio Neto's
  personal Confluence space. MANUAL-ONLY skill: use this ONLY when the user explicitly
  runs the `/gcn-pm` command, or explicitly asks to "generate / build the GCN
  production meeting page". Do NOT trigger proactively, and do NOT trigger for
  general questions about Confluence, Grafana, Kibana, SIP, call metrics, or
  production meetings — only on the explicit invocation above.
  Usage: /gcn-pm SPRINT-START SPRINT-END [section...] [region...] (dates as YYYY-MM-DD).
  Omit section/region for the full page. Run /gcn-pm help to list all available
  section tokens, region tokens, and examples without building any page.
  Examples:
    /gcn-pm 2026-06-01 2026-06-02 xcc-metrics              (XCC, all regions)
    /gcn-pm 2026-06-01 2026-06-02 xcc-metrics eu-south-1   (XCC, one region only)
    /gcn-pm help                                            (show reference card)
---

# GCN Production Meeting — Page Builder (Orchestrator)

This skill assembles a single Confluence page that mirrors the existing
UCInterconnect "Production Meeting" pages, and publishes it into Fábio Neto's
personal space.

This file is a pure bash dispatcher — no subagents, no reference files. Each
section's data collection, HTML rendering, and fallback behavior lives
entirely in its `scripts/generate_*.py`. The whole run — wiping `tmp/`,
running the requested generators in order, fail-fasting on the first
failure, and publishing once — is driven by a single entry point,
`scripts/run.py`; this file only decides what to pass it and how to react
to its exit code.

## ACTIVATION

This skill is manual. Only proceed when the user explicitly invokes it
(`/gcn-pm ...`) or explicitly asks to build the GCN production meeting page.

## HELP MODE

If the user runs `/gcn-pm help` (the single token `help` with no dates):
return the following block verbatim (as a code block). Do NOT add
commentary. Do NOT build or publish a page.

```
GCN Production Meeting builder — available runs

Usage:
  /gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
  /gcn-pm help

Section tokens (partial / block runs):
  on-call            → Meeting Ops (Status Review, Alarms, Post-Mortem, Events)
  xcc-metrics        → XCC Metrics (Kamailio)
  rtpengine-metrics  → RTP Engine Metrics
  sbc-metrics        → Executive Summary + Detailed data by Region (SBC/calls)
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
  /gcn-pm 2026-06-01 2026-06-14 on-call xcc-metrics        two sections only
  /gcn-pm help                                             show this message
```

## ARGUMENTS

```
/gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
```

- `sprint-start`, `sprint-end` (required): the sprint window (ISO dates).
- `section ...` (optional): one or more SECTION TOKENS below. Present →
  **block mode**, render only those sections. Absent → full page (all 4
  generators + Events Tracking).
- `region ...` (optional): one or more REGION TOKENS below. Only meaningful
  for `xcc-metrics` / `rtpengine-metrics`. Present → analyse only those
  region(s), others render as "Not analysed in this run (region filter
  active)". Absent → all regions.

Parsing rule: after the two dates, classify each remaining token in order —
(1) known section token, (2) known region token, (3) neither → stop and ask
the user to clarify. If invoked without dates (and not `help`), ask once for
the usage line above.

## SECTION TOKENS

Case-insensitive; `-`/`_` interchangeable.

| Canonical token      | Generator                          | Aliases                            |
|-----------------------|-------------------------------------|-------------------------------------|
| `on-call`             | `scripts/generate_oncall.py`        | on_call, ops                       |
| `xcc-metrics`         | `scripts/generate_xcc.py`           | xcc_metrics, xcc, kamailio         |
| `rtpengine-metrics`   | `scripts/generate_rtpengine.py`     | rtpengine_metrics, rtpengine, rtp  |
| `sbc-metrics`         | `scripts/generate_sbc.py`           | sbc_metrics, sbc, calls            |
| `all`                 | (all of the above)                  | full, page                         |

`on-call` also writes `tmp/section_events_tracking.html` (Events Tracking
has no reference file/tokens of its own — it rides with On-Call).

Unknown token → list the valid tokens and ask.

## REGION TOKENS

Case-insensitive; `-`/`_` interchangeable. Canonical list + ribbon groupings
live in `scripts/regions.py` (shared by `generate_xcc.py`,
`generate_rtpengine.py`, `generate_sbc.py`) — do not duplicate it here.

| Token            | Ribbon  |
|------------------|---------|
| `eu-south-1`     | EU      |
| `eu-west-3`      | EU      |
| `us-east-1`      | US      |
| `us-west-2`      | US      |
| `ap-southeast-1` | APAC    |
| `ap-southeast-2` | APAC    |
| `sa-east-1`      | LATAM   |
| `ca-central-1`   | (other) |

Unknown region → list the valid region tokens and ask.

## RUN

Every run — full or block — produces a page containing ONLY the section(s)
of THAT run; the page is wiped and rebuilt from scratch each time. Canonical
section order: On-Call → XCC Metrics → RTP Engine Metrics → SBC Metrics →
Events Tracking.

1. **Run the single orchestrator**, forwarding exactly the section/region
   tokens the user gave (or none, for a full run):
   ```
   python3 gcn-pm/scripts/run.py <start> <end> [section ...] [region ...]
   ```
   `run.py` does the entire run by itself, with no further input needed:
   wipes `gcn-pm/tmp/` and writes a run marker; runs each requested
   generator in order, fail-fasting immediately (before running the rest or
   publishing) on the first non-zero exit; then calls
   `confluence_publish.py` exactly once. `confluence_publish.py` itself
   refuses to publish — regardless of what `run.py` thought happened — if
   any XCC/RTP Engine section is missing a region block versus
   `scripts/regions.py` (stale/truncated file) or if any section file
   predates this run's marker (stale leftover from an earlier run). It
   cleans `gcn-pm/tmp/` on success and leaves it in place on any failure,
   for debugging. Never touches `gcn-pm/.auth/` (session cookies +
   Playwright profile) — that's a sibling directory, not under `tmp/`.

   A generator's own *documented fallback* (e.g. `generate_oncall.py`
   rendering the On-Call Alarms warning panel when Playwright can't
   complete) is a successful exit 0 inside `run.py` — not a failure.

2. **If `run.py` exits non-zero:** read the reported stderr.
   - If the cause is one you can recognize and fix without guessing (e.g.
     the Grafana/Kibana session needs a manual re-login that `run.py`'s own
     one internal auth-retry couldn't resolve, or an obviously transient
     network error) — apply that one fix and re-run `run.py`
     **exactly one more time**.
   - If it fails again, or the cause isn't recognizable/fixable, **stop and
     report the exact error to the user** as the FINAL OUTPUT. Never guess
     further, never retry more than that one time, never publish a partial
     page.

3. **If `run.py` exits 0:** fetch the just-published page
   (`getConfluencePage`, page id `6568476792`) and, for whichever of the
   XCC Metrics / RTP Engine Metrics sections this run rendered, count the
   region block titles against the 8 tokens in `scripts/regions.py`. This
   is a second, independent sanity check on top of `confluence_publish.py`'s
   own guardrail — it should always agree; report it (and any discrepancy)
   in the FINAL OUTPUT.

4. **Never call `generate_*.py` or `confluence_publish.py` individually for
   a real `/gcn-pm` run** — `run.py` is the only entry point. (Running an
   individual generator, or `confluence_publish.py --no-publish`, by hand
   for standalone testing outside of a real `/gcn-pm` invocation is fine.)

5. **Run at most one cycle of step 1, plus the single retry in step 2, per
   `/gcn-pm` invocation.** If the user wants another attempt after that,
   they invoke `/gcn-pm` again.

## PUBLISH TARGET (mandatory)

- Space: `~622745edb7e7c7007159b8df`, numeric `spaceId` = `3406136357`.
- Parent page: **Notes**, `pageId` = `3541107151`.
- `cloudId`: `talkdesk.atlassian.net`.
- Title: `Production Meeting Sprint <YYYYMMDD>-<YYYYMMDD>` (derived from the
  sprint start/end args each run).
- Page id: `6568476792`.
- Publish only via REST + `representation: "storage"` — never Atlassian MCP
  tools for publishing.

## FINAL OUTPUT

After publishing, report back:
- ✅ Page rebuilt (state: full run or block run)
- 🧩 Which section(s) this run rendered — note that all other sections were cleared
- 📊 Which metrics/regions deviated and got a chart + table this run
- 🔎 Region completeness check (step 3 of RUN): N/8 region blocks confirmed
  per region-aware section rendered this run
- 📄 The page URL (printed by `run.py`/`confluence_publish.py` on success)
