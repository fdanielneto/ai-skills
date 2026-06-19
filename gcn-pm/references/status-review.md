# Status_Review — "Status Review" section

Owns the first content section of the page. Mirrors the exact structure used
in existing Production Meeting pages (IC260522, IC260508, IC260424).

> FORMAT: use **storage format** (`representation: "storage"`) for the whole
> page. Do NOT use `atlas_doc_format` (ADF) — mixing ADF `mediaSingle` (charts)
> with ADF `blockCard`/`panel` breaks Confluence rendering (confirmed bug).
> In storage format, `blockCard` is expressed as an `<a data-datasource="...">`
> element and `panel` as `<ac:structured-macro ac:name="info">` — both work
> correctly alongside `<ac:image>` chart embeds.

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

> FORMAT: this is published in **storage format**, so the live Jira table is a
> single `<a … data-card-appearance="block" data-datasource="{…}">` element
> (NOT ADF JSON, NOT a plain link, NOT a static table). This is the exact markup
> that rendered correctly in the working run (v47, confirmed in incognito).
>
> **EDITOR-NATIVE STRUCTURE (MANDATORY):** the card MUST be wrapped with an
> empty `<p local-id="…"/>` paragraph immediately before AND after the `<a>`.
> Without these wrapper paragraphs the storage→ADF parser does not register the
> `<a>` as a proper top-level blockCard node — the Custom Jira Charts app "fails
> to get context" and renders nothing (confirmed bug, v46 regression).
> Generate 3 fresh UUID v4s per run: one for the `<p>` before, one for the `<a>`
> `local-id`, one for the `<p>` after.
> Attribute order on `<a>` MUST be: `href, data-layout, local-id,
> data-card-appearance, data-datasource` (matches editor-saved pages).

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
- NEVER build a static or manual table for the issue list, and NEVER emit a plain
  paragraph (e.g. "Ops Improvement Actions — production-meetings-interconnect")
  in its place. That plain-text degradation was the v38 bug — it happens when the
  page is published through the MCP html path instead of REST + storage. Always
  emit the storage blockCard above and publish via REST + storage.
- Do NOT emit a bare URL link to the JQL filter as the visible content — the
  blockCard (which carries the URL as its href) replaces it.
- Do NOT use ADF `atlas_doc_format` JSON for this node — storage `<a>` only.
- **ALWAYS wrap the `<a>` card with `<p local-id="…"/>` before AND after it.**
  Omitting either paragraph causes the datasource app to "fail to get context"
  and render a blank (confirmed regression; fixed in v47).
- Always generate **3 fresh UUID v4s** per run: one for each `<p>` and one for
  the `<a local-id>`. Never reuse local-ids from a previous run.
- Attribute order on `<a>`: `href, data-layout, local-id, data-card-appearance,
  data-datasource` — match the editor-saved page order exactly.
- When constructing the full ADF doc, wrap all section nodes inside the top-level
  `{ "version": 1, "type": "doc", "content": [...] }` envelope.
