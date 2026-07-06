# Status_Review — "Status Review" section

Owns the first content section of the page. Mirrors the exact structure used
in existing Production Meeting pages (IC260522, IC260508, IC260424).

> Publish format: storage only. See `references/common-patterns.md` — Storage-Only Publish Rule.

---

## Structure (in order)

### 1. Heading
Storage `<h1>` — text: **"Status Review"**

```html
<h1>Status Review</h1>
```

### 2. Info panel (bullet list)
Storage `info` macro wrapping a `<ul>`.
Bullet text is verbatim (no code/inline formatting on "Ops Improvement Action"):

- Review the status of all Ops Improvement Action items from last meetings at the beginning of the meeting.
- Assign clear ownership for each item and set due dates.
- Track the age of Ops Improvement Action items to prioritise older, unresolved tasks.

Storage shape:
```html
<ac:structured-macro ac:name="info" ac:schema-version="1">
  <ac:rich-text-body>
    <ul>
      <li><p>Review the status of all Ops Improvement Action items from last meetings at the beginning of the meeting.</p></li>
      <li><p>Assign clear ownership for each item and set due dates.</p></li>
      <li><p>Track the age of Ops Improvement Action items to prioritise older, unresolved tasks.</p></li>
    </ul>
  </ac:rich-text-body>
</ac:structured-macro>
```

### 3. Live issue list (storage blockCard — Custom Jira Charts datasource)

> blockCard wrapper structure and attribute order: see `references/publish.md` — blockCard wrapper structure.
> Generate **3 fresh UUID v4s** per run. Never reuse local-ids from a previous run.

```html
<p local-id="<generate-fresh-uuid-v4>" />
<a href="https://talkdesk.atlassian.net/issues/?jql=filter%20%3D%20%22production-meetings-interconnect%22"
   data-layout="full-width"
   local-id="<generate-fresh-uuid-v4>"
   data-card-appearance="block"
   data-datasource="{&quot;id&quot;: &quot;d8b75300-dfda-4519-b6cd-e49abbd50401&quot;, &quot;parameters&quot;: {&quot;cloudId&quot;: &quot;66f0204c-1684-409c-b644-8cac70022a54&quot;, &quot;jql&quot;: &quot;filter = \&quot;production-meetings-interconnect\&quot;&quot;}, &quot;views&quot;: [{&quot;type&quot;: &quot;table&quot;, &quot;properties&quot;: {&quot;columns&quot;: [{&quot;key&quot;: &quot;issuetype&quot;}, {&quot;key&quot;: &quot;key&quot;, &quot;width&quot;: 88}, {&quot;key&quot;: &quot;summary&quot;, &quot;width&quot;: 471}, {&quot;key&quot;: &quot;status&quot;}, {&quot;key&quot;: &quot;parent&quot;}, {&quot;key&quot;: &quot;customfield_10007&quot;, &quot;width&quot;: 109}, {&quot;key&quot;: &quot;assignee&quot;, &quot;width&quot;: 114}, {&quot;key&quot;: &quot;created&quot;}]}}]}">https://talkdesk.atlassian.net/issues/?jql=filter%20%3D%20%22production-meetings-interconnect%22</a>
<p local-id="<generate-fresh-uuid-v4>" />
```

The `data-datasource` attribute value is HTML-entity-encoded JSON (`&quot;` for
each `"`, `\&quot;` for the escaped quotes inside the JQL). Keep that encoding —
storage format requires it. The decoded JSON is:

```json
{
  "id": "d8b75300-dfda-4519-b6cd-e49abbd50401",
  "parameters": {
    "cloudId": "66f0204c-1684-409c-b644-8cac70022a54",
    "jql": "filter = \"production-meetings-interconnect\""
  },
  "views": [{
    "type": "table",
    "properties": { "columns": [
      { "key": "issuetype" },
      { "key": "key", "width": 88 },
      { "key": "summary", "width": 471 },
      { "key": "status" },
      { "key": "parent" },
      { "key": "customfield_10007", "width": 109 },
      { "key": "assignee", "width": 114 },
      { "key": "created" }
    ] }
  }]
}
```

Key values (do not modify):
- `datasource.id` = `d8b75300-dfda-4519-b6cd-e49abbd50401` (Custom Jira Charts app)
- `datasource.parameters.cloudId` = `66f0204c-1684-409c-b644-8cac70022a54`
  (Jira cloud instance — distinct from the Confluence cloudId used in API calls)
- `jql` = `filter = "production-meetings-interconnect"` (saved filter)
- Column order and widths must be preserved exactly as shown above

---

## Rules
- NEVER build a static or manual table for the issue list. Never emit a plain paragraph in its place (that is the v38 bug — it happens when publishing via MCP html instead of REST + storage).
- Do NOT emit a bare URL link to the JQL filter — the blockCard (which carries the URL as its href) replaces it.
- Do NOT use ADF `atlas_doc_format` JSON for this node — storage `<a>` only.
- **ALWAYS wrap the `<a>` card with `<p local-id="…"/>` before AND after it** (see `references/publish.md` — blockCard wrapper structure).
- Always generate **3 fresh UUID v4s** per run. Never reuse local-ids from a previous run.
- Attribute order on `<a>`: `href, data-layout, local-id, data-card-appearance, data-datasource`.
- Storage-only publish: see `references/common-patterns.md` — Storage-Only Publish Rule.
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
# Post-Mortem — "Post-Mortem (last 90 days)" section

Owns the Post-Mortem section. Mirrors the example page (IC260522).

> Publish format: storage only. See `references/common-patterns.md` — Storage-Only Publish Rule.

---

## Structure (in order)

### 1. Heading
Storage `<h1>` — text: **"Post-Mortem (last 90 days)"**

```html
<h1>Post-Mortem (last 90 days)</h1>
```

### 2. Info panel (bullet list)
Storage `info` macro wrapping a `<ul>`. Bullet text verbatim:

- Link all relevant post-mortems to the meeting documentation for easy reference.
- Use insights from post-mortems to prevent similar incidents in the future.

```html
<ac:structured-macro ac:name="info" ac:schema-version="1">
  <ac:rich-text-body>
    <ul>
      <li><p>Link all relevant post-mortems to the meeting documentation for easy reference.</p></li>
      <li><p>Use insights from post-mortems to prevent similar incidents in the future.</p></li>
    </ul>
  </ac:rich-text-body>
</ac:structured-macro>
```

### 3. Live incident list (storage blockCard — Custom Jira Charts datasource)

> blockCard wrapper structure and attribute order: see `references/publish.md` — blockCard wrapper structure.
> Generate **3 fresh UUID v4s** per run. Never reuse local-ids from a previous run.
> JQL: TD Incidents from the last 90 days assigned to the Interconnect team.

```html
<p local-id="<generate-fresh-uuid-v4>" />
<a href="https://talkdesk.atlassian.net/issues/?jql=project%20in%20(INCIDENT)%20and%20type%20in%20(%22TD%20Incident%22)%20and%20assignee%20in%20(712020%3Ae99666d8-42ea-4f69-be46-1d96262ac54e%2C%20622745edb7e7c7007159b8df%2C%20712020%3A3a4c738b-581a-432c-a471-82d7e70c57f6%2C%205f9fde30632c620071778e2b%2C%20712020%3Ad39b9372-96d2-4be1-98a0-e17ad4292a0c%2C%2060380d934623c60069cfc0ea%2C%2061ead968e2261a0069580f6c%2C%2061d89c7d90cfd20071343f62%2C%205fba1b20cbead500690e3ffd%2C%20603cac0581a8400068b23bcd%2C%20712020%3A9baaf1c0-1a40-4795-92ca-f879f03a96fd)%20and%20created%20%3E%3D%20-90d%20ORDER%20BY%20created%20DESC"
   data-layout="full-width"
   local-id="<generate-fresh-uuid-v4>"
   data-card-appearance="block"
   data-datasource="{&quot;id&quot;: &quot;d8b75300-dfda-4519-b6cd-e49abbd50401&quot;, &quot;parameters&quot;: {&quot;cloudId&quot;: &quot;66f0204c-1684-409c-b644-8cac70022a54&quot;, &quot;jql&quot;: &quot;project in (INCIDENT) and type in (\&quot;TD Incident\&quot;) and assignee in (712020:e99666d8-42ea-4f69-be46-1d96262ac54e, 622745edb7e7c7007159b8df, 712020:3a4c738b-581a-432c-a471-82d7e70c57f6, 5f9fde30632c620071778e2b, 712020:d39b9372-96d2-4be1-98a0-e17ad4292a0c, 60380d934623c60069cfc0ea, 61ead968e2261a0069580f6c, 61d89c7d90cfd20071343f62, 5fba1b20cbead500690e3ffd, 603cac0581a8400068b23bcd, 712020:9baaf1c0-1a40-4795-92ca-f879f03a96fd) and created &gt;= -90d ORDER BY created DESC&quot;}, &quot;views&quot;: [{&quot;type&quot;: &quot;table&quot;, &quot;properties&quot;: {&quot;columns&quot;: [{&quot;key&quot;: &quot;issuetype&quot;}, {&quot;key&quot;: &quot;key&quot;, &quot;width&quot;: 88}, {&quot;key&quot;: &quot;summary&quot;, &quot;width&quot;: 471}, {&quot;key&quot;: &quot;status&quot;}, {&quot;key&quot;: &quot;priority&quot;}, {&quot;key&quot;: &quot;assignee&quot;, &quot;width&quot;: 114}, {&quot;key&quot;: &quot;created&quot;}]}}]}">https://talkdesk.atlassian.net/issues/?jql=project%20in%20(INCIDENT)%20...%20ORDER%20BY%20created%20DESC</a>
<p local-id="<generate-fresh-uuid-v4>" />
```

The `data-datasource` value is HTML-entity-encoded JSON (`&quot;` for `"`,
`\&quot;` for escaped quotes inside the JQL, `&gt;` for `>`). Keep that encoding.
Columns (in order): issuetype, key (88), summary (471), status, priority,
assignee (114), created.

Key values (do not modify):
- `datasource.id` = `d8b75300-dfda-4519-b6cd-e49abbd50401` (Custom Jira Charts app)
- `datasource.parameters.cloudId` = `66f0204c-1684-409c-b644-8cac70022a54`
- The `-90d` window is baked into the JQL; it auto-updates every time the page
  is viewed in Confluence.
- Always generate a new UUID v4 for `local-id` on each run.

---

## Rules
- NEVER build a static table for the incident list. Never emit a plain paragraph in its place (that is the v38 degradation caused by publishing via MCP html instead of REST + storage).
- Do NOT use ADF `atlas_doc_format` JSON for this node — storage `<a>` only.
- **ALWAYS wrap the `<a>` card with `<p local-id="…"/>` before AND after it** (see `references/publish.md` — blockCard wrapper structure).
- Always generate **3 fresh UUID v4s** per run. Never reuse local-ids from a previous run.
- Attribute order on `<a>`: `href, data-layout, local-id, data-card-appearance, data-datasource`.
- Storage-only publish: see `references/common-patterns.md` — Storage-Only Publish Rule.
# Events_Tracking — "Events Tracking" section

Owns the final section of the page. Mirrors the example page (IC260522).

## Structure

1. Heading (H1): **Events Tracking**

2. A 4-column table with pre-filled checkpoint rows and several empty rows for
   the team to fill during the meeting:

   | Checkpoints          | Description | Action | Date |
   |----------------------|-------------|--------|------|
   | EMS Alarms Analysis  |             |        |      |
   | Ribbon Licenses      |             |        |      |
   | …                    |             |        |      |
   |                      |             |        |      |
   |                      |             |        |      |
   |                      |             |        |      |
   |                      |             |        |      |

## Notes
- Keep the first rows pre-labelled (EMS Alarms Analysis, Ribbon Licenses, "…")
  exactly as on the example, then leave ~4 empty rows.
- This section is intentionally a blank working table — do not pre-fill
  Description / Action / Date.
