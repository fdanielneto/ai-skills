# SBC_Metrics — Executive Summary + Detailed data by Region (Calls)

This reference owns two consecutive parts of the page. The per-region **call
records** live here (not in a separate Calls reference) because the call data
comes from the SBC CDR logs.

Order on the page: **(A) Executive Summary → (B) Detailed data by Region**.
All region/Ribbon dropdowns are collapsed-by-default expand macros.

---

## DATA COLLECTION

### Source — single Kibana CDR dashboard via Playwright MCP

Call records live in `kibana-logging.svc.talkdeskapp.com`. CDR data collection
uses **Playwright** to navigate **one single dashboard** for the WHOLE section.

#### `SBC_DASHBOARD_URL` (the only URL used by this section)

```
https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/97c532ef-3354-4392-a153-141a02816e90?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:'<START_SPRINT_DATE>T00:00:00.000Z',to:'<END_SPRINT_DATE>T23:59:59.000Z'))
```

- `<START_SPRINT_DATE>` / `<END_SPRINT_DATE>` = the sprint window (ISO `YYYY-MM-DD`).
- All panels read by this section live on THIS dashboard:
  `Total Call Attempts (all)`, `Total Media Anchoring Calls (all)`,
  `Call Disconnect Reason (all)`, `Call Disconnect Reason - Table (all)`,
  `Call Attempts`.

#### Shared panel-interaction pattern (MANDATORY — fast, single page load)

Load the dashboard **once per pass**, then operate panel-by-panel without
reloading. For each panel: apply KQL → click **Update** → wait on
`textGone="Search session loading"` → maximize → capture → minimize → clear
KQL bar. Never reload between panels.

> DEFAULT FILTER NOTE (verified live): the dashboard already ships with a saved
> filter pill `NOT Record Type.keyword: START`. So A-1 and A-3 (which only need
> that default) usually require NO extra KQL — confirm the pill is present and
> read the panels directly. Only type `NOT Record Type.keyword : "START"` in the
> KQL bar if the pill is missing. A-2 and §B/§B-1 still type their own KQL on top.

### Region → SBC → Kibana filter map

Each sub-region corresponds to exactly **one SBC**. Filter in §B and §B-1 by
**`Gateway Name.keyword`** (the SBC name), NOT by `region.keyword` — because
both LATAM SBCs share `sa-east-1`.

| Region             | Ribbon  | SBC name (`Gateway Name.keyword`) | `region.keyword` (ref) |
|--------------------|---------|-----------------------------------|------------------------|
| EU-South-1         | EU      | `PRDEUS1RSBC`      | `eu-south-1`            |
| EU-West-3          | EU      | `PRDEUW3RSBC`      | `eu-west-3`             |
| US-East-1          | US      | `prduse1rsbc`      | `us-east-1`             |
| US-West-2          | US      | `prdusw2rsbc`      | `us-west-2`             |
| AP1 - Singapore    | APAC    | `PRDAPS1RSBC`      | `ap-southeast-1`        |
| AP2 - Sydney       | APAC    | `PRDAPS2RSBC`      | `ap-southeast-2`        |
| LATAM-AZ1 (São Paulo) | LATAM | `PRDSAE1RSBC1`   | `sa-east-1`             |
| LATAM-AZ2 (São Paulo) | LATAM | `PRDSAE1RSBC2`   | `sa-east-1`             |

### Collection rules

1. **If the Playwright MCP is available:**

   Load `references/sbc-collection-prompts.md` and follow the collection prompts
   defined there (A-1, A-2, A-3, B-1, and per-SBC template), in that order.
   Reuse the same loaded dashboard page for every panel — never reload between panels.

   **Screenshot integrity check (MANDATORY after all 7/8 region screenshots):**
   Compute the MD5/SHA-256 hash of each file and assert every file has a distinct
   hash. If two files share a hash, the KQL filter was not applied — discard and
   re-run those regions. See `references/sbc-collection-prompts.md` for the full
   check command.

2. **If the Playwright MCP is NOT available:** emit, per block, the dashboard
   link (`SBC_DASHBOARD_URL`) plus a `warning` panel:
   *"Live CDR data requires Kibana access via browser (Playwright). Playwright is
   unavailable in this environment."*
   Never `[TODO]` text. (See `references/common-patterns.md` — No-TODO Rule.)

> PII rule: never fabricate CALL_IDs, account names, phone numbers or IPs.
> Keep raw identifiers redacted; use the dashboards as the source of truth.

---

## A. Executive Summary

A single heading (H1) that is itself a link to the Kibana overview dashboard
(`SBC_DASHBOARD_URL`, with the sprint dates substituted):

**[Executive Summary](SBC_DASHBOARD_URL)**

Immediately after the heading-link, emit **exactly one** plain sentence:

```
Total: <N> completed calls.
```

- `<N>` = total STOP-record call count for the sprint (collected from Kibana).
- Use comma-separated thousands (e.g. `2,365,167`).

Then emit the following three content blocks **in this exact order**:
`A-1 table → A-2 chart → A-3 table`. Each block is preceded by its own **H3 heading**.

---

### A-1. Total Call Attempts & Media Anchoring

Emit a visible **H3 heading**: `Total Call Attempts & Media Anchoring`

> Collection prompt: see `references/sbc-collection-prompts.md` § A-1.

Render the resulting two-row table in storage format on the page.

---

### A-2. Call Disconnect Reason (all regions)

Emit a visible **H3 heading**: `Call Disconnect Reason (all regions)`

> Collection prompt: see `references/sbc-collection-prompts.md` § A-2.

Upload the resulting PNG as a page attachment and embed:
```xml
<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="sbc-call-disconnect-reason-without-16.png"/>
</ac:image>
```

---

### A-3. Call Disconnect Reason (all regions) — Top 10

> Collection prompt: see `references/sbc-collection-prompts.md` § A-3.

Render the resulting table in storage format on the page.

---

## B. Detailed data by Region

1. Heading (H1): **Detailed data by Region**

2. Grouped by Ribbon (H2), in order: **Ribbon EU, Ribbon US, Ribbon APAC,
   Ribbon LATAM**. Region membership:
   - Ribbon EU   → EU-South-1, EU-West-3
   - Ribbon US   → US-East-1, US-West-2
   - Ribbon APAC → AP1 - Singapore, AP2 - Sydney
   - Ribbon LATAM→ LATAM-AZ1 (São Paulo), LATAM-AZ2 (São Paulo)

### B-1. Disconnect Codes by Region (4 mini-tables, 2+2 layout)

Rendered **once** at the top of §B, before any per-region dropdown.

Four mini-tables in two rows of two via `<ac:layout>` with `two_equal` sections
— EU and US side-by-side in the first row, APAC and LATAM side-by-side in the
second row.

Layout structure (storage format):
```xml
<ac:layout>
  <ac:layout-section ac:type="two_equal">
    <ac:layout-cell><!-- EU mini-table --></ac:layout-cell>
    <ac:layout-cell><!-- US mini-table --></ac:layout-cell>
  </ac:layout-section>
  <ac:layout-section ac:type="two_equal">
    <ac:layout-cell><!-- APAC mini-table --></ac:layout-cell>
    <ac:layout-cell><!-- LATAM mini-table --></ac:layout-cell>
  </ac:layout-section>
</ac:layout>
```

Each mini-table structure:
```
| <Ribbon Name>               |                    |   ← colspan=2 header row
|-----------------------------|--------------------| 
| Total calls (STOP)          | <count>            |
| <Reason Name> (<code>)      | <count> (<pct>%)   |
| …                           | …                  |
```

- First row spans both columns and shows the Ribbon name (e.g. **Ribbon EU**).
- Second row: `Total calls (STOP)` → total STOP count (no percentage).
- Remaining rows: one per disconnect code, ordered by count descending,
  `<Reason Name> (<code>)` → `<count> (<pct>%)`, pct = one decimal place.
- **Font size:** wrap each mini-table in
  `<div style="font-size: 0.85em;">…</div>`.

> Collection prompt: see `references/sbc-collection-prompts.md` § B-1.
> Run 4 times (once per Ribbon: EU, US, APAC, LATAM) using the Ribbon → SBC pair
> mapping defined there.

---

3. For **each sub-region**, an expandable dropdown (sub-region name as title).

   **With Playwright:**
   One screenshot of the **"Call Attempts"** panel for that sub-region, using the
   per-SBC collection prompt template in `references/sbc-collection-prompts.md`.

   > SELECTOR NOTE (verified on the live dashboard): the panel is **displayed**
   > as "Call Attempts", but its underlying `data-title` is
   > `Average Call Service Duration (all) - Chart`. Use
   > `[data-title="Average Call Service Duration (all) - Chart"]`.
   > `[data-title="Call Attempts"]` does NOT exist.

   After capturing, upload the PNG as a page attachment and embed:
   ```xml
   <ac:image ac:align="center" ac:width="950">
     <ri:attachment ri:filename="sbc-<FILTER>-<TIMESTAMP>.png"/>
   </ac:image>
   ```

   **Without Playwright:** dashboard link + warning panel:
   *"Live CDR data requires Kibana access via browser (Playwright). Playwright is
   unavailable in this environment."*

---

## Notes
- Image alignment: see `references/common-patterns.md` — Image Alignment Rule.
- No-TODO / fallback: see `references/common-patterns.md` — No-TODO Rule.
- The Disconnect Codes by Region tables (§B-1) are placed at the top of §B,
  before the per-region dropdowns.
- Mirror example pages (IC260508 / IC260522) for per-Ribbon dashboard order.
- All of Part B depends on Playwright. When unavailable, emit warning panels.
