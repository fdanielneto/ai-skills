# SBC Collection Prompts — Playwright MCP (load only when Playwright is available)

**Load this file only when the Playwright MCP is confirmed available and you are
ready to collect SBC/Kibana data.**

The dashboard URL pattern (substitute sprint dates):
```
SBC_DASHBOARD_URL = https://kibana-logging.svc.talkdeskapp.com/app/dashboards#/view/97c532ef-3354-4392-a153-141a02816e90?_g=(filters:!(),refreshInterval:(pause:!t,value:0),time:(from:'<START_SPRINT_DATE>T00:00:00.000Z',to:'<END_SPRINT_DATE>T23:59:59.000Z'))
```

---

## A-1. Total Call Attempts & Media Anchoring

```
Use Playwright MCP only.

1) Open SBC_DASHBOARD_URL (single dashboard, sprint dates already in the URL)
   and wait with browser_wait_for textGone="Search session loading".

2) Apply the default KQL filter: click the KQL search bar, Control+a, type
   EXACTLY:
      NOT Record Type.keyword : "START"
   then click "Update" (NOT "Search"). Wait with browser_wait_for
   textGone="Search session loading".

3) Locate the visualization/panel whose title contains exactly
   "Total Call Attempts (all)" and read the numeric value shown in that panel.
   Call this value TOTAL_CALL_ATTEMPTS.

4) Locate the visualization/panel whose title contains exactly
   "Total Media Anchoring Calls (all)" and read the numeric value shown in that
   panel. Call this value TOTAL_MEDIA_ANCHORING_CALLS.

5) Return ONLY a Markdown table with two rows and the following structure:

| Metric                              | Value                          |
|-------------------------------------|--------------------------------|
| Total Call Attempts (all)           | <TOTAL_CALL_ATTEMPTS>          |
| Total Media Anchoring Calls (all)   | <TOTAL_MEDIA_ANCHORING_CALLS>  |

Use the exact numbers as displayed in the dashboard (including thousands
separators if present). Do not include any additional text besides the
Markdown table.
```

---

## A-2. Call Disconnect Reason (all regions) — chart screenshot

```
Use Playwright MCP only.

1) Reuse the already-loaded SBC_DASHBOARD_URL page (do NOT reload). If this is
   the first panel of the run, open SBC_DASHBOARD_URL and wait with
   browser_wait_for textGone="Search session loading".

2) BEFORE maximizing any panel, click the KQL search bar, Control+a to select
   any existing text, and type EXACTLY the following KQL query, then click
   "Update" (NOT "Search"). Wait with browser_wait_for
   textGone="Search session loading" so the panels re-render filtered.

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

6) Minimize (restore) the panel and clear the KQL bar (Control+a → delete) so
   the dashboard is ready for the next block.

Return ONLY:
- final URL after all interactions
- absolute file path of the screenshot
```

---

## A-3. Call Disconnect Reason (all regions) — Top 10 table

```
Use Playwright MCP only.

1) Reuse the already-loaded SBC_DASHBOARD_URL page (do NOT reload). If this is
   the first panel of the run, open SBC_DASHBOARD_URL and wait with
   browser_wait_for textGone="Search session loading".

2) Apply the default KQL filter: click the KQL search bar, Control+a, type
   EXACTLY:
      NOT Record Type.keyword : "START"
   then click "Update" (NOT "Search"). Wait with browser_wait_for
   textGone="Search session loading".

3) Find the dashboard panel element with data-test-subj="dashboardPanel" whose
   heading text contains "Call Disconnect Reason - Table (all)".

4) Click its data-test-subj="embeddablePanelToggleMenuIcon" button and then
   "Maximize panel" to show the table in full-screen.

5) Create an accessibility / DOM snapshot of the maximized table panel and
   extract the tabular data for disconnect reasons:
   - one row per disconnect reason/code
   - columns: Reason name, Code, Count, Percentage.

6) Order all disconnect codes by Count in descending order and keep ONLY the
   top 10 rows (highest counts).

7) Minimize (restore) the panel and clear the KQL bar (Control+a → delete) so
   the dashboard is ready for the next block.

8) Return ONLY a Markdown table with the following columns:
   | Metric | Value |
   Where:
   - The first row is "Total calls (STOP)" with the total count of STOP calls
     (for the full dataset, not just the top 10).
   - Each subsequent row (up to 10 rows) is "<Reason Name> (<code>)" →
     "<count> (<pct>%)", using <pct> = code_count / total_STOP_calls with
     one decimal place.
```

---

## B-1. Disconnect Codes by Ribbon (run once per Ribbon)

Substitute `<SBC_A>`, `<SBC_B>`, `<RIBBON_NAME>` — the two SBC names of that Ribbon.

Ribbon → SBC pair mapping:
| Ribbon       | SBC_A          | SBC_B          |
|--------------|----------------|----------------|
| Ribbon EU    | `PRDEUS1RSBC`  | `PRDEUW3RSBC`  |
| Ribbon US    | `prduse1rsbc`  | `prdusw2rsbc`  |
| Ribbon APAC  | `PRDAPS1RSBC`  | `PRDAPS2RSBC`  |
| Ribbon LATAM | `PRDSAE1RSBC1` | `PRDSAE1RSBC2` |

```
Use Playwright MCP only.

1) Reuse the already-loaded SBC_DASHBOARD_URL page (do NOT reload). If this is
   the first panel of the run, open SBC_DASHBOARD_URL and wait with
   browser_wait_for textGone="Search session loading".

2) Apply this Ribbon's KQL filter (filter by Gateway Name — NOT by region, so
   the two LATAM SBCs that share sa-east-1 are not merged): click the KQL search
   bar, Control+a, type EXACTLY (substituting this Ribbon's two SBC names):

      NOT Record Type.keyword : "START" and Gateway Name.keyword : ("<SBC_A>" or "<SBC_B>")

   then click "Update" (NOT "Search"). Wait with browser_wait_for
   textGone="Search session loading" so the panel re-renders filtered.

3) Find the dashboard panel with data-test-subj="dashboardPanel" whose heading
   contains "Call Disconnect Reason - Table (all)". Maximize it.

4) Snapshot the maximized table and extract: Reason name, Code, Count,
   Percentage (one row per disconnect code).

5) Order by Count descending and keep ONLY the top 5 rows (highest counts).

6) Minimize (restore) the panel and clear the KQL bar (Control+a → delete)
   before moving to the next Ribbon.

7) Return ONLY a Markdown table | Metric | Value |:
   - first row "Total calls (STOP)" = total STOP count for this Ribbon group,
   - then one row per code (up to 5 rows) "<Reason Name> (<code>)" → "<count> (<pct>%)",
     pct = code_count / total_STOP, one decimal place.
```

Run this prompt **4 times** (once per Ribbon: EU, US, APAC, LATAM).

---

## Per-SBC Call Attempts screenshot template

Substitute `<SBC_NAME>` (Gateway Name column value) and `<FILTER>` = `<SBC_NAME>` lowercased.

> SELECTOR NOTE (verified live): the panel is **displayed** as "Call Attempts",
> but its underlying saved-object `data-title` attribute is
> `Average Call Service Duration (all) - Chart`. Every CSS selector MUST use
> `[data-title="Average Call Service Duration (all) - Chart"]`.
> `[data-title="Call Attempts"]` does NOT exist. Do not fix the selector to match
> the display name.

```
Use Playwright MCP only.

1) Reuse the already-loaded SBC_DASHBOARD_URL page (do NOT reload). If this is
   the first panel of the run, open SBC_DASHBOARD_URL and wait with
   browser_wait_for textGone="Search session loading".

2) APPLY THE KQL FILTER — follow every sub-step exactly:

   a) Use browser_click to click directly on the KQL search bar
      (the input element with placeholder "Search").

   b) Use browser_press_key with key "Control+a" to select all existing
      text in the bar.

   c) Use browser_type with slowly=false and submit=false to type EXACTLY:
         Gateway Name.keyword : "<SBC_NAME>" and NOT Record Type.keyword : "START"
      (substituting <SBC_NAME>).

   d) Click the "Update" button (NOT "Search") to submit the KQL query to
      Kibana and refresh the panels.

   e) Use browser_wait_for with textGone="Search session loading" to wait
      until Kibana finishes reloading all panels with the new filter.

3) VERIFY THE FILTER WAS APPLIED — mandatory before taking any screenshot:

   Use browser_evaluate to read the text content of the "Call Attempts"
   panel (whose data-title is "Average Call Service Duration (all) - Chart"):
     document.querySelector('[data-title="Average Call Service Duration (all) - Chart"]')?.innerText
   Confirm that the legend contains ONLY "<SBC_NAME>" and does NOT contain
   the SBC names of other regions.

   If the expected SBC is absent, or if the legend still shows multiple SBCs,
   the filter did not take effect. In that case:
     - Wait 2 seconds.
     - Repeat step 2 from sub-step (a).
     - Repeat step 3.
   Retry at most 3 times before reporting a failure.

4) Take a PNG screenshot of ONLY the Call Attempts chart element using
   browser_take_screenshot with:
     target: '[data-title="Average Call Service Duration (all) - Chart"]'
   Save to: /Users/fdanielneto/sbc-<FILTER>-<TIMESTAMP>.png
   where <TIMESTAMP> is the current UTC time formatted as YYYYMMDDTHHmmssZ
   (e.g. 20260622T120000Z).

   Do NOT maximize the panel — the element screenshot captures the chart
   directly without any state-management side-effects. After the screenshot,
   clear the KQL bar (Control+a → delete) before the next sub-region.

Return ONLY:
- the Gateway Name filter that was verified as active
- the SBC name confirmed in the Call Attempts chart legend
- absolute file path of the screenshot
```

Save screenshots to `/Users/fdanielneto/sbc-<FILTER>-<TIMESTAMP>.png`.
Upload each PNG as a page attachment and embed via:
```xml
<ac:image ac:align="center" ac:width="950">
  <ri:attachment ri:filename="sbc-<FILTER>-<TIMESTAMP>.png"/>
</ac:image>
```

**Screenshot integrity check (MANDATORY after all 7/8 region screenshots):**
Compute the MD5 (or SHA-256) hash of each file and assert that every file has a
distinct hash. If two or more files share the same hash, the KQL filter was not
properly applied — discard those files, re-run the per-SBC prompt for the affected
regions, and re-check hashes before proceeding.

```bash
# Example check (macOS):
md5 /Users/fdanielneto/sbc-*-<TIMESTAMP>.png
# All lines must show different hashes.
```
