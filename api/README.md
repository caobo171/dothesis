# DoThesis API (FastAPI)

HTTP surface for the chat-first thesis workspace. It drives the chat **deep agent** (`agent/`), spawns + monitors **auto-approve** runs (`orchestrator/`), and serves projects, uploads, credits, and exports.

> Operating contract: [`../AGENTS.md`](../AGENTS.md). System map: [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md). The method: [`../docs/PIPELINE.md`](../docs/PIPELINE.md).

## Conventions

- **POST-only.** Every endpoint is `@router.post` and the access token rides in the JSON body (read by `deps.current_user`). The single exception is `GET /api/v1/health`. Read filters that used to be query params live in the body. See [`../CLAUDE.md`](../CLAUDE.md).
- No cookie auth: JWT (HS256, signed with `SESSION_SECRET`) or Google ID-token verify. CORS `allow_credentials` is off.

## Routers (`app/routers/`)

- `auth.py` — signup/login/verify, password reset, Google sign-in (`/auth/google`, verify-only), stream tokens.
- `chat_v3.py` — the chat turn. Persists the user message, runs `agent.runtime.stream_turn`, and bridges its events onto SSE (`token`/`progress`/`tool_calls`/`error`/`done`). Charges credits + persists the assistant reply via an idempotent finalizer that also fires on client disconnect. (`chat.py` is the legacy graph path, used only when `DOTHESIS_AGENT_V3` is off.)
- `runs.py` — auto-approve runs: start, list, status, pause/resume/cancel, and `POST /runs/{id}/events` (SSE progress). `job_runner.py` spawns the `python -m orchestrator --auto-draft` subprocess and tails its `events.jsonl` into `JobEvent` + `pubsub`.
- `credit.py` — packages, Polar checkout/webhook, and `transactions` (chat/auto charges, deep-linked back to the thread).
- `uploads.py`, `exports.py`, `m5_editor.py`, `papers.py`, `jobs.py`, `announcements.py`, and the `admin_*.py` routers.

## Persistence

- `projects` — `context_store` JSONB slice columns (`m1_topic … m5_writing`) + `module_status` map + `focus`. `agent_state.py:DbProjectStateStore` maps flat module keys ↔ these columns and is the DB implementation of the `commit_slice` contract.
- `threads` / `messages` — one LangGraph thread per chat; transcript rows carry `module_tag`, `tool_calls_json` (widget hints), and per-turn `cost_credits`/`duration_ms`/`total_tokens`.
- `jobs` (auto runs) + `job_events`, `credit_transactions`, `token_ledger`.
- LangGraph `AsyncPostgresSaver` (chat) / `PostgresSaver` (auto) provide checkpoint/resume.

## Dev

```bash
cd api
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload --port 7100
```

Required env: `DATABASE_URL`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`, `ORCHESTRATOR_ENABLED=true` (mounts chat/runs/exports/uploads/editor and primes the graphs + token-meter sink), `DOTHESIS_AGENT_V3=1` (chat served by the deep agent). Most local work just runs `./dev.sh` from the repo root.

## Test

```bash
pytest          # api/tests
```
