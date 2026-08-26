---
name: gcn-pm-verify
description: >
  Runs the /gcn-pm orchestrator (run.py), waits for the Confluence publish to
  finish, then validates the *published* page — every requested section's
  heading present, no unrequested section's heading present, and all 8
  regions (scripts/regions.py) present for any XCC Metrics / RTP Engine
  Metrics section rendered. All of this happens inside a single Python
  script; the page body is never read by the model. MANUAL-ONLY skill: use
  this ONLY when the user explicitly runs the `/gcn-pm-verify` command, or
  explicitly asks to "run gcn-pm and validate/verify the page". Do NOT
  trigger proactively, and do NOT trigger for general /gcn-pm requests that
  don't ask for validation — those stay with /gcn-pm.
  Usage: /gcn-pm-verify SPRINT-START SPRINT-END [section...] [region...]
  (dates as YYYY-MM-DD, same section/region tokens as /gcn-pm — see
  /gcn-pm help for the full token reference).
  Examples:
    /gcn-pm-verify 2026-06-01 2026-06-14                     (full page, all regions)
    /gcn-pm-verify 2026-06-01 2026-06-14 xcc-metrics          (XCC only, all regions)
---

# GCN Production Meeting — Run + Verify (Orchestrator, no page-body reads)

This skill wraps `/gcn-pm`: it runs the exact same `gcn-pm/scripts/run.py`
orchestrator, waits for it to finish (synchronous — no polling needed), then
validates the page Confluence actually stored. All of the running, waiting,
fetching, and checking is done by `scripts/verify_publish.py`. This file is a
pure bash dispatcher — do not call any Confluence/Atlassian tool yourself, do
not fetch or read the page, and do not summarize its content. Relay only the
single `RESULT: ...` line the script prints.

This skill never modifies anything under `gcn-pm/` and never publishes via
Atlassian MCP tools (same REST-only rule as `/gcn-pm`) — it only reuses
`gcn-pm/scripts/run.py` and `gcn-pm/scripts/confluence_publish.py` as
read-only imports/subprocess calls.

## ACTIVATION

Manual only. Only proceed when the user explicitly invokes
`/gcn-pm-verify ...` or explicitly asks to run `/gcn-pm` **and** validate the
result.

## HELP MODE

If invoked as `/gcn-pm-verify help` (or with no arguments): return the
following verbatim, run nothing:

```
gcn-pm-verify — run /gcn-pm and validate the published page

Usage:
  /gcn-pm-verify <sprint-start YYYY-MM-DD> <sprint-end YYYY-MM-DD> [section ...] [region ...]
  /gcn-pm-verify help

Same section/region tokens as /gcn-pm — run /gcn-pm help for the full list.
Omit section tokens for the full page (all 4 sections); region tokens are
only meaningful for xcc-metrics / rtpengine-metrics.

Examples:
  /gcn-pm-verify 2026-06-01 2026-06-14                    full page, all regions
  /gcn-pm-verify 2026-06-01 2026-06-14 xcc-metrics        XCC only, all regions
  /gcn-pm-verify help                                      show this message
```

## RUN

1. Run:
   ```
   python3 gcn-pm-verify/scripts/verify_publish.py <sprint-start> <sprint-end> [section ...] [region ...]
   ```
   forwarding exactly the tokens the user gave. This single script call runs
   `run.py`, blocks until the publish finishes, fetches the live page once,
   and validates it — nothing else needs to run.

2. **Never retry automatically.** The script itself runs `run.py` at most
   once and does no retries. If the result is `FAIL`, stop and report it as
   the FINAL OUTPUT; if the user wants another attempt, they invoke
   `/gcn-pm-verify` (or `/gcn-pm`) again.

3. **Never call `getConfluencePage` or any other Atlassian/MCP tool, and
   never read `tmp/page_full.html` or any section HTML file.** The script's
   final stdout line is the only thing you read.

## FINAL OUTPUT

Report back exactly what the script's final `RESULT:` line says, nothing
more:

- `RESULT: PASS page=<id> url=<url> sections=<a,b,c> regions=N/M` →
  ✅ page published and validated; show the URL and which sections/region
  count it confirmed.
- `RESULT: FAIL stage=run ...` → `run.py`/the generators or publish failed;
  show `exit`/`stderr_tail` verbatim.
- `RESULT: FAIL stage=parse ...` or `stage=parse-args` → could not determine
  the published page id, or an unknown section/region token was given; show
  the reason verbatim.
- `RESULT: FAIL stage=auth ...` or `stage=fetch ...` → could not read the
  page back from Confluence after publish; show the reason verbatim.
- `RESULT: FAIL stage=validate ...` → page published, but
  `missing_sections` / `unexpected_sections` / `missing_regions` were
  non-empty; show those fields verbatim plus the page URL (the page exists
  and is reachable — it's just not the shape this run expected).
