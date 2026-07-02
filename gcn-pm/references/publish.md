# Publish Reference — REST + Storage (load at publish step only)

**Load this file only when you are about to publish to Confluence.**

---

## DELETE & RECREATE semantics

Each run must end with the page showing ONLY that run's sections.

1. Find the existing page titled exactly `GCN PM Auto Test` under Notes
   (`getPagesInConfluenceSpace` with `spaceId=3406136357`, `title` filter).
2. Build the brand-new body for this run (header + TOC + this run's sections only).
3. Reset the page by replacing its ENTIRE body via the Confluence REST API with
   `representation: "storage"`. Full-body overwrite clears all previously-present
   sections and keeps the same `pageId`/URL. If the page does NOT exist → CREATE it.

> CONNECTOR LIMITATION — no hard delete. The full-body overwrite is the faithful
> equivalent of delete+recreate.

Never create a second/duplicate page. Title is always exactly `GCN PM Auto Test`.

---

## Canonical publish path (REST + storage — MANDATORY)

Auth uses `$ATLASSIAN_USERNAME` and `$ATLASSIAN_API_TOKEN`.
Base URL: `https://talkdesk.atlassian.net/wiki`.
Fixed page id: `6568476792`.

**Step 1 — Read current version number:**
```
GET /rest/api/content/6568476792?expand=version
```

**Step 2 — Overwrite whole body with next version number:**
```
PUT /rest/api/content/6568476792
Content-Type: application/json
{
  "version": { "number": <current+1>, "message": "<run description>" },
  "type": "page",
  "title": "GCN PM Auto Test",
  "body": { "storage": { "value": "<full storage HTML>", "representation": "storage" } }
}
```

Use `curl -u "$ATLASSIAN_USERNAME:$ATLASSIAN_API_TOKEN"`. Write the storage body
to a temp file and reference it from the JSON payload (build with a small Python/jq
step) to avoid shell-escaping issues with the large HTML and embedded
`data-datasource` JSON.

Chart/screenshot PNGs are uploaded as attachments to the same page id BEFORE the
PUT, then embedded via `ac:image` + `ri:attachment`. Upload via:
```
POST /rest/api/content/6568476792/child/attachment
X-Atlassian-Token: no-check
```
with the same `$ATLASSIAN_API_TOKEN` when the Atlassian MCP upload tool is not available.

The `gcn_pm_storage.py` helper (session temp directory) implements this PUT; keep
it as the canonical implementation and always send `representation: "storage"`.

---

## DO NOT use MCP page tools

> DO NOT publish with `updateConfluencePage` / `createConfluencePage`. Those tools
> only accept `contentFormat` of `html | markdown | adf` — they CANNOT emit
> `storage`. Publishing through them silently degrades the page (Jira datasource
> blockCards collapse to plain paragraphs, TOC macro becomes a bullet list, expand
> / ac:image macros are mangled). This is exactly the v38 regression.

---

## Post-publish verification gate (MANDATORY — every run)

After the PUT, immediately GET the page storage and assert:

```python
# Pseudo-code — run after every PUT
storage = GET /rest/api/content/6568476792?expand=body.storage
assert storage.count('data-datasource') == 2,  "FAIL: datasource cards missing"
for m in re.finditer(r'data-datasource', storage):
    astart = storage.rfind('<a ', 0, m.start())
    pre    = storage[max(0, astart-50):astart]
    assert '<p local-id=' in pre, "FAIL: missing <p local-id/> before card"
for tag in re.finditer(r'<ac:image[^>]*>', storage):
    assert 'ac:align="center"' in tag.group(), "FAIL: image not centered"
```

If any assertion fails: report the specific failure, do NOT mark the run as
successful, and either fix and re-PUT or surface the error to the user.

---

## Publish target

- Space: `~622745edb7e7c7007159b8df` (Fábio Neto — personal space),
  numeric `spaceId` = `3406136357`.
- Parent page: **Notes**, `pageId` = `3541107151`.
- `cloudId`: `talkdesk.atlassian.net`.
- Title (FIXED): `GCN PM Auto Test`.

---

## blockCard wrapper structure (MANDATORY for every Jira datasource card)

Every Jira datasource blockCard MUST be wrapped with empty self-closing paragraphs
carrying fresh `local-id` UUIDs:

```html
<p local-id="<uuid-pre>" />
<a href="..." data-layout="full-width" local-id="<uuid-card>"
   data-card-appearance="block" data-datasource="{...}">...</a>
<p local-id="<uuid-post>" />
```

Attribute order on `<a>` MUST be: `href, data-layout, local-id, data-card-appearance, data-datasource`.
Generate **3 fresh UUID v4s** per card per run. Never reuse local-ids from a previous run.

---

## Storage feature reference

| Feature | Storage format equivalent |
|---------|--------------------------|
| Info/warning panel | `<ac:structured-macro ac:name="info|note|warning">` |
| Jira datasource blockCard | See blockCard wrapper structure above |
| Expand/accordion | `<ac:structured-macro ac:name="expand">` |
| Attachment image | `<ac:image ac:align="center" ac:width="950"><ri:attachment ri:filename="..."/></ac:image>` |
| TOC macro | `<ac:structured-macro ac:name="toc">` inside an expand |
