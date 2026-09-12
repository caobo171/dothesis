# DoThesis — Next.js frontend

Next.js 15 (App Router) frontend for the DoThesis chat-first thesis assistant. Renders the chat thread + per-module widgets (Card / Grid / ListEditor / FlowChart) streamed by the deep-agent runtime through the FastAPI chat router.

> Current architecture: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). Agent contract: [`../AGENTS.md`](../AGENTS.md). Module focus is an advisory UI/continuity signal, never a router or tool restriction; widgets and context panels must reflect each artifact's owning module.

The legacy per-paper "agent run" / "draft editor" / "citations" views below render output from the DoThesis engine and remain useful for the standalone draft-generator product (see [`../engine/README.md`](../engine/README.md)). They are NOT part of the M1–M5 chat flow.

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

- `app/page.jsx` — entry; routes between Dashboard / Chat / Billing / per-paper view via local state.
- `app/components/`
  - `shared.jsx` — Sidebar, Topbar, Brand, Badge, Card, ProgressBar, KPI
  - `dashboard.jsx` — drafts table + credit card + KPI strip + running highlight
  - `chat/` — chat-based research copilot (M1–M5 module flow, ChatPane, ProjectListGrid). Replaced the legacy wizard surface on 2026-05-27.
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
