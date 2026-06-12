# ResearchFlow — Target Architecture (fix design)

> Companion to [`../../researchflow-architecture-brief.md`](../../researchflow-architecture-brief.md). The brief is the spec; this is the **concrete target architecture** that resolves the six §1 NON-NEGOTIABLE violations tracked in [`../../AGENTS.md`](../../AGENTS.md). Stack is Python (FastAPI + LangGraph + Postgres) + Next.js — language is tooling, the brief's principles are the contract.

The brief is written in TypeScript. Each section below restates the principle in Python terms and pins the exact shape we will land on. Migration sequencing is in §7.

---

## 1. State shape — `focus` separate from `status` (resolves §1.4 / gap #4)

**Today.** `OrchestratorState.current_module` is the only routing knob. A module is "confirmed" iff its slice has `confirmed_at`. There is no `focus`, no per-module status map, no `needs_review`.

**Target.**

```python
# orchestrator/state.py
ModuleStatus = Literal["locked", "in_progress", "done", "needs_review"]

class ModuleStatusMap(BaseModel):
    M1: ModuleStatus = "locked"
    M2: ModuleStatus = "locked"
    M3: ModuleStatus = "locked"
    M4: ModuleStatus = "locked"
    M5: ModuleStatus = "locked"

class ContextStore(BaseModel):
    m1_topic: dict | None = None
    m2_literature: dict | None = None
    m3_design: dict | None = None
    m4_analysis: dict | None = None
    m5_writing: dict | None = None
    # NEW — per brief §5: rolling per-module summaries.
    module_summaries: dict[ModuleKey, str] = Field(default_factory=dict)

class OrchestratorState(TypedDict, total=False):
    project_id: UUID
    thread_id: UUID
    messages: Annotated[list[BaseMessage], add_messages]
    context_store: ContextStore
    # NEW — split out of current_module.
    focus: ModuleKey | None       # default conversation context (brief §1.4)
    status: ModuleStatusMap       # workflow state (brief §1.4)
    mode: Mode
    target_artifact: str | None   # unchanged
    pending_widget_payload: dict | None
```

Status semantics (deterministic, no overlap):

| Status | When set |
|---|---|
| `locked` | Module has empty slice AND a prior-module gap blocks it. UI hint, not a wall (brief §8.4). |
| `in_progress` | Slice has content but `dod_<module>(slice)` returns `done=False`. |
| `done` | `dod_<module>(slice).done == True` (replaces the bare `confirmed_at` heuristic). |
| `needs_review` | An upstream mutate invalidated this module (set by §2's propagation rule). |

`status` is **derived state** — recomputed from `(context_store, dod_*)` on every state load (`compute_status_map(cs)`), persisted alongside `context_store` for fast reads, never the source of truth. The router writes `needs_review` explicitly; everything else flows from DoD checks.

**Schema migration** — add columns to `projects`:

```sql
ALTER TABLE projects ADD COLUMN focus VARCHAR(8) NULL;
ALTER TABLE projects ADD COLUMN status JSONB NOT NULL DEFAULT '{}'::jsonb;
-- Backfill from existing context_store + current_module:
--   focus := current_module (best available default for live projects)
--   status[M] := done iff slice has confirmed_at, locked otherwise.
```

Keep `projects.current_module` for one release as `focus`'s shadow; drop after callers (chat router, web) cut over.

---

## 2. Router — `(intent, target, changesFocus)` + `needs_review` propagation (resolves §1.5 / gap #5)

**Today.** v2 `router_agent.py` picks a module and always invokes its `step()`. No `read`. No `needs_review` propagation. `target_artifact` exists but backfills prerequisites — not downstream invalidation.

**Target.**

```python
# orchestrator/agents/router_agent.py
Intent = Literal["continue", "read", "mutate"]

class RouteDecision(BaseModel):
    intent: Intent
    target: ModuleKey
    changes_focus: bool      # true ONLY for mutate to non-focus module
    reason: str              # for logs + diagnostics
```

**Dispatch (one-tool-per-turn preserved):**

```
1. Short-circuits (no LLM):
   - cold-start (no module 'done')      → {continue, M1, false}
   - any _awaiting_field set            → {continue, that_module, false}
2. Else LLM classifies (Gemini, tool_choice="any" over 3 tools:
   answer_read, work_module, edit_module).
3. Execute:
   - intent=continue → focus.step(state)
   - intent=read     → run a thin "slice-answer" handler against
                       target.slice — NO write, NO module step,
                       focus unchanged.
   - intent=mutate   → target.step(state) with edit flag,
                       focus := target, propagate downstream.

4. Propagation on mutate (the §1.5 rule):
   for m in modules_after(target):
       if status[m] == 'done':
           status[m] = 'needs_review'
```

**Read handler** (new, tiny — `orchestrator/agents/read_handler.py`):

- Input: `(target, message, slice=cs[target])`.
- Output: an `AIMessage` that quotes/explains the slice. Pure prose; no write; no widget.
- Cost: one Gemini call against a ~1k-token prompt — cheaper than the full module step. This is how "what was gap 2 while I'm in M4" stops triggering a module visit.

**LLM router prompt** (replaces `orchestrator/prompts/router.md`): given recent turns + slice digest + focus, return JSON `{intent, target, changes_focus, reason}`. Three tools (`answer_read`, `work_module(target)`, `edit_module(target)`) — `tool_choice="any"` forces structured output. Domain-answer overlap (e.g. "PLS-SEM" while M3 awaits) is still caught upstream by the awaiting-field short-circuit, so the LLM only sees genuine routing choices.

---

## 3. Three handler shapes — Wizard / PhaseChat / Pipeline (resolves §1.7 / §3 / gap #7)

**Today.** All 5 modules subclass `ModuleAgent`. Only M2 actually wants the chat loop.

**Target.** Promote `ModuleAgent` from a class hierarchy into a Protocol; provide three concrete bases:

```python
# orchestrator/agents/base.py
class ModuleHandler(Protocol):
    module_key: ModuleKey
    slice_field: str

    def slice(self, cs: ContextStore) -> dict: ...
    def system_prompt(self, cs: ContextStore) -> str: ...
    def step(self, state: OrchestratorState) -> ModuleStepResult: ...
    def read(self, slice: dict, message: str) -> str: ...   # NEW — for intent=read

class WizardAgent(ModuleHandler):
    """M1, M3, M5. ONE structured-output call per turn against a Pydantic
    schema. Output validates → write slice → transition. No clarification
    loop, no _awaiting_field. The wizard owns the whole module decision
    in one shot; the user accepts/edits/rejects through widget actions."""
    schema: type[BaseModel]   # M1Output, M3Output, M5Output

class PhaseChatAgent(ModuleHandler):
    """M2 only. The brief's chat loop with the explicit phase machine
    (familiarization → research_state → gap_analysis → reference_confirm →
    output_gen). Existing orchestrator/agents/m2/* keeps its shape; we
    just stop inheriting it for the other modules."""

class PipelineAgent(ModuleHandler):
    """M4. Detect data type → propose outline → user confirms → execute
    steps. Execution calls a whitelisted analysis DSL inside the Python
    sidecar (brief §8). LLM does interpretation; sandbox does math."""
    dsl: AnalysisDSL
```

Migration: M1, M3, M5 keep their Pydantic schemas (`schemas/m{1,3,5}.py`); their `step()` becomes a single `generate_structured(schema)` call instead of a clarification walk. The existing `card_fields` widget mechanism survives — wizards still emit Card/Grid render hints; the difference is one validated commit per visit instead of N partial-field turns.

M2 and M4 keep their current internal flows. They just stop sharing the M1/M3/M5 base.

---

## 4. Memory — FULL MODE first, tiered later (resolves §1.6 / §5 / gap #6)

**Today.** Whole `messages` list flows through LangGraph state. Works until it doesn't.

**Target.** Implement the brief's mode switch, FULL mode first:

```python
# orchestrator/memory.py
WINDOW = 200_000             # model context window
TARGET = 40_000              # aim
FULL_MODE_CEILING = 90_000   # fits → skip all tiering

class AssembledContext(BaseModel):
    system_prompt: str
    handler_prompt: str
    state_slice: dict          # focus slice + (target slice if cross-module)
    turns: list[BaseMessage]   # full transcript in FULL mode; recent only in tiered
    retrieved: list[BaseMessage] = []
    summaries: dict[ModuleKey, str] = {}

def assemble_context(msg, route, store, transcript) -> AssembledContext:
    fixed = tk(system) + tk(handler) + tk(state_slice)
    if tk(transcript) + fixed < FULL_MODE_CEILING:
        return AssembledContext(..., turns=transcript)        # ← phase 1
    # phase 2 (not built yet): recent_window + retrieval + summaries
    ...
```

**Phase 1 (lands with #5):** transcript table + `assemble_context` with the `FULL_MODE_CEILING` check + a stub that raises `NotImplementedError` for the tiered path. Persistence: the existing `messages` table IS the transcript — no schema change.

**Phase 2 (later):** add `message_embeddings` (pgvector), an async compaction job that folds aged-out turns into `context_store.module_summaries[M]` via Gemini Flash, and `searchTranscript()` for retrieval.

The point of building phase 1 first: it forces every handler to read its context through `assemble_context()` instead of `state['messages']`. The day phase 2 lands, no handler changes.

---

## 5. Token meter (resolves §1.8 / gap #8)

**Today.** `bounded_invoke` wraps every LLM call for wall-clock; nothing meters tokens.

**Target.** A thin wrapper that estimates → reserves → reconciles:

```python
# orchestrator/token_meter.py
class TokenLedger(BaseModel):
    project_id: UUID
    reserved: int = 0          # estimate held against a credit account
    consumed: int = 0          # actual, from response usage
    entries: list[LedgerEntry] = []

def metered_invoke(llm, prompt, *, project_id, action_kind, max_seconds):
    estimate = estimate_tokens(prompt, llm)
    reserve(project_id, estimate, action=action_kind)
    try:
        resp = bounded_invoke(llm, prompt, max_seconds=max_seconds)
    finally:
        actual = usage_from(resp)
        reconcile(project_id, estimate, actual, action=action_kind)
    return resp
```

Persistence: new `token_ledger` table (`project_id, ts, action_kind, model, estimate, actual, delta`). Aggregates feed the per-action pricing table the brief alludes to in §1.8.

Every site that today calls `bounded_invoke(llm, ...)` becomes `metered_invoke(llm, ..., project_id=..., action_kind=...)`. The wall-clock cap survives (it's still inside).

---

## 6. Resume without LangGraph checkpoint (resolves §1.3 / gap #3)

**Today.** `init_interactive_graph()` and `get_auto_graph()` wire `AsyncPostgresSaver` / `PostgresSaver` as the checkpoint. Resume = LangGraph reloads state by `thread_id` from its internal checkpoint tables.

**Target.** Drop the checkpointer. Reconstruct the state we need at the start of every turn from our own tables:

```python
# orchestrator/loader.py
async def load_state(project_id, thread_id, *, db) -> OrchestratorState:
    cs = ContextStore(**load_context_store(db, project_id))
    msgs = load_messages(db, thread_id)         # full transcript
    project = load_project(db, project_id)
    return {
        "project_id": project_id,
        "thread_id": thread_id,
        "messages": msgs,
        "context_store": cs,
        "focus": project.focus,
        "status": compute_status_map(cs),       # derived
        "mode": "interactive",
        "target_artifact": project.target_artifact,
    }

async def persist_turn(turn_writes, *, db):
    # in ONE transaction:
    upsert_context_store(db, turn_writes.context_patch)
    update_project(db, focus=turn_writes.focus, status=turn_writes.status)
    insert_message(db, turn_writes.assistant_message)
    insert_messages(db, turn_writes.extra_messages)
    if turn_writes.snapshot:
        insert_version_history(db, ...)         # also closes brief §2 gap
```

The graph itself runs `MemorySaver` (in-memory) — no checkpoint persistence at the LangGraph layer. The single-source-of-truth becomes our own `context_store` + `messages` + `projects` tables, exactly as the brief §1.3 demands.

**Bonus:** this drops the dependency on `langgraph.checkpoint.postgres` and removes the msgpack-can't-serialize-callables problem that already bit us in `progress.py` (see `commit 14e75f5` — the emitter had to be moved out of graph state because PostgresSaver couldn't pickle it).

`version_history` (brief §2): a new `version_history` table written by `persist_turn` whenever `intent == 'mutate'` lands a slice change. One row per snapshot — `(project_id, ts, slice, before, after, reason)`. Closes the §2 gap with no extra code path.

---

## 7. Sequencing & landing order

Each PR is independently shippable behind a feature flag. Order is constrained by data dependencies:

1. **State shape** (§1) — add `focus` + `status` columns, backfill, compute_status_map, dual-write old + new. **No behavior change.** Flag: none — schema only.
2. **Token meter** (§5) — orthogonal, can land in parallel with #1. Flag: `TOKEN_METER_ENABLED` (off → fall through to plain `bounded_invoke`).
3. **Router rewrite + read handler + needs_review propagation** (§2) — depends on #1. Flag: `ORCHESTRATOR_ROUTER=v3` (v2 remains; v1 can retire after v3 soaks).
4. **FULL_MODE memory layer** (§4 phase 1) — all handlers read via `assemble_context()`. Flag: `MEMORY_ASSEMBLE=v1` (off → today's behavior).
5. **Handler shape split** (§3) — `WizardAgent` for M1/M3/M5, `PhaseChatAgent` for M2, `PipelineAgent` skeleton for M4. Flag: per-module (`M1_SHAPE=wizard`, …) so we can promote one module at a time.
6. **Drop LangGraph checkpoint** (§6) — switch to `MemorySaver` + `load_state` / `persist_turn`. Last because every prior step still works with the checkpoint in place; only this step requires every caller to be on the new persistence path. Flag: `RESUME_VIA_DB=true`.
7. **Tiered memory** (§4 phase 2) + **§8 Python sidecar** (GROBID / pyreadstat / sandboxed stats) — separate spec, not gated on the above.

Tests stay green at each step because each flag defaults off; the AGENTS.md gap map flips ❌ → ✅ entry by entry as flags flip on in production.

---

## 8. What does NOT change

- The 5-module decomposition (M1–M5) and their owned `context_store` slices.
- The widget render-hint protocol (`tool_calls_json`) and the four widget shapes (Card / Grid / ListEditor / FlowChart).
- M2's internal phase machine — only its base class changes.
- The intake flow (`orchestrator/intake.py`) — it gains `needs_review` propagation as a free side-effect of #1+#2.
- The HTTP surface (`/projects`, `/threads`, `/threads/{id}/messages`) — additive only.

The brief stays the contract. This doc is how we land it.
