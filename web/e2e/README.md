# DoThesis E2E harness

Playwright journeys against the real stack — real Postgres, MinIO (S3), FastAPI,
Next.js, deepagents tool loop. Only the LLM completion is mocked (fixture-scripted)
in the default tier. Design doc: `docs/superpowers/specs/2026-07-08-e2e-testing-design.md`.

## Run it

```bash
# everything (needs Docker; LibreOffice optional — export suite skips without it)
web/e2e/run-e2e.sh

# one suite, headed, with the inspector
web/e2e/run-e2e.sh tests/onboarding.spec.ts --headed --debug
```

Never run the suite through bare `npx playwright test` — `run-e2e.sh` owns the
ephemeral Postgres/MinIO containers and the env contract. The harness uses its own
ports (api 7143, web 3106, pg 55432, minio 9123) and never touches the `dev.sh` stack.

## How it works (30 seconds)

- `run-e2e.sh`: containers → `alembic upgrade head` → bucket → `playwright test`.
- `playwright.config.ts` `webServer`: boots `uvicorn app.main:app` (:7143) and
  `next dev` (:3106) with `DOTHESIS_E2E_MOCK=1` + `DOTHESIS_TEST_SUPPORT=1`.
- `tests/auth.setup.ts` (setup project): REAL signup → `/test/verify-email` seam →
  REAL login → storageState (localStorage token + the `proxy.js` cookie mirror).
- `DOTHESIS_E2E_MOCK=1` makes `agent/runtime.py:_default_model()` return
  `agent/testing/fake_model.py:FakeChatModel`, which replays `fixtures/*.json`.
  Scripted `tool_calls` are executed FOR REAL by deepagents (`commit_slice`,
  `export_docx`, …) — only the text generation is fake.

## Adding a scenario (the F1–F13 contract)

1. **Fixture** — `fixtures/<feature>.json`:
   - `entry`: regex matched against the FIRST user message of a conversation.
     Must not collide with existing entries (`onboarding` → `/bootstrap`,
     `m1-to-m5` → `finalize my topic`, `export` → `Export my thesis`).
     Don't anchor it — the runtime prepends a `[PROJECT STATE]` header.
   - `steps`: one entry per LLM completion, in order. A step with `tool_calls`
     is followed by the tool executing for real and the model being called
     again — script that next completion as the next step (use `expect_user`
     against the ToolMessage JSON, e.g. `"\"module\": \"M2\""`, to fail fast).
   - `response` may embed the real markers: `[OPTIONS] a | b | c` (last line),
     `[OPTIONS: field] …`, `[PAPERS] {…} [/PAPERS]`, `{{cite: label | title | url}}`.
2. **Spec** — `tests/<feature>.spec.ts`. It auto-runs in the `journeys` project
   (add its name to that project's `testMatch` in `playwright.config.ts`),
   already authenticated via storageState. Start mid-journey by seeding:
   `apiPost(rc, "/test/seed-project", { access_token, slices: {...}, done: [...] })`
   — slices go through the real guarded store, so use each module's OWNED keys
   (`agent/state.py` `SLICE_OWNERSHIP`).
3. That's it. The fixture auto-loads (directory glob); any scripting mistake
   surfaces as a `FixtureError` in the error bubble + trace, never a silent pass.

## Debugging

- `--headed`, `--debug`, `npx playwright show-report` (from `web/`).
- Server logs stream into the Playwright output (`stdout: "pipe"`).
- Turn-level agent diagnostics are on the API's stderr (`[agent.stream] …`).
- A `FixtureError` message tells you which scenario/step diverged and what the
  actual latest message was.
