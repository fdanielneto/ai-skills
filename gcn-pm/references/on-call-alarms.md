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

1. `browser_navigate` to the URL below.
2. `browser_wait_for` any visible alert content to confirm the page loaded.
3. Apply the **created-date filter** to the sprint window in the UI (set the date
   range picker to `sprint_start`–`sprint_end`) so only alerts **created during
   the sprint** are visible. Do NOT add `createdAt` to the URL query string — it
   causes a "We couldn't load the alerts" server error; filter in-UI after load.
4. `browser_take_screenshot` — save to `/tmp/oncall-alerts-{sprint}.png`, upload
   as a page attachment and embed via `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>`
   (storage format), **directly under the plain link with no caption, no label, and no
   surrounding descriptive text**. Do NOT emit any text such as
   "OnCall Interconnect alerts — sprint … (screenshot from Atlassian Ops)" or
   similar before or after the image.

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
- The screenshot must show only alerts **created within the sprint window**
  (apply the date-range filter in the UI after navigation; do not append date
  params to the URL).
- Embed the screenshot **directly under the plain link** — no caption, no label,
  no surrounding paragraph.
- Do NOT add `createdAt` to the URL query string — it causes a server error.
- Responder ID `5b660e34-8c85-4c01-b3c5-c96d192300cf` = OnCall Interconnect.
- Never invent or fabricate alert data.
- If Playwright is unavailable, emit the warning panel and the plain link only — never `[TODO]`.
