# AGENTS.md — DoThesis architecture & agent contract (v3)

> **Architecture:** [`docs/architecture/2026-06-10-deepagent-skills-architecture.md`](docs/architecture/2026-06-10-deepagent-skills-architecture.md) — the deep-agent + skills redesign. This file is the **agent-facing operational map** of that architecture in this codebase.
>
> Historical context: the v2 brief ([`researchflow-architecture-brief.md`](researchflow-architecture-brief.md)) and its state-machine fix design ([`docs/architecture/2026-06-03-researchflow-target-architecture.md`](docs/architecture/2026-06-03-researchflow-target-architecture.md)) are **superseded**. v3 deliberately reversed the brief's "state machine, not a free agent" principle; everything else the brief cared about survives as deterministic code (see the invariants table below).

DoThesis is the commercial chat-first thesis SaaS. The student talks to **one deep agent** (LangChain deepagents) whose domain expertise is packaged as **skills** with progressive disclosure, moving freely across 5 modules:

| Key | Module | Skill | Owns (flat context_store keys) |
|-----|--------|-------|-------------------------------|
| M1  | Topic Discovery | `skills/dothesis-m1-topic/` | `research_title`, `research_questions` |
| M2  | Literature Review | `skills/dothesis-m2-literature/` | `literature_sources`, `research_gaps` |
| M3  | Research Design | `skills/dothesis-m3-design/` | `conceptual_model`, `hypotheses`, `methodology`, `instrument` |
| M4  | Data Analysis | `skills/dothesis-m4-analysis/` | `analysis_outline`, `analysis_results` |
| M5  | Writing | `skills/dothesis-m5-writing/` | `final_sections` |

Plus `skills/dothesis/` (root: state protocol + routing semantics — read first every conversation) and `skills/dothesis-bootstrap/` (one-time entry wizard).

---

## Surfaces

- `agent/` — **the v3 runtime.** `runtime.py` (create_deep_agent factory + `stream_turn` SSE-shaped event stream), `state.py` (guarded ProjectStateStore: ownership, version snapshots, focus shift, needs_review propagation), `tools/` (research_scout, parse_reference, run_stats whitelist, write_pipeline/export_docx seams, state tools), `cli.py` (spike CLI).
- `skills/` — the 8 DoThesis skills (deepagents SKILL.md layout). Source of truth for module behavior; the Claude.ai bundle in `dothesis_v2/` is the zero-infra distribution of the same skills.
- `api/` — FastAPI. Chat SSE (`routers/chat.py` → `routers/chat_v3.py` when `DOTHESIS_AGENT_V3=1`), `agent_state.py` (DB-backed store mapping flat keys ↔ context_store slice columns), projects/threads/uploads/billing.
- `web/` — Next.js 15. Chat UI (DoThesis.html design), dashboard, module tracker. Consumes the same SSE vocabulary from either brain.
- `engine/` — the research + writing muscle. `utils/deep_research.py` + `utils/api_citations/` back M2's `research_scout`; the draft pipeline (structure→compose→citations→compile→validate + docx post-processor) backs M5's `write_pipeline`/`export_docx`.
- `orchestrator/` — **legacy graph (v1/v2), being strangled.** Serves chat turns only when `DOTHESIS_AGENT_V3` is off. `orchestrator/tools/m2_literature.py` is still load-bearing (research_scout reuses it); `shapes.py` schemas survive as commit validation. Do not invest new feature work here.

## Runtime selection

`DOTHESIS_AGENT_V3=1` (set in `.env`) → chat turns served by the deep agent. Unset/0 → legacy graph_v2/v1 per `ORCHESTRATOR_ROUTER`. Rollback is the env var; the two runtimes use disjoint checkpoint namespaces (`v3:<thread_id>` vs `<thread_id>`) over the same Postgres saver.

---

## Invariants (NON-NEGOTIABLE) and where each is enforced

| Invariant | Enforced by |
|---|---|
| `context_store` is the single source of truth, **project-scoped** (shared by every thread/session of a project) | `agent/state.py:ProjectStateStore` (file-backed, CLI) / `api/app/agent_state.py:DbProjectStateStore` (Postgres slice columns + `projects.module_status`/`focus`) |
| The ONLY write path is `commit_slice` | Tool boundary — validates slice ownership (`SLICE_OWNERSHIP`), snapshots version, applies, shifts focus, flags downstream. The agent never free-writes the state file. |
| Read = free; mutate = focus shift + downstream `needs_review` ⚠ | `commit_slice` propagation over the static DAG (M1→M2..M5, M2→M3..M5, M3→M4,M5, M4→M5); only *started* modules get flagged. `read_slice` never mutates. |
| Soft locks, never walls | Skill instructions (`skills/dothesis/SKILL.md` invariants section) |
| No fabricated sources / numbers / prose mechanics | Tools over memory: papers via `research_scout`/`parse_reference` (engine validation), stats via `run_stats` (whitelisted ops only — the whitelist IS the security boundary), docs via `write_pipeline`/`export_docx` |
| Long turns stay alive over SSE | `agent/runtime.py:stream_turn` yields token/tool_start/tool_end/error/done events; `api/app/routers/chat_v3.py` bridges them onto the existing SSE channel (tool activity rides `progress` → live ProgressBubble) |
| Token metering wraps the LLM call | `orchestrator/token_meter.py` — middleware integration for the agent path is **pending** (next: wrap the model in `build_agent`) |

**When updating any code**: keep the comment-the-reasoning rule — non-obvious decisions get a short `# Decision: ...` (or prose) block.

**When updating a skill**: skill name == directory name, description ≤1024 chars, body <500 lines; heavy detail goes in `references/`. Behavioral edits land in `skills/` first, back-port to `dothesis_v2/` for the Claude.ai bundle.

---

## v3 migration status (strangler)

| Step | Status |
|---|---|
| 1. CLI spike (skills + state tools + runtime) | ✅ verified live — bootstrap → M1 wizard with real commits |
| 2. Engine tools | ✅ `research_scout` (reuses the proven m2_literature path), `parse_reference` (Crossref + PDF), `run_stats` (6 whitelisted ops). 🟡 `write_pipeline`/`export_docx` are honest not-wired seams — the engine's draft path needs a job-context adapter. |
| 3. Web behind flag | ✅ `DOTHESIS_AGENT_V3=1` → `chat_v3.py`; state lands in the same rows the web reads (module tracker, ContextPanel, dashboard unchanged) |
| 4. Middleware parity | ❌ token metering + HITL interrupts + per-turn budget caps |
| 5. Cutover & deletion of the graph | ❌ after soak; delete router_agent, module agent classes, graph_v2 |
| 6. Later | auto-draft runs converge on a `writer` subagent; tiered memory; version_history table wiring for DbProjectStateStore |

---

## Where to look

- Architecture: `docs/architecture/2026-06-10-deepagent-skills-architecture.md`
- Runtime + tools: `agent/runtime.py`, `agent/state.py`, `agent/tools/`
- Skills: `skills/*/SKILL.md` (+ `skills/README.md` for the v2-bundle deltas)
- API bridge: `api/app/routers/chat_v3.py`, `api/app/agent_state.py`
- Engine muscle: `engine/utils/deep_research.py`, `engine/utils/api_citations/`, `engine/phases/`, `engine/utils/docx_post_processor.py`
- Tests: `agent/tests/`, `api/tests/test_agent_state.py`, `api/tests/test_chat_v3.py`
- Legacy graph (flag-off path only): `orchestrator/graph.py`, `orchestrator/graph_v2.py`, `orchestrator/agents/`
- Frontend chat: `web/app/components/chat/`
