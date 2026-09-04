# Auto-draft on the deep agent — retiring the orchestrator graph

Date: 2026-08-19
Status: approved (design), pending implementation plan

## Decision

One brain. `POST /projects/{id}/runs` (consumer auto-draft, "one prompt to
thesis") stops spawning `python -m orchestrator --auto-draft` and spawns the
deep-agent headless runner instead — the same spine the partner/B2B report path
has been running in production. The orchestrator LangGraph (supervisor ↔ M1–M5)
is then deleted, not kept as a fallback.

Three decisions were taken explicitly by the owner and are not open in the plan:

1. **Cutover:** flip and delete in one go. No engine flag, no shadow period.
   Accepted consequence: auto-draft may regress for real students before we
   find out, because the deep agent has never run headless at full-thesis
   scope (see Risk 1).
2. **Pause/resume:** keep the UI exactly as it is; change the mechanism
   underneath. Accepted consequence: resume no longer resumes mid-module.
3. **Billing:** keep charging measured tokens. Auto-draft must not become free.

## Why this is a swap, not a rewrite

`api/app/job_runner.py:543` `spawn_headless_run` was written for this migration.
Its own docstring:

> Reuses the events.jsonl contract so the existing `_monitor` works unchanged,
> which is exactly what makes C (auto-mode migration) a swap later: point THIS
> spawner at auto briefs instead of `python -m orchestrator --auto-draft`.

Everything downstream of the subprocess — `_monitor` (`job_runner.py:240`),
`JobEvent` rows, SSE `/runs/{id}/events`, `AutoDraftDrawer` — keys off
`events.jsonl` and does not care which process wrote it.

## Scope: what "delete the orchestrator" means

`orchestrator/` is not deleted. It remains a library that the rest of the system
depends on: `tools/m5_writing`, `tools/compose_export`, `tools/domain_sources`,
`tools/m2_literature`, `backfill`, `chapter_split`, `artifacts`, `llm`,
`token_meter`, `message_utils`, `agents/base` (`bounded_invoke`). Consumers
include `api/app/partner_run.py:26`, `agent_state.py:359`, `citation_job.py:111`,
`import_route.py:152`, `thread_namer.py:71`, `routers/exports.py:214`.

What dies is the **graph layer only**:

| Deleted | Why it can go |
|---|---|
| `orchestrator/graph.py`, `graph_v2.py` | the supervisor/router loop itself |
| `orchestrator/studio.py` | exists only to expose the graph to Studio |
| `orchestrator/agents/{m1_topic,m2,m3_design,m4_analysis,m5_writing,supervisor,router_agent,read_handler,module_tools}` | imported only by `graph.py` / `graph_v2.py` / evals / their own tests |
| `orchestrator/__main__.py` `--auto-draft` path | the process being replaced |
| `job_runner.spawn_orchestrator_run` (`:414`) | no callers left |
| `job_runner._sync_context_store_from_checkpoint` (`:160`) + call site `:314` | see below |
| `api/app/main.py:45-47` graph warmup | no graph to warm |
| `orchestrator/evals/sim_thesis.py`, `backfill_eval.py` | drive the deleted graph |

`orchestrator/agents/base.py` **survives** — `token_meter.py:27`,
`tools/m2_literature.py:323`, `tools/m3_design.py:16` and `llm.py:113` all import
`bounded_invoke` from it.

`_sync_context_store_from_checkpoint` is pure loss-avoidance for a design the
deep agent does not have: the orchestrator kept module state in its LangGraph
checkpoint and never wrote the DB, so the API had to mirror the checkpoint into
`context_store` at every module boundary. `DbProjectStateStore.commit_slice`
writes that table directly. Deleting the mirror removes work, not a feature.

## Ordering constraint (this one bites)

`orchestrator/graph.py:272` defines `_get_async_pool()`, the lazy
`AsyncConnectionPool` behind `AsyncPostgresSaver`. **`api/app/routers/chat_v3.py:95`
imports it to build the checkpointer for interactive chat.** Deleting `graph.py`
before relocating that helper breaks chat, which is the one flow this project
cannot break.

So step 1 of implementation, before any deletion: move `_get_async_pool` (and the
module-level `_async_pool` global) into `api/app/db.py`, repoint `chat_v3.py:95`
and `main.py:45`, verify chat still streams. Only then delete.

## Changes to `headless_entry.py`

The runner currently serves exactly one caller (partner reports), so several
partner-specific behaviours are unconditional. They become mode-dependent, keyed
off a new `params["mode"]` (`"full_thesis"` for consumer auto-draft; absent /
`"report"` keeps today's behaviour).

**1. Profile (`_build_profile`, `:48`).**
`mode=full_thesis` → `required_modules=None` (all five). Skip
`set_report_chapters` and `set_grounded_backfill` (`:170-176`) — those scope M5 to
an ordered chapter subset and swap M2 for a grounded search, both meaningful only
for a partner report.

**2. Seed the brief.**
The orchestrator's `_seed` node (`graph.py:161`, START→`_seed`) turned
`{topic, language, citation_style}` into an M1 slice. The deep agent has no
equivalent, and `KICKOFF_PROMPT` (`:31`) assumes an already-seeded project
because partners seed via payload before spawning.

Before the first turn, `headless_entry` commits the brief through
`store.commit_slice("M1", {...}, reason="auto-draft brief")`. Deliberately **not**
appended to the kickoff prompt: `_state_header` (`agent/runtime.py:655`) re-reads
the store and re-injects it every turn, so a store-committed topic survives turn
40 while a prompt-only topic depends on the model remembering.

**3. SIGTERM → `paused`.**
`job_runner.cancel_job` sends SIGTERM (`:327`). `orchestrator/__main__.py:60,78`
installs a handler that writes a `paused` event and exits cleanly, which is what
`job_runner.py:300` reads to mark the run resumable. `headless_entry` has no
handler, so today a pause would kill the process with no terminal event and leave
the run stuck at `running`. Add the same handler, same event shape.

**4. Billing.**
`_charge_auto_run` (`job_runner.py:345`) sums `token_ledger` rows since
`run.started_at`. Those rows are written by `orchestrator/token_meter.py`, which
wraps `bounded_invoke` — a path the deep agent never takes. Without this change
auto-draft charges 0.

`agent/runtime.py:831` already emits `{"type": "usage", "input_tokens",
"output_tokens", "model"}` for every LLM step, and `headless_entry._on_event`
(`:194`) already sees every event. Accumulate there and write `token_ledger` rows
(`action_kind="deep_agent_turn"`, model from the event). `_charge_auto_run` then
needs no change at all, and the Transactions page keeps working.

## Budgets

`RunProfile` defaults (`agent/headless.py:66-69`) are `max_turns=40`,
`wall_clock_s=1800`, `max_stalls=5` — sized for a 4-chapter analysis report.
A full thesis is five modules including a real literature pass and full-length
M5 composition.

Proposed `full_thesis` budgets: `max_turns=120`, `wall_clock_s=7200`,
`max_stalls=5` unchanged. **These are estimates, not measurements.** The
30-minute ceiling that constrains the partner path is fillform's axios timeout
(`headless_entry.py:200-241`), which does not apply to the consumer flow — that
one polls SSE and can run long. The first real run validates or corrects these;
both stay overridable via job params, per the "budgets have ONE home" rule at
`headless_entry.py:64-67`.

`DOTHESIS_HEADLESS_RETRY_BUDGET_S` (default 1200) scales with the mode for the
same reason.

## Pause / resume semantics

Unchanged in the UI (`AutoDraftDrawer.tsx:57` pause, `ChatPane.tsx:388` resume).
Changed underneath:

- **Pause**: SIGTERM handler writes `paused`; monitor marks the run paused.
- **Resume**: `runs.py:172` spawns a **fresh** headless run over the state
  `commit_slice` already persisted, instead of re-entering a LangGraph
  checkpoint. `headless_entry.py:189-193` already describes this as the intended
  model ("a failed run *resumes* by re-running against that state, not by
  replaying chat"), and its internal retry loop already works this way.
- **Regression, stated plainly**: a module in progress but not yet committed is
  redone from the start. Completed modules are intact. The comment at
  `runs.py:158-162` describing checkpoint resume becomes false and must be
  rewritten, not left.

## langgraph.json

With the orchestrator graph gone, the file's only entry is dead. Repoint it at
the surviving loop: add `agent/studio.py` (no-arg factory returning
`build_agent(tmpdir, checkpointer=MemorySaver())`, mirroring
`orchestrator/studio.py:20`) and declare `"deepagent"`. `dev.sh:304-322` then
gives Studio on the loop that actually serves users — which is also the cheapest
way to inspect the `recursion_limit` question raised in the agent-loop audit.

## Testing

Existing tests that must keep passing, and that are the real safety net:

- `api/tests/test_auto_run_credit.py` — billing. Extend so it exercises a
  headless-sourced ledger row, not just an orchestrator one.
- `api/tests/test_runs_router.py`, `test_job_runner.py`, `test_stuck_runs.py`
- `agent/tests/test_headless_runner.py` — the three budget tests already cover
  `max_turns` / `wall_clock` / `max_stalls`.

New coverage:

1. `mode=full_thesis` → profile has `required_modules=None` and neither
   `set_report_chapters` nor `set_grounded_backfill` was called.
2. Brief seeding: after spawn, M1 slice holds topic/language/citation_style, and
   `_state_header` renders it.
3. SIGTERM → a `paused` event lands in `events.jsonl` and the monitor marks the
   job `paused`.
4. Usage → `token_ledger` rows exist for a headless run, and `_charge_auto_run`
   debits > 0. This is the test that would have caught the silent-free-run bug.
5. Deletion guard: no module outside `orchestrator/` imports `orchestrator.graph`.

The E2E harness (`DOTHESIS_E2E_MOCK=1`, `agent/testing/fake_model.py`) drives a
full fake-model auto-draft end to end without spending tokens.

## Risks

**1. Unproven at full-thesis scope — and the one test that would have proved it
was red.** In production the deep agent has never run headless with all five
modules required; partner runs always pass a chapter subset
(`headless_entry.py:72,172`).

Worse, `agent/tests/test_headless_runner.py::test_happy_path_runs_to_done` — the
only automated proof that a headless run drives M1–M5 to `done` — **fails on
master today**. Its fixture commits `conceptual_model: "CM"`, which the M3 gate
correctly refuses (`m3_model_required`: needs ≥2 constructs and ≥1
relationship); the model retries, exhausts the scripted completions, and the run
ends `failed / max_stalls` with `M3: locked`. So the spine's completion path has
had no green evidence behind it.

Verified while planning: replacing that fixture with the canonical
`{nodes, edges}` shape from `agent/m3_contract.py:13-18` makes the same run reach
`done / roadmap_done` in **5 turns with all five modules `done`**. Fixing it is
Task 1 of the plan and gates everything after it.

Residual risk after that fix: turn count and wall time at *real* model latency
and real content length remain unmeasured, so the budgets in Task 3 are an
estimate. Mitigation is that failure is loud — `max_turns` / `wall_clock` /
`max_stalls` all end as a failed run with partial state preserved, and every
completed module is already committed, so a bad run loses time, not work.

**2. No mid-module resume.** Stated above; accepted.

**3. Deleting the evals with the graph.** `orchestrator/evals/sim_thesis.py` is
the only simulated-student harness in the repo. Deleting it removes the one
automated way to exercise a whole run. Out of scope here, but it should be
rebuilt against the deep agent rather than quietly lost — noted for the backlog.
