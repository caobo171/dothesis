# DoThesis API (FastAPI)

HTTP surface for the chat-first thesis assistant. Wraps the orchestrator agent graph (`orchestrator/`) and exposes the legacy OpenDraft engine (`engine/`) as background jobs.

> Operating contract for the agent graph this API drives is in [`../AGENTS.md`](../AGENTS.md). Architecture brief: [`../researchflow-architecture-brief.md`](../researchflow-architecture-brief.md). Anything that touches `context_store`, routing, or memory MUST be checked against the brief's §1 NON-NEGOTIABLE principles — several are still gaps (see `AGENTS.md`).

## Surfaces

- `POST /projects` / `GET /projects/{id}` — create or fetch a project (the `context_store` root per the brief §2).
- `POST /projects/{id}/import`, `POST /projects/{id}/assess` — entry-wizard data path (`orchestrator/intake.py` `merge_import` / `assess_work`). The brief's full §9 dependency-hole reconciliation depends on `needs_review` status (gap — see `AGENTS.md`).
- `POST /threads`, `POST /threads/{id}/messages` — chat thread + streaming message endpoint. Mounted only when `ORCHESTRATOR_ENABLED=true`.
- `runs.py`, `jobs.py`, `exports.py`, `m5_editor.py`, `papers.py`, `credit.py`, `uploads.py`, `auth.py`, plus the `admin_*.py` routers — billing, exports, file pipeline, OpenDraft engine jobs.

## Persistence

Migration `20260526_add_orchestrator_tables.py` adds the brief's spine:

- `projects` — `current_module`, `field`, `language`, `citation_style`. (Missing `focus` and `status: Record<ModuleId, ModuleStatus>` map per brief §1.4 — gap.)
- `threads` — one LangGraph thread per chat. `langgraph_thread_id` is the checkpoint key.
- `messages` — full transcript (one row per turn), with `module_tag` + `tool_calls_json` for widget render hints.
- `context_store` — JSONB columns `m1_topic | m2_literature | m3_design | m4_analysis | m5_writing`. Updated in place; no `version_history` table yet (brief §2 gap).

The orchestrator additionally uses LangGraph's `PostgresSaver` for resume — note this conflicts with brief §1.3 ("DB is the checkpoint — do NOT reach for a checkpoint framework"). See `AGENTS.md` gap #3.

## Dev

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 7100
```

Required env: `DATABASE_URL`, `GOOGLE_API_KEY` (Gemini), `ORCHESTRATOR_ENABLED=true` to mount the chat router. Optional: `ORCHESTRATOR_ROUTER=v2` to flip the orchestrator graph from supervisor-spokes (v1) to router-agent (v2).

## Test

```bash
pytest
```
