# orchestrator/ — DoThesis agent graph

LangGraph-based agent graph that drives the chat-first thesis assistant. Five module agents (M1 Topic → M2 Literature → M3 Design → M4 Analysis → M5 Writing) over a shared Postgres-backed `ContextStore`.

> **Always read [`../AGENTS.md`](../AGENTS.md) and [`../researchflow-architecture-brief.md`](../researchflow-architecture-brief.md) before changing state shape, routing, or memory.** The brief's §1 lists NON-NEGOTIABLE principles and several are not yet met — `AGENTS.md` tracks which.

## Topology

Two graphs live side-by-side; selected by `ORCHESTRATOR_ROUTER`:

- **v1** (`graph.py`, default) — `START → _seed → supervisor → (M1|M2|M3|M4|M5|END)`. Conditional edge per module back to supervisor or END based on `_module_paused`. Used by interactive (FastAPI chat) AND auto-mode (subprocess `python -m orchestrator`).
- **v2** (`graph_v2.py`, `ORCHESTRATOR_ROUTER=v2`) — `START → _seed → router_agent_node → END`. One node, one tool call per turn. Closer to the brief's §4 router but still missing `(intent, target, changesFocus)` classification (see `AGENTS.md` gap #5).

Both share `_MODULE_FIELD`, the seed node, and the module agents themselves.

## State

`state.py:OrchestratorState` (LangGraph state) + `state.ContextStore` (Pydantic mirror of the `context_store` JSONB table). One slice per module — `m1_topic`, `m2_literature`, `m3_design`, `m4_analysis`, `m5_writing` — and a module is "confirmed" iff its slice has `confirmed_at` set.

> Brief §1.4: workflow status (`locked | in_progress | done | needs_review`) and conversation focus are **separate** concepts. Today we only have `current_module`; neither a `focus` field nor a per-module `status` map exists. Adding them is gap #4.

## Module agents

| Module | File | Owned slice | Shape (today) | Shape (brief §3) |
|---|---|---|---|---|
| M1 | `agents/m1_topic.py` | `m1_topic` | `ModuleAgent` chat loop | Wizard (`generateObject`) |
| M2 | `agents/m2/` | `m2_literature` | Phase machine ✓ | Phase chat ✓ |
| M3 | `agents/m3_design.py` | `m3_design` | `ModuleAgent` chat loop | Wizard |
| M4 | `agents/m4_analysis.py` | `m4_analysis` | Chat loop + paste-text parsers | Pipeline with sandboxed Python stats |
| M5 | `agents/m5_writing.py` | `m5_writing` | `ModuleAgent` chat loop | Wizard |

All five share `agents/base.py:ModuleAgent.step()`, which returns:

```python
ModuleStepResult(
    assistant_message: str,
    context_patch: dict,
    transition: bool,
    tool_calls_json: dict | None,    # widget render hint
    extra_messages: list[BaseMessage] | None,
)
```

A module writes ONLY into its own slice. The router (supervisor or router_agent) is the single place that decides whose turn it is.

## Routers

- `agents/supervisor.py` (v1) — rule-based `next_unconfirmed_module` + an LLM nav classifier (gated by `_awaiting_field` to prevent domain answers being misclassified as navigation).
- `agents/router_agent.py` (v2) — short-circuits (cold-start → M1, awaiting-field → that module), then LLM `bind_tools(..., tool_choice="any")` picks a module-tool. Module tools live in `agents/module_tools.py`.

Neither classifies **read vs mutate** (brief §1.5 / §4) yet — that's gap #5.

## Intake / planner / artifacts

- `intake.py` — `merge_import` (deterministic seed of slices), `assess_work` (LLM classifies pasted prose into proposed slices). Backs `POST /projects/{id}/import` and `/assess`.
- `artifacts.py` — DAG of deliverables (`topic`, `literature`, `design`, `analysis`, per-chapter `ch_*`) + deterministic DoD validators per artifact.
- `planner.py` — `plan_next(cs, target=...)` decides which artifact to work on or backfill next; drives `target_artifact` in state (enter-at-any-step).

Brief §9 dependency-hole reconciliation (model present + gaps absent → `M2 = needs_review`) is **not** wired because the `needs_review` status state doesn't exist yet (gap #4).

## Persistence

LangGraph PostgresSaver checkpoint backs interactive resume (`_get_pool`, `init_interactive_graph` → AsyncPostgresSaver; auto-mode uses sync `PostgresSaver`). **This conflicts with brief §1.3** ("DB is the checkpoint — do NOT reach for a checkpoint framework"). See `AGENTS.md` gap #3 for the fix path.

## Run

Interactive (via the FastAPI chat router): see `../api/README.md`.

Auto-mode (one-shot, used by the engine subprocess):

```bash
DATABASE_URL=postgresql://... GOOGLE_API_KEY=... python -m orchestrator <project_id>
```

## Tests

```bash
cd .. && pytest orchestrator/tests
```

## See also

- Brief: `../researchflow-architecture-brief.md`
- Gap map + module contract: `../AGENTS.md`
- HTTP: `../api/README.md`
- Frontend: `../web/README.md`
- Legacy CLI engine (independent product): `../engine/README.md`
