# Web ↔ Engine MVP — Design Spec

**Status:** Approved (brainstorming phase complete)
**Date:** 2026-05-23
**Scope:** First slice of OpenDraft as a hosted SaaS. Wires the existing `web/` Next.js template to the existing Python `engine/` pipeline through a new FastAPI service, with auth and S3 storage. Billing is explicitly out of scope and will be its own spec.

---

## 1. Goals and non-goals

### Goals
1. A logged-in user can submit a thesis brief from the Wizard and have the real `engine.draft_generator.generate_draft()` pipeline run end-to-end.
2. The AgentRun page reflects real pipeline progress in real time — live activity feed, phase states, chapter progress.
3. After completion, the user can view the generated draft (read-only), inspect verified citations, and download PDF / DOCX / LaTeX / Markdown / ZIP exports.
4. All artifacts persist in AWS S3 (existing `fillformposts` bucket, `opendraft/` prefix); jobs and users persist in Postgres.
5. The existing engine source is unchanged in spirit. Only a thin `engine/__main__.py` entrypoint is added.
6. The existing `web/` component visual design is unchanged — except the Sidebar drops the Billing and Affiliate entries (one-line edit). Only data sources, routing, and auth are added.

### Non-goals (deferred to future specs)
- Stripe, credit system, paid plans, affiliate program.
- Rich-text draft editing with save-back. MVP is read-only viewer.
- Admin UI, per-org workspaces, quota management UI.
- Multi-region storage, CDN, observability stack.
- Email verification, magic links, password reset flow (basic password auth only).
- Resume-from-checkpoint UI (engine supports it; API/UI deferred).

---

## 2. Architecture

```
┌──────────────┐   HTTPS/SSE   ┌────────────────┐   subprocess   ┌─────────────────────┐
│ Next.js web  │  ───────────► │ FastAPI server │  ────────────► │ engine job process  │
│ (existing UI)│  ◄─────────── │  (api/)        │  ◄──JSONL──    │ draft_generator.py  │
└──────────────┘               └────────────────┘                └─────────────────────┘
                                  │           │                            │
                                  ▼           ▼                            ▼
                              Postgres     AWS S3                   local job workdir
                              (jobs/users)  (drafts, exports)       (artifacts, JSONL)
```

Three deployable units, all in this monorepo:

- **`web/`** — existing Next.js 15 app. Gains an API client, an auth context, real Next.js routing for `/login`, `/signup`, `/wizard`, `/paper/[id]`, and data fetching to replace mock imports.
- **`api/`** — new FastAPI service (Python 3.10+). Owns auth, paper/job CRUD, SSE for live progress, S3-signed download URLs. Imports nothing from `engine/` at runtime — it spawns engine jobs as subprocesses.
- **`engine/`** — existing pipeline. Gains a single new file `engine/__main__.py` that runs `generate_draft()` with a custom tracker/streamer writing to a JSONL events file, and uploads artifacts to S3 on completion.

Local development: real AWS S3 is used directly (no MinIO). Postgres is user-provided (local docker, Neon, Supabase, etc. — `DATABASE_URL` set in `.env`). A single `dev.sh` at the repo root starts the FastAPI service with `uvicorn --reload` and the Next.js dev server.

---

## 3. API surface (FastAPI)

All routes mounted under `/api/v1`. Auth via httpOnly secure session cookie (`opendraft_session`). JSON request/response except SSE.

### Auth
```
POST   /auth/signup           { email, password }             → 201 { user }
POST   /auth/login            { email, password }             → 200 { user }   (+ Set-Cookie)
POST   /auth/logout                                            → 204            (+ clear cookie)
GET    /auth/me                                                → 200 { user } | 401
```

### Papers
```
GET    /papers                                                 → 200 [{ id, title, level, status, progress, updated_at, discipline }]
POST   /papers                { topic, research_question,     → 201 { paper_id, job_id }
                                academic_level, language,
                                model, citation_style,
                                sources: { crossref: bool, ... },
                                tone }
GET    /papers/:id                                             → 200 { paper, latest_job }
```

### Jobs
```
GET    /jobs/:id                                               → 200 { id, paper_id, status, phase, progress, started_at, finished_at, error_text }
GET    /jobs/:id/events?since=<event_id>   (SSE)               → text/event-stream of activity events
POST   /jobs/:id/cancel                                        → 202
```

### Draft, citations, exports
```
GET    /papers/:id/draft                                       → 200 { markdown, html, word_count, chapters: [{num, title, words}] }
GET    /papers/:id/citations                                   → 200 [{ key, title, authors, year, doi, source, venue, verified }]
GET    /papers/:id/exports                                     → 200 [{ format, size, generated_at }]
GET    /papers/:id/exports/:format                             → 302 to signed S3 URL  (format ∈ pdf | docx | tex | md | zip)
```

### SSE event shape
Each `data:` line is a single JSON object:
```json
{ "id": 142, "type": "activity",        "phase": "compose", "agent": "Crafter · Discussion",
  "text": "Drafted paragraph on EU AI Act Article 5 prohibitions (218 words)", "ts": "2026-05-23T10:14:31Z" }
{ "id": 143, "type": "phase_progress",  "phase": "compose", "progress": 0.68, "active_agents": ["Crafter · Discussion", "Crafter · Results"] }
{ "id": 144, "type": "job_done",        "exports": ["pdf", "docx", "tex", "md", "zip"] }
{ "id": 145, "type": "error",           "phase": "compose", "text": "RateLimitError: ...", "traceback": "..." }
```

These exactly match what the existing `AgentRun` component already renders.

### Errors
Standard JSON: `{ "error": { "code": "string", "message": "string" } }`. HTTP status reflects category (`400`/`401`/`403`/`404`/`409`/`422`/`429`/`500`).

### Quotas (hard-coded for MVP)
`POST /papers` enforces:
- `MAX_RUNNING_JOBS_PER_USER = 1` — returns `409 already_running` if exceeded.
- `MAX_JOBS_PER_DAY = 3` per user, counted in UTC calendar days — returns `429 daily_quota` if exceeded.

No UI surfaces these counters in the MVP. They become real with the billing spec.

---

## 4. Data model (Postgres)

Five tables, kept narrow on purpose.

### `users`
| col            | type                     | notes                  |
|----------------|--------------------------|------------------------|
| id             | uuid pk                  |                        |
| email          | text unique not null     | citext, lowercased     |
| password_hash  | text not null            | bcrypt                 |
| created_at     | timestamptz default now()|                        |

### `sessions`
| col          | type                      | notes                 |
|--------------|---------------------------|-----------------------|
| id           | uuid pk                   | also the cookie value |
| user_id      | uuid fk users(id) cascade |                       |
| expires_at   | timestamptz not null      | 30-day rolling        |
| ip           | inet                      |                       |
| created_at   | timestamptz default now() |                       |

### `papers`
| col                 | type                      | notes                                |
|---------------------|---------------------------|--------------------------------------|
| id                  | uuid pk                   |                                      |
| user_id             | uuid fk users(id) cascade |                                      |
| topic               | text not null             | working title                        |
| research_question   | text                      |                                      |
| academic_level      | text not null             | research \| bachelor \| master \| phd |
| language            | text not null             | e.g. "en-US", "de"                   |
| citation_style      | text not null             | apa \| ieee \| mla \| chicago \| harvard |
| tone                | text                      |                                      |
| model               | text not null             | gemini-flash \| claude-sonnet \| ... |
| sources_json        | jsonb not null            | `{ crossref: true, ... }`            |
| status              | text not null             | draft \| running \| done \| failed   |
| latest_job_id       | uuid                      | nullable, denormalized for list view |
| created_at          | timestamptz default now() |                                      |
| updated_at          | timestamptz default now() |                                      |

### `jobs`
| col          | type                      | notes                                       |
|--------------|---------------------------|---------------------------------------------|
| id           | uuid pk                   |                                             |
| paper_id     | uuid fk papers(id) cascade|                                             |
| status       | text not null             | queued \| running \| done \| failed \| canceled |
| phase        | text                      | research \| structure \| compose \| qa \| compile \| export |
| progress     | float                     | 0..1, overall                               |
| pid          | int                       | OS pid of subprocess                        |
| workdir      | text                      | local path holding `events.jsonl` + artifacts |
| events_processed | int default 0         | count of `events.jsonl` lines already ingested; recovery cursor |
| started_at   | timestamptz               |                                             |
| finished_at  | timestamptz               |                                             |
| error_text   | text                      |                                             |

### `job_events`
Append-only activity feed. Indexed on `(job_id, id)` for cheap SSE replay.
| col       | type                      | notes                                            |
|-----------|---------------------------|--------------------------------------------------|
| id        | bigserial pk              | monotonic per-row, used as SSE `since` cursor    |
| job_id    | uuid fk jobs(id) cascade  |                                                  |
| ts        | timestamptz default now() |                                                  |
| type      | text not null             | activity \| phase_progress \| job_done \| error  |
| phase     | text                      |                                                  |
| agent     | text                      |                                                  |
| text      | text                      |                                                  |
| meta_json | jsonb                     | for typed payloads (progress, exports list, ...) |

### S3 layout
The bucket is the existing AWS S3 bucket `fillformposts` in `ap-southeast-1` (shared infrastructure). All OpenDraft objects live under a top-level `opendraft/` prefix to keep them isolated from other tenants of the bucket.
```
s3://fillformposts/opendraft/users/{user_id}/papers/{paper_id}/jobs/{job_id}/
    exports/draft.pdf
    exports/draft.docx
    exports/draft.tex
    exports/draft.md
    exports/bundle.zip
    research/...     (combined_research.md, bibliography.json, papers/*)
    drafts/...       (per-chapter markdown)
```

---

## 5. Engine integration

The engine source is not refactored. The integration lives in a single new file: `engine/__main__.py`.

### `engine/__main__.py`
```
python -m engine \
    --job-id <uuid> \
    --paper-id <uuid> \
    --workdir /var/lib/opendraft/jobs/<uuid> \
    --brief-json /var/lib/opendraft/jobs/<uuid>/brief.json
```

Behavior:
1. Reads `brief.json` (the request body sent to `POST /papers`).
2. Constructs a `JobTracker` and `JobStreamer` whose every call appends one JSON line to `{workdir}/events.jsonl`. Each line is a dict matching the SSE event shape above. File is opened in line-buffered append mode and `flush()`ed after each write so the API can tail it without races.
3. Calls `generate_draft(topic=..., language=..., academic_level=..., citation_style=..., tracker=JobTracker, streamer=JobStreamer, output_dir=Path(workdir))`.
4. On success: uploads `{workdir}/exports/*`, `research/`, `drafts/` to S3 under the layout above. Appends a final `{"type":"job_done","exports":[...]}` line. Exits 0.
5. On failure: appends `{"type":"error","text":<message>,"traceback":<tb>}`. Exits non-zero.

S3 credentials are read from env vars (`AWS_REGION`, `S3_BUCKET`, `S3_PREFIX`, `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`) using the standard AWS endpoint.

### FastAPI subprocess lifecycle
- `POST /papers` inserts `papers` and `jobs` rows (`status=queued`), writes `brief.json` into `workdir`, then `subprocess.Popen(["python", "-m", "engine", ...])`. Updates `jobs` with `pid` and sets `status=running`.
- A `JobMonitor` background task (one per running job) tails `events.jsonl`:
  - For each new line, inserts a row into `job_events`, updates `jobs.phase`/`progress` if applicable, and increments `jobs.events_processed` atomically.
  - Notifies any active SSE subscribers via in-process pubsub keyed by `job_id`.
- `POST /jobs/:id/cancel` sends `SIGTERM` to `pid`, then marks the job `canceled` after the process exits (or after a 30s grace, then `SIGKILL`).
- On API restart: scan `jobs` where `status=running`, check `pid` still alive via `os.kill(pid, 0)`. If alive, resume tailing `events.jsonl` by reopening the file and skipping the first `events_processed` lines, then continuing from there. If dead, mark `failed`.

### SSE endpoint
`GET /jobs/:id/events?since=<event_id>`:
1. Query `job_events` where `job_id=:id and id>:since order by id` — replay backlog.
2. Subscribe to in-process pubsub for new events on this `job_id`.
3. On unsubscribe (client disconnect), clean up.
4. Heartbeat comment line every 15s to keep proxies happy.

---

## 6. Frontend changes (Next.js)

All visual design unchanged. Only data sources, routing, and auth are added.

### New files
- **`web/app/lib/api.js`** — `apiFetch(path, opts)` (adds JSON headers + credentials), `apiSSE(path, onEvent)` (wraps `EventSource`, surfaces `since` cursor for reconnect).
- **`web/app/lib/auth-context.jsx`** — React context exposing `useAuth() → { user, login, signup, logout }`.
- **`web/middleware.js`** — redirects unauthenticated requests to `/login` for protected routes.
- **`web/app/login/page.jsx`**, **`web/app/signup/page.jsx`** — minimal pages reusing existing `Card`/`Field` styles.
- **`web/app/wizard/page.jsx`** — wraps the existing `Wizard` component.
- **`web/app/paper/[id]/page.jsx`** — wraps `PaperShell` and reads tab from `?tab=`.

### Modified files
- **`web/app/page.jsx`** — becomes the Dashboard route (`/`), reading `useSWR('/papers')` instead of mock `RECENT_DRAFTS`. The hand-rolled `route` `useState` switch is replaced by real Next.js routing.
- **`web/app/components/shared.jsx`** — `Sidebar` drops Billing and Affiliate entries.
- **`web/app/components/dashboard.jsx`** — accepts papers prop or fetches `/papers`. Empty state for new users.
- **`web/app/components/wizard.jsx`** — "Start agent pipeline" button calls `POST /papers` with the brief, then `router.push('/paper/{id}?tab=run')`. Loading state on the button.
- **`web/app/components/agent-run.jsx`** — replaces `NEW_FEED_LINES` and mock `phaseStates` with `apiSSE('/jobs/{id}/events')`. The existing `feed`, `phaseStates`, `tick` state shapes are preserved. `phase_progress` events drive the phase map; `activity` events push into `feed`; `job_done` flips a banner; `error` flips an error banner.
- **`web/app/components/citations.jsx`** — fetches `/papers/:id/citations`.
- **`web/app/components/draft-editor.jsx`** — fetches `/papers/:id/draft`, renders `html` read-only with the existing typography styles. Save/edit affordances guarded by a `READ_ONLY = true` flag.
- **`web/app/components/export-tab.jsx`** — fetches `/papers/:id/exports`, download buttons link to `/api/v1/papers/:id/exports/:format`.

### Deletions
- `web/app/components/data.js` is removed once all consumers migrate. Until then, it stays as a typed stub for components mid-migration.

---

## 7. Repository layout (after this spec lands)

```
opendraft/
├── api/                       # NEW — FastAPI service
│   ├── app/
│   │   ├── main.py            # FastAPI app + router includes
│   │   ├── auth.py            # signup/login/logout/me, session cookie
│   │   ├── papers.py          # papers CRUD + job submission
│   │   ├── jobs.py            # job status, SSE, cancel
│   │   ├── exports.py         # signed download URLs
│   │   ├── db.py              # SQLAlchemy models + session
│   │   ├── s3.py              # S3 client (boto3), prefix-locked to S3_PREFIX
│   │   ├── job_monitor.py     # tails events.jsonl, in-process pubsub
│   │   ├── quotas.py          # MAX_RUNNING_JOBS_PER_USER, MAX_JOBS_PER_DAY
│   │   └── settings.py
│   ├── migrations/            # Alembic
│   ├── pyproject.toml
│   └── Dockerfile
├── engine/
│   ├── __main__.py            # NEW — subprocess entrypoint
│   └── ... (unchanged)
├── web/
│   ├── app/
│   │   ├── lib/api.js         # NEW
│   │   ├── lib/auth-context.jsx # NEW
│   │   ├── login/page.jsx     # NEW
│   │   ├── signup/page.jsx    # NEW
│   │   ├── wizard/page.jsx    # NEW
│   │   ├── paper/[id]/page.jsx # NEW
│   │   ├── page.jsx           # MODIFIED (dashboard route)
│   │   └── components/        # MODIFIED (no visual changes)
│   ├── middleware.js          # NEW
│   └── ... (unchanged)
├── dev.sh                     # MODIFIED — starts api (uvicorn) + web (next dev)
└── docs/superpowers/specs/2026-05-23-web-engine-mvp-design.md  (this file)
```

---

## 8. Local development

`dev.sh` starts the FastAPI service with `uvicorn --reload` and `npm run dev` for Next.js. Alembic migrations run on API startup.

Postgres is user-provided — any reachable `DATABASE_URL` works (local docker, Neon, Supabase, RDS). The other credentials are sourced from the existing `survify-backend/.env` to avoid provisioning new services.

Required env vars (loaded from `.env` at the repo root):

| Var | Value source | Notes |
|---|---|---|
| `DATABASE_URL` | user-provided | e.g. `postgresql+psycopg://opendraft:opendraft@localhost:5432/opendraft` |
| `AWS_REGION` | `survify-backend/.env` (`AWS_REGION`) | `ap-southeast-1` |
| `S3_BUCKET` | `survify-backend/.env` (`BUCKET_NAME`) | `fillformposts` (shared bucket) |
| `S3_PREFIX` | new constant | `opendraft/` — isolates this project's objects |
| `AWS_ACCESS_KEY` | `survify-backend/.env` (`AWS_ACCESS_KEY`) | |
| `AWS_SECRET_KEY` | `survify-backend/.env` (`AWS_SECRET_KEY`) | |
| `SESSION_SECRET` | reuse `JWT_ENCODE_USER_KEY` from survify .env, or generate fresh | signs session cookie |
| `GEMINI_API_KEY` | `survify-backend/.env` | passed through to engine subprocesses |
| `OPENAI_API_KEY` | `survify-backend/.env` | passed through to engine subprocesses |
| `ANTHROPIC_API_KEY` | user-provided | optional; needed for Claude models in the wizard |

The S3 bucket `fillformposts` is shared with other products — all OpenDraft writes must go under the `opendraft/` prefix and must never list / delete anything outside it. The S3 client wrapper enforces this prefix on every call.

---

## 9. Testing strategy

- **API unit tests** (`api/tests/`): auth flow, quota enforcement, paper/job state transitions, SSE event replay logic. Postgres via testcontainers; S3 via moto.
- **Engine smoke test**: `python -m engine` against a tiny brief with a stub model that returns canned text — verifies `events.jsonl` is produced and parseable. Already-existing engine tests stay as-is.
- **Web integration**: a Playwright test that signs up, submits a brief, mocks the SSE stream, and asserts the AgentRun page updates. Uses MSW to stub the API.
- **Manual gate**: one full real-engine run end-to-end with `gemini-flash` before declaring the slice complete.

---

## 10. Open questions for the implementation plan

Not blockers, but the implementation plan should resolve them:
- Should `engine/__main__.py` upload artifacts incrementally (per-phase) or only on completion? Incremental allows partial recovery and earlier "Export PDF" availability for the abstract, but adds S3 calls. Default proposal: only on completion for MVP.
- SSE reconnect: do we accept the small risk of duplicate events if the client reconnects mid-batch, or do we strict-dedupe by `id` on the client? Default: client dedupes.
- Engine subprocess concurrency limit at the API level. With `MAX_RUNNING_JOBS_PER_USER = 1` and a small user base this is naturally bounded, but a global cap should be a config knob.

---

**End of spec.**
