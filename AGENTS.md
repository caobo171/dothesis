# AGENTS.md — DoThesis architecture & agent contract

> This is the **agent-facing operational map**: what the agent is, where each piece lives, and the invariants you must not break. System overview: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). End-to-end method: [`docs/PIPELINE.md`](docs/PIPELINE.md).

DoThesis is a commercial, chat-first thesis product. The student talks to **one deep agent** (LangChain `deepagents`) whose domain expertise is packaged as **skills** with progressive disclosure. The agent moves freely across five modules, each owning a slice of a project-scoped `context_store`:

| Key | Module | Skill | Owns (flat `context_store` keys) |
|-----|--------|-------|----------------------------------|
| M1  | Topic Discovery | `skills/dothesis-m1-topic/` | `research_title`, `research_questions` |
| M2  | Literature Review | `skills/dothesis-m2-literature/` | `literature_sources`, `research_gaps` |
| M3  | Research Design | `skills/dothesis-m3-design/` | `conceptual_model`, `hypotheses`, `methodology`, `instrument` |
| M4  | Data Analysis | `skills/dothesis-m4-analysis/` | `analysis_outline`, `analysis_results` |
| M5  | Writing | `skills/dothesis-m5-writing/` | `final_sections` / `chapters` |

Plus `skills/dothesis/` (root: state protocol + routing — read first every conversation) and `skills/dothesis-bootstrap/` (one-time entry wizard, fired by the new-project modal).

---

## Two runtimes, one state

There are **two brains**, both writing the same project state:

1. **Interactive chat — the deep agent (`agent/`).** Serves a chat turn when `DOTHESIS_AGENT_V3=1` (current default). One LLM agent + skills + tools, streamed over SSE.
2. **Auto-approve — the orchestrator graph (`orchestrator/`).** The "Auto approve" button starts a detached subprocess (`python -m orchestrator --auto-draft`) that runs a LangGraph M1→M5 graph unattended, composes all six chapters, and renders DOCX + PDF. This is **not legacy** — it is the production auto-mode path. (When `DOTHESIS_AGENT_V3` is off, the same orchestrator graph can also serve interactive chat via `ORCHESTRATOR_ROUTER`, but that path is being retired.)

Both paths persist to the same Postgres-backed `context_store` slices; checkpoint namespaces are disjoint (`v3:<thread_id>` for the agent, `<run_id>` for auto runs).

- Chat AND auto-draft both run the deep agent (`agent/runtime.py`).
  Auto-draft is the same brain driven headless (`api/app/headless_entry.py`).
- `langgraph.json` exists only for `langgraph dev` (Studio) via `dev.sh`.
  It is not read by any deployment.

---

## Surfaces

- `agent/` — **the chat runtime.** `runtime.py` (`create_deep_agent` factory + `stream_turn`, which yields `token`/`tool_start`/`tool_end`/`tool_calls`/`usage`/`error`/`done` events), `tools/` (`research_scout`, `parse_reference`, `run_stats` whitelist, `export_docx`, `make_state_tools` → `read_slice`/`commit_slice`, writing tools), `multimodal.py` (attachments), `cli.py` (spike CLI).
- `skills/` — the eight DoThesis skills (deepagents SKILL.md layout). Source of truth for module behavior. Read-only at runtime, mounted at `/skills/`.
- `api/` — FastAPI, **POST-only** (auth token in the JSON body; `/api/v1/health` is the one GET). Chat SSE = `routers/chat_v3.py`; auto runs = `routers/runs.py`; `job_runner.py` spawns + monitors the auto subprocess; `agent_state.py` (`DbProjectStateStore`) maps flat keys ↔ slice columns + `projects.module_status`/`focus`.
- `web/` — Next.js 15 chat workspace. Streams SSE via `fetch`+ReadableStream (not EventSource) so the token rides in the POST body; hits `NEXT_PUBLIC_API_BASE` directly to dodge the dev proxy's SSE buffering.
- `orchestrator/` — the auto-mode graph + agents (`agents/m1_topic.py` … `m5_writing.py`, `agents/base.py`), `__main__.py` (subprocess entrypoint, writes `events.jsonl`), `tools/m5_writing.py` (chapter composition + export), `tools/m2_literature.py` (research, reused by the agent's `research_scout`), `schemas/` (commit validation).
- `engine/` — research + writing muscle: `utils/api_citations/` + `utils/deep_research.py` back M2's search; `phases/` + `utils/export_professional.py` back the draft/export path.

---

## Invariants (NON-NEGOTIABLE) and where each is enforced

| Invariant | Enforced by |
|---|---|
| `context_store` is the single source of truth, **project-scoped** (shared by every thread of a project) | `agent/state.py:ProjectStateStore` (file, CLI) / `api/app/agent_state.py:DbProjectStateStore` (Postgres slice columns + `projects.module_status`/`focus`) |
| The ONLY write path is `commit_slice` | State tool boundary — validates slice ownership, snapshots version, applies, shifts focus, flags downstream. The agent never free-writes state. |
| Read = free; mutate = focus shift + downstream `needs_review` ⚠ | `commit_slice` propagation over the static DAG (M1→…, M2→M3..M5, M3→M4,M5, M4→M5); only *started* modules get flagged. `read_slice` never mutates. |
| Soft locks, never walls | Skill instructions (`skills/dothesis/SKILL.md`) — the student may jump modules. |
| **No fabricated sources / numbers** | Tools over memory: papers via `research_scout`/`parse_reference` (engine validation against CrossRef/OpenAlex/Semantic Scholar/arXiv); stats via `run_stats` (whitelisted ops only — the whitelist IS the security boundary). M4's skill forbids committing `analysis_results` without a real uploaded dataset. |
| **No *incorrect* numbers — hard stats-validation findings block M4 commits** | Deterministic self-validation (thesis-stats) runs at `run_stats`/`check_thresholds` and at the M4 `commit_slice` gate (`agent/stats_validation.py`). A *hard* finding — a number that is mathematically impossible or self-contradictory (loading > 1, AVE ≠ mean λ², t↔p impossible, CI excludes its estimate, PLS/CB-SEM family mix) — blocks the `analysis_results` commit. The third hard boundary alongside verified sources and the whitelist. Soft findings warn only; the validator fails open. |
| **Prose must match state — coherence gate blocks M5 commits** | The M5 `commit_slice` gate (`agent/coherence.py`) hard-blocks `final_sections` when a β/t/p/R²/f² quoted in the prose (attributed to a hypothesis) contradicts the persisted `analysis_results` beyond display-precision tolerance — a differing quote is provably wrong against state that already passed the M4 gate. Coverage/direction/decision/undiscussed checks are soft `coherence_warnings`. Also enforced by the rubric `coherence` dimension (hard → `blocking`) for the auto-draft/editor/legacy paths. Fails open. |
| Long turns stay alive over SSE, survive disconnect | `agent/runtime.py:stream_turn` + `api/app/routers/chat_v3.py`: tool activity rides `progress` (plain-language, student-facing labels built in `chat_v3._tool_progress_label`); on client disconnect the agent task is cancelled and the partial reply is persisted via an idempotent `_finalize()`. |
| Token metering + per-turn charge | `orchestrator/token_meter.py` sink registered in `api/app/main.py` lifespan; chat turns charge credits in `chat_v3._finalize`; auto runs charge in `job_runner._charge_auto_run`. |
| Auto runs are simple + analysable | M3 auto-fill is constrained to plain multiple linear regression (`m3_design.py:auto_fill_directive`); M4/M5 prompts forbid mixing PLS-SEM and CB-SEM fit indices and require real-data tables. |

**When updating any code:** comment the *reasoning* behind non-obvious changes (a short `# Decision:`/prose note). **When updating a module's behavior:** edit its `skills/*/SKILL.md` first (skill name == directory name, description ≤1024 chars, body <500 lines; heavy detail → `references/`).

---

## Auto-approve run lifecycle

1. `POST /api/v1/projects/{id}/runs` → `job_runner.spawn_orchestrator_run` writes `brief.json` + `events.jsonl`, spawns `python -m orchestrator --auto-draft`, and `start_monitor` schedules an async tailer on the app loop (works even though the endpoint is sync — the loop is captured at startup).
2. The subprocess streams the graph, writing semantic events (`activity`, `phase_progress`, `job_done`, `error`) to `events.jsonl`. Agent-internal beats (M2 scout search, M5 per-chapter writing) are bound through `engine.utils.progress` and written too, so the feed isn't silent during long phases.
3. `_monitor` tails the file → `JobEvent` rows + `pubsub`. The drawer subscribes via `POST /api/v1/runs/{id}/events` (SSE: DB backlog replay, then live).
4. Controls: `pause`/`resume` (resume re-enters at the LangGraph checkpoint), `cancel` (SIGTERM + mark canceled), and the drawer's **Retry** for failed/canceled runs.

---

## Where to look

- Runtime + tools: `agent/runtime.py`, `agent/tools/`, `agent/state.py`
- Skills: `skills/*/SKILL.md`
- Chat bridge: `api/app/routers/chat_v3.py`, `api/app/agent_state.py`
- Auto runs: `api/app/routers/runs.py`, `api/app/job_runner.py`, `orchestrator/__main__.py`, `orchestrator/agents/`, `orchestrator/tools/m5_writing.py`
- Engine muscle: `engine/utils/api_citations/`, `engine/utils/deep_research.py`, `engine/utils/export_professional.py`, `engine/phases/`
- Frontend chat: `web/app/components/chat/`
- Tests: `agent/tests/`, `api/tests/`, `orchestrator/tests/`
