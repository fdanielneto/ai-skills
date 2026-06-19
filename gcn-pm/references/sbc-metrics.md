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
`kibana-logging.svc.talkdeskapp.com`. The `kibana-prd` MCP handles the OAuth
flow; CDR data collection uses **Playwright** to navigate the dashboards.

1. **If the Playwright MCP is available:**
   - Navigate to each region's Kibana call-records dashboard and each Ribbon SBC
     dashboard for the sprint window.
    - Capture a focused screenshot of each dashboard panel (call-records overview,
      disconnect reasons) with `browser_take_screenshot`, save to
      `/tmp/sbc-{region}-{panel}.png`, upload as a page attachment and
      embed via `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`
      (storage format). **Always set `ac:align="center"` — omitting it causes
      left-alignment in Confluence.**
    - Build the full disconnect-code breakdown table (see §B item 4) for each
      region, derived from what the dashboard shows. The table is always emitted
      (SILENCE does not apply to the SBC per-region disconnect-code table).

2. **If the Playwright MCP is NOT available:** emit, per region block, the
   dashboard link plus a `warning` panel:
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
Sprint <YYYY-MM-DD> to <YYYY-MM-DD>. Total: <N> completed calls.
```

- `<N>` = total STOP-record call count for the sprint (collected from Kibana).
- Use comma-separated thousands (e.g. `2,365,167`).
- **Forbidden text**: any reference to `logs-td-ribbonsbc-cdr*`, `STOP records only`,
  `Data sourced from`, `Code 16 (Normal Clearing)`, `accounts for N% of all
  disconnects`, or any other provenance/methodology sentence. The only allowed
  content is the one Sprint + Total sentence above.

---

## B. Detailed data by Region  (the call records)

1. Heading (H1): **Detailed data by Region**

2. Grouped by Ribbon (H2), in order: **Ribbon EU, Ribbon US, Ribbon APAC,
   Ribbon LATAM**. Region membership:
   - Ribbon EU   → EU-South-1, EU-West-3
   - Ribbon US   → US-East-1, US-West-2
   - Ribbon APAC → AP1 - Singapore, AP2 - Sydney
   - Ribbon LATAM→ LATAM-AZ1, LATAM-AZ2

3. For EACH region, an expandable dropdown. Content:

   **With Playwright:**
   ```
   ### [Kibana <Region>](<region-overview Kibana dashboard URL>)
   <sprint-specific Kibana goto short URL>

   * **<call-records observation>**                  ← bold
   <screenshot — call records overview, ac:align="center">

   ### [Kibana Disconnect Reasons](https://kibana-logging.svc.talkdeskapp.com/goto/cd000d20-aa9f-11f0-a0ca-6920a21a9c7f)
   <sprint-specific disconnect-reasons goto short URL>

   Calls with errors: <N> (<pct>%).
   <screenshot — disconnect reasons, ac:align="center">
   ```

   **Error summary line (mandatory, exactly this format):**
   ```
   Calls with errors: <N> (<pct>%).
   ```
   - `<N>` = total calls with a non-normal disconnect code (any code other than 16 /
     Normal Clearing), comma-separated thousands.
   - `<pct>` = `<N>` / total STOP calls for that region, one decimal place (e.g. `0.4`).
   - **Forbidden forms**: "Non-normal disconnect reasons: X out of Y", "Code 16 (Normal
     Clearing) accounts for N% of all disconnects", or any other sentence beyond the
     one-liner above. Emit ONLY the `Calls with errors: <N> (<pct>%).` line.

   **Without Playwright:** dashboard link + warning panel (see DATA COLLECTION).

4. Immediately after the screenshots, a **single full disconnect-code breakdown table**
   for the region (data-driven — emit always, not only for anomalies). Two columns:
   `Metric` and `Value`. Rows:
   - First row: **Total calls (STOP)** → total STOP-record count (no percentage).
   - One row per disconnect code present, ordered by **descending count**:
     `<Reason Name> (<code>)` → `<count> (<pct>%)`
   - `<pct>` = code count / total STOP calls, one decimal place.
   - Use canonical Q.850 reason names (e.g. "Normal Clearing", "Normal Unspecified",
     "Call Rejected", "User Busy", "Destination Out of Order", "Timer Recovery",
     "Temporary Failure").

   Example for one region:

   | Metric                          | Value              |
   |---------------------------------|--------------------|
   | Total calls (STOP)              | 700,624            |
   | Normal Clearing (16)            | 699,157 (99.8%)    |
   | Normal Unspecified (31)         | 1,030 (0.1%)       |
   | Call Rejected (21)              | 103 (0.0%)         |
   | User Busy (17)                  | 77 (0.0%)          |
   | Destination Out of Order (27)   | 59 (0.0%)          |
   | Timer Recovery (102)            | 52 (0.0%)          |
   | Temporary Failure (41)          | 44 (0.0%)          |

   > SILENCE OVERRIDE: this table is emitted for EVERY region (not only anomalous
   > ones). The SILENCE rule does NOT apply to the SBC per-region disconnect-code
   > table. All codes present in the dashboard data must appear, regardless of volume.

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
