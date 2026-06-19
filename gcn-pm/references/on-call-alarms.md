# On-Call_Alarms — "On-Call Alarms" section

Owns the On-Call Alarms section.
Column structure confirmed from the UCInterconnect template (page 5238128641).

---

## Structure (in order)

### 1. Heading
H1: **On-Call Alarms**

### 2. Info panel (bullet list — verbatim, tight)
Wrap in a Confluence info panel. Use a single tight `<ul>` with no empty
`<p>`, no `<br>`, and no blank list items between or after bullets. Sub-bullets
nest inside their parent `<li>`. Storage format snippet:

```xml
<ac:structured-macro ac:name="info">
  <ac:rich-text-body>
    <ul>
      <li>Review both paged and non-paged alarms for accuracy and effectiveness.
        <ul>
          <li>Include on-call team members in the meeting and actively seek their input, especially regarding recent paged events.</li>
          <li>Use their feedback to improve alarms, runbooks, and processes for managing incidents.</li>
        </ul>
      </li>
      <li>Analyze the false positive rate of alarms and take steps to improve their quality.</li>
      <li>Update runbooks based on on-call feedback and alarm effectiveness.</li>
    </ul>
  </ac:rich-text-body>
</ac:structured-macro>
```

### 3. Plain link
`https://talkdesk.atlassian.net/jira/ops/alerts?view=list&query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22`

### 4. Alerts evidence via Playwright

**Playwright MCP is the only supported method for this section.**

#### Primary — Playwright MCP available

1. **Resize the browser to a wide desktop viewport** (`browser_resize`,
   width=1920, height=1080) before navigating. This is **only** to force the
   desktop multi-column table layout (so columns render side by side, not a
   responsive stacked layout) — it is **not** the screenshot/cropping mechanism.
   The full-width capture is guaranteed later by the **element screenshot**
   (step 5), not by the viewport size.

2. `browser_navigate` to the URL below.

3. **Authentication guard** — poll until the alerts page is fully loaded (handles
   SSO redirects and session-expiry scenarios). The persistent Playwright profile
   (`~/Library/Caches/ms-playwright/mcp-*/`) retains the session after the first
   login, so this guard is a no-op on warm runs; it only activates when auth is
   actually required.

   Repeat up to **6 times** (= 30 s maximum), with a **5 s pause between checks**:

   **a. Check current URL:**
   ```js
   // browser_evaluate
   () => window.location.href
   ```
   - Result contains `"jira/ops/alerts"` → authenticated; exit loop, proceed to step 4.
   - Result contains `"login"`, `"id.atlassian"`, or `"sso"` → still on auth page;
     go to step b.
   - Tool raises `"no page"` / `"context closed"` / `"Target page, context or browser
     has been closed"` error → the browser window was closed during the auth flow;
     call `browser_navigate` once with the alerts URL to reopen it, then restart
     the loop from step a (reset the iteration counter).

   **b. Wait 5 seconds:**
   ```js
   // browser_evaluate
   () => new Promise(r => setTimeout(r, 5000))
   ```
   Then return to step a.

   **If 6 iterations are exhausted without reaching the alerts page:** emit a
   `warning` macro — *"Authentication did not complete within 30 s. See link
   above."* — and abort this section. Do not proceed to the filter or screenshot.

4. **Filter rows by the "Created" column, in the DOM** (authoritative — do NOT
   use the page's "time" UI filter; it does not restrict reliably). Hide every
   row whose Created date falls **outside** the sprint window
   `[sprint_start 00:00:00 … sprint_end 23:59:59]`, leaving only in-sprint rows
   visible, then tag the table so the next step can target it.

   The "Created" cell shows an absolute date like `Jun 17, 2026 10:55 AM`, which
   `new Date(...)` parses directly. Prefer a `<time datetime>` or `title`
   attribute if present; fall back to the cell text.

   Run via `browser_evaluate` (inspect the table first with `browser_snapshot`
   to confirm the row/column selectors, then adapt this template):
   ```js
   () => {
     const start = new Date('SPRINT_START' + 'T00:00:00');
     const end   = new Date('SPRINT_END'   + 'T23:59:59');
     const table = document.querySelector('table, [role="grid"]');        // adapt
     const headers = [...table.querySelectorAll('th,[role="columnheader"]')];
     const createdIdx = headers.findIndex(h => /created/i.test(h.textContent));
     const rows = [...table.querySelectorAll('tbody tr, [role="row"]')]
       .filter(r => r.querySelector('td,[role="gridcell"]'));            // skip header row
     let visible = 0;
     for (const r of rows) {
       const cell = r.querySelectorAll('td,[role="gridcell"]')[createdIdx];
       const raw = cell?.querySelector('time')?.getAttribute('datetime')
                || cell?.getAttribute('title')
                || cell?.textContent?.trim();
       const d = new Date(raw);
       if (isNaN(d) || d < start || d > end) r.style.display = 'none';
       else visible++;
     }
     table.setAttribute('data-pm-shot', '1');
     return { visible, total: rows.length, createdIdx };
   }
   ```
   Confirm `createdIdx` is not `-1` (header matched) and that `visible` is the
   expected in-sprint count before continuing. If `visible === 0`, still proceed
   to capture the filtered (header-only) table as evidence that no alerts were
   created in the window — never fabricate rows.

5. **Element screenshot of the filtered table** — capture the tagged table
   element directly. An element screenshot grabs the element's **full bounding
   box**, including columns that overflow the viewport horizontally, so **all 9
   columns (including Assignee) are captured** and only the in-sprint rows
   (the rest are `display:none`).

   `browser_take_screenshot` with:
   - `target`: `[data-pm-shot="1"]` (the table element — element screenshot)
   - `filename`: `oncall-alerts-{sprint}.png`
   - do NOT set `fullPage` (it is incompatible with element screenshots)

   Upload the PNG as a page attachment and embed it via the storage snippet
   below, **directly under the plain link with no caption, no label, and no
   surrounding descriptive text**. Do NOT emit any text such as
   "OnCall Interconnect alerts — sprint … (screenshot from Atlassian Ops)" or
   similar before or after the image.

   ```xml
   <ac:image ac:align="center" ac:layout="center" ac:width="950">
     <ri:attachment ri:filename="oncall-alerts-{sprint}.png"/>
   </ac:image>
   ```

   > `ac:layout="center"` is mandatory — it is the attribute that produces visual
   > centering in Confluence Cloud. `ac:align="center"` alone does not centre
   > the image in the rendered page; both attributes must be present.

#### URL

```
https://talkdesk.atlassian.net/jira/ops/alerts?view=list&query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22
```

#### Fallback — Playwright MCP unavailable

Emit a `warning` macro only:

> *"Live alert data was not collected in this run (Playwright tool unavailable). See link above."*

Do **not** attempt to build any table or invent alert rows. Never emit `[TODO]`.

---

## Rules
- Evidence is a Playwright **element screenshot of the alerts table** — no
  structured table authored by hand.
- **Resize to 1920×1080 before navigating** — only to force the desktop
  multi-column layout, NOT as the capture mechanism.
- **Authentication guard is mandatory**: after `browser_navigate`, poll
  `window.location.href` every 5 s for up to 30 s before proceeding. If the
  browser window closes during SSO, call `browser_navigate` again (once) to
  reopen it. If auth does not complete within 30 s, emit the warning panel and
  abort — never skip or shorten the guard.
- **Filter by the "Created" column in the DOM** — hide every row outside
  `[sprint_start 00:00:00 … sprint_end 23:59:59]` via `display:none` before the
  screenshot. Do NOT use the page's "time" UI filter (it does not restrict
  reliably) and do NOT append date params to the URL.
- **Capture with an element screenshot** (`target="[data-pm-shot='1']"`), never a
  viewport/`fullPage` screenshot. The element screenshot captures the table's
  full width, guaranteeing all 9 columns (ID, Priority, Summary, Status, Tags,
  Created, Responders, Assignee, Actions) — including **Assignee** — and only the
  in-sprint rows.
- Embed the screenshot **directly under the plain link** — no caption, no label,
  no surrounding paragraph.
- The `<ac:image>` embed **must carry both `ac:align="center"` and
  `ac:layout="center"`**. Using only `ac:align` leaves the image left-aligned
  in the rendered Confluence Cloud page.
- Responder ID `5b660e34-8c85-4c01-b3c5-c96d192300cf` = OnCall Interconnect.
- Never invent or fabricate alert data. If no alerts fall in the sprint window,
  capture the filtered (empty) table as evidence — never `[TODO]`.
- If Playwright is unavailable, emit the warning panel and the plain link only — never `[TODO]`.
