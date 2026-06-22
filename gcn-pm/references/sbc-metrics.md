# SBC_Metrics — Executive Summary + Detailed data by Region (Calls)

This reference owns two consecutive parts of the page. The per-region **call
records** live here (not in a separate Calls reference) because the call data
comes from the SBC CDR logs.

Order on the page: **(A) Executive Summary → (B) Detailed data by Region**.
All region/Ribbon dropdowns are collapsed-by-default expand macros.

---

## DATA COLLECTION

### Source — Kibana CDR logs via Playwright MCP

Call records (volumes, disconnect reasons, per-account attribution) live in
`kibana-logging.svc.talkdeskapp.com`. CDR data collection uses **Playwright**
to navigate the dashboards.

### Region → SBC → Kibana filter map

Each sub-region corresponds to exactly **one SBC** and one `region.keyword`
value. Use the `region.keyword` value from the table below when applying the
DSL filter for that sub-region in §B (the SBC name is kept only for the dropdown
caption).

| Region             | Ribbon  | SBC name (caption) | `region.keyword` filter |
|--------------------|---------|--------------------|-------------------------|
| EU-South-1         | EU      | `PRDEUS1RSBC`      | `eu-south-1`            |
| EU-West-3          | EU      | `PRDEUW3RSBC`      | `eu-west-3`             |
| US-East-1          | US      | `prduse1rsbc`      | `us-east-1`             |
| US-West-2          | US      | `prdusw2rsbc`      | `us-west-2`             |
| AP1 - Singapore    | APAC    | `PRDAPS1RSBC`      | `ap-southeast-1`        |
| AP2 - Sydney       | APAC    | `PRDAPS2RSBC`      | `ap-southeast-2`        |
| LATAM-AZ1 (São Paulo) | LATAM | `PRDSAE1RSBC1`   | `sa-east-1`             |
| LATAM-AZ2 (São Paulo) | LATAM | `PRDSAE1RSBC2`   | `sa-east-2`             |

### Collection rules

1. **If the Playwright MCP is available:**

   **Executive Summary data (§A):**
   - Run the three collection prompts defined in §A (Totals table, Disconnect
     Reason chart/screenshot, Disconnect Reason top-10 table) against the
     global dashboards (all regions combined).

   **Detailed data by Region data (§B):**
   - Run the per-Ribbon disconnect-code prompt (defined in §B-1) four times
     (EU, US, APAC, LATAM), each time applying the two `region.keyword` filters
     for that Ribbon via the DSL `should` filter. Build one mini-table per Ribbon
     from the results.
   - For each sub-region, apply the KQL filter and capture the ACD chart
     using the **per-SBC collection prompt template** (defined in §B below).
     That prompt includes a mandatory **filter-application sequence** and a
     **verification gate** — both must pass before the screenshot is taken.
   - Save to `/Users/fdanielneto/sbc-<FILTER>-<TIMESTAMP>.png`
     where `<FILTER>` is the exact `region.keyword` value (e.g. `eu-south-1`) and
     `<TIMESTAMP>` is a compact UTC ISO-8601 string (e.g. `20260620T101500Z`).
   - Upload each PNG as a page attachment and embed via:
     `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`
     (**Always** set `ac:align="center"` — omitting it causes left-alignment.)

   **Screenshot integrity check (MANDATORY after all 7/8 region screenshots):**
   After taking all per-region screenshots, compute the MD5 (or SHA-256) hash of
   each file and assert that **every file has a distinct hash**. If two or more
   files share the same hash, the KQL filter was not properly applied for those
   regions — discard those files, re-run the per-SBC prompt for the affected
   regions, and re-check hashes before proceeding.

   ```bash
   # Example check (macOS):
   md5 /Users/fdanielneto/sbc-*-<TIMESTAMP>.png
   # All lines must show different hashes.
   ```

2. **If the Playwright MCP is NOT available:** emit, per block, the dashboard
   link plus a `warning` panel:
   *"Live CDR data requires Kibana access via browser (Playwright). Playwright is
   unavailable in this environment."*
   Never `[TODO]` text.

> PII rule: never fabricate CALL_IDs, account names, phone numbers or IPs.
> Prefer the screenshot/dashboard as the source of truth; keep raw identifiers
> redacted in the page text.

---

## A. Executive Summary

A single heading (H1) that is itself a link to the Kibana overview dashboard:

**[Executive Summary](https://kibana-logging.svc.talkdeskapp.com/goto/d6c9c100-aa74-11f0-bf0b-535e63bd4e70)**

Immediately after the heading-link, emit **exactly one** plain sentence:

```
Total: <N> completed calls.
```

- `<N>` = total STOP-record call count for the sprint (collected from Kibana).
- Use comma-separated thousands (e.g. `2,365,167`).
- Do NOT include the sprint date in this sentence.

Then, in sequence, emit the following three content blocks **in this exact order**:
`A-1 table → A-2 chart → A-3 table`.
Each block is preceded by its own **H3 heading** (see below).

---

### A-1. Total Call Attempts & Media Anchoring

Emit a visible **H3 heading on the page**: `Total Call Attempts & Media Anchoring`

**Collection prompt:**

```
Use Playwright MCP only.

1) Open https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/97c532ef-3354-4392-a153-141a02816e90
   and wait for the dashboard to fully load (all visualizations rendered).

2) Locate the visualization/panel whose title contains exactly
   "Total Call Attempts (all)" and read the numeric value shown in that panel.
   Call this value TOTAL_CALL_ATTEMPTS.

3) Locate the visualization/panel whose title contains exactly
   "Total Media Anchoring Calls (all)" and read the numeric value shown in that
   panel. Call this value TOTAL_MEDIA_ANCHORING_CALLS.

4) Return ONLY a Markdown table with two rows and the following structure:

| Metric                              | Value                          |
|-------------------------------------|--------------------------------|
| Total Call Attempts (all)           | <TOTAL_CALL_ATTEMPTS>          |
| Total Media Anchoring Calls (all)   | <TOTAL_MEDIA_ANCHORING_CALLS>  |

Use the exact numbers as displayed in the dashboard (including thousands
separators if present). Do not include any additional text besides the
Markdown table.
```

Render the resulting two-row table in storage format on the page.

---

### A-2. Call Disconnect Reason (all regions)

Emit a visible **H3 heading on the page**: `Call Disconnect Reason (all regions)`

This block is rendered **below** the A-1 table (after the call-attempts metrics).

**Collection prompt:**

```
Use Playwright MCP only.

1) Open https://kibana-logging.svc.talkdeskapp.com/goto/d6c9c100-aa74-11f0-bf0b-535e63bd4e70
   and wait for the dashboard to fully load (all panels rendered, legends visible).

2) BEFORE maximizing any panel, locate the KQL search bar at the top of the
   Kibana dashboard (the input field that says "Search" or shows a KQL query).
   Click it, clear any existing content, and type EXACTLY the following KQL
   query, then press Enter (or click "Refresh"). Wait for all panels to
   re-render with the filter applied.

   NOT Call Disconnect Reason.keyword : "16" and not Record Type.keyword : "START"

   (This KQL expression excludes disconnect code 16 / Normal Clearing AND
   excludes START-type records, so only non-trivial STOP records are shown.)

3) Find the dashboard panel element with data-test-subj="dashboardPanel" whose
   heading text contains "Call Disconnect Reason (all)".

4) Click the button with data-test-subj="embeddablePanelToggleMenuIcon" and then
   click "Maximize panel" so that the "Call Disconnect Reason (all)" chart is
   shown in full-screen (now already filtered by the KQL query from step 2).

5) Take a PNG screenshot of the entire maximized dashboard panel using
   browser_take_screenshot and save it to:
   /Users/fdanielneto/sbc-call-disconnect-reason-without-16.png

Return ONLY:
- final URL after all interactions
- absolute file path of the screenshot
```

Upload the resulting PNG as a page attachment and embed:
```xml
<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="sbc-call-disconnect-reason-without-16.png"/>
</ac:image>
```

---

### A-3. Call Disconnect Reason (all regions) — Top 10

**Collection prompt:**

```
Use Playwright MCP only.

1) Open https://kibana-logging.svc.talkdeskapp.com/goto/b1236460-5e74-11f1-bcc7-e33c7b83c1f3
   and wait for the dashboard to fully load.

2) Find the dashboard panel element with data-test-subj="dashboardPanel" whose
   heading text contains "Call Disconnect Reason - Table (all)".

3) Click its data-test-subj="embeddablePanelToggleMenuIcon" button and then
   "Maximize panel" to show the table in full-screen.

4) Create an accessibility / DOM snapshot of the maximized table panel and
   extract the tabular data for disconnect reasons:
   - one row per disconnect reason/code
   - columns: Reason name, Code, Count, Percentage.

5) Order all disconnect codes by Count in descending order and keep ONLY the
   top 10 rows (highest counts).

6) Return ONLY a Markdown table with the following columns:
   | Metric | Value |
   Where:
   - The first row is "Total calls (STOP)" with the total count of STOP calls
     (for the full dataset, not just the top 10).
   - Each subsequent row (up to 10 rows) is "<Reason Name> (<code>)" →
     "<count> (<pct>%)", using <pct> = code_count / total_STOP_calls with
     one decimal place.
```

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
  `<div style="font-size: 0.85em;">…</div>` so the text is visibly smaller
  than the surrounding body text.

**Collection prompt (run once per Ribbon, substituting `<REGION_A>`, `<REGION_B>`,
`<RIBBON_NAME>`):**

```
Use Playwright MCP only.

1) Open https://kibana-logging.svc.talkdeskapp.com/goto/b1236460-5e74-11f1-bcc7-e33c7b83c1f3
   and wait for the dashboard to fully load.

2) Add a filter via the Kibana filter bar: "Add filter" → "Edit as Query DSL" →
   paste EXACTLY the following DSL (substituting this Ribbon's two regions), then
   Save. Wait for all panels to re-render with the filter applied.

   {
     "query": {
       "bool": {
         "should": [
           { "match_phrase": { "region.keyword": "<REGION_A>" } },
           { "match_phrase": { "region.keyword": "<REGION_B>" } }
         ],
         "minimum_should_match": 1
       }
     }
   }

3) Find the dashboard panel with data-test-subj="dashboardPanel" whose heading
   contains "Call Disconnect Reason - Table (all)". Maximize it.

4) Snapshot the maximized table and extract: Reason name, Code, Count,
   Percentage (one row per disconnect code).

5) Order by Count descending and keep ONLY the top 5 rows (highest counts).

6) Return ONLY a Markdown table | Metric | Value |:
   - first row "Total calls (STOP)" = total STOP count for this Ribbon group,
   - then one row per code (up to 5 rows) "<Reason Name> (<code>)" → "<count> (<pct>%)",
     pct = code_count / total_STOP, one decimal place.
```

Ribbon → region.keyword pair mapping (used for the DSL `should` filter above):

| Ribbon       | REGION_A         | REGION_B         |
|--------------|------------------|------------------|
| Ribbon EU    | `eu-south-1`     | `eu-west-3`      |
| Ribbon US    | `us-east-1`      | `us-west-2`      |
| Ribbon APAC  | `ap-southeast-1` | `ap-southeast-2` |
| Ribbon LATAM | `sa-east-1`      | `sa-east-2`      |

Run the prompt **4 times** (once per Ribbon), collect the 4 resulting tables,
and render them inside the four `<ac:layout-cell>` blocks defined above.

---

3. For **each sub-region**, an expandable dropdown. The dropdown title is the
   sub-region name (e.g. `EU-South-1`). Content:

    **With Playwright:**

   One screenshot of the **"Average Call Service Duration (all) - Chart"** panel
    for that sub-region, captured using a `Gateway Name.keyword` filter on the
    exact SBC name. This guarantees each dropdown shows exactly one SBC,
    regardless of whether multiple SBCs share the same `region.keyword`
    (e.g. both LATAM SBCs are in `sa-east-1`).

    **Per-SBC collection prompt template** (substitute `<SBC_NAME>` and `<FILTER>`,
    where `<SBC_NAME>` is the SBC name column value from the DATA COLLECTION map
    above, and `<FILTER>` = `<SBC_NAME>` lowercased used in the filename):

   ```
    Use Playwright MCP only.

    1) Open the SBC CDR dashboard:
       https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/97c532ef-3354-4392-a153-141a02816e90
       Wait for the dashboard to fully load (all visualizations rendered,
       "Search session loading" indicator gone).

    2) APPLY THE KQL FILTER — follow every sub-step exactly:

       a) Use browser_click to click directly on the KQL search bar
          (the input element with placeholder "Search").

       b) Use browser_press_key with key "Control+a" to select all existing
          text in the bar.

       c) Use browser_type with slowly=false and submit=true to type EXACTLY:
             Gateway Name.keyword : "<SBC_NAME>" and NOT Record Type.keyword : "START"
          (substituting <SBC_NAME>). The submit=true causes Enter to be sent
          automatically, which submits the KQL query to Kibana.

       d) Use browser_wait_for with textGone="Search session loading" to wait
          until Kibana finishes reloading all panels with the new filter.

    3) VERIFY THE FILTER WAS APPLIED — mandatory before taking any screenshot:

       Use browser_evaluate to read the text content of the "Average Call Service
       Duration (all) - Chart" element:
         document.querySelector('[data-title="Average Call Service Duration (all) - Chart"]')?.innerText
       Confirm that the legend contains ONLY "<SBC_NAME>" and does NOT contain
       the SBC names of other regions.

       If the expected SBC is absent, or if the legend still shows multiple SBCs,
       the filter did not take effect. In that case:
         - Wait 2 seconds.
         - Repeat step 2 from sub-step (a).
         - Repeat step 3.
       Retry at most 3 times before reporting a failure.

    4) Take a PNG screenshot of ONLY the ACD chart element using
       browser_take_screenshot with:
         target: '[data-title="Average Call Service Duration (all) - Chart"]'
       Save to: /Users/fdanielneto/sbc-<FILTER>-<TIMESTAMP>.png
       where <TIMESTAMP> is the current UTC time formatted as YYYYMMDDTHHmmssZ
       (e.g. 20260622T120000Z).

       Do NOT maximize the panel — the element screenshot captures the chart
       directly without any state-management side-effects.

    Return ONLY:
    - the Gateway Name filter that was verified as active
    - the SBC name confirmed in the ACD chart legend
    - absolute file path of the screenshot
    ```

   After capturing, upload the PNG as a page attachment and embed it:
   ```xml
   <ac:image ac:align="center" ac:width="950">
     <ri:attachment ri:filename="sbc-<FILTER>-<TIMESTAMP>.png"/>
   </ac:image>
   ```

   **Without Playwright:** dashboard link + warning panel:
   *"Live CDR data requires Kibana access via browser (Playwright). Playwright is
   unavailable in this environment."*

### PII / data rule for Part B

Call records contain sensitive values: CALL_IDs, customer account names, dialed
/ diversion phone numbers, and IP addresses. Never reproduce or invent these.
Keep raw identifiers redacted; use the dashboards as the source of truth.

## Notes
- Mirror example pages (IC260508 / IC260522) for per-Ribbon dashboard order and
  captions.
- Keep screenshots cropped and reasonably sized; place each directly under the
  block it illustrates.
- All of Part B depends on Playwright. When Playwright is unavailable, emit
  warning panels (not `[TODO]` text).
- The Disconnect Codes by Region tables (§B-1) are placed at the top of §B,
  before the per-region dropdowns. Each per-region dropdown contains only the
  "Average Call Service Duration (all) - Chart" screenshot for that sub-region.
