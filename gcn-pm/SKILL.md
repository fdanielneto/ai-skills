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

This file is the ORCHESTRATOR. It defines the page skeleton, section order,
shared anchors (regions, URLs, publish target), and delegates the structure of
each section to one reference file.

> SCOPE — DATA COLLECTION IS MANDATORY (NOT structure-only)
> This skill must produce a page filled with REAL collected data. For every
> section that has a wired data source, you MUST actually query it and render
> the result. Placeholders are allowed ONLY for customer PII (CALL_IDs, account
> names, phone numbers, IPs) or when a required tool is genuinely unavailable.
> Any `[TODO: run analysis ...]` text in the published page is a BUG.
> See `references/common-patterns.md` — No-TODO Rule.

## ACTIVATION

This skill is manual. Only proceed when the user explicitly invokes it
(`/gcn-pm ...`) or explicitly asks to build the GCN production meeting page.

## TOKEN EFFICIENCY POLICY (mandatory)

1. Dispatch one subagent task per requested section token.
2. Per subagent, include only: sprint dates, optional region filter, the one
   matching section reference file, plus `references/common-patterns.md` when
   relevant and `references/output-schema.md` when relevant.
3. Load `references/publish.md` only at the publish step — not before.
4. Load `references/sbc-collection-prompts.md` only when Playwright is confirmed
   available and collection is about to begin.

## HELP MODE

If the user runs `/gcn-pm help` (the single token `help` with no dates):
return the contents of `references/help-card.md` verbatim (as a code block).
Do NOT build or publish a page.

## ARGUMENTS

```
/gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
```

- `sprint-start`, `sprint-end` (required): the sprint window (ISO dates). Fill
  the header table Date/Timeframe; do NOT affect the page title (FIXED).
- `section ...` (optional): one or more SECTION TOKENS. When present, run in
  **partial / block mode** and render ONLY those sections; when absent, render
  the FULL page (all 7 sections).
- `region ...` (optional): one or more REGION TOKENS. Only meaningful for
  `xcc-metrics` / `rtpengine-metrics`. When present, analyse only the specified
  region(s); when absent, analyse all regions.

Parsing rule: after the two dates, classify each remaining token in order:
1. Matches a known **section token** → add to section list.
2. Matches a known **region token** → add to region filter.
3. Matches neither → stop and ask the user to clarify.

If invoked without dates (and not `help`), ask once:
```
Please provide the sprint window:
  /gcn-pm <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
```

## REGION TOKENS

Case-insensitive; `-` and `_` are interchangeable.

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

When a region filter is active:
- **Host Details table**: always built from the full instant PromQL query.
- **Per-region analysis**: ONLY the filtered region(s) are queried and rendered.
  Other regions: one-line entry `<p><em>Not analysed in this run (region filter active).</em></p>`.

Unknown region → list the valid region tokens and ask.

## SECTION TOKENS

Case-insensitive; `-` and `_` are interchangeable.

| Canonical token      | Reference file                     | Aliases                                  |
|----------------------|------------------------------------|------------------------------------------|
| `status-review`      | `references/status-review.md`      | status_review, status                    |
| `on-call-alarms`     | `references/on-call-alarms.md`     | on_call_alarms, on-call, oncall, alarms  |
| `post-mortem`        | `references/post-mortem.md`        | post_mortem, postmortem                  |
| `xcc-metrics`        | `references/xcc-metrics.md`        | xcc_metrics, xcc, kamailio               |
| `rtpengine-metrics`  | `references/rtpengine-metrics.md`  | rtpengine_metrics, rtpengine, rtp        |
| `sbc-metrics`        | `references/sbc-metrics.md`        | sbc_metrics, sbc, calls                  |
| `events-tracking`    | `references/events-tracking.md`    | events_tracking, events                  |
| `all`                | (all of the above)                 | full, page                               |

Unknown token → list the valid tokens and ask.

## RUN MODES

Every run — full OR block — produces a page containing ONLY the section(s) of
THAT run. The page is wiped and rebuilt from scratch on each run.

**Full run** (no section tokens): header table + TOC + all 7 sections in canonical order.

**Block / partial run** (e.g. `/gcn-pm 2026-06-01 2026-06-02 status-review`):
header table + TOC + ONLY the requested section(s) in canonical order.
A later block run replaces the page completely — prior sections are gone.

Publish algorithm (load `references/publish.md` at this step):
1. Build the full body for THIS run (header + TOC + this run's sections only).
2. Locate the fixed-title page under Notes.
3. REPLACE its ENTIRE body (or CREATE if absent) via REST + storage.
4. Header Date/Timeframe always reflect THIS run's sprint window.

## SECTION → REFERENCE MAP

Read the matching reference file before authoring each section.

| # | Page section                          | Reference file                       | Requested name    |
|---|---------------------------------------|--------------------------------------|-------------------|
| 0 | Header table + Table of Contents      | (this file — see STEP 0 below)       | —                 |
| 1 | Status Review                         | `references/status-review.md`        | Status_Review     |
| 2 | On-Call Alarms                        | `references/on-call-alarms.md`       | On-Call_Alarms    |
| 3 | Post-Mortem (last 90 days)            | `references/post-mortem.md`          | Post-Mortem       |
| 4 | XCC Metrics (Kamailio)                | `references/xcc-metrics.md`          | XCC_Metrics       |
| 5 | RTP Engine Metrics                    | `references/rtpengine-metrics.md`    | RTPEngine_Metrics |
| 6 | Executive Summary + Detailed data     | `references/sbc-metrics.md`          | SBC_Metrics       |
| 7 | Events Tracking                       | `references/events-tracking.md`      | Events_Tracking   |

Design decisions (confirmed with requester):
- XCC_Metrics and RTPEngine_Metrics are TWO SEPARATE sections.
- Call records ("Detailed data by Region") live inside SBC_Metrics.

## STEP 0 — HEADER TABLE + TABLE OF CONTENTS (owned here)

At the very top of the page body, emit:

1. A 2-row header table:

   | Date      | <meeting date — the day after sprint end>     |
   | Timeframe | <sprint start> to <sprint end>                |

   Date format: e.g. "May 21st", "May 07th to May 20th".

2. A Table of Contents: the Confluence **Índice / Table of Contents** macro,
   collapsed by default (expand macro wrapping the TOC is acceptable). Omit if
   the authoring format cannot express the macro.

Then emit the section(s) selected by this run, in canonical order.

## REGIONS & RIBBON GROUPINGS (shared anchors)

Per-region order used by XCC §4 and RTP Engine §5:
```
EU-South-1      → eu-south-1
EU-West-3       → eu-west-3
US-East-1       → us-east-1
US-West-2       → us-west-2
AP1 - Singapore → ap-southeast-1
AP2 - Sydney    → ap-southeast-2
SA-East-1       → sa-east-1
CA-Central-1    → ca-central-1
```

Ribbon groupings used by SBC_Metrics §6:
```
Ribbon EU    → EU-South-1, EU-West-3
Ribbon US    → US-East-1, US-West-2
Ribbon APAC  → AP1 - Singapore, AP2 - Sydney
Ribbon LATAM → LATAM-AZ1 (São Paulo), LATAM-AZ2 (São Paulo)
```

## PUBLISH TARGET (mandatory)

See `references/publish.md` for the full canonical publish algorithm.

- Space: `~622745edb7e7c7007159b8df`, numeric `spaceId` = `3406136357`.
- Parent page: **Notes**, `pageId` = `3541107151`.
- `cloudId`: `talkdesk.atlassian.net`.
- Title (FIXED): `GCN PM Auto Test`.
- Page id: `6568476792`.

Publish only via REST + `representation: "storage"`. See
`references/common-patterns.md` — Storage-Only Publish Rule.

## FINAL OUTPUT

After publishing, report back:
- ✅ Page rebuilt (state: full run or block run)
- 🧩 Which section(s) this run rendered — note that all other sections were cleared
- 📊 Which metrics/regions deviated and got a chart + table this run
- 📄 The page URL
- ⚠️ Any section that fell back to a warning panel (never report `[TODO]` as a
  normal outcome; if a wired data source produced no data, say why)
