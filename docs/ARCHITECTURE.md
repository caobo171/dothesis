# DoThesis — System Architecture

This is the system map for the current DoThesis product: a chat-first thesis workspace built as **one deep agent driven by skills**, plus an unattended **Auto Thesis** path that drives the same agent. For the agent contract and invariants see [`../AGENTS.md`](../AGENTS.md); for the step-by-step method see [`PIPELINE.md`](PIPELINE.md).

> Historical design docs (the v1/v2 LangGraph orchestration foundation, the per-feature SP plans/specs, and the dated `architecture/2026-*` files) are kept as point-in-time records and are superseded by this document.

---

## Components

| Layer | Path | Responsibility |
|-------|------|----------------|
| **Web** | `web/` | Next.js 15 chat workspace: project sidebar, module tracker, chat pane, Context store panel, Auto Thesis modal + drawer, credits/transactions, editor. |
| **API** | `api/` | FastAPI gateway. **POST-only** (auth token in the JSON body; `/api/v1/health` is the lone GET). Auth (JWT + Google), projects/threads/messages, uploads, credits, chat SSE, auto-runs, exports. |
| **Chat agent** | `agent/` | The deep-agent runtime (`deepagents`): builds the agent, streams a turn, exposes the tools. Serves chat when `DOTHESIS_AGENT_V3=1`. |
| **Skills** | `skills/` | Domain knowledge as SKILL.md files: routing + state protocol (`dothesis`), entry wizard (`dothesis-bootstrap`), and M1–M5. Mounted read-only at `/skills/`. |
| **Auto Thesis** | `agent/headless.py` + `api/app/headless_entry.py` | Drives the SAME deep agent to roadmap completion with no human present. Budgets are data the caller passes. |
| **Composition library** | `orchestrator/` | No longer a runtime — its LangGraph layer was deleted 2026-08-20. Remains the M5 chapter composer + export, literature search, backfill, and the token meter. |
| **Engine** | `engine/` | Research + writing muscle: literature-search APIs, citation cascade, draft pipeline, DOCX/PDF rendering. Also a standalone CLI. |
| **Data** | Postgres · S3 | `context_store` slice columns, projects/threads/messages, jobs (runs) + job_events, credit ledger, token ledger. S3 holds uploads + exports. |

---

## Request topology

- The browser holds a JWT (from email/password or Google sign-in) in `tokenStore` and sends it in the **body** of every POST. There is no cookie auth; CORS `allow_credentials` is off.
- Streaming endpoints (chat, run events) are **POST** and consumed via `fetch` + `ReadableStream`. The web client targets `NEXT_PUBLIC_API_BASE` (the API origin) directly, because the Next dev proxy buffers `text/event-stream`.
- `api/app/main.py` mounts routers under `/api/v1`. Chat/runs/exports/uploads/editor mount only when `ORCHESTRATOR_ENABLED=true`, which also warms the shared async Postgres pool (`app/db.py:get_async_pool`, the chat checkpointer's) and registers the token-meter DB sink at startup.

---

## State model

The **`context_store`** is the single source of truth, scoped to a *project* (shared by all of its chat threads).

- **Shape:** flat keys per module (e.g. `research_title`, `literature_sources`, `analysis_results`, `chapters`) grouped into slices `m1_topic … m5_writing`. Persisted as JSONB slice columns on the project, with `projects.module_status` (`locked`/`in_progress`/`done`/`needs_review`) and `projects.focus` as fast-read derivations.
- **Only write path:** `commit_slice(module, patch, reason, confirm_done?)`. It validates that the patch only touches keys the module owns, snapshots a version, applies the patch, shifts focus, and flags downstream modules `needs_review` along the dependency DAG (M1→M2..M5, M2→M3..M5, M3→M4,M5, M4→M5) — but only modules that have already started.
- **Reads** (`read_slice`) never mutate.

Stores: `agent/state.py:ProjectStateStore` (file-backed, CLI/tests) and `api/app/agent_state.py:DbProjectStateStore` (Postgres). Both honor the same contract.

---

## The two execution paths

### 1. Interactive chat (deep agent)
`POST /api/v1/threads/{id}/messages` → `chat_v3.send_message_v3`:
- Persists the user message, gets/builds the per-project cached agent (deepagents over an `AsyncPostgresSaver` checkpointer), materializes any attachments.
- Streams `agent/runtime.py:stream_turn` events, multiplexed with engine progress, onto SSE: `token`, `progress` (tool activity → live ProgressBubble), `tool_calls` (interactive widgets), `error`, `done`.
- An idempotent `_finalize()` persists the assistant message and charges credits — and runs on disconnect too, so a browser reload saves the partial reply and stops the agent (no orphaned token burn).

### 2. Auto Thesis (headless deep agent, subprocess)
`POST /api/v1/projects/{id}/runs` → `job_runner.spawn_headless_run`:
- Spawns `python -m app.headless_entry` with `params["mode"] = "full_thesis"`; an async monitor tails the run's `events.jsonl` into `JobEvent` + `pubsub`.
- It is the SAME deep agent chat uses, driven with no human present (`agent/headless.py`): the runner plays the student's part, and budgets (turns / wall clock / stalls) are data the caller passes, never something the agent sees.
- The drawer streams progress via `POST /api/v1/runs/{id}/events`; controls are pause/resume, cancel, and retry. Resume does NOT re-enter a checkpoint — there is none. Durable progress is whatever `commit_slice` persisted, so resuming runs a fresh agent over that state; a module in flight but uncommitted is redone.

> Until 2026-08-20 this path ran a separate LangGraph supervisor graph
> (`python -m orchestrator --auto-draft`). That layer is deleted; `orchestrator/`
> survives as a library (tools, backfill, llm, token_meter, agents/base).

`langgraph.json` exists only for `langgraph dev` (Studio) via `dev.sh`; no deployment reads it.

---

## External services

- **LLM:** Google Gemini (`gemini-2.5-flash` default); Anthropic Claude when `ANTHROPIC_API_KEY` is set.
- **Literature:** CrossRef, OpenAlex, Semantic Scholar, arXiv, plus DataForSEO / Gemini-grounded search (engine citation cascade).
- **Storage:** S3 (uploads + exported DOCX/PDF). **Email:** AWS SES (verification + password reset). **Auth:** Google Identity Services (verify-only ID token). **Tracing:** LangSmith (optional). **Payments:** Polar (credits top-up).

---

## Conventions

- **POST-only HTTP** (see [`../CLAUDE.md`](../CLAUDE.md)). New routes are `@router.post`; read filters live in the body.
- **Comment the reasoning** for non-obvious changes.
- **Behavior lives in skills.** Both paths run the same agent, so there is one place to change behavior: the relevant `skills/*/SKILL.md`. Change the skill first, code second.
