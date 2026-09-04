# Auto-draft on the Deep Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make consumer auto-draft (`POST /projects/{id}/runs`) run on the deep-agent headless spine, then delete the orchestrator LangGraph layer.

**Architecture:** `runs.py` stops spawning `python -m orchestrator --auto-draft` and spawns `python -m app.headless_entry` — the same subprocess the partner report path already uses in production. `headless_entry` grows a `params["mode"]` branch for full-thesis runs (all five modules, bigger budgets, brief seeding, SIGTERM handling, token metering). The `events.jsonl` contract is unchanged, so `job_runner._monitor`, the SSE stream and `AutoDraftDrawer` need no work. The orchestrator graph layer is then deleted; `orchestrator/` survives as a library.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, LangGraph + deepagents 0.6.8, pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-auto-draft-deep-agent-design.md`

## Global Constraints

- **Every new endpoint is `@router.post(...)`.** No `@router.get(...)`. (`CLAUDE.md`)
- **Run all Python tests through the arm64 wrapper**, from the repo root: `api/run.sh pytest <path> -q`. Paths are relative to `api/` (e.g. `../agent/tests/...`). Never call `api/.venv/bin/pytest` directly — the venv wheels are arm64 and the shell may be x86_64.
- **Comment the reasoning behind each change**, not just the what. This repo's comments carry decisions; match that density.
- **`orchestrator/` is not deleted.** Only the graph layer named in Task 9 goes. `orchestrator/agents/base.py`, `orchestrator/tools/*`, `llm.py`, `token_meter.py`, `backfill.py`, `chapter_split.py`, `artifacts.py`, `message_utils.py` all survive and keep their consumers.
- **The API is the single writer of `Job` rows.** Subprocesses communicate only by appending to `<workdir>/events.jsonl`.
- **`DOTHESIS_MODEL_ROUTE=openai`, `DOTHESIS_AGENT_MODEL=gpt-5.6-luna`** is the live config (`.env:117-118`). Tests must not depend on a model id.

---

### Task 1: Un-break the full-thesis headless proof

The only test that proves a headless run drives all five modules to `done` —
`test_happy_path_runs_to_done` — is **red on master today**. Its M3 fixture
commits `conceptual_model: "CM"`, and the M3 gate correctly refuses it:

```
{"error": "m3_model_required — methodology cannot be finalized without a
structured conceptual model with at least two constructs and one relationship"}
```

The model then retries, exhausts the 10 scripted completions, and the run ends
`failed / max_stalls` with `M3: locked`. The gate is right; the fixture predates
the canonical M3 shape in `agent/m3_contract.py:13-18`. This task must land
first — flipping production onto a spine whose completion test is red is how a
regression gets discovered by students.

**Files:**
- Modify: `agent/tests/test_headless_runner.py:30-32`

**Interfaces:**
- Consumes: nothing.
- Produces: a green `test_happy_path_runs_to_done`, the baseline every later task re-runs.

- [ ] **Step 1: Run the test to see the documented failure**

```bash
api/run.sh pytest ../agent/tests/test_headless_runner.py::test_happy_path_runs_to_done -q
```

Expected: FAIL — `assert ('failed' == 'done')`.

- [ ] **Step 2: Replace the M3 fixture with the canonical shape**

In `agent/tests/test_headless_runner.py`, replace the M3 entry of `HAPPY`
(currently lines 30-31) with:

```python
    # conceptual_model must be the canonical {nodes, edges} shape from
    # agent/m3_contract.py:13-18. A prose string is refused by the M3 gate
    # ("m3_model_required": >=2 constructs, >=1 relationship), which used to
    # burn the fixture's remaining steps on retries and fail this test.
    *_module_steps("M3", {"conceptual_model": {
                              "nodes": [{"id": "PU", "label": "Perceived Usefulness"},
                                        {"id": "INT", "label": "Intention to Use"}],
                              "edges": [{"source": "PU", "target": "INT",
                                         "hypothesis": "H1"}]},
                          "hypotheses": ["H1: PU -> INT"],
                          "methodology": "PLS-SEM"}),
```

- [ ] **Step 3: Run the whole file**

```bash
api/run.sh pytest ../agent/tests/test_headless_runner.py -q
```

Expected: 8 passed. (Verified while planning: the run reaches
`done / roadmap_done` in 5 turns with all five modules `done`.)

- [ ] **Step 4: Commit**

```bash
git add agent/tests/test_headless_runner.py
git commit -m "test(headless): give the happy-path fixture a canonical M3 model

The M3 gate refuses a prose conceptual_model (m3_model_required), so the
scripted run burned its remaining completions on retries and the only
full-five-module headless proof was red on master."
```

---

### Task 2: Move the async PG pool out of the graph module

`orchestrator/graph.py:272` owns `_get_async_pool()`, and
`api/app/routers/chat_v3.py:95` imports it to build the checkpointer for
**interactive chat**. Deleting `graph.py` before moving this breaks chat. The
pool also cannot live in `orchestrator/` long-term: `orchestrator` is an
editable-installed library and must not be a dependency of the API's own
plumbing.

**Files:**
- Modify: `api/app/db.py` (add `get_async_pool`)
- Modify: `api/app/routers/chat_v3.py:95-96`
- Modify: `api/app/main.py:45-47`
- Test: `api/tests/test_async_pool.py` (create)

**Interfaces:**
- Produces: `async def get_async_pool() -> AsyncConnectionPool` in `app.db`, lazily created and process-global (same semantics as the original).

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_async_pool.py`:

```python
"""The async PG pool lives in app.db, not in the orchestrator graph module.

Regression guard for the auto-draft migration: chat_v3 builds its
AsyncPostgresSaver from this pool, so if the helper ever moves back behind
orchestrator.graph, deleting that module silently kills interactive chat.
"""
import inspect


def test_app_db_exposes_get_async_pool():
    from app import db
    assert inspect.iscoroutinefunction(db.get_async_pool)


def test_chat_v3_does_not_import_the_pool_from_orchestrator():
    from app.routers import chat_v3
    src = inspect.getsource(chat_v3)
    assert "orchestrator.graph" not in src


@pytest.mark.skipif(not os.getenv("DATABASE_URL"), reason="needs a database URL")
async def test_pool_is_memoized():
    """One pool per process: a second call must hand back the same object, not
    open a second connection pool against the same database."""
    from app import db
    assert await db.get_async_pool() is await db.get_async_pool()
```

(`import os` and `import pytest` at the top of the file; `asyncio_mode = "auto"`
is already set in `api/pyproject.toml:74`, so the async test needs no decorator.)

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_async_pool.py -q
```

Expected: FAIL — `AttributeError: module 'app.db' has no attribute 'get_async_pool'`.

- [ ] **Step 3: Add the helper to `api/app/db.py`**

Append to `api/app/db.py` (copy the body from `orchestrator/graph.py:272-300`,
including its connection-validation kwargs, and keep the original docstring's
reasoning):

```python
_async_pool = None


async def get_async_pool():
    """Lazy AsyncConnectionPool behind AsyncPostgresSaver.

    Moved here from orchestrator/graph.py during the auto-draft migration:
    interactive chat (routers/chat_v3.py) needs this pool, and it must not
    die with the orchestrator graph layer. Only AsyncPostgresSaver implements
    the async checkpointer path — the sync PostgresSaver raises
    NotImplementedError on aget_tuple.
    """
    global _async_pool
    if _async_pool is None:
        from psycopg_pool import AsyncConnectionPool

        url = os.environ["DATABASE_URL"].replace(
            "postgresql+psycopg://", "postgresql://", 1)
        _async_pool = AsyncConnectionPool(
            url,
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            kwargs={"autocommit": True},
            check=AsyncConnectionPool.check_connection,
        )
    return _async_pool
```

Read `orchestrator/graph.py:272-300` first and carry over every kwarg and
comment it has — do not reconstruct them from this snippet alone.

- [ ] **Step 4: Repoint the two callers**

`api/app/routers/chat_v3.py:95-96`:

```python
        from ..db import get_async_pool
        pool = await get_async_pool()
```

`api/app/main.py:45-47` — drop the `get_auto_graph()` warmup line here only if
Task 9 has already run; otherwise change just the pool import:

```python
            from ..db import get_async_pool
            await get_async_pool()
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_async_pool.py tests/test_chat_router.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/db.py api/app/routers/chat_v3.py api/app/main.py api/tests/test_async_pool.py
git commit -m "refactor(db): move the async PG pool out of orchestrator.graph

Chat's checkpointer depends on it; the graph module is about to be deleted."
```

---

### Task 3: `full_thesis` run profile

**Files:**
- Modify: `api/app/headless_entry.py:48-73` (`_build_profile`), `:165-176`
- Test: `api/tests/test_headless_full_thesis.py` (create)

**Interfaces:**
- Consumes: `agent.headless.RunProfile` (`interactive`, `max_turns`, `wall_clock_s`, `max_stalls`, `on_options`, `required_modules`).
- Produces: `_build_profile(params)` returns `required_modules=None` when `params["mode"] == "full_thesis"`; `_is_full_thesis(params) -> bool` used by Tasks 4 and 6.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_headless_full_thesis.py`:

```python
"""Consumer auto-draft runs the deep agent over ALL five modules.

The partner report path scopes a run to the chapters it ordered; a thesis
cannot be scoped that way, so mode=full_thesis must clear required_modules
and must not apply the report-only chapter/grounding context vars.
"""
from app.headless_entry import _build_profile, _is_full_thesis


def test_full_thesis_requires_every_module():
    profile = _build_profile({"mode": "full_thesis", "topic": "X"})
    assert profile.required_modules is None
    assert profile.interactive is False


def test_full_thesis_gets_a_bigger_budget_than_a_report():
    full = _build_profile({"mode": "full_thesis", "topic": "X"})
    report = _build_profile({"depth": "analysis_report"})
    assert full.max_turns > report.max_turns
    assert full.wall_clock_s > report.wall_clock_s


def test_explicit_params_still_win_over_the_mode_default():
    profile = _build_profile({"mode": "full_thesis", "max_turns": 7,
                              "wall_clock_s": 60})
    assert profile.max_turns == 7 and profile.wall_clock_s == 60


def test_report_mode_is_unchanged():
    profile = _build_profile({"depth": "analysis_report"})
    assert profile.required_modules is not None


def test_mode_predicate():
    assert _is_full_thesis({"mode": "full_thesis"}) is True
    assert _is_full_thesis({"depth": "analysis_report"}) is False
    assert _is_full_thesis({}) is False
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py -q
```

Expected: FAIL — `ImportError: cannot import name '_is_full_thesis'`.

- [ ] **Step 3: Implement the branch**

In `api/app/headless_entry.py`, above `_build_profile`:

```python
# Budgets for a whole thesis, not a 4-chapter report. RunProfile's defaults
# (40 turns / 1800s) were measured against analysis_report; a full run adds a
# real literature pass and full-length M5 composition. These numbers are an
# ESTIMATE pending the first production run — the 30-minute ceiling that
# shapes the report path is fillform's axios timeout, which the consumer flow
# (SSE-polled) does not have. Both stay overridable via job params.
_FULL_THESIS_MAX_TURNS = 120
_FULL_THESIS_WALL_CLOCK_S = 7200


def _is_full_thesis(params: dict) -> bool:
    return (params.get("mode") or "") == "full_thesis"
```

Then in `_build_profile`, branch before building the chapter scope:

```python
    if _is_full_thesis(params):
        # No chapter scoping: "done" means all five modules. required_modules
        # stays None, which RunProfile documents as "every module".
        return RunProfile(
            interactive=False,
            max_turns=int(params["max_turns"]) if params.get("max_turns")
            else _FULL_THESIS_MAX_TURNS,
            wall_clock_s=int(params["wall_clock_s"]) if params.get("wall_clock_s")
            else _FULL_THESIS_WALL_CLOCK_S,
            required_modules=None,
        )
```

- [ ] **Step 4: Skip the report-only context vars in `main()`**

`api/app/headless_entry.py:170-176` currently calls `set_report_chapters(...)`
and `set_grounded_backfill()` unconditionally. Guard them:

```python
        # Report-only. set_report_chapters scopes M5 to the ordered chapters and
        # set_grounded_backfill swaps M2's backfill for a real literature search;
        # a full thesis needs neither scope nor that substitution.
        if not _is_full_thesis(params):
            from agent.run_context import set_grounded_backfill, set_report_chapters
            from app.partner_run import resolve_chapters
            set_report_chapters(resolve_chapters(
                params.get("depth") or "analysis_report", params.get("chapters")))
            set_grounded_backfill()
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py tests/test_partner_report.py -q
```

Expected: PASS (partner tests prove the report path is untouched).

- [ ] **Step 6: Commit**

```bash
git add api/app/headless_entry.py api/tests/test_headless_full_thesis.py
git commit -m "feat(headless): add a full_thesis run mode"
```

---

### Task 4: Seed the brief into M1

The orchestrator's `_seed` node turned `{topic, language, citation_style}` into
an M1 slice. The deep agent has no equivalent, and `KICKOFF_PROMPT`
(`headless_entry.py:31`) assumes an already-seeded project. The brief goes into
the **store**, not the prompt: `_state_header` (`agent/runtime.py:655`) re-reads
the store and re-injects it every turn, so a committed topic survives turn 40
while a prompt-only topic depends on the model remembering it.

`user_context` is an M1-owned key that `agent/state.py:30-34` deliberately keeps
out of the model-facing slice map — it holds what the user asked for and must be
writable by seeding code but never rewritable by the agent. That is exactly this
brief.

**Files:**
- Modify: `api/app/headless_entry.py` (new `_seed_brief`, called from `main()`)
- Test: `api/tests/test_headless_full_thesis.py` (extend)

**Interfaces:**
- Consumes: `ProjectStateStore.commit_slice(module, writes, reason, confirm_done=False, status_overrides=None)`.
- Produces: `_seed_brief(store, params) -> bool` (True when it wrote).

- [ ] **Step 1: Write the failing test**

Append to `api/tests/test_headless_full_thesis.py`:

```python
def test_seed_brief_writes_topic_and_language(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "AI in SMEs",
                                "language": "vi", "citation_style": "APA"})
    assert wrote is True
    m1 = store.load()["contextStore"]
    assert m1["research_title"] == "AI in SMEs"
    assert m1["language"] == "vi"
    # The raw brief is kept for audit under the seeding-only key.
    assert m1["user_context"]["citation_style"] == "APA"


def test_seed_brief_does_not_overwrite_an_existing_topic(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    store.commit_slice("M1", {"research_title": "Student's own title"},
                       reason="prior work")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "Something else"})
    assert wrote is False
    assert store.load()["contextStore"]["research_title"] == "Student's own title"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py -q -k seed
```

Expected: FAIL — `ImportError: cannot import name '_seed_brief'`.

- [ ] **Step 3: Implement**

```python
def _seed_brief(store, params: dict) -> bool:
    """Commit the consumer brief into M1 before the first turn.

    Replaces the orchestrator's `_seed` graph node. Goes into the STORE rather
    than the kickoff prompt because _state_header re-injects store state on
    every turn — a prompt-only topic is one the model has to remember for 40
    turns, and it does not.

    Refuses to overwrite an existing research_title: resume re-runs this path
    over a project that already has work, and the student's own title outranks
    the brief that started the run.
    """
    topic = (params.get("topic") or "").strip()
    if not topic:
        return False
    existing = (store.load().get("contextStore") or {}).get("research_title")
    if existing:
        return False
    writes = {"research_title": topic,
              # user_context is the seeding-only key (agent/state.py:30-34):
              # the agent must not be able to rewrite the brief it is steered by.
              "user_context": {k: v for k, v in {
                  "topic": topic,
                  "citation_style": params.get("citation_style"),
              }.items() if v}}
    if params.get("language"):
        writes["language"] = params["language"]
    store.commit_slice("M1", writes, reason="auto-draft brief")
    return True
```

- [ ] **Step 4: Call it from `main()`**

In `api/app/headless_entry.py`, immediately after `store` is constructed
(`:159`) and before `profile = _build_profile(params)`:

```python
        # Seed BEFORE the profile/agent so the first _state_header already
        # carries the topic (see _seed_brief).
        _seed_brief(store, params)
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/headless_entry.py api/tests/test_headless_full_thesis.py
git commit -m "feat(headless): seed the auto-draft brief into M1"
```

---

### Task 5: SIGTERM writes a `paused` event

`job_runner.cancel_job` sends SIGTERM (`job_runner.py:327`).
`orchestrator/__main__.py:60,78` handles it by writing a `paused` event and
exiting cleanly, which `job_runner.py:300` reads to mark the run resumable.
`headless_entry` has no handler, so today a pause kills the process with no
terminal event and the run sits at `running` forever.

**Files:**
- Modify: `api/app/headless_entry.py` (handler installed in `main()`)
- Test: `api/tests/test_headless_full_thesis.py` (extend)

**Interfaces:**
- Consumes: `engine.job_io.JsonlAppender.write(dict)`.
- Produces: `_install_pause_handler(appender) -> None`.

- [ ] **Step 1: Write the failing test**

```python
def test_sigterm_writes_a_paused_event(tmp_path):
    """The monitor reads `paused` to mark a run resumable (job_runner.py:300).
    Without it, pausing an auto-draft leaves the Job stuck at `running`."""
    import signal
    from app.headless_entry import _install_pause_handler

    written = []

    class _Appender:
        def write(self, ev):
            written.append(ev)

    raised = []
    # signal.signal is process-global: leaving the runner's handler installed
    # would make every later test in this process exit(0) on SIGTERM, and that
    # failure would surface nowhere near its cause.
    previous = signal.getsignal(signal.SIGTERM)
    try:
        _install_pause_handler(_Appender())
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not previous, "handler was not installed"
        try:
            handler(signal.SIGTERM, None)
        except SystemExit as e:
            raised.append(e.code)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert written and written[0]["type"] == "paused"
    assert raised == [0]
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py -q -k sigterm
```

Expected: FAIL — `ImportError: cannot import name '_install_pause_handler'`.

- [ ] **Step 3: Implement**

```python
def _install_pause_handler(appender) -> None:
    """SIGTERM -> write `paused`, then exit 0.

    Mirrors orchestrator/__main__.py:60,78. job_runner.cancel_job pauses a run
    by sending SIGTERM; the monitor (job_runner.py:300) turns the `paused`
    event into a resumable Job status. Progress is whatever commit_slice has
    already persisted, so exiting here loses nothing that was committed.
    """
    import signal

    def _on_term(_signum, _frame):
        try:
            appender.write({"type": "paused", "agent": "headless",
                            "text": "run paused by request"})
        except Exception:  # noqa: BLE001 — never block the exit path
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _on_term)
```

- [ ] **Step 4: Install it in `main()`**

Immediately after `appender = JsonlAppender(workdir / "events.jsonl")`
(`headless_entry.py:148`):

```python
    _install_pause_handler(appender)
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_headless_full_thesis.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add api/app/headless_entry.py api/tests/test_headless_full_thesis.py
git commit -m "fix(headless): emit a paused event on SIGTERM so pause works"
```

---

### Task 6: Meter tokens into `token_ledger`

`_charge_auto_run` (`job_runner.py:345`) bills a run by summing `token_ledger`
rows for the project since `run.started_at`, **grouped by model**, each priced at
its own rate. Those rows come from `orchestrator/token_meter.py`, which wraps
`bounded_invoke` — a path the deep agent never takes. Without this task,
auto-draft charges nothing.

**Do NOT write `token_ledger` from this subprocess.** That contract already
exists and the subprocess is deliberately not the DB writer:

- `orchestrator/__main__.py:82-97` routes its meter entries into `events.jsonl`
  as `{"type": "token_usage", ...}` events.
- `api/app/job_runner.py:215-236` `_ingest_event` turns each such event into the
  `TokenLedger` row, incrementing `events_processed` so a resumed monitor cannot
  replay lines and double-bill.
- `api/tests/test_auto_run_credit.py:120` already tests exactly that path.
- `api/app/headless_entry.py:6-8` states the invariant: this process never writes
  Job rows; the API is the single DB writer.

So the runner's job is only to EMIT the event. `agent/runtime.py:831-848` already
emits `{"type": "usage", "input_tokens", "output_tokens", "model"?}` per LLM
step, and `_on_event` (`headless_entry.py:194`) already sees every event. Buffer
per turn, flush on `done`, one `token_usage` event per model per turn.

Note: chat turns bill through `chat_v3._finalize` and write **no** `token_ledger`
rows, so a chat message sent while a run is in flight cannot be double-charged
by `_charge_auto_run`'s sweep.

**Files:**
- Modify: `api/app/headless_entry.py` (new `_UsageMeter`, wired into `_on_event`)
- Test: `api/tests/test_headless_usage_meter.py` (create)

**Interfaces:**
- Consumes: `engine.job_io.JsonlAppender.write(dict)`; the `token_usage` event shape read by `job_runner._ingest_event` (`action_kind`, `model`, `prompt_tokens`, `completion_tokens`, `reserved`, `duration_ms`, `project_id`).
- Produces: `_UsageMeter(project_id, appender)` with `.observe(ev: dict) -> None` and `.flush() -> int` (events written).

This task needs no database, so its tests run with Docker down.

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_headless_usage_meter.py`:

```python
"""Headless runs must emit token_usage events or auto-draft is free.

_charge_auto_run sums token_ledger per model, and those rows are written
API-side by job_runner._ingest_event from `token_usage` events on the
events.jsonl contract (job_runner.py:215-236). The deep agent never goes
through orchestrator.token_meter, so the runner has to emit its own.

No DB here on purpose: the subprocess is not the DB writer, so the unit under
test is the event it emits.
"""
import uuid

from app.headless_entry import _UsageMeter


class _Appender:
    def __init__(self):
        self.events = []

    def write(self, ev):
        self.events.append(ev)


def test_usage_events_are_summed_per_model_and_emitted_once_per_flush():
    pid = uuid.uuid4()
    appender = _Appender()
    meter = _UsageMeter(pid, appender)
    meter.observe({"type": "usage", "input_tokens": 1000,
                   "output_tokens": 500, "model": "gemini-2.5-flash"})
    meter.observe({"type": "usage", "input_tokens": 200,
                   "output_tokens": 100, "model": "gemini-2.5-flash"})
    assert meter.flush() == 1

    (ev,) = appender.events
    assert ev["type"] == "token_usage"
    assert ev["action_kind"] == "deep_agent_turn"
    assert ev["model"] == "gemini-2.5-flash"
    assert ev["prompt_tokens"] == 1200
    assert ev["completion_tokens"] == 600
    assert ev["project_id"] == str(pid)
    # NOT NULL columns on token_ledger; _ingest_event coerces via int().
    assert ev["reserved"] == 0 and "duration_ms" in ev


def test_each_model_gets_its_own_event():
    """_charge_auto_run prices each row at its own model's rate, so a turn that
    failed over to a second model must not be collapsed into one."""
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5,
                   "model": "gemini-2.5-flash"})
    meter.observe({"type": "usage", "input_tokens": 20, "output_tokens": 7,
                   "model": "gpt-5.6-luna"})
    assert meter.flush() == 2
    assert {e["model"] for e in appender.events} == {"gemini-2.5-flash",
                                                     "gpt-5.6-luna"}


def test_flush_is_empty_when_no_usage_was_seen():
    appender = _Appender()
    assert _UsageMeter(uuid.uuid4(), appender).flush() == 0
    assert appender.events == []


def test_flush_clears_the_buffer_so_turns_are_not_double_billed():
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "usage", "input_tokens": 10, "output_tokens": 5,
                   "model": "m"})
    meter.flush()
    assert meter.flush() == 0
    assert len(appender.events) == 1


def test_non_usage_events_are_ignored():
    appender = _Appender()
    meter = _UsageMeter(uuid.uuid4(), appender)
    meter.observe({"type": "tool_start", "name": "commit_slice"})
    meter.observe({"type": "done"})
    assert meter.flush() == 0
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_headless_usage_meter.py -q
```

Expected: FAIL — `ImportError: cannot import name '_UsageMeter'`.

- [ ] **Step 3: Implement**

```python
class _UsageMeter:
    """Turn the agent's `usage` events into `token_usage` events for the API.

    The API is the single DB writer (module docstring), so this emits on the
    events.jsonl contract and job_runner._ingest_event (job_runner.py:215-236)
    creates the token_ledger row — the same path orchestrator/__main__.py:82-97
    uses. _charge_auto_run then prices each row at ITS OWN model's rate, which
    is why usage is grouped by the model that actually served the step:
    OpenRouter can fail over to a pricier fallback mid-run and runtime.py
    reports the served model on the event.

    Buffered per turn so a long turn emits one event per model, not one per
    LLM step.
    """

    def __init__(self, project_id, appender):
        self.project_id = project_id
        self._appender = appender
        self._buf: dict[str, list[int]] = {}

    def observe(self, ev: dict) -> None:
        if ev.get("type") != "usage":
            return
        model = ev.get("model") or os.getenv("DOTHESIS_AGENT_MODEL", "unknown")
        slot = self._buf.setdefault(model, [0, 0])
        slot[0] += int(ev.get("input_tokens") or 0)
        slot[1] += int(ev.get("output_tokens") or 0)

    def flush(self) -> int:
        if not self._buf:
            return 0
        buf, self._buf = self._buf, {}
        for model, (prompt, completion) in buf.items():
            self._appender.write({
                "type": "token_usage",
                "action_kind": "deep_agent_turn",
                "model": model,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                # NOT NULL on token_ledger. token_meter's reserve-then-reconcile
                # loop has no analogue here: the agent reports true usage, so
                # there is nothing reserved and no separate call to time.
                "reserved": 0,
                "duration_ms": 0,
                "project_id": str(self.project_id),
            })
        return len(buf)
```

- [ ] **Step 4: Wire it into `_on_event`**

In `main()`, alongside the existing hooks:

```python
        meter = _UsageMeter(project_id, appender)

        def _on_event(ev: dict) -> None:
            meter.observe(ev)
            if ev.get("type") == "done":
                # One turn's worth of usage per flush; a crash mid-turn loses at
                # most that turn's metering, never a committed slice.
                meter.flush()
                try:
                    timer.mark((store.load() or {}).get("focus") or "M1")
                except Exception:  # noqa: BLE001
                    pass
            progress_hook(ev)
```

- [ ] **Step 5: Run the tests**

```bash
api/run.sh pytest tests/test_headless_usage_meter.py -q
```

Expected: PASS. (`tests/test_auto_run_credit.py` covers the API-side half of
this contract and needs a database; run it too if one is available, but it is
not this task's gate.)

- [ ] **Step 6: Commit**

```bash
git add api/app/headless_entry.py api/tests/test_headless_usage_meter.py
git commit -m "feat(headless): emit token_usage events so auto-draft is billable"
```

---

### Task 7: Point `start_run` at the headless spawner

**Files:**
- Modify: `api/app/routers/runs.py:121-141`
- Test: `api/tests/test_runs_router.py:28-45` — **replace** `test_post_run_spawns_orchestrator_subprocess`, don't add alongside it. That test asserts the orchestrator spawner is called; keeping it would assert exactly what this task removes.

**Interfaces:**
- Consumes: `job_runner.spawn_headless_run(db, run, params)`; `_is_full_thesis` reads `params["mode"] == "full_thesis"`.
- Produces: no signature change to the endpoint. `StartRunBody` is unchanged.

The file's conventions (`api/tests/test_runs_router.py:10-26`): a `client`
fixture returning `TestClient(create_app())`, and `_setup(client)` which creates
a user, puts a bearer token on `client.headers`, and returns a project id. There
is no separate `auth_headers` fixture. Monkeypatching is by string target.

- [ ] **Step 1: Write the failing test**

Replace lines 28-45 of `api/tests/test_runs_router.py` with:

```python
def test_post_run_spawns_the_headless_deep_agent(client, monkeypatch):
    """Auto-draft runs the deep agent headless, not the orchestrator graph."""
    pid = _setup(client)
    spawned = []

    def fake_spawn(db, run, params):
        run.pid = 12345
        run.status = "running"
        spawned.append({"mode": run.mode, "params": params})

    monkeypatch.setattr("app.job_runner.spawn_headless_run", fake_spawn)

    r = client.post(f"/api/v1/projects/{pid}/runs",
                    json={"mode": "auto", "topic": "Leadership in SMEs",
                          "language": "vi"})
    assert r.status_code == 200, r.text
    assert "run_id" in r.json()
    # Job.mode stays "auto" — it is the column the UI and admin screens read.
    # params["mode"] is the headless runner's own vocabulary.
    assert spawned[0]["mode"] == "auto"
    assert spawned[0]["params"]["mode"] == "full_thesis"
    assert spawned[0]["params"]["topic"] == "Leadership in SMEs"
    assert spawned[0]["params"]["language"] == "vi"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_runs_router.py -q -k headless
```

Expected: FAIL — the orchestrator spawner is called.

- [ ] **Step 3: Implement**

Replace `runs.py:135-139` (the `brief` dict and the spawn call):

```python
    # The deep agent is the only brain (2026-08-19 migration). `mode` is the
    # headless runner's own vocabulary — "auto" is the Job.mode column, which
    # the UI and admin screens still read, so the two must not be conflated.
    params = {
        "mode": "full_thesis",
        "topic": body.topic,
        "language": body.language or p.language,
        "citation_style": body.citation_style or p.citation_style,
    }
    job_runner.spawn_headless_run(db, run, params)
```

- [ ] **Step 4: Run the tests**

```bash
api/run.sh pytest tests/test_runs_router.py tests/test_runs_latest.py tests/test_jobs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/runs.py api/tests/test_runs_router.py
git commit -m "feat(runs): auto-draft spawns the deep-agent headless runner"
```

---

### Task 8: Resume re-runs the agent over committed state

Resume no longer re-enters a LangGraph checkpoint — there is none. It spawns a
fresh headless run over whatever `commit_slice` persisted. The comment at
`runs.py:158-162` describing checkpoint resume becomes false and must be
rewritten, not left to mislead the next reader.

**Files:**
- Modify: `api/app/routers/runs.py:155-173`
- Test: `api/tests/test_runs_router.py:58` — **replace** `test_resume_failed_run_resumes_checkpoint`. Its name and its `resume_from == run.id` assertion describe a checkpoint that no longer exists.

**Interfaces:**
- Consumes: `job_runner.spawn_headless_run(db, run, params)`.
- Produces: unchanged endpoint contract (`{"status": ...}`); still 409s for a non-resumable run.

Use the file's `_setup(client)` and `_mark_run(rid, **fields)` helpers
(`api/tests/test_runs_router.py:16, :48`).

- [ ] **Step 1: Write the failing test**

Replace `test_resume_failed_run_resumes_checkpoint` with:

```python
def test_resume_respawns_headless_over_committed_state(client, monkeypatch):
    """A failed run resumes by re-running a fresh agent over the state
    commit_slice already persisted — there is no checkpoint to re-enter — and
    the stale error markers are cleared."""
    pid = _setup(client)
    spawned = []
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: spawned.append(params))
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "T"}).json()["run_id"]
    _mark_run(rid, status="failed", error_text="boom")

    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 200, r.text
    # The resume spawn carries no topic: the project already holds its M1
    # slice, and _seed_brief refuses to overwrite an existing research_title.
    assert spawned[-1] == {"mode": "full_thesis"}

    sf = get_session_factory()
    with sf() as db:
        from app.models import Job
        run = db.get(Job, uuid.UUID(rid))
        assert run.error_text is None and run.finished_at is None


def test_resume_rejects_a_running_run(client, monkeypatch):
    pid = _setup(client)
    monkeypatch.setattr("app.job_runner.spawn_headless_run",
                        lambda db, run, params: None)
    rid = client.post(f"/api/v1/projects/{pid}/runs",
                      json={"mode": "auto", "topic": "T"}).json()["run_id"]
    _mark_run(rid, status="running")
    r = client.post(f"/api/v1/runs/{rid}/resume")
    assert r.status_code == 409
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_runs_router.py -q -k resume
```

Expected: FAIL.

- [ ] **Step 3: Implement**

Replace the docstring/comment and spawn call in `resume_run`:

```python
    # Resume covers paused runs AND terminal-but-recoverable ones (failed /
    # canceled). There is no checkpoint to re-enter: the deep agent's durable
    # progress is whatever commit_slice wrote to the project store, so resuming
    # means running a FRESH agent over that state. Completed modules are intact;
    # a module that was in flight but never committed is redone.
    if run.status not in {"paused", "failed", "canceled"}:
        raise HTTPException(409,
                            detail={"error": {"code": "not_resumable",
                                              "message": f"run is {run.status}"}})
    run.error_text = None
    run.finished_at = None
    job_runner.spawn_headless_run(db, run, {"mode": "full_thesis"})
    db.commit()
    return {"status": run.status}
```

- [ ] **Step 4: Run the tests**

```bash
api/run.sh pytest tests/test_runs_router.py tests/test_stuck_runs.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/runs.py api/tests/test_runs_router.py
git commit -m "feat(runs): resume re-runs the agent over committed state"
```

---

### Task 9: Delete the orchestrator spawn + checkpoint mirror

**Files:**
- Modify: `api/app/job_runner.py` — delete `spawn_orchestrator_run` (`:414-475`), `_sync_context_store_from_checkpoint` (`:160-230`) and its call site (`:314`)
- Modify: `api/app/main.py:45-47` — drop the `get_auto_graph()` warmup
- Test: `api/tests/test_job_runner.py` (extend)

**Interfaces:**
- Produces: `job_runner` no longer exports `spawn_orchestrator_run` or `_sync_context_store_from_checkpoint`.

- [ ] **Step 1: Write the failing test**

```python
def test_job_runner_has_no_orchestrator_spawn():
    """The deep agent is the only auto-draft brain; a lingering spawner is a
    second, untested path back to the deleted graph."""
    from app import job_runner
    assert not hasattr(job_runner, "spawn_orchestrator_run")
    assert not hasattr(job_runner, "_sync_context_store_from_checkpoint")


def test_context_store_is_written_by_the_store_not_a_mirror():
    """DbProjectStateStore.commit_slice writes context_store directly, which is
    why the checkpoint mirror could go."""
    import inspect
    from app import job_runner
    assert "get_auto_graph" not in inspect.getsource(job_runner)
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_job_runner.py -q -k orchestrator
```

Expected: FAIL.

- [ ] **Step 3: Delete**

Remove the three regions named above. In `main.py`, the startup block keeps only
the pool warmup from Task 2:

```python
            # Warm the async PG pool so the first chat turn doesn't pay for
            # connection setup. (The auto graph warmed here died with the
            # orchestrator graph layer — auto-draft is a subprocess now.)
            from ..db import get_async_pool
            await get_async_pool()
```

- [ ] **Step 4: Run the API suite**

```bash
api/run.sh pytest tests -q
```

Expected: PASS. Any test that imported `spawn_orchestrator_run` is now stale —
delete it rather than adapt it; the path it covered no longer exists.

- [ ] **Step 5: Commit**

```bash
git add api/app/job_runner.py api/app/main.py api/tests/test_job_runner.py
git commit -m "refactor(jobs): drop the orchestrator spawner and checkpoint mirror"
```

---

### Task 10: Delete the graph layer

Delete only the graph layer. `orchestrator/agents/base.py` **survives** —
`token_meter.py:27`, `tools/m2_literature.py:323`, `tools/m3_design.py:16` and
`llm.py:113` import `bounded_invoke` from it.

**Files:**
- Delete: `orchestrator/graph.py`, `orchestrator/graph_v2.py`, `orchestrator/studio.py`
- Delete: `orchestrator/agents/{m1_topic,m2,m3_design,m4_analysis,m5_writing,supervisor,router_agent,read_handler,module_tools}.py` (and the `agents/m2/` package)
- Delete: `orchestrator/evals/sim_thesis.py`, `orchestrator/evals/backfill_eval.py`
- Delete: `orchestrator/__main__.py` `--auto-draft` path (the whole module if nothing else uses it)
- Delete: `orchestrator/tests/test_graph.py`, `orchestrator/tests/test_read_handler.py`, `api/tests/test_m3_round_trip.py`, `api/tests/test_m4_round_trip.py`, and the `_router_llm` case in `api/tests/test_orchestrator_llm.py`
- Test: `api/tests/test_no_graph_imports.py` (create)

**Interfaces:**
- Produces: no module outside `orchestrator/` imports `orchestrator.graph`.

- [ ] **Step 1: Write the failing guard test**

Create `api/tests/test_no_graph_imports.py`:

```python
"""Nothing may import the deleted graph layer.

The pool that chat depends on used to live in orchestrator.graph; this guard
is what stops it (or anything else) drifting back there.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
BANNED = re.compile(r"from orchestrator\.graph|import orchestrator\.graph|"
                    r"orchestrator\.graph_v2|orchestrator\.studio")


def test_no_module_imports_the_graph_layer():
    offenders = []
    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", "node_modules", "__pycache__"} for part in path.parts):
            continue
        if BANNED.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"graph layer still referenced by: {offenders}"
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_no_graph_imports.py -q
```

Expected: FAIL, listing every remaining reference. That list is this task's
work queue.

- [ ] **Step 3: Delete, one file at a time, re-running the guard**

Before deleting each `orchestrator/agents/*` module, confirm it has no consumer
outside the graph layer:

```bash
grep -rn "agents.m3_design\|agents\.supervisor" --include="*.py" . \
  | grep -v "\.venv\|node_modules"
```

- [ ] **Step 4: Run both suites**

```bash
api/run.sh pytest tests -q
api/run.sh pytest ../agent/tests -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

List the deleted paths explicitly. Do **not** use `git add -A`: the working tree
carries unrelated uncommitted work (`web/proxy.js`, `web/app/landing/`) that
belongs to the repo owner, and `-A` would sweep it into this commit.

```bash
git add -u orchestrator/ api/tests/
git commit -m "refactor(orchestrator): delete the graph layer

The deep agent serves both chat and auto-draft. orchestrator/ remains a
library (tools, backfill, llm, token_meter, agents/base)."
```

---

### Task 11: Point Studio at the surviving loop

`langgraph.json`'s only entry is now dead. Repoint it at the deep agent so
`dev.sh:304-322` gives Studio on the loop that actually serves users.

**Files:**
- Create: `agent/studio.py`
- Modify: `langgraph.json`
- Test: `api/tests/test_no_graph_imports.py` (extend)

**Interfaces:**
- Produces: `agent.studio.get_studio_graph()` — no-arg, returns a compiled deep agent with an in-memory checkpointer.

- [ ] **Step 1: Write the failing test**

```python
def test_langgraph_json_points_at_the_deep_agent():
    import json
    cfg = json.loads((ROOT / "langgraph.json").read_text(encoding="utf-8"))
    assert "deepagent" in cfg["graphs"]
    assert "orchestrator" not in cfg["graphs"]


def test_studio_factory_takes_no_arguments():
    import inspect
    from agent import studio
    assert inspect.signature(studio.get_studio_graph).parameters == {}
```

- [ ] **Step 2: Run it and watch it fail**

```bash
api/run.sh pytest tests/test_no_graph_imports.py -q -k studio
```

Expected: FAIL — `ModuleNotFoundError: No module named 'agent.studio'`.

- [ ] **Step 3: Implement**

Create `agent/studio.py`:

```python
"""LangGraph Studio entrypoint for the deep agent.

Studio's `langgraph dev` server wants a no-arg factory and its own checkpoint
storage, so this hands it an in-memory checkpointer over a throwaway project
directory — the topology (model <-> tools, plus deepagents' middleware) is
identical to production, only the checkpointer and workspace differ.

Replaces orchestrator/studio.py: with the graph layer gone, the deep agent is
the only loop worth stepping through.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

from agent.runtime import build_agent


def get_studio_graph():
    """Return a fresh deep agent for `langgraph dev`."""
    workspace = Path(tempfile.mkdtemp(prefix="dothesis-studio-"))
    return build_agent(workspace, checkpointer=MemorySaver())
```

Rewrite `langgraph.json`:

```json
{
  "dependencies": ["./agent"],
  "graphs": {
    "deepagent": "./agent/studio.py:get_studio_graph"
  },
  "env": ".env"
}
```

- [ ] **Step 4: Verify Studio loads the graph**

```bash
api/run.sh pytest tests/test_no_graph_imports.py -q
api/run.sh python -c "from agent.studio import get_studio_graph; print(list(get_studio_graph().nodes))"
```

Expected: the node list includes `model` and `tools`.

- [ ] **Step 5: Update the docs**

Add to `AGENTS.md` (and `docs/ARCHITECTURE.md` if it describes the run paths):

```markdown
- Chat AND auto-draft both run the deep agent (`agent/runtime.py`).
  Auto-draft is the same brain driven headless (`api/app/headless_entry.py`).
- `langgraph.json` exists only for `langgraph dev` (Studio) via `dev.sh`.
  It is not read by any deployment.
```

- [ ] **Step 6: Commit**

```bash
git add agent/studio.py langgraph.json AGENTS.md docs/ARCHITECTURE.md api/tests/test_no_graph_imports.py
git commit -m "chore(studio): point langgraph.json at the deep agent"
```

---

## Post-plan verification

- [ ] `api/run.sh pytest tests -q` — API suite green
- [ ] `api/run.sh pytest ../agent/tests -q` — agent suite green, including `test_happy_path_runs_to_done`
- [ ] One real auto-draft run against a scratch project: confirm the drawer streams, pause marks the run `paused`, resume continues, and a `CreditTransaction` with `reason="auto_run"` lands with a non-zero delta
- [ ] Record the run's real turn count and wall time, and correct `_FULL_THESIS_MAX_TURNS` / `_FULL_THESIS_WALL_CLOCK_S` from measurement rather than the estimate in Task 3

## Known follow-up (out of scope)

`orchestrator/evals/sim_thesis.py` dies with the graph. It is the repo's only
simulated-student harness — the one automated way to exercise a whole run. It
should be rebuilt against the deep agent (it can drive `run_headless` with a
scripted `FakeChatModel`, as `agent/tests/test_headless_runner.py` already
does). Tracked here so it is a decision, not an accident.
