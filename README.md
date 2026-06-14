<h1 align="center">DoThesis — Chat-First AI Thesis Workspace</h1>

<p align="center">
  <b>A commercial, chat-first product that takes a student from a blank topic to a finished, citation-grounded thesis — one conversation, five guided modules, real verified sources.</b>
</p>

> **Orientation for contributors.** DoThesis is built as a **single deep agent driven by skills** (LangChain `deepagents`). The student chats with one agent that moves freely across five thesis modules (M1–M5); all decisions land in a project-scoped `context_store` with deterministic read/mutate propagation. There is also a one-click **"Auto approve"** mode that writes the whole thesis end-to-end unattended.
>
> Before changing the agent runtime, skills, state shape, or the API, read **[`AGENTS.md`](AGENTS.md)** (agent contract + invariants) and **[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)** (system map). The end-to-end method is in **[`docs/PIPELINE.md`](docs/PIPELINE.md)**.
>
> The repo also contains the original open-source **19-agent draft-generator CLI** under `engine/`. It is still maintained and, more importantly, it is the **research + writing muscle** the agent calls through its tools (literature search, reference parsing, document export). See [`engine/README.md`](engine/README.md).

---

## What DoThesis does

A thesis is not one prompt. DoThesis breaks the work into **five modules**, each owning a slice of the project state, and the agent guides the student through them in plain conversation:

| Key | Module | What it produces (owned `context_store` keys) |
|-----|--------|-----------------------------------------------|
| **M1** | Topic Discovery | `research_title`, `research_questions` |
| **M2** | Literature Review | `literature_sources` (verified), `research_gaps` |
| **M3** | Research Design | `conceptual_model`, `hypotheses`, `methodology`, `instrument` |
| **M4** | Data Analysis | `analysis_outline`, `analysis_results` (real stats, never invented) |
| **M5** | Writing | `final_sections` / `chapters` → exported DOCX + PDF |

Two ways content gets produced:

1. **Guided chat** — the student talks to the agent turn by turn. The agent reads the relevant skill, proposes options (rendered as clickable cards / editable models), and commits each decision to the project state. Soft guidance, never hard walls — the student can jump modules.
2. **Auto approve** — one button runs the whole M1→M5 pipeline unattended (a detached `orchestrator` subprocess), composes all six chapters, compiles citations, and renders DOCX + PDF. Progress streams live into the run drawer.

Core guarantees:

- **No fabricated sources.** Every paper comes through the engine's literature search / reference parser and is verified against CrossRef, OpenAlex, Semantic Scholar, and arXiv.
- **No invented statistics.** M4 only reports numbers computed by a whitelisted `run_stats` tool on the student's uploaded data — it never makes up β/R²/AVE.
- **One source of truth.** The project `context_store` is shared across every chat thread of a project; the only write path is `commit_slice`, which validates ownership and propagates `needs_review` flags downstream.

---

## Architecture at a glance

```
┌────────────┐   POST /api/v1 (SSE chat, runs, projects, credits, uploads)
│  web/      │ ───────────────────────────────────────────────► ┌────────────┐
│ Next.js 15 │ ◄─── token / progress / tool_calls / done (SSE) ── │  api/      │
│ chat UI    │                                                    │  FastAPI   │
└────────────┘                                                    └─────┬──────┘
                                                                        │
                   chat turn (DOTHESIS_AGENT_V3=1)                      │ auto run
                   ┌────────────────────────────────┐                  │ (subprocess)
                   ▼                                 │                  ▼
            ┌──────────────┐   reads /skills/   ┌────┴─────┐   ┌──────────────────┐
            │  agent/      │ ◄───────────────── │ skills/  │   │  orchestrator/   │
            │ deepagents   │   commit_slice ──► │ M1–M5 +  │   │ LangGraph auto   │
            │ runtime+tools│                    │ routing  │   │ graph (M1–M5)    │
            └──────┬───────┘                    └──────────┘   └────────┬─────────┘
                   │  research_scout / parse_reference / run_stats / export_docx
                   ▼                                                    ▼
            ┌─────────────────────────────────────────────────────────────────┐
            │  engine/  — literature search + citations + draft/export muscle  │
            └─────────────────────────────────────────────────────────────────┘
                   │
                   ▼
            Postgres (context_store slices, threads, messages, jobs, credits)  ·  S3 (uploads, exports)
```

- **`web/`** — Next.js 15 chat workspace (project sidebar, module tracker, Context store panel, Auto-approve drawer, credits/transactions).
- **`api/`** — FastAPI. **POST-only** (the auth token rides in the JSON body; only `/api/v1/health` is GET). Serves chat SSE (`routers/chat_v3.py`), auto-runs (`routers/runs.py`), projects/threads/uploads/credits.
- **`agent/`** — the deep-agent runtime: `runtime.py` (`create_deep_agent` factory + `stream_turn` SSE event stream), tools (`research_scout`, `parse_reference`, `run_stats`, `export_docx`, state tools).
- **`skills/`** — the source of truth for module behavior: `dothesis/` (routing + state protocol, read first), `dothesis-bootstrap/` (entry wizard), and `dothesis-m1-topic` … `dothesis-m5-writing`.
- **`orchestrator/`** — the **auto-mode brain**. `python -m orchestrator --auto-draft` runs the LangGraph M1→M5 graph for Auto-approve runs, and its M5 composer + `tools/m5_writing.py` render the final document.
- **`engine/`** — the research/writing engine (literature APIs, citation cascade, draft pipeline, DOCX/PDF export) behind the agent's tools.

Full map: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Local development

### Prerequisites
- Python 3.13 (the API venv) · Node 18+ · PostgreSQL (local on port 5499 per the default `DATABASE_URL`)
- A Google Gemini API key (default model is `gemini-2.5-flash`). Claude is used automatically if `ANTHROPIC_API_KEY` is set.
- Optional but recommended for real exports: `pandoc` + LibreOffice (DOCX/PDF rendering).

### Run the stack
```bash
cp .env.example .env   # then fill in keys (see below)
./dev.sh               # starts API (:7100), web (:3006), and (optional) LangGraph Studio (:8123)
```
`dev.sh` exports `.env` to all subprocesses, wipes `web/.next` for a clean boot, and runs `uvicorn` with `--reload`. Open **http://localhost:3006**.

> Don't run `next build` while `dev.sh`'s `next dev` is up — it serves stale UI.

### Key environment variables
| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | Postgres (default `postgresql+psycopg://dothesis:dothesis@localhost:5499/dothesis`) |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | LLM (Gemini 2.5 Flash default) |
| `ANTHROPIC_API_KEY` | Optional — switches the agent to Claude when set |
| `DOTHESIS_AGENT_V3` | `1` = chat served by the deep agent (current default) |
| `ORCHESTRATOR_ENABLED` | `true` = mount chat/runs/exports/uploads routers + prime graphs |
| `NEXT_PUBLIC_API_BASE` | Browser → API base, e.g. `http://localhost:7100/api/v1` (SSE hits this directly to bypass the dev proxy's buffering) |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` / `DOTHESIS_GOOGLE_CLIENT_ID` | Google sign-in (must share the same client id) |
| `S3_BUCKET` / `AWS_*` | Upload + export storage |
| `DATAFORSEO_LOGIN` / `_PASSWORD`, `ENABLE_SEMANTIC_SCHOLAR` | Literature search backends |
| `LANGSMITH_*` | Optional tracing |
| `ORCHESTRATOR_AUTOFILL_MAX_SECONDS` | Wall-clock cap for an auto-mode module fill (default 60s) |

---

## How a chat turn works (the short version)

1. The browser POSTs the message to `/api/v1/threads/{id}/messages`; the API streams SSE back.
2. The agent reads the `dothesis` routing skill, then the relevant module skill, and works the turn — emitting `token`, `progress` (tool activity, shown as plain-language beats), and `tool_calls` (interactive widgets) events.
3. Every decision is persisted via `commit_slice`, which updates the project state and flags downstream modules for review.
4. On completion the assistant message is persisted and the turn is metered (credits). If the student reloads mid-turn, the agent is stopped and the partial reply is saved.

Details and the Auto-approve run flow: [`docs/PIPELINE.md`](docs/PIPELINE.md).

---

## The open-source engine (`engine/`)

The original DoThesis CLI — a 19-agent draft generator with verified citations and PDF/DOCX/LaTeX export — lives in `engine/` and is documented in [`engine/README.md`](engine/README.md). It runs standalone *and* powers the agent's `research_scout`, `parse_reference`, and document-export tools. It is MIT-licensed.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). When you change code, follow the repo conventions: **POST-only endpoints**, **comment the reasoning** behind non-obvious changes, and put behavioral changes for a module in its **skill** first. Maintainer push/auth: [`docs/MAINTAINER_PUSH_RUNBOOK.md`](docs/MAINTAINER_PUSH_RUNBOOK.md).

## Links
- License: [MIT](LICENSE)
- Changelog: [CHANGELOG.md](CHANGELOG.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) · Agent contract: [`AGENTS.md`](AGENTS.md) · Method: [`docs/PIPELINE.md`](docs/PIPELINE.md)
