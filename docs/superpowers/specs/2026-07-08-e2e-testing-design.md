# E2E Testing Harness (Playwright)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation:** Hard prerequisite for the F1–F13 feature wave. Each of those features must be
validated against real user journeys, not just unit tests — this spec creates the harness
they will all extend (one new fixture + one new spec file per feature).

## Problem

DoThesis has **zero real end-to-end tests**. Nothing anywhere drives a browser against the
running product:

- No Playwright/Cypress config exists in the repo.
- The two existing workflows (`.github/workflows/live-validation.yml`, `quality.yml`) are
  **stale** — they reference a root `requirements.txt` / `engine` / root `tests/` layout that
  predates the current `api/` + `agent/` + `web/` architecture, and neither drives a browser.
- The pytest suite (`api/tests/`) covers routers and stores in isolation; the vitest suite
  (`web/`) covers components against MSW mocks. Neither proves that a signup → chat →
  commit_slice → export journey works when all the pieces run together.

The gaps this causes are concrete: the `[OPTIONS]` / `[PAPERS]` / `{{cite: …}}` marker
pipeline (agent → SSE → widget) has broken silently before (Gemini 3.x list-content regression,
fixed in `agent/runtime.py:_text_content`), the export path spans four layers
(tool → engine → S3 → signed-URL download), and auth is a bespoke body-token design
(`CLAUDE.md` POST-only convention) that no test exercises through a real browser.

The blocker to writing E2E tests has always been the LLM: real completions are slow,
non-deterministic, and cost money. This design removes the LLM from the deterministic tier
while keeping **everything else real** — real Postgres, real FastAPI, real Next.js, real
deepagents tool loop, real `commit_slice` writes, real DOCX/PDF export.

## Goals

- **Playwright + TypeScript harness in `web/e2e/`** with four journey suites: onboarding,
  M1→M5 progression, export, auth/billing.
- **Hermetic environment per run:** ephemeral Postgres (Docker) + ephemeral MinIO (S3 API)
  + Alembic migrations + FastAPI (`uvicorn app.main:app`) + Next.js (`next dev`) — booted
  and torn down by the harness itself, never touching the developer's `dev.sh` stack.
- **Scripted mock LLM** behind `DOTHESIS_E2E_MOCK=1`: a `FakeChatModel` that replays
  per-scenario JSON fixtures. It emits real marker syntax (`[OPTIONS]`, `{{cite: …}}`) and
  real LangChain tool-call blocks, so the deepagents loop executes **real tools** against the
  **real store/DB** — only the text generation is fake.
- **Body-token auth handled once** in a Playwright setup project: real signup + login against
  the API, token injected into `localStorage` (+ the `dothesis_access_token` cookie mirror
  that `web/proxy.js` gates on) via `storageState`, so journey suites start logged in.
- **Two CI tiers** in a new `.github/workflows/e2e.yml`: mocked (all suites, deterministic,
  free, every PR to `master`) and live (small smoke set against a real cheap model,
  nightly/manual, secret-gated like `live-validation.yml`).
- **Extension contract:** adding an E2E scenario for a future feature = one fixture JSON +
  one spec file, documented in `web/e2e/README.md`.

## Non-goals

- **Do not touch or depend on `dev.sh`.** Developers run `dev.sh` (`next dev` on 3006,
  uvicorn on 7100, the `dothesis-postgres` compose service on 5499) and must never run
  `next build` alongside it (`project_dev_server` memory). The E2E harness runs entirely
  separate processes on its own ports (API 7143, web 3106, Postgres 55432, MinIO 9123) with
  its own containers (`dothesis-e2e-pg`, `dothesis-e2e-minio`) and its own `.next`-equivalent
  lifecycle — orthogonal to the dev stack; both can run at the same time.
- **Do not retire the stale workflows.** `live-validation.yml` and `quality.yml` stay
  untouched; retiring/replacing them is a follow-up cleanup once `e2e.yml` has proven itself.
- **No visual-regression / screenshot-diff testing.** Assertions are semantic (testids,
  roles, text), not pixels.
- **No load/perf testing, no mobile browsers.** One Chromium project.
- **No qualitative flows.** DoThesis is quantitative-only (SmartPLS/SPSS/AMOS); fixtures
  script quantitative journeys.
- **Not a replacement for unit tests.** The mock model's own matching logic gets pytest
  coverage, but router/store behavior stays covered where it is today.

## Design

### Directory layout

```
web/
  playwright.config.ts          # webServer array + projects + env plumbing
  e2e/
    run-e2e.sh                  # entrypoint: containers up → migrate → playwright test → teardown
    auth.setup.ts               # Playwright "setup" project: seed users, write storageState
    lib/api.ts                  # tiny typed helpers for the POST-only API
    fixtures/
      onboarding.json
      m1-to-m5.json
      export.json               # auth/billing needs no fixture (no chat turn involved)
    tests/
      smoke.spec.ts             # stack-boots sanity (kept — cheapest failure signal)
      onboarding.spec.ts
      m1-to-m5.spec.ts
      export.spec.ts
      auth-billing.spec.ts
      live-smoke.spec.ts        # @live tier only
    .auth/                      # storageState + seeded credentials (gitignored)
    .work/                      # JOB_WORKDIR_ROOT for the API under test (gitignored)
```

### Ephemeral environment — `web/e2e/run-e2e.sh`

The pytest suite already gets its hermetic Postgres from
`testcontainers.postgres.PostgresContainer` (`api/tests/conftest.py`: `pg_url` fixture +
`_bind_db` monkeypatching `DATABASE_URL`). E2E reuses the same *pattern* — ephemeral Docker
Postgres, `DATABASE_URL` injected — but from a shell wrapper rather than a pytest fixture,
because the consumers here are two long-lived server processes, not test functions.

Why a wrapper script and not Playwright `globalSetup`: the servers in Playwright's
`webServer` array need `DATABASE_URL` **at boot**, and migrations must run against the DB
**before** the API boots (its lifespan primes the orchestrator pool). Sequencing containers →
migrations → servers inside Playwright would depend on undocumented ordering between
`globalSetup` and `webServer` startup; a wrapper makes the order explicit and identical in
CI and locally.

`run-e2e.sh` does, in order:

1. `docker run` `postgres:16-alpine` as `dothesis-e2e-pg` on host port `55432`
   (dev compose uses 5499 — no collision), and `minio/minio` as `dothesis-e2e-minio` on
   host port `9123`. A `trap … EXIT` removes both, pass or fail.
2. Waits for readiness: `docker exec dothesis-e2e-pg pg_isready`, and MinIO's
   `/minio/health/ready`.
3. Exports the env contract (below) and runs migrations with the repo's real command:
   `cd api && ./run.sh alembic upgrade head` (`api/run.sh` forces `arch -arm64` for the
   venv's arm64 wheels on macOS and falls back to direct exec on Linux/CI).
4. Creates the `dothesis-e2e` bucket via a short boto3 script run through `./run.sh python`
   (reuses the api venv's boto3 — no `mc`/aws-cli dependency).
5. Detects LibreOffice (`command -v soffice`) and exports `DOTHESIS_E2E_HAS_SOFFICE=1` when
   present — the export suite hard-requires it (the engine's `run_export` builds the PDF via
   LibreOffice headless, `orchestrator/tools/m5_writing.py`).
6. `npx playwright test "$@"` — Playwright's `webServer` array then boots API + web.

### Server processes — `webServer` array

`playwright.config.ts` declares two `webServer` entries (Playwright boots both before tests,
waits on their health URLs, and kills them after; `reuseExistingServer: false` so a
`dev.sh` stack on other ports is never accidentally reused):

| | command | cwd | ready URL |
|---|---|---|---|
| API | `./run.sh uvicorn app.main:app --host 127.0.0.1 --port 7143` | `api/` | `http://localhost:7143/api/v1/health` (the repo's one GET endpoint) |
| Web | `npx next dev -p 3106` | `web/` | `http://localhost:3106/login` |

Env contract for the API process (Playwright merges these over `process.env`):

| var | value | why |
|---|---|---|
| `DATABASE_URL` | from `run-e2e.sh` (`postgresql+psycopg://…@localhost:55432/dothesis_e2e`) | api engine (`app/settings.py`) **and** orchestrator pools (`orchestrator/graph.py` reads `os.environ["DATABASE_URL"]`) |
| `SESSION_SECRET` | `dothesis-e2e-secret` | required by `Settings`; signs the JWTs the tests capture |
| `ORCHESTRATOR_ENABLED` | `true` | chat/exports/uploads routers only mount when set (`api/app/main.py:create_app`) |
| `DOTHESIS_E2E_MOCK` | `1` (omitted in live tier) | mock-LLM switch in `agent/runtime.py:_default_model` |
| `DOTHESIS_E2E_FIXTURES_DIR` | abs path of `web/e2e/fixtures` | where `FakeChatModel` loads scenarios |
| `DOTHESIS_TEST_SUPPORT` | `1` | mounts the `/test/*` seeding router (both tiers — the live tier still seeds users) |
| `DOTHESIS_MAIL` | `dummy` | `app/mail.py` logs instead of calling SES; signup works with no AWS creds |
| `WEB_ORIGIN` | `http://localhost:3106` | CORS allowlist + verify/reset links |
| `JOB_WORKDIR_ROOT` | `web/e2e/.work/jobs` | agent workspaces isolated from the dev tree |
| `S3_BUCKET` | `dothesis-e2e` | export upload target (`m5_writing._upload_to_s3` reads `S3_BUCKET`) |
| `AWS_ACCESS_KEY` / `AWS_SECRET_KEY` (+ `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`) | `minioadmin` | the repo's boto3 factories read the custom names; the standard names cover any default-chain fallback |
| `AWS_ENDPOINT_URL_S3` | `http://localhost:9123` | botocore's native env endpoint override — every `boto3.client("s3", …)` in the repo (none pass `endpoint_url`) transparently targets MinIO, including presigned URLs, **without app changes** |

Env for the web process: `NEXT_PUBLIC_API_PROXY_TARGET=http://localhost:7143` (the
`next.config.mjs` rewrite for relative `fetch("/api/v1/…")`) and
`NEXT_PUBLIC_API_BASE=http://localhost:7143/api/v1` (the direct-fetch spots:
`app/lib/api.js`, uploads, export cards — several default to port 7100 and must be pointed
at 7143). CORS is satisfied because `WEB_ORIGIN` matches the browser origin.

### Mock LLM — `DOTHESIS_E2E_MOCK=1`

**Injection point (verified):** `agent/runtime.py:_default_model()` (line ~469) is the single
model factory — `build_agent(...)` calls it whenever `model is None`, and the api's chat path
(`api/app/routers/chat_v3.py:_get_agent`) calls `build_agent` without a model. It currently
returns `ChatAnthropic` when `ANTHROPIC_API_KEY` is set, else `ChatGoogleGenerativeAI`. The
hook is one guard at the top:

```python
if os.getenv("DOTHESIS_E2E_MOCK") == "1":
    from agent.testing.fake_model import FakeChatModel
    return FakeChatModel.from_fixtures_dir(os.environ["DOTHESIS_E2E_FIXTURES_DIR"])
```

**`FakeChatModel`** lives in a new `agent/testing/fake_model.py` — inside `agent/` so the
layering rule holds (`agent/` never imports `app/`; the module depends only on
`langchain_core` + stdlib). It subclasses `langchain_core`'s `BaseChatModel` and implements:

- `_generate` — the sync/async-fallback completion path.
- `_astream` — chunked streaming, so `stream_turn`'s
  `agent.astream(payload, config=config, stream_mode=["messages", "updates"])` (verified,
  `agent/runtime.py:565`) produces token deltas and the web's streaming UI
  (`streaming-cursor` testid) is exercised like production. Tool calls ride a final
  `AIMessageChunk(tool_call_chunks=[…])`.
- `bind_tools(tools, **kwargs) → self` — deepagents binds its tool set at agent build;
  `BaseChatModel.bind_tools` raises `NotImplementedError` by default. The fake ignores the
  schemas (the fixture decides which calls to emit) and returns itself.

**Step matching — deterministic, stateless.** The model receives the full message history on
every call, so no hidden counters are needed:

1. **Scenario selection:** the first `HumanMessage` of the conversation is matched against
   each fixture's `entry` regex (`re.search`; the runtime prepends a
   `[PROJECT STATE] …` header to user turns, so entries must not be start-anchored).
2. **Step index = number of `AIMessage`s already in the history.** Each scripted step is
   exactly one LLM completion. A step that emits `tool_calls` is followed by deepagents
   executing the tools and calling the model again (with `ToolMessage`s appended) — that next
   call has one more `AIMessage` in history and therefore consumes the **next** step. Tool
   loops are thus scripted explicitly, never inferred.
3. **Fail fast, fail loud:** a step may declare `expect_user`, a regex checked against the
   latest `HumanMessage`/`ToolMessage` text. On mismatch — or on an exhausted script, or no
   matching scenario — the model raises `FixtureError`. `stream_turn` already converts
   exceptions into an SSE `{"type": "error"}` event, which the web renders as the
   `error-bubble` testid — the Playwright assertion fails immediately with the mismatch
   message in the trace, instead of drifting.

Because the emitted `tool_calls` are real LangChain tool-call blocks, deepagents executes
them for real: a scripted `commit_slice` runs `agent/tools/state_tools.py:commit_slice` →
`DbProjectStateStore` → Postgres, with ownership validation, the strict done-gate, and focus
shift all running as real code on every scripted commit. `DOWNSTREAM` `needs_review`
propagation is the same real code path, but neither the M1→M5 nor the export fixture actually
*triggers* it — both script modules strictly in forward canonical order and mark each `done`
immediately, so every downstream module is still `locked` (the only state the propagation
check skips) at the moment its neighbor commits. This is a genuine coverage gap, not a mocked
shortcut — see plan Note 14 for the follow-up scenario that would close it. A scripted
`export_docx` runs the real engine compose/export and uploads to (Min)S3.

**What stays unmocked but harmless:** `api/app/thread_namer.py` builds its own
`ChatGoogleGenerativeAI` for background thread auto-naming. It is wrapped in
`try/except … logger.exception` ("naming is best-effort, never raise"), so with no key
configured it logs a failure and leaves the default name. Tests must not assert on thread
names.

### Fixture format — `web/e2e/fixtures/<scenario>.json`

```jsonc
{
  // Unique name; used in error messages only.
  "scenario": "m1-to-m5",
  // Regex (re.search) against the FIRST user message of a conversation.
  // Entries across fixtures must be mutually exclusive — first match wins
  // in sorted-filename order, and an ambiguous entry is a fixture bug.
  "entry": "finalize my topic",
  // Ordered list; step N answers the (N+1)-th model invocation.
  "steps": [
    {
      // Optional regex against the latest Human/Tool message. Mismatch -> FixtureError.
      "expect_user": "finalize my topic",
      // Assistant text. May embed the real UI marker syntax:
      //   [OPTIONS] a | b | c           (own line, last line -> card grid)
      //   [OPTIONS: field_name] a | b   (named field variant)
      //   [PAPERS] {…json…} [/PAPERS]   (papers panel)
      //   {{cite: label | title | url}} (citation chip)
      "response": "Committing your topic now…",
      // Optional real tool calls, executed by deepagents against real tools.
      "tool_calls": [
        {
          "name": "commit_slice",
          "args": {
            "module": "M1",
            "writes": { "research_title": "…", "research_questions": ["…"] },
            "reason": "User confirmed the topic",
            "confirm_done": true
          }
        }
      ]
    },
    {
      // The post-tool completion: expect_user matches the ToolMessage JSON.
      "expect_user": "\"module\": \"M1\"",
      "response": "M1 is committed and marked done.\n\n[OPTIONS] Continue to M2 | Revisit the topic"
    }
  ]
}
```

`response` and `tool_calls` may appear on the same step (text streams first, then the tool
block). Three fixtures ship with this spec: `onboarding.json`, `m1-to-m5.json`,
`export.json`. Auth/billing has no fixture — no chat turn is involved.

### Test-support router — `api/app/routers/test_support.py`

Three seams the tests need cannot ride existing endpoints without either faking auth
(defeats the point) or replaying entire journeys (slow, coupled):

- `POST /api/v1/test/verify-email` `{email}` — marks the user verified + grants the signup
  bonus (mirrors `auth.verify`'s effect). Needed because **real signup does not return a
  token**: `POST /auth/signup` returns `{ok, email}` and requires the emailed verify link
  (`api/app/routers/auth.py:signup`). This endpoint stands in for clicking that link, keeping
  signup and login themselves fully real.
- `POST /api/v1/test/seed-project` `{access_token, name, slices, done}` — creates a
  project + `Main` thread + `ContextStore` row exactly like `chat.create_project`, then
  writes each provided module slice **through `DbProjectStateStore.commit_slice`** — the
  real guarded write path (ownership validation, done-gate, `needs_review` propagation) —
  never raw SQL/JSON pokes. Used by the export suite to seed a near-complete project without
  replaying the M1→M5 script.
- `POST /api/v1/test/set-credit` `{access_token, credit}` — pins a user's balance (e.g. 0
  for the 402 journey). Sets the column directly (deliberately not via `credit_ledger` — the
  ledger records real financial events; synthetic entries would pollute admin reporting).

Gating (per the POST-only + never-in-prod requirement):

1. **Mount-time:** `create_app` includes the router only when
   `settings.test_support_enabled` (new `Settings` field, alias `DOTHESIS_TEST_SUPPORT`,
   default `False`). Unset ⇒ the routes do not exist ⇒ 404.
2. **Request-time (defense in depth):** every endpoint re-checks the flag via a dependency
   and 404s, in case the router is ever mounted by mistake.
3. All routes are `@router.post` per `CLAUDE.md`; auth'd ones take the token in the body
   (`AuthedBody`).

`DOTHESIS_TEST_SUPPORT` is a separate flag from `DOTHESIS_E2E_MOCK` because the **live** tier
needs seeding (users, projects) while running the **real** model.

### Auth — `web/e2e/auth.setup.ts` (Playwright setup project)

Auth is body-token, not cookie: login returns `{user, access_token, expires_at}` and the
client stores the token in `localStorage` (`dothesis_access_token`,
`dothesis_access_expires_at` — `web/app/lib/tokenStore.ts`) plus a non-HTTPOnly cookie
mirror of the same name that `web/proxy.js` checks for server-side route gating.

A Playwright **setup project** (`testMatch: /auth\.setup\.ts/`; the journey projects declare
`dependencies: ["setup"]`) runs after the servers are up and, via Playwright's API request
context:

1. `POST /auth/signup` with a per-run unique user (real endpoint, real validation).
2. `POST /test/verify-email` (the one test seam; stands in for the emailed link).
3. `POST /auth/login` → captures the **real** `access_token` + `expires_at`.
4. Writes a `storageState` JSON to `web/e2e/.auth/user.json` containing **both** halves the
   client keeps: the two `localStorage` keys for origin `http://localhost:3106`, and the
   `dothesis_access_token` cookie for `localhost` (SameSite Lax) so `proxy.js` doesn't bounce
   the first navigation to `/login`.
5. Repeats for a second "broke" user, then `POST /test/set-credit {credit: 0}` — saved as
   `web/e2e/.auth/broke.json`. Raw credentials/tokens for API-level calls go to
   `web/e2e/.auth/session.json`.

The onboarding / M1→M5 / export suites run with `storageState: "e2e/.auth/user.json"` — they
start logged in with zero UI coupling to the auth forms. The auth/billing suite runs with
**no** storageState and drives the real forms.

### The four suites

**`onboarding.spec.ts`** — the `/new` drop-first flow (`web/app/(inapp)/new/page.tsx`),
"describe it instead" variant (no file upload → no PDF parsing in the loop):
open `/new` → expand the note box → type a study description → **Analyze** → the page
creates a real project (`POST /projects` auto-creates the `Main` thread), navigates to
`/chat/projects/{id}?analyzing=1`, and ChatPane fires the real `/bootstrap` first turn.
`onboarding.json` answers it with an analysis summary ending in an `[OPTIONS]` line.
Asserts: chat URL reached; scripted text rendered; options card visible
(`card-grid-user_choice` — the default `field_name` from `_parse_options_marker`); context
panel (`context-panel` testid) present.

**`m1-to-m5.spec.ts`** — creates a fresh project via the API (real token from
`session.json`), opens its thread, then sends five user turns ("finalize my topic…", "now
find the literature", …). Each turn's fixture pair emits a real `commit_slice` (with
`confirm_done: true`) and a follow-up confirmation; the M2 confirmation embeds a
`{{cite: …}}` marker. After each turn the test asserts the ContextPanel module cards
(`web/app/components/chat/ContextPanel.tsx`) show the right status via new
`data-testid="ctx-M{n}"` / `data-status` hooks (a small component change this spec includes —
the status today is only a color-dot class, which is style-coupled and unassertable).
Note: the repo has no `RoadmapPanel` component — the M1–M5 rail was folded into ContextPanel
("the right-hand ContextPanel already surfaces module status", `WorkflowSidebar.tsx`), so
ContextPanel is the assertion surface.

**`export.spec.ts`** — seeds a near-complete project via `POST /test/seed-project`
(M1–M4 committed `done`; M5 gets six `final_sections` chapters but stays `in_progress` —
committing M5 `done` would fire `DbProjectStateStore`'s auto-export hook during seeding).
Sends "Export my thesis"; the fixture emits a real `export_docx` tool call
(`agent/tools/writing.py`). Because ≥ 6 chapters are seeded, the tool **reuses them without
any compose LLM call** (verified: the full-scope path only composes when
`chapter_count < len(M5_CHAPTER_ORDER)`), runs the real `run_export` (DOCX build; PDF via
LibreOffice headless), uploads to MinIO, and persists to the `exports` table. Asserts: the
export artifacts card appears in the message; clicking DOCX mints a real stream token,
follows the real `GET /projects/{id}/exports/{filename}?st=` 302 to the MinIO presigned URL,
and Playwright's `download` event yields a `.docx` file. Skipped (loudly) when
`DOTHESIS_E2E_HAS_SOFFICE` is unset.

**`auth-billing.spec.ts`** — the one suite that drives the auth forms for real:
- bad credentials on `/login` → stays on `/login`, shows "invalid email or password"
  (the API's `bad_credentials` message surfaced via `ApiError`);
- no auth cookie → `proxy.js` redirects any protected path to `/login?next=…`;
- garbage token (cookie present, API rejects) → `app/lib/api.js`'s 401 handler wipes the
  store and redirects to `/login`;
- real signup form → lands on `/wait-verify?email=…`;
- broke user (seeded credit 0): thread page shows the "You're out of credits." banner with
  the **Upgrade credits** CTA (`href="/credit"`) and a disabled composer; and an API-level
  probe of `POST /threads/{id}/messages` returns **402** with
  `detail.error.code == "insufficient_credit"` (verified: `api/app/routers/chat.py`
  `send_message` credit gate).

### CI — `.github/workflows/e2e.yml`

- **`e2e-mocked`** — on every `pull_request` to `master` (+ `workflow_dispatch`).
  ubuntu-latest: setup Python 3.13 + Node 22, `apt-get install libreoffice-writer` (PDF
  export), build `api/.venv` (`pip install -e api -e agent -e orchestrator`), `npm ci` +
  `playwright install --with-deps chromium`, then `web/e2e/run-e2e.sh`. Deterministic, no
  LLM secrets. Playwright HTML report uploaded on failure.
- **`e2e-live`** — nightly cron + `workflow_dispatch`. Mirrors `live-validation.yml`'s
  secret-check pattern: a first step probes `GEMINI_API_KEY`/`GOOGLE_API_KEY` and the job
  no-ops (green) when absent. Runs `DOTHESIS_E2E_LIVE=1 web/e2e/run-e2e.sh --grep @live` —
  only `live-smoke.spec.ts`, which sends one real completion to the cheap default model and
  asserts a marker (`[OPTIONS]` → card grid) survives a real generation + the SSE + widget
  pipeline. `DOTHESIS_E2E_MOCK` is left unset in this tier; `DOTHESIS_TEST_SUPPORT` stays on
  for seeding.

The stale `live-validation.yml` / `quality.yml` are left as-is (see Non-goals); flagged here
as follow-up cleanup candidates once `e2e.yml` is green on a few PRs.

### Extending the harness (F1–F13 contract)

Documented in `web/e2e/README.md` (shipped with the plan). Adding a scenario is:

1. Add `web/e2e/fixtures/<feature>.json` — pick a unique `entry` regex, script the turns.
2. Add `web/e2e/tests/<feature>.spec.ts` — seed via `test/seed-project` if the journey
   doesn't start from scratch; drive the UI; assert on testids/roles.
3. Nothing else: the fixture auto-loads (directory glob), the spec auto-runs (testDir glob),
   the setup project already provides an authed browser.

## Data flow

```
run-e2e.sh
  ├─ docker: dothesis-e2e-pg (Postgres :55432)   dothesis-e2e-minio (S3 :9123)
  ├─ api/run.sh alembic upgrade head   (DATABASE_URL → fresh schema)
  ├─ boto3 create_bucket dothesis-e2e
  └─ npx playwright test
       ├─ webServer[0]: api/run.sh uvicorn app.main:app :7143
       │     env: DATABASE_URL, DOTHESIS_E2E_MOCK=1, DOTHESIS_TEST_SUPPORT=1,
       │          AWS_ENDPOINT_URL_S3=:9123, ORCHESTRATOR_ENABLED=true, …
       ├─ webServer[1]: npx next dev -p 3106
       │     env: NEXT_PUBLIC_API_PROXY_TARGET=:7143, NEXT_PUBLIC_API_BASE=:7143/api/v1
       ├─ setup project (auth.setup.ts):
       │     signup → test/verify-email → login → storageState (.auth/*.json)
       └─ suites (chromium, storageState):
             browser → next :3106 → fetch /api/v1/* → uvicorn :7143
                 → chat_v3 → build_agent → _default_model()
                       └─ DOTHESIS_E2E_MOCK=1 → FakeChatModel(fixtures/*.json)
                 → deepagents loop → REAL tools (commit_slice / export_docx)
                       → DbProjectStateStore → Postgres :55432
                       → run_export → DOCX/PDF → MinIO :9123
                 → SSE events → widgets ([OPTIONS] card, export card) → assertions
```

## Error handling

- **Fixture drift** (wrong step order, unexpected user text, exhausted script, no matching
  scenario): `FakeChatModel` raises `FixtureError` with scenario/step/expected/actual;
  `stream_turn` surfaces it as an SSE error event → `error-bubble` in the UI → the test's
  positive assertion fails with the message visible in the Playwright trace. Never a silent
  wrong-path pass.
- **Environment boot failures:** `run-e2e.sh` is `set -euo pipefail`; readiness loops have
  bounded retries; the `trap` cleanup always removes containers so re-runs never collide
  with leftovers. Playwright's `webServer` timeout kills the run if a server never becomes
  healthy, printing its captured stdout/stderr.
- **Missing LibreOffice:** export suite `test.skip`s with an explanatory message locally;
  CI installs `libreoffice-writer` so the suite always runs there.
- **Prod safety:** both `DOTHESIS_TEST_SUPPORT` and `DOTHESIS_E2E_MOCK` default off; the
  test router 404s unless mounted *and* the request-time check passes; the mock model is
  only reachable through `_default_model`'s env guard. No production config sets either.

## Testing

The harness is itself the test surface, but its two non-trivial pieces get unit coverage
that can fail-then-pass independently of any browser:

- `agent/tests/test_fake_model.py` — scenario selection by entry regex, step indexing by
  AI-message count, `expect_user` mismatch → `FixtureError`, exhausted script →
  `FixtureError`, tool-call step shape (`AIMessage.tool_calls`). Run:
  `cd api && ./run.sh pytest ../agent/tests/test_fake_model.py -q`.
- `api/tests/test_test_support.py` — router absent (404) without `DOTHESIS_TEST_SUPPORT`;
  verify-email flips the flag + grants bonus; seed-project writes land via the guarded store
  (statuses propagate, ownership enforced); set-credit pins the balance. Runs on the existing
  testcontainers conftest.
- `tests/smoke.spec.ts` — cheapest full-stack signal: `/api/v1/health` returns `{ok: true}`
  and `/login` renders. Kept permanently as the first thing to check when the harness breaks.

## Migration / rollout

1. Land the harness scaffolding + smoke spec (no app changes) — proves the environment
   bootstrap on CI runners and dev machines.
2. Land the two app-side seams (test-support router; `FakeChatModel` + `_default_model`
   guard) with their unit tests — both inert in prod by default.
3. Land the suites one at a time (onboarding → M1→M5 → export → auth/billing), each with its
   fixture; each is independently revertible.
4. Land `e2e.yml`; run it manually on a branch until green twice, then let the PR trigger
   take over. Only then consider the stale-workflow cleanup (separate change).

## Dependencies

- **New (web devDependencies):** `@playwright/test` (^1.48 — `webServer[].cwd` and setup
  projects required). Chromium via `playwright install`.
- **Host tools:** Docker (already required by `dev.sh`), LibreOffice (`soffice`) for the
  export suite's PDF leg — optional locally (suite skips), installed in CI.
- **No new Python deps:** `FakeChatModel` uses `langchain_core` (already an api/agent dep);
  the bootstrap's bucket script uses the venv's boto3.
- **Existing conventions consumed:** POST-only endpoints (`CLAUDE.md`), body-token auth
  (`api/app/jwt_auth.py`), `api/run.sh` arm64 wrapper, marker syntax
  (`agent/runtime.py` parsers), `data-testid` hooks already present
  (`context-panel`, `error-bubble`, `streaming-cursor`, `card-grid-<field>`).
