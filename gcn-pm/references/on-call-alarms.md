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

1. **Resize the browser viewport** to at least **1920×1080** before navigating:
   ```js
   // browser_resize or equivalent
   width: 1920, height: 1080
   ```
   This ensures all table columns fit in the viewport without horizontal overflow.

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

4. **Apply the time filter** to restrict the view to the sprint window:
   - Click the **"time"** filter field in the alerts UI.
   - Select the **"between"** option.
   - Set **start time** = `sprint_start` (sprint start date).
   - Set **end time** = `sprint_end` (sprint end date).
   - Wait for the table to reload — only alerts created within the sprint window
     should remain visible.
   - Do NOT add date parameters to the URL query string — it causes a
     "We couldn't load the alerts" server error; filter in-UI after load.

5. **Verify all required columns are visible** in the viewport before taking the
   screenshot. The following 9 columns must all be fully visible:
   **ID, Priority, Summary, Status, Tags, Created, Responders, Assignee, Actions**.
   If any column is hidden or clipped by horizontal overflow, reduce the browser
   zoom level via:
   ```js
   // browser_evaluate
   document.body.style.zoom = '80%'
   ```
   Then wait for the re-render and confirm all columns are visible before
   proceeding.

6. `browser_take_screenshot` — save to `/tmp/oncall-alerts-{sprint}.png`, upload
   as a page attachment and embed via the storage snippet below,
   **directly under the plain link with no caption, no label, and no
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
- Evidence is a Playwright **screenshot** only — no structured table.
- **Viewport must be ≥ 1920×1080** before navigating to avoid column overflow.
- **Authentication guard is mandatory**: after `browser_navigate`, poll
  `window.location.href` every 5 s for up to 30 s before proceeding. If the
  browser window closes during SSO, call `browser_navigate` again (once) to
  reopen it. If auth does not complete within 30 s, emit the warning panel and
  abort — never skip or shorten the guard.
- The screenshot must show only alerts **created within the sprint window**:
  apply the **"time"** filter, select **"between"**, set start = `sprint_start`
  and end = `sprint_end` in the UI. Do not append date params to the URL.
- All **9 columns** (ID, Priority, Summary, Status, Tags, Created, Responders,
  Assignee, Actions) must be fully visible before taking the screenshot. Reduce
  browser zoom if needed to fit all columns in the viewport.
- Embed the screenshot **directly under the plain link** — no caption, no label,
  no surrounding paragraph.
- The `<ac:image>` embed **must carry both `ac:align="center"` and
  `ac:layout="center"`**. Using only `ac:align` leaves the image left-aligned
  in the rendered Confluence Cloud page.
- Do NOT add `createdAt` to the URL query string — it causes a server error.
- Responder ID `5b660e34-8c85-4c01-b3c5-c96d192300cf` = OnCall Interconnect.
- Never invent or fabricate alert data.
- If Playwright is unavailable, emit the warning panel and the plain link only — never `[TODO]`.
