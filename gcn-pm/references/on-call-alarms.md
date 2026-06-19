# On-Call_Alarms — Playwright MCP Section

Owns the On-Call Alarms section.  
Column structure confirmed from the UCInterconnect template (page 5238128641).

---

## Structure (in order)

### 1. Heading
H1: **On-Call Alarms**

---

### 2. Info panel (bullet list — verbatim, tight)

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

---

### 3. Plain link

https://talkdesk.atlassian.net/jira/ops/alerts?view=list&query=responders%3A%225b660e34-8c85-4c01-b3c5-c96d192300cf%22

---

## 4. Alerts evidence via Playwright

### Primary flow

#### 1. Resize browser
- width: 1920
- height: 1080

#### 2. Navigate + auth guard
- wait until URL contains jira/ops/alerts
- retry up to 30s if redirected

#### 3. Normalize layout (critical)

```js
document.body.style.zoom = "50%";

document.body.style.margin = "0";
document.body.style.padding = "0";
document.documentElement.style.margin = "0";
document.documentElement.style.padding = "0";

const root = document.querySelector('#jira, #root, main, body');
if (root) {
  root.style.width = "100vw";
  root.style.maxWidth = "none";
}
```

#### 4. Filter by sprint dates

```js
const start = new Date('SPRINT_STARTT00:00:00');
const end   = new Date('SPRINT_ENDT23:59:59');

const table = document.querySelector('table');
const headers = [...table.querySelectorAll('th')];
const createdIdx = headers.findIndex(h => /created/i.test(h.textContent));

const rows = [...table.querySelectorAll('tbody tr')];

for (const r of rows) {
  const cell = r.querySelectorAll('td')[createdIdx];
  const raw = cell?.textContent?.trim();
  const d = new Date(raw);

  if (isNaN(d) || d < start || d > end) {
    r.style.display = "none";
  }
}

table.setAttribute("data-pm-shot", "1");
```

#### 5. FINAL SCREENSHOT (ONLY ONE)

- FULL PAGE screenshot
- filename: oncall-alerts-{sprint}.png
- target: [data-pm-shot="1"]

---

## Rules

- Only one screenshot
- Must use full page capture
- Zoom 50% required
- No element screenshots
- No scroll manipulation
