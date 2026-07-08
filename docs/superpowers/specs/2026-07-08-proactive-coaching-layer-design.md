# Proactive Coaching Layer Design

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Sequence:** Spec 2 of 2. Depends on Spec 1 (Unify Headless Generation) for the single
chapter-scoped `assess_export_readiness` gate, which this layer reads as one input to
per-module completeness.

## Problem

DoThesis's agent is **reactive**: it answers well when asked, but it doesn't lead. The
state machine tracks only 5 coarse modules (M1–M5, `locked/in_progress/done/needs_review`),
so the agent can say "work on M2" but not "you are here → do this next → why." There is no
roadmap, no next-best-action, no proactive nudge. The product goal is to **guide a student
step-by-step to finish their (quantitative) thesis**, which requires the agent to lead.

## Goals

- **Proactive leading:** every turn, the agent knows the student's exact position and the
  single next action, and closes the turn leading toward it.
- **A visible roadmap:** the student sees modules → sub-steps → where they are → what's
  next, in the UI.
- **Position is derived, never narrated:** the current sub-step is *computed* from real
  artifacts in the store (Approach A), consistent with the codebase's "done must be earned,
  not narrated" philosophy. The model cannot lie about progress.
- **Hybrid grain:** a fixed sub-step spine (stable, renderable) + agent-inserted
  student-specific tasks under a step (the messy real-world blockers).

## Non-goals

- No change to the headless surfaces (auto-mode, partner API). This is chat-only. See
  `project_headless_surfaces` memory: null-safe on headless-produced state, no new gates,
  the new `roadmap` slice is unread/unwritten by headless paths.
- No stats engine, no deadline/timeline planning (possible later; YAGNI now).
- Not the three follow-on gaps (quality-evals, cross-session memory, prod observability) —
  each is its own future spec. This layer is their host.

## Approach A (chosen): derived roadmap

Rejected alternatives (from brainstorming): **B — explicit sub-step tracking** (agent
advances steps) reintroduces the confabulation the codebase fights; **C — agent-todo
driven** (deepagents `write_todos`) is thread-scoped and non-deterministic, can't anchor a
persistent roadmap. Approach A computes position from state, so it's deterministic,
testable, and can't hallucinate.

## Design

### 1. Data model

Three pieces:

**a) The fixed spine (`ROADMAP`, code constant in `agent/roadmap.py` — not stored).**
A static per-module ordered sub-step list, transcribed from the phases the skills already
define:

```python
ROADMAP = {
    "M1": ["frame_topic", "propose_titles", "confirm_title", "derive_questions"],
    "M2": ["familiarize", "map_research_state", "find_gaps", "confirm_refs", "generate_output"],
    "M3": ["define_constructs", "build_model", "state_hypotheses", "choose_method", "design_instrument"],
    "M4": ["detect_data", "outline_analysis", "confirm_plan", "run_per_step", "interpret"],
    "M5": ["synthesize_sections", "assemble", "export"],
}
```

Lives in code (like `SLICE_OWNERSHIP`) — no migration, can't drift.

**b) `derive_substep(module, state) -> str | None`** — a pure function per module reading
existing slice contents to compute the current sub-step. It reuses Spec 1's
`assess_export_readiness` where it can (e.g. "M2 has real sources+gaps" ⇒ past
`find_gaps`). Returns `None` when the module is untouched (→ its first sub-step) or fully
satisfied (→ ready to confirm done).

**c) A `roadmap_tasks` key + its own write path** — the hybrid layer. Agent-inserted
blockers: `[{id, module, substep, title, why, status: "open"|"done"}]` stored under a
`roadmap_tasks` key in the context store.

**Not via `commit_slice`.** `commit_slice` is coupled to real modules — it shifts `focus`,
sets module `status`, and propagates `needs_review` downstream (`agent/state.py:194-205`).
Routing coaching blockers through it would corrupt focus/status. Instead, add a dedicated
lightweight store path `upsert_roadmap_task` / `resolve_roadmap_task` that writes only the
`roadmap_tasks` key (no focus shift, no status change, no version snapshot — blockers are
ephemeral coaching aids, not thesis content). The agent calls two new small tools
`flag_blocker(module, substep, title, why)` and `resolve_blocker(task_id)` that wrap those.
An open blocker under the current sub-step means "not done until cleared."

### 2. Next-action engine

`next_action(state) -> NextAction | None` in `agent/roadmap.py` — pure, deterministic,
top-down:

1. **Open blocker wins** — highest-priority open `roadmap_tasks` entry.
2. **Else `needs_review` wins** — resolve stale foundations before advancing.
3. **Else advance focus** — `derive_substep(focus, state)`; if focus's last sub-step is
   satisfied → "confirm this module done."
4. **Else next module** — first `locked/in_progress` module in M1→M5 order; surface any
   missing prerequisite as the reason.
5. **Else** — "export your thesis / final review."

```python
NextAction = {
    "module": str, "substep": str, "title": str, "why": str,
    "cta_options": list[str],   # rendered via the existing [OPTIONS] marker
}
```

Null-safe: on headless-produced state (no `roadmap_tasks`), steps 2–5 still work.

### 3. Agent behavior

- **Per-turn injection:** `_state_header` (`agent/runtime.py:495`) gains a `[NEXT]` line
  built from `next_action(state)`, injected alongside `[PROJECT STATE]`
  (`agent/runtime.py:543`). The model sees position + next-action every turn — ground truth
  it can't ignore, same mechanism as the existing state header.
- **System prompt** (`agent/runtime.py:160`) gains a short "proactive leading" rule: close
  each turn by leading toward `[NEXT]`, rendering `cta_options` via `[OPTIONS]`.
- **Root skill** (`skills/dothesis/SKILL.md`) gains a "Proactive leading" section
  formalizing continue → lead, and documents the blocker convention (insert/clear a
  student-specific task via the `flag_blocker` / `resolve_blocker` tools).
- `derive_substep`/`next_action` live in `agent/roadmap.py`, imported by both the runtime
  (injection) and the API (UI) — one source of truth.

### 4. API

One new endpoint, POST-only (project convention): `POST /projects/{id}/roadmap`:

```json
{ "modules": [
    { "id": "M2", "status": "in_progress", "current": "find_gaps",
      "substeps": [ { "id": "familiarize", "label": "…", "state": "done" }, … ] }, … ],
  "tasks": [ { "id": "…", "module": "M4", "substep": "interpret", "title": "…", "why": "…" } ],
  "next_action": { "module": "M4", "substep": "interpret", "title": "…", "why": "…",
                   "cta_options": ["…"] } }
```

Computed server-side from `DbProjectStateStore` (`api/app/agent_state.py`) by calling
`agent/roadmap.py`. Sub-step `state` ∈ `done | current | upcoming`. Null-safe.

### 5. UI

Extend the right-hand **`ContextPanel`** (`web/app/components/chat/ContextPanel.tsx`) — the
current home of module status (the left `WorkflowSidebar` rail was removed):

- A pinned **"Next" card** at the top = `next_action`, with `cta_options` as buttons that
  post the CTA text straight into the chat input.
- Each module expandable to its sub-steps, with the **current** sub-step highlighted and
  open `roadmap_tasks` shown as items beneath their step.
- Fed by `POST /projects/{id}/roadmap`, refreshed on each turn's `done` SSE event.

## Data flow

```
turn:  user msg
        → runtime prepends [PROJECT STATE] + [NEXT] (from next_action(state))
        → agent leads, may flag_blocker(…) to insert a student-specific blocker
        → done event
UI:     on 'done' → POST /projects/{id}/roadmap → re-render roadmap + Next card
```

## Error handling

- `derive_substep`/`next_action` are pure and total — no exceptions on partial/empty/
  headless state; missing pieces yield `None`/first-step, never a crash.
- The roadmap endpoint errs safe: a load failure returns the coarse module status with an
  empty `next_action` rather than 500ing (mirrors `_state_header`'s silent-omit).
- `upsert_roadmap_task`/`resolve_roadmap_task` never touch module status/focus/history, so
  a malformed blocker can't corrupt thesis state; the worst case is a no-op task. The module
  `commit_slice` path is unchanged and still raises `SliceOwnershipError` on bad keys.

## Testing

- **`derive_substep`:** table test per module — for each fixture store, assert the computed
  sub-step (untouched → first; partial → mid; satisfied → None/ready-to-confirm).
- **`next_action` ordering:** assert the 5-way precedence (blocker > needs_review > advance
  > next-module > done) with fixtures hitting each branch; assert null-safety on `{}`.
- **Header injection:** `_state_header` emits a `[NEXT]` line for a mid-project store;
  omits gracefully on load failure.
- **Blocker write path:** `upsert_roadmap_task` adds/updates a blocker without touching
  `focus`/`status`/`versionHistory`; `resolve_roadmap_task` flips one to `done`.
  `commit_slice` still rejects `roadmap_tasks` as an illegal key for every real module
  (proving the two paths stay separate).
- **Endpoint:** `POST /projects/{id}/roadmap` returns the derived shape; null-safe on a
  headless-seeded project; POST-only (no GET route).
- **UI:** ContextPanel renders the Next card + sub-steps; a CTA button posts its text to the
  chat input (component test).
- Run api tests via `./run.sh` (arm64). Frontend via the web test runner.

## Migration / rollout

1. `agent/roadmap.py` (spine + `derive_substep` + `next_action`) — pure, unit-tested alone.
2. `roadmap` slice ownership in `agent/state.py`.
3. `[NEXT]` injection + system-prompt/skill leading rules.
4. `POST /projects/{id}/roadmap` endpoint.
5. ContextPanel roadmap UI + Next card.

Each step ships independently; the agent leads in text (steps 1–3) before the UI lands
(step 5).

## Relationship to the follow-on gaps

This layer is the host for the three deferred specs (`project_agent_gaps` memory):
quality-evals slot in as a roadmap step ("committee-readiness check"), cross-session memory
personalizes `next_action`, and the roadmap's derived events are the observability signal.
