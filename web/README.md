# DoThesis — Next.js frontend

A Next.js 15 (App Router) port of the DoThesis design — the brand-line frontend for the OpenDraft thesis pipeline.

## Run locally

```bash
cd web
npm install
npm run dev      # http://localhost:3000
```

## Build for production

```bash
npm run build
npm start
```

## Structure

- `app/page.jsx` — entry; routes between Dashboard / Wizard / Billing / per-paper view via local state.
- `app/components/`
  - `shared.jsx` — Sidebar, Topbar, Brand, Badge, Card, ProgressBar, KPI
  - `dashboard.jsx` — drafts table + credit card + KPI strip + running highlight
  - `wizard.jsx` — new-thesis brief (topic, level, sources, model, style, language)
  - `paper-shell.jsx` — per-paper header + 4 tabs (Live progress · Draft · Citations · Export)
  - `agent-run.jsx` — hero pipeline view: 6 phases, 19 agents, live activity feed, chapter progress, citation stream
  - `draft-editor.jsx` — serif-typeset thesis with outline rail + citation rail
  - `citations.jsx` — verified / conflicts / rejected / queued
  - `export-tab.jsx` — PDF / DOCX / LaTeX / Markdown + preflight checks + mini preview
  - `billing.jsx` — credit balance, plans, recent runs
  - `icons.jsx` — outline icon set
  - `data.js` — sample paper + 19 agents + 6 phases + citations + activity feed
- `app/globals.css` — design tokens + component styles

All credits are denominated in **credits** (not dollars). The sample paper is *"Algorithmic Decision-Making and Democratic Accountability: A Comparative Study of EU and US Regulatory Frameworks"* (master's thesis, 32 verified citations, 14,820 / 27,000 words).
