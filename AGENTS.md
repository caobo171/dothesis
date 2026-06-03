# AGENTS.md — DoThesis / ResearchFlow architecture & agent contract

> **Source of truth:** `researchflow-architecture-brief.md` (the brief).
> This file is the **agent-facing operational map**: how the brief lands in this codebase, where the implementation matches, and where it diverges.

DoThesis is the commercial chat-first SaaS built on top of the OpenDraft engine. The student talks to one assistant in one thread and moves freely across **5 modules**:

| Key | Module | Output owned (ContextStore field) |
|-----|--------|-----------------------------------|
| M1  | Topic Discovery | `m1_topic` |
| M2  | Literature Review | `m2_literature` |
| M3  | Research Design | `m3_design` |
| M4  | Data Analysis | `m4_analysis` |
| M5  | Writing | `m5_writing` |

---

## Stack note — language is just tooling

The brief (§7) recommends Next.js + Vercel AI SDK + Claude. This codebase uses Python (FastAPI + LangGraph) + Gemini Flash + Next.js (frontend only). **That is a tooling choice, not an architectural violation.** The brief's §1 principles are the contract; they MUST hold regardless of language.

Surfaces in this repo:

- `api/` — FastAPI. HTTP entry: projects, threads, chat SSE, exports, billing.
- `orchestrator/` — Python agent graph. 5 module agents, supervisor (v1) or router_agent (v2), Postgres-backed state.
- `web/` — Next.js 15 frontend. Renders the chat thread + per-module widgets.
- `engine/` — Legacy OpenDraft CLI (19-agent draft pipeline). Independent of the chat SaaS — kept for the standalone draft-generator product and reused for citation utilities.

---

## §1 Non-negotiables — status against the brief

The brief calls these NON-NEGOTIABLE. Treat any ❌ below as a MUST-FIX before further feature work.

| # | Principle (brief §1) | Status | Where it lives / what's missing |
|---|---|---|---|
| 1 | State machine, not a free agent | ✅ | `orchestrator/graph.py` (v1: supervisor + 5 spokes), `orchestrator/graph_v2.py` (v2: router_agent + module tools). One module per turn — no open-ended ReAct loop. |
| 2 | `context_store` is the single source of truth | ✅ | Postgres JSONB table `context_store` per project (`api/migrations/versions/20260526_add_orchestrator_tables.py`). Modeled as `orchestrator.state.ContextStore`. |
| 3 | DB is the checkpoint — **do NOT reach for a checkpoint framework (LangGraph etc.)** | ❌ MUST-FIX | We DO use LangGraph's `PostgresSaver` / `AsyncPostgresSaver` for checkpointing (`orchestrator/graph.py:_get_pool`, `init_interactive_graph`). The brief's intent — resume falls out of `context_store` + per-module status, not a checkpoint framework — is violated. Fix path: drop the checkpointer, drive resume from `context_store` + `messages` table directly. |
| 4 | Conversation focus ≠ workflow state. Current module is a **default context, never a lock**. | ❌ MUST-FIX | We only have `OrchestratorState.current_module` and `projects.current_module`. There is no separate `focus` field, and no per-module `status: locked \| in_progress \| done \| needs_review` map. Today "confirmed" is encoded by a `confirmed_at` timestamp inside each slice — there is no `needs_review` state to set. Fix path: add `project.focus`, add `project.status: Record<ModuleId, ModuleStatus>`, route off `focus` (not `current_module`). |
| 5 | Reads are free; mutates shift focus + flag downstream `needs_review ⚠` | ❌ MUST-FIX | The router (v1 supervisor / v2 `router_agent.py`) picks a module and runs `agent.step()`. It does NOT classify `intent ∈ {continue, read, mutate}`, never returns a `read` that answers from a slice without invoking the module, and never propagates `invalidates` to downstream modules. `target_artifact` + `orchestrator/planner.py` exists but only backfills prerequisites — it does not flag downstream `needs_review` on a mutate. Fix path: introduce `RouteDecision { intent, target, changesFocus }`; for `read`, answer from the target slice and **change nothing**; for `mutate`, write + shift focus + mark M(target+1..M5) `needs_review`. |
| 6 | "Reads all previous messages" via **layered memory**, not by stuffing the transcript every turn | ❌ MUST-FIX | We rely on LangGraph state + recent messages only. No `FULL_MODE_CEILING` switch, no recent-window + retrieval + rolling-summaries assembly (brief §5), no pgvector table, no async compaction on turn-commit, no `ContextStore.module_summaries`. Today this is invisibly broken on long threads — a thesis project will eventually overflow. Fix path: implement FULL MODE first (just send the whole transcript while it fits — perfect recall, zero machinery), then add the tiered path keyed off `FULL_MODE_CEILING`. |
| 7 | Three interaction shapes — don't treat all modules as "an agent" (brief §3) | ❌ MUST-FIX | All 5 modules inherit `orchestrator/agents/base.py:ModuleAgent` and run the same clarification chat loop. The brief says **M1, M3, M5 should be wizards** (one structured-output call against a Zod/Pydantic schema → write a validated slice), **M2 a chat loop with phases** (✅ implemented — `orchestrator/agents/m2/` + `orchestrator/prompts/m2/1_familiarize.md`…`5_output_gen.md`), **M4 a pipeline that actually runs stats**. We have only the M2 shape — bent to fit M1/M3/M5. Fix path: split `ModuleAgent` into `WizardAgent` (M1/M3/M5) and `PhaseChatAgent` (M2) and `PipelineAgent` (M4). |
| 8 | Token metering wraps the actual LLM call | ❌ MUST-FIX | No `TokenLedger` on `Project`. `bounded_invoke` in `orchestrator/agents/base.py` caps wall-clock but does not estimate → reserve → reconcile against real usage. Per-action pricing therefore cannot be trusted to match cost. Fix path: meter at the LangChain/Gemini call boundary, persist to a `token_ledger` table, reconcile on every turn. |

### Other contract gaps (non-§1 but called out elsewhere in the brief)

| Where | Gap | Status |
|---|---|---|
| §2 | `version_history` — append-only snapshots of `context_store` | ❌ Not implemented. `context_store` table updates in place. |
| §3 / §8 | M4 sandboxed Python stats (pandas / scipy / statsmodels / pingouin in gVisor/Firecracker or a network-less container) | ❌ Not implemented. M4 currently parses pasted text (`orchestrator/tools/m4_parsers/`) and asks the LLM to interpret — it does NOT execute statistics on raw data. This is also the §8 security surface (prompt-injection → arbitrary Python) and must be sandboxed before raw-data upload ships. |
| §7 | Python sidecar — GROBID for PDF→references, pyreadstat for `.sav`/`.spv` | ❌ Not implemented. Citation APIs (CrossRef/OpenAlex/SemanticScholar/arXiv) live in `engine/utils/api_citations/` but the academic-PDF → structured-reference path is hand-rolled, not GROBID. |
| §9 | Entry wizard / `bootstrapProject` | 🟡 Partial. `orchestrator/intake.py` has `merge_import` (deterministic seed) + `assess_work` (LLM classify pasted prose into slices). Dependency-hole reconciliation (model present + gaps absent → `M2 = needs_review`) is **not** wired because `needs_review` (gap #4) doesn't exist yet. |
| §7 | Redis + BullMQ for async file parsing / batch paper analysis / compaction | ❌ Not implemented. Long work runs inline or via the engine subprocess. |

### Already in good shape

- M2 phase machine (`familiarization → research_state → gap_analysis → reference_confirm → output_gen`) — `orchestrator/agents/m2/phases/` + `orchestrator/prompts/m2/`.
- Widget render-hint protocol (Card/Grid/ListEditor/FlowChart) — `orchestrator/agents/widgets.py` + `web/app/components/chat/widgets/`. Mutate-on-confirm + dynamic LLM-grounded card options.
- `target_artifact` + `orchestrator/planner.py` + `orchestrator/artifacts.py` — enter-at-any-step via prerequisite backfill (still needs to be paired with `needs_review` propagation per §1.5).
- `orchestrator.message_utils`, `orchestrator/agents/base.py:bounded_invoke` — wall-clock-bounded Gemini calls + transient retry.
- Projects / threads / messages schema with `context_store` JSONB — matches brief §2 shape.

---

## Module agent contract (today)

Every module agent in `orchestrator/agents/` implements `ModuleAgent.step(state) -> ModuleStepResult`:

```python
@dataclass
class ModuleStepResult:
    assistant_message: str          # text shown to the user
    context_patch: dict             # write into the owning slice (e.g. m3_design)
    transition: bool                # True → module finished this turn; False → waiting on user
    tool_calls_json: dict | None    # widget render hint (Card/Grid/ListEditor/FlowChart)
    extra_messages: list[BaseMessage] | None  # M4 step emissions
```

`ContextStore` field per module is fixed (`orchestrator/state.py:_MODULE_TO_FIELD`); a module writes ONLY into its own slice. The router (v1 supervisor or v2 router_agent) is the single place that decides which module owns the next turn.

**When updating an agent**: keep the comment-the-reasoning rule — non-obvious decisions get a short `# Decision: ...` block.

---

## Graphs — v1 vs v2

Selected by `ORCHESTRATOR_ROUTER` env (`v1` default, `v2` opt-in):

- **v1** (`orchestrator/graph.py`): START → `_seed` → `supervisor` → (`M1`|`M2`|`M3`|`M4`|`M5`|END). Conditional edge per module back to supervisor or END based on `_module_paused`. Used by both interactive (FastAPI chat) and auto-mode (subprocess `python -m orchestrator`).
- **v2** (`orchestrator/graph_v2.py`): START → `_seed` → `router_agent_node` → END. One node, one tool call per turn. Closer to the brief's §4 router, but still missing the `(intent, target, changesFocus)` shape (see gap #5).

Both share `_MODULE_FIELD`, the seed node, and the module agents themselves — only routing differs.

---

## Build order (brief §10) — where we are

1. ✅ Project + `context_store` schema + version snapshots → **partial** (no `version_history` yet).
2. ✅ Single chat thread, FULL transcript mode, one module end-to-end.
3. ✅ ModuleHandler interface + 5 handlers — but shape #1 only (chat loop). Wizard (M1/M3/M5) + Pipeline (M4) still pending (gap #7).
4. 🟡 Entry wizard — `intake.py` exists; dependency-hole reconciliation gated on gap #4.
5. 🟡 Router — v2 exists but no `(intent, target)` classification (gap #5).
6. ❌ Read vs mutate + downstream `needs_review` propagation (gap #5).
7. ❌ Token meter (gap #8).
8. ❌ Tiered memory (gap #6).
9. ❌ Python sidecar (GROBID / pyreadstat / sandboxed stats) (gaps §3/§7/§8).

---

## Where to look

- Brief: `researchflow-architecture-brief.md`
- Graph + state: `orchestrator/graph.py`, `orchestrator/graph_v2.py`, `orchestrator/state.py`
- Module agents: `orchestrator/agents/m1_topic.py`, `m2/`, `m3_design.py`, `m4_analysis.py`, `m5_writing.py`
- Routers: `orchestrator/agents/supervisor.py` (v1), `orchestrator/agents/router_agent.py` (v2)
- Schemas (Pydantic): `orchestrator/schemas/m{1..5}.py`
- Tools: `orchestrator/tools/m{1..5}_*.py`
- Prompts: `orchestrator/prompts/m{1..5}.md` (+ `prompts/m2/<phase>.md`)
- Intake / planner / artifacts: `orchestrator/intake.py`, `orchestrator/planner.py`, `orchestrator/artifacts.py`
- HTTP surface: `api/app/routers/chat.py`, `api/app/models.py`, `api/migrations/versions/20260526_add_orchestrator_tables.py`
- Frontend chat: `web/app/components/chat/`
