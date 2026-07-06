# Common Patterns for Metric Sections

Use this file for shared rules across `xcc-metrics.md`,
`rtpengine-metrics.md`, `xcc-datasources.md`, and
`rtpengine-datasources.md`.

## Grafana Link Format

Per-region Grafana links must be parameterized from the datasource `goto` URL:

```
<base_goto_url>&var-region=<region>&from=<sprint_start_epoch_ms>&to=<sprint_end_epoch_ms>
```

- Convert dates to UTC epoch milliseconds (`YYYY-MM-DDT00:00:00Z`).
- Link text must include metric + region.

## Finding Bullet Format

When a metric deviates:

1. Emit one line: `Reference = N.NN <unit>`.
2. Emit one bullet per deviating instance:
   `* <instance>: <metric> peak <value> <unit> at <YYYY-MM-DDTHH:MMZ>`
3. Never include in bullets:
   - AZ / instance-type annotations
   - Threshold internals (`mean+3sigma`, `median+2xIQR`, percentage deltas)
   - Summaries for non-deviating instances
   - Editorial commentary or inferred causes

## Silence Rule (Global)

- Publish only deviating metrics.
- Within deviating metrics, publish only deviating instances.
- If a region has zero deviations, emit only the region dashboard link.

## Deviation Policy (Global)

- RATE metrics: `Median + 3*MAD` with metric floor when defined. Never use `Mean + 3sigma`.
- RESOURCE metrics: Percentile thresholds (e.g. `P95 > 80%`). Never use `Median + 2xIQR`.
- STATE metrics: Alive gap > 5 mins, or Stepwise session increases (leaks).

## Datasource Conventions

- Replace `$region` at runtime with target region.
- Replace `$__range` with sprint duration in seconds when running via MCP.
- Keep selection dynamic; do not hardcode instance lists.

## Fallback Rule

If a required tool is unavailable, emit the documented warning panel and keep
real links. Never emit fabricated values or TODO placeholders.

## No-TODO Rule (canonical — reference from other files)

Never emit `[TODO]` or `[TODO: ...]`-style placeholder text anywhere in the
published page. If a required tool is genuinely unavailable, emit the documented
warning panel for that section and the dashboard link. As soon as the tool IS
available, collect the data. Any `[TODO: run analysis …]` text in the published
page is a BUG.

## Image Alignment Rule (canonical — reference from other files)

All `<ac:image>` tags MUST carry `ac:align="center" ac:width="950"`.
Omitting `ac:align="center"` causes left-alignment in Confluence.
For On-Call Alarms screenshots use `ac:width="760"` (matches content area width).

## Storage-Only Publish Rule (canonical — reference from other files)

Always publish via the Confluence REST API with `representation: "storage"`.
Never use the Atlassian MCP tools `updateConfluencePage` / `createConfluencePage`
— those tools cannot emit storage format and silently degrade the page
(blockCards → plain text, macros → bullet lists). See `references/publish.md`
for the full canonical publish path.
# Output Schema (Subagent Contract)

Use this contract to emit section content only. Do not emit orchestration,
publishing, rationale, or repeated rule text.

## section_xcc_metrics

Required order:
1. `H1: XCC Metrics`
2. Expand: `XCC - Host Details`
  - one table with columns: `XCC | Version | Instance Type`
  - optional short note paragraphs after the table for detected changes
3. One collapsed region block per discovered region
  - first line: region Grafana link
  - then only deviating metric groups
  - each deviating metric group:
    - short bold heading
    - `Reference = N.NN <unit>`
    - bullet list in common finding format
    - embedded chart image(s)

Forbidden:
- "within normal range" text
- TODO placeholders
- invented values
- editorial/causal commentary

## section_rtpengine_metrics

Required order:
1. `H1: RTP Engine Metrics`
2. One collapsed region block per configured region/order
  - first line: region Grafana link
  - then only deviating metric groups
  - each deviating metric group:
    - short bold heading
    - `Reference = N.NN <unit>`
    - bullet list in common finding format
    - embedded chart image(s)

Forbidden:
- "within normal range" text
- TODO placeholders
- invented values
- editorial/causal commentary

## Shared constraints

- Follow `references/common-patterns.md` for links, silence rule, and bullets.
- Emit only final section body content.
- Keep wording short and factual.