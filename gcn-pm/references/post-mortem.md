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
