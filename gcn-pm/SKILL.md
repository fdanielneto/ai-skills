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
> See `references/on-call.md` — No-TODO Rule.
>
> This rule governs what a subagent writes into its section, not how many
> times the orchestrator runs. A documented fallback (e.g. an info/warning
> panel + plain link when a tool is genuinely unavailable) is a SUCCESSFUL
> outcome, not a bug — it must be rendered once and reported, never used as
> a reason to re-dispatch. See "Run exactly once" below.

## ACTIVATION

This skill is manual. Only proceed when the user explicitly invokes it
(`/gcn-pm ...`) or explicitly asks to build the GCN production meeting page.

## ORCHESTRATION ARCHITECTURE

1. **Parallel Extraction**: The orchestrator launches subagents for each requested section in parallel. 
2. **Local Storage**: Each subagent must collect its data, generate the final Confluence Storage HTML for its section, and save it to a local temporary file (e.g., `output/section_oncall.html`, `output/section_xcc.html`, etc.).
3. **No Direct Publishing by Extractors**: The section subagents DO NOT publish to Confluence. Their job ends when the local HTML file is written.
4. **Publisher Assembly**: Once all section subagents complete (successfully or with a documented fallback), the orchestrator launches a final **Publisher** subagent. The Publisher reads `references/publish.md`, reads the local HTML files, assembles the complete page body (Header + TOC + Sections), and performs the final REST PUT to Confluence via `scripts/confluence_publish.py`.

### Run exactly once (mandatory — this is what prevents the infinite-loop bug)

Each `/gcn-pm` invocation runs the extraction → publish pipeline **exactly
once**. Once the Publisher subagent returns — success OR failure — the
orchestrator writes the FINAL OUTPUT report and STOPS. Never re-dispatch
section subagents and never re-attempt the publish within the same
invocation, even if:
- a data source was genuinely unavailable (render the documented fallback
  once and move on — see the SCOPE note above),
- the post-publish verification gate in `references/publish.md` failed
  (report the exact failure text to the user instead of re-PUTting).

If the user wants another attempt, they will invoke `/gcn-pm` again.

## TOKEN EFFICIENCY POLICY (mandatory)

1. Dispatch one subagent task per requested section token.
2. DO NOT inject file contents into the subagent prompt. Instead, provide only the sprint dates, region filter, and the relative path to the section's reference file, instructing the subagent to save its HTML output locally. Instruct the subagent to use the `read` tool on-demand to load its specific reference file.
3. Load `references/publish.md` only for the final Publisher subagent — not before.
4. For `sbc-metrics` data collection, you MUST act as a mini-orchestrator, dispatching isolated subagents to execute the Playwright fetch queries and format the results as Native Confluence Chart XML macros.



## TOKEN EFFICIENCY & SCRIPT OFF-LOADING

To minimize token usage and improve deterministic accuracy, this skill heavily relies on python scripts:

1. **`scripts/grafana_analyzer.py`**: Executes Grafana PromQL queries, calculates P95/MAD/IQR, and determines deviations automatically based on rules defined in `config/xcc_metrics.yaml` and `config/rtp_metrics.yaml`. The subagent ONLY receives the summary output (e.g. "Deviations found: Alive dropped below 1").
2. **`scripts/sbc_analyzer.py`**: Replaces `kb-proxy.js`. Filters, aggregates and computes percentages from Kibana Elasticsearch payloads. Returns pre-formatted Markdown tables, eliminating the need for the LLM to parse thousands of lines of logs.
3. **`scripts/confluence_publish.py`**: Publishes the assembled Confluence Storage HTML — reads current page version, PUTs the full body with `representation: "storage"`, and runs the post-publish verification gate. Called once, by the Publisher subagent only. See `references/publish.md`.

DO NOT parse raw Kibana or Grafana JSONs directly in the LLM. ALWAYS route the data through these scripts.

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
| `on-call`            | `references/on-call.md`            | on_call, ops                             |
| `xcc-metrics`        | `references/xcc-metrics.md`        | xcc_metrics, xcc, kamailio               |
| `rtpengine-metrics`  | `references/rtpengine-metrics.md`  | rtpengine_metrics, rtpengine, rtp        |
| `sbc-metrics`        | `references/sbc-metrics.md`        | sbc_metrics, sbc, calls                  |
| `all`                | (all of the above)                 | full, page                               |

Unknown token → list the valid tokens and ask.

## RUN MODES

Every run — full OR block — produces a page containing ONLY the section(s) of
THAT run. The page is wiped and rebuilt from scratch on each run.

**Full run** (no section tokens): header table + TOC + all sections in canonical order.
Canonical order is: On-Call -> XCC Metrics -> RTP Engine Metrics -> SBC Metrics -> Events Tracking.

**Block / partial run** (e.g. `/gcn-pm 2026-06-01 2026-06-02 on-call`):
header table + TOC + ONLY the requested section(s) in canonical order.
A later block run replaces the page completely — prior sections are gone.

Publish algorithm (load `references/publish.md` at this step):
1. Wait for all dispatched subagents to finish and write their local HTML files.
2. Launch the Publisher subagent to read the local files and assemble the full body for THIS run.
3. The Publisher replaces the ENTIRE body (or CREATEs if absent) of the fixed-title page via REST + storage.
4. Header Date/Timeframe always reflect THIS run's sprint window.

## SECTION → REFERENCE MAP

Read the matching reference file before authoring each section. 

| # | Page section                          | Reference file                       | Requested name    |
|---|---------------------------------------|--------------------------------------|-------------------|
| 0 | Header table + Table of Contents      | (this file — see STEP 0 below)       | —                 |
| 1 | Meeting Ops (Status, Alarms, Post-Mortem)         | `references/on-call.md`  | On-Call           |
| 2 | XCC Metrics (Kamailio)                | `references/xcc-metrics.md`          | XCC_Metrics       |
| 3 | RTP Engine Metrics                    | `references/rtpengine-metrics.md`    | RTPEngine_Metrics |
| 4 | Executive Summary + Detailed data     | `references/sbc-metrics.md`          | SBC_Metrics       |

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
`references/publish.md` — Storage-Only Publish Rule.

## FINAL OUTPUT

After publishing, report back:
- ✅ Page rebuilt (state: full run or block run)
- 🧩 Which section(s) this run rendered — note that all other sections were cleared
- 📊 Which metrics/regions deviated and got a chart + table this run
- 📄 The page URL
