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

#### Step 1 — Navigate + auth guard
- `browser_navigate` to the URL below.
- Poll until URL contains `jira/ops/alerts`; retry up to 30 s if redirected.
- If auth does not complete within 30 s, emit the warning panel and abort.

#### Step 2 — Filter by sprint dates (resilient lazy-load filter)

The alerts table lazy-loads rows in batches as the page renders. A one-shot
filter misses rows that arrive after the first pass. Use `browser_evaluate`
with the following logic: install a `MutationObserver` to re-apply the filter
on every new batch, then wait until the row count is stable for 1.5 s (or 8 s
total), then do a final pass.

The "Created" column is the **8th** column — read it directly from
`td:nth-child(8)` (do NOT search the header for the index):

```js
async () => {
  const start = new Date('SPRINT_STARTT00:00:00');
  const end   = new Date('SPRINT_ENDT23:59:59');

  function applyFilter() {
    const rows = [...document.querySelectorAll('table tbody tr')];
    let visible = 0, invalid = 0;
    for (const r of rows) {
      const raw = r.querySelector('td:nth-child(8)')?.textContent?.trim();
      const d = new Date(raw);
      if (isNaN(d))             { invalid++; r.style.display = 'none'; continue; }
      if (d < start || d > end) {           r.style.display = 'none'; continue; }
      r.style.display = '';
      visible++;
    }
    return { total: rows.length, visible, invalid };
  }

  const tbody = document.querySelector('table tbody');
  const obs = new MutationObserver(() => applyFilter());
  obs.observe(tbody, { childList: true, subtree: true });

  let last = -1, stableMs = 0;
  const t0 = Date.now();
  while (Date.now() - t0 < 8000) {
    const n = document.querySelectorAll('table tbody tr').length;
    applyFilter();
    if (n === last) { stableMs += 250; if (stableMs >= 1500) break; }
    else            { stableMs = 0; last = n; }
    await new Promise(r => setTimeout(r, 250));
  }
  obs.disconnect();
  return { ...applyFilter(), settledRows: last };
}
```

If no rows fall in the sprint window, still proceed to capture the filtered
(header-only) table as evidence — never fabricate rows.

#### Step 3 — Screenshot

`browser_take_screenshot` with:
- `filename`: `oncall-alerts-{sprint}.png`
- do NOT use `target` (no element screenshots)

#### Step 4 — Publish to Confluence

Upload the PNG as a page attachment and embed it **directly under the plain
link** — no caption, no label, no surrounding descriptive text:

```xml
<ac:image ac:align="center" ac:width="760">
  <ri:attachment ri:filename="oncall-alerts-{sprint}.png"/>
</ac:image>
```

> `ac:align="center"` centres the image. `ac:width="760"` matches the
> Confluence Cloud content area width — prevents overflow and keeps the
> image visually centred.

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
- Only one screenshot. No element screenshots (no `target`).
- **Authentication guard**: after `browser_navigate`, poll until URL contains
  `jira/ops/alerts`, retrying up to 30 s. If auth does not complete, emit the
  warning panel and abort.
- **Filter by the "Created" column in the DOM** using `td:nth-child(8)` with a
  `MutationObserver` that re-applies the filter on every lazy-load batch, waiting
  until the row count is stable (max 8 s). Do NOT use the page's "time" UI
  filter and do NOT append date params to the URL.
- Embed the screenshot **directly under the plain link** — no caption, no label,
  no surrounding paragraph.
- Responder ID `5b660e34-8c85-4c01-b3c5-c96d192300cf` = OnCall Interconnect.
- Never invent or fabricate alert data.
- If Playwright is unavailable, emit the warning panel and the plain link only — never `[TODO]`.
