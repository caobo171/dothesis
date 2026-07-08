# Proactive Coaching Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the chat agent lead the student step-by-step — a derived sub-step roadmap and a deterministic next-action injected into every turn, plus agent-inserted blockers and a roadmap UI.

**Architecture:** A pure module `agent/roadmap.py` holds a fixed display spine + `derive_substep` (position computed from persisted artifacts, never narrated) + `next_action` (5-way precedence). The runtime injects a `[NEXT]` line every turn; a dedicated store path holds ephemeral `roadmap_tasks` blockers (NOT `commit_slice`, which is coupled to real modules); a POST endpoint feeds a ContextPanel roadmap UI.

**Tech Stack:** Python 3, LangChain `@tool`, FastAPI, pytest (api via `./run.sh`, arm64). Frontend: Next.js/React/TypeScript in `web/`.

## Global Constraints

- **POST-only endpoints** (`@router.post`, params in body; `/health` is the only GET). Verbatim from CLAUDE.md.
- **Chat-only, never affects headless surfaces.** `derive_substep`/`next_action` must be null-safe on headless-produced state (no `roadmap_tasks`); no new gates on auto-mode/partner. (`project_headless_surfaces` memory.)
- **Position is derived, never narrated.** The model cannot set its own sub-step. Only `roadmap_tasks` (ephemeral coaching aids) are agent-writable, and via a dedicated path — not `commit_slice`.
- **Depends on Spec 1** landing first (chapter-scoped `assess_export_readiness`). This plan does not re-implement it.
- **Comment the decision behind each change** (project convention).
- State shape (from `agent/state.py`): `state = {"contextStore": {…owned keys…}, "status": {M1..M5}, "focus": str}`. `roadmap_tasks` is a key inside `contextStore`.

---

### Task 1: `agent/roadmap.py` — spine + `derive_substep`

Pure module: the fixed display spine and per-module sub-step derivation from persisted
artifacts. No I/O, no LLM.

**Files:**
- Create: `agent/roadmap.py`
- Test: `agent/tests/test_roadmap.py` (create; run from `api/` via `../agent` importability — see run cmd)

**Interfaces:**
- Produces:
  - `ROADMAP: dict[str, list[str]]` — ordered display sub-step ids per module.
  - `SUBSTEP_LABELS: dict[str, str]` — id → human label.
  - `derive_substep(module: str, state: dict) -> str | None` — the current sub-step id (a member of `ROADMAP[module]`), or `None` when the module has no unmet checkpoint (ready to confirm done / already done).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_roadmap.py
from agent.roadmap import ROADMAP, derive_substep


def _state(cs=None, status=None, focus="M1"):
    return {"contextStore": cs or {}, "status": status or {m: "locked" for m in ROADMAP},
            "focus": focus}


def test_m1_untouched_is_first_substep():
    assert derive_substep("M1", _state()) == "frame_topic"


def test_m1_title_only_advances_to_questions():
    assert derive_substep("M1", _state({"research_title": "T"})) == "derive_questions"


def test_m1_complete_returns_none():
    s = _state({"research_title": "T", "research_questions": ["Q"]})
    assert derive_substep("M1", s) is None


def test_m2_sources_but_no_gaps_is_find_gaps():
    assert derive_substep("M2", _state({"literature_sources": [{"title": "x"}]})) == "find_gaps"


def test_derived_substep_is_always_in_spine_or_none():
    for m in ROADMAP:
        sub = derive_substep(m, _state())
        assert sub is None or sub in ROADMAP[m]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_roadmap.py -q`
Expected: FAIL — `ModuleNotFoundError: agent.roadmap`.

- [ ] **Step 3: Implement the spine + derivation**

```python
# agent/roadmap.py
"""Derived coaching roadmap: a fixed display spine + position computed from
persisted artifacts (Approach A — state is truth, never narrated). Pure module:
no I/O, no LLM, so it's deterministic and trivially testable, and safe to import
from both the runtime (per-turn [NEXT] injection) and the API (roadmap endpoint).

The display spine is finer than the set of persisted checkpoints (some wizard
phases leave no artifact), so derivation SNAPS to the nearest persisted milestone
— it returns the first spine step whose backing artifact is absent. Steps before
it render as done, that step as current, later steps as upcoming.
"""
from __future__ import annotations

ROADMAP: dict[str, list[str]] = {
    "M1": ["frame_topic", "propose_titles", "confirm_title", "derive_questions"],
    "M2": ["familiarize", "map_research_state", "find_gaps", "confirm_refs", "generate_output"],
    "M3": ["define_constructs", "build_model", "state_hypotheses", "choose_method", "design_instrument"],
    "M4": ["detect_data", "outline_analysis", "confirm_plan", "run_per_step", "interpret"],
    "M5": ["synthesize_sections", "assemble", "export"],
}

SUBSTEP_LABELS: dict[str, str] = {
    "frame_topic": "Frame the topic", "propose_titles": "Propose titles",
    "confirm_title": "Confirm the title", "derive_questions": "Derive research questions",
    "familiarize": "Familiarize with the field", "map_research_state": "Map the research state",
    "find_gaps": "Find research gaps", "confirm_refs": "Confirm references",
    "generate_output": "Write the literature review",
    "define_constructs": "Define constructs", "build_model": "Build the conceptual model",
    "state_hypotheses": "State hypotheses", "choose_method": "Choose the method",
    "design_instrument": "Design the instrument",
    "detect_data": "Detect the dataset", "outline_analysis": "Outline the analysis",
    "confirm_plan": "Confirm the analysis plan", "run_per_step": "Run each analysis step",
    "interpret": "Interpret the results",
    "synthesize_sections": "Synthesize the chapters", "assemble": "Assemble the thesis",
    "export": "Export the document",
}


def derive_substep(module: str, state: dict) -> str | None:
    """First spine sub-step whose persisted artifact is missing; None when the
    module's tracked artifacts are all present (ready to confirm done / done)."""
    cs = state.get("contextStore") or {}
    if module == "M1":
        if not cs.get("research_title"):
            return "frame_topic"
        if not cs.get("research_questions"):
            return "derive_questions"
        return None
    if module == "M2":
        if not cs.get("literature_sources"):
            return "familiarize"
        if not cs.get("research_gaps"):
            return "find_gaps"
        return None
    if module == "M3":
        if not cs.get("conceptual_model"):
            return "build_model"
        if not cs.get("hypotheses"):
            return "state_hypotheses"
        if not cs.get("methodology"):
            return "choose_method"
        return None
    if module == "M4":
        if not cs.get("analysis_outline"):
            return "outline_analysis"
        if not cs.get("analysis_results"):
            return "run_per_step"
        return None
    if module == "M5":
        if not cs.get("final_sections"):
            return "synthesize_sections"
        return None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_roadmap.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/roadmap.py agent/tests/test_roadmap.py
git commit -m "feat(agent): roadmap spine + derived sub-step position

Approach A: current sub-step is computed from persisted artifacts, snapping to
the nearest milestone, so the model can't narrate fake progress.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `next_action` — the deterministic 5-way precedence

**Files:**
- Modify: `agent/roadmap.py`
- Test: `agent/tests/test_roadmap.py`

**Interfaces:**
- Consumes: `derive_substep`, `ROADMAP`, `SUBSTEP_LABELS`, `MODULES` (from `agent.state`).
- Produces: `next_action(state: dict) -> dict | None` → `{module, substep, title, why, cta_options}` or `None` when everything is done.

- [ ] **Step 1: Write the failing test**

```python
# add to agent/tests/test_roadmap.py
from agent.roadmap import next_action


def _full(status, cs=None, focus="M1"):
    return {"contextStore": cs or {}, "status": status, "focus": focus}


def test_open_blocker_wins():
    s = _full({"M1": "in_progress", "M2": "locked", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T", "roadmap_tasks": [
                  {"id": "b1", "module": "M4", "substep": "interpret",
                   "title": "HTMT 0.91 fails", "why": "discriminant validity", "status": "open"}]},
              focus="M1")
    na = next_action(s)
    assert na["module"] == "M4" and "HTMT" in na["title"]


def test_needs_review_wins_over_advance():
    s = _full({"M1": "done", "M2": "needs_review", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T", "research_questions": ["Q"]}, focus="M2")
    na = next_action(s)
    assert na["module"] == "M2" and "review" in na["why"].lower()


def test_advance_focus_when_clean():
    s = _full({"M1": "in_progress", "M2": "locked", "M3": "locked", "M4": "locked", "M5": "locked"},
              cs={"research_title": "T"}, focus="M1")
    na = next_action(s)
    assert na["module"] == "M1" and na["substep"] == "derive_questions"


def test_all_done_returns_none_or_export():
    s = _full({m: "done" for m in ["M1", "M2", "M3", "M4", "M5"]},
              cs={"final_sections": [{"x": 1}]}, focus="M5")
    na = next_action(s)
    assert na is None or na["substep"] == "export"


def test_null_safe_on_empty_state():
    # headless-produced state (no roadmap_tasks, minimal status) must not crash.
    assert next_action({"contextStore": {}, "status": {}, "focus": None}) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_roadmap.py -k next_action -q`
Expected: FAIL — no `next_action`.

- [ ] **Step 3: Implement `next_action`**

```python
# add to agent/roadmap.py
from agent.state import MODULES  # ["M1".."M5"]


def _title_for(module: str, substep: str | None) -> str:
    if substep is None:
        return f"Confirm {module} is done"
    return SUBSTEP_LABELS.get(substep, substep)


def next_action(state: dict) -> dict | None:
    """The single next thing the student should do. Deterministic precedence:
    open blocker > needs_review > advance focus > next module > done."""
    cs = state.get("contextStore") or {}
    status = state.get("status") or {}
    focus = state.get("focus") or "M1"

    # 1) An open agent-inserted blocker jumps the queue.
    for t in cs.get("roadmap_tasks") or []:
        if t.get("status") == "open":
            return {"module": t.get("module", focus), "substep": t.get("substep", ""),
                    "title": t.get("title", "Resolve blocker"),
                    "why": t.get("why", "This is blocking progress."),
                    "cta_options": ["How do I fix this?", "Skip for now"]}

    # 2) A started module flagged for review beats marching forward.
    for m in MODULES:
        if status.get(m) == "needs_review":
            return {"module": m, "substep": derive_substep(m, state) or "",
                    "title": f"Re-check {m}",
                    "why": "An upstream change flagged it for review — resolve it before moving on.",
                    "cta_options": [f"Review {m}", "Why does this need review?"]}

    # 3) Advance the focus module.
    if status.get(focus) not in ("done", None) or derive_substep(focus, state) is not None:
        sub = derive_substep(focus, state)
        if sub is not None:
            return {"module": focus, "substep": sub, "title": _title_for(focus, sub),
                    "why": "This is the next step in your current module.",
                    "cta_options": [_title_for(focus, sub), f"Skip to next module"]}
        if status.get(focus) != "done":
            return {"module": focus, "substep": "", "title": f"Confirm {focus} is done",
                    "why": f"{focus} has all its content — confirm it so we move on.",
                    "cta_options": [f"Mark {focus} done", "Not yet"]}

    # 4) Move to the first not-done module in order.
    for m in MODULES:
        if status.get(m) != "done":
            sub = derive_substep(m, state)
            return {"module": m, "substep": sub or "", "title": _title_for(m, sub),
                    "why": f"{focus} is done — {m} is next.",
                    "cta_options": [f"Start {m}", f"What does {m} involve?"]}

    # 5) Everything done.
    return {"module": "M5", "substep": "export", "title": "Export your thesis",
            "why": "Every module is done — generate the final document.",
            "cta_options": ["Export my thesis", "Review it first"]}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_roadmap.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add agent/roadmap.py agent/tests/test_roadmap.py
git commit -m "feat(agent): next_action 5-way precedence engine

blocker > needs_review > advance focus > next module > done. Pure + null-safe
on headless state.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `roadmap_tasks` write path on the store

A dedicated lightweight path — NOT `commit_slice` (which shifts focus + status + downstream).

**Files:**
- Modify: `agent/state.py` (add two methods to `ProjectStateStore`)
- Test: `agent/tests/test_state.py` (append; or create if absent)

**Interfaces:**
- Produces (on `ProjectStateStore`):
  - `upsert_roadmap_task(task: dict) -> dict` — adds or replaces a blocker by `id` (generates an id if absent). Returns the stored task. Writes only `contextStore["roadmap_tasks"]`; no focus/status/version change.
  - `resolve_roadmap_task(task_id: str) -> bool` — flips a task's `status` to `"done"`; returns whether it matched.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_state.py (append)
import uuid
from agent.state import ProjectStateStore


def _store(tmp_path):
    return ProjectStateStore(tmp_path / f"proj-{uuid.uuid4().hex}")


def test_upsert_roadmap_task_does_not_touch_focus_or_status(tmp_path):
    s = _store(tmp_path)
    before = s.load()
    s.upsert_roadmap_task({"module": "M4", "substep": "interpret",
                           "title": "HTMT fails", "why": "validity", "status": "open"})
    after = s.load()
    assert after["focus"] == before["focus"]
    assert after["status"] == before["status"]           # unchanged
    assert after["contextStore"]["roadmap_tasks"][0]["title"] == "HTMT fails"


def test_resolve_roadmap_task_flips_status(tmp_path):
    s = _store(tmp_path)
    t = s.upsert_roadmap_task({"module": "M4", "title": "x", "why": "y", "status": "open"})
    assert s.resolve_roadmap_task(t["id"]) is True
    assert s.load()["contextStore"]["roadmap_tasks"][0]["status"] == "done"
    assert s.resolve_roadmap_task("missing") is False


def test_commit_slice_still_rejects_roadmap_tasks_key(tmp_path):
    s = _store(tmp_path)
    import pytest
    from agent.state import SliceOwnershipError
    with pytest.raises(SliceOwnershipError):
        s.commit_slice("M4", {"roadmap_tasks": []}, reason="x")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state.py -k roadmap -q`
Expected: FAIL — no `upsert_roadmap_task`.

- [ ] **Step 3: Implement the two methods**

Add to `ProjectStateStore` in `agent/state.py` (after `commit_slice`):

```python
    # -- roadmap_tasks (coaching blockers) --------------------------------
    # Deliberately NOT commit_slice: blockers are ephemeral coaching aids, so
    # writing one must never shift focus, change module status, propagate
    # needs_review, or add a version snapshot. This keeps the module state
    # machine pristine while still funneling writes through the store.
    def upsert_roadmap_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Add or replace a blocker (by id). Only touches roadmap_tasks."""
        import uuid as _uuid
        state = self.load()
        tasks = list(state["contextStore"].get("roadmap_tasks") or [])
        stored = {**task}
        stored.setdefault("id", _uuid.uuid4().hex)
        stored.setdefault("status", "open")
        tasks = [t for t in tasks if t.get("id") != stored["id"]] + [stored]
        state["contextStore"]["roadmap_tasks"] = tasks
        self._save(state)
        return stored

    def resolve_roadmap_task(self, task_id: str) -> bool:
        """Flip a blocker to done. Returns False if the id wasn't found."""
        state = self.load()
        tasks = state["contextStore"].get("roadmap_tasks") or []
        hit = False
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = "done"
                hit = True
        if hit:
            self._save(state)
        return hit
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state.py -k roadmap -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add agent/state.py agent/tests/test_state.py
git commit -m "feat(agent): dedicated roadmap_tasks write path (not commit_slice)

Blockers are ephemeral coaching aids — upsert/resolve touch only roadmap_tasks,
never focus/status/history, so the module state machine stays pristine.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `flag_blocker` / `resolve_blocker` agent tools

Wire the store methods into two small LangChain tools the agent can call.

**Files:**
- Modify: `agent/tools/state_tools.py` (add two tools inside `make_state_tools`, closing over `store`, appended to the returned list)
- Test: `agent/tests/test_state_tools.py` (append/create)

No `runtime.py` change: `build_agent` already spreads `*make_state_tools(store)` into its
tool list (`agent/runtime.py:449`), so appending the two tools to that factory's return list
registers them automatically.

**Interfaces:**
- Consumes: `ProjectStateStore.upsert_roadmap_task`, `resolve_roadmap_task` (Task 3).
- Produces: two tools returned from `make_state_tools(store)`, closing over `store`:
  `flag_blocker(module, substep, title, why) -> str` (json), `resolve_blocker(task_id) -> str` (json).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_state_tools.py (append)
import json, uuid
from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


def test_flag_and_resolve_blocker(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    assert "flag_blocker" in tools and "resolve_blocker" in tools

    out = json.loads(tools["flag_blocker"].func(
        module="M4", substep="interpret", title="HTMT fails", why="validity"))
    assert out["status"] == "open" and out["module"] == "M4"

    res = json.loads(tools["resolve_blocker"].func(task_id=out["id"]))
    assert res["resolved"] is True
    assert store.load()["contextStore"]["roadmap_tasks"][0]["status"] == "done"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state_tools.py -k blocker -q`
Expected: FAIL — `flag_blocker` not among the returned tools.

- [ ] **Step 3: Implement the tools inside the factory**

In `agent/tools/state_tools.py`, inside `make_state_tools(store)` (which already closes over
`store` for `read_slice`/`commit_slice`), add these before its `return [...]`:

```python
    @tool
    def flag_blocker(module: str, substep: str, title: str, why: str) -> str:
        """Record a student-specific blocker under a roadmap sub-step (e.g. a
        failed discriminant-validity check). Use ONLY for a concrete obstacle
        that must be cleared before the student can proceed — not for normal
        steps. Does NOT change module status. Returns the stored task (with id).
        """
        task = store.upsert_roadmap_task(
            {"module": module, "substep": substep, "title": title, "why": why, "status": "open"})
        return json.dumps(task, ensure_ascii=False)

    @tool
    def resolve_blocker(task_id: str) -> str:
        """Mark a previously flagged blocker resolved once the student fixed it."""
        return json.dumps({"resolved": store.resolve_roadmap_task(task_id)}, ensure_ascii=False)
```

Then add `flag_blocker, resolve_blocker` to the list this factory returns (next to
`read_slice, commit_slice`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state_tools.py -k blocker -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/state_tools.py agent/tests/test_state_tools.py
git commit -m "feat(agent): flag_blocker/resolve_blocker tools

Let the agent record + clear student-specific blockers (the hybrid layer) via
the dedicated roadmap_tasks path, without touching module status.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `[NEXT]` per-turn injection + leading instructions

**Files:**
- Modify: `agent/runtime.py:495` (`_state_header`)
- Modify: `agent/runtime.py:160` (SYSTEM_PROMPT — add a "proactive leading" rule)
- Modify: `skills/dothesis/SKILL.md` (add a "Proactive leading" section)
- Test: `agent/tests/test_runtime_header.py` (create)

**Interfaces:**
- Consumes: `next_action` (Task 2).
- Produces: `_state_header` now returns `[PROJECT STATE] …\n[NEXT] <module>/<substep> — <title> :: <why>` (or just the state line if no next action / on failure).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_runtime_header.py
from agent.runtime import _state_header


class _FakeStore:
    def __init__(self, state): self._s = state
    def load(self): return self._s


def test_header_includes_next_line_midproject():
    store = _FakeStore({"focus": "M1", "status": {"M1": "in_progress", "M2": "locked",
                        "M3": "locked", "M4": "locked", "M5": "locked"},
                        "contextStore": {"research_title": "T"}})
    h = _state_header(store)
    assert "[PROJECT STATE]" in h
    assert "[NEXT]" in h
    assert "derive_questions" in h or "research question" in h.lower()


def test_header_survives_load_failure():
    class Boom:
        def load(self): raise RuntimeError("db down")
    assert _state_header(Boom()) == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_runtime_header.py -q`
Expected: FAIL — no `[NEXT]` line.

- [ ] **Step 3: Add the `[NEXT]` line**

Extend `_state_header` (`agent/runtime.py:495`) — after building `pairs`:

```python
    header = f"[PROJECT STATE] focus={state.get('focus')} | {pairs}"
    # Append the single next action so the model leads from ground truth every
    # turn (same rationale as the state line: it can't narrate its own position).
    try:
        from agent.roadmap import next_action  # local import: avoid load cycle
        na = next_action(state)
        if na:
            header += (f"\n[NEXT] {na['module']}/{na.get('substep') or '-'} — "
                       f"{na['title']} :: {na['why']}")
    except Exception:
        pass  # a roadmap hiccup must never break the turn
    return header
```

Add to SYSTEM_PROMPT (`agent/runtime.py:160`), near the `[PROJECT STATE]` guidance:

```
- The `[NEXT]` line is the single most useful next step, computed from real
  project state. Unless the user redirects, CLOSE every turn by leading toward
  it: name what to do next and why, and offer its options with the [OPTIONS]
  marker. Never invent a different "next step" than the one derived.
```

Add a "Proactive leading" section to `skills/dothesis/SKILL.md` documenting: read `[NEXT]`,
lead toward it, and use `flag_blocker`/`resolve_blocker` for concrete obstacles.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_runtime_header.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/runtime.py skills/dothesis/SKILL.md agent/tests/test_runtime_header.py
git commit -m "feat(agent): inject [NEXT] every turn + proactive-leading rules

The runtime appends the derived next-action to the authoritative state header,
and the prompt/skill tell the agent to close each turn leading toward it.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `POST /projects/{id}/roadmap` endpoint

**Files:**
- Create: `api/app/routers/roadmap.py`
- Modify: `api/app/main.py` (mount the router)
- Test: `api/tests/test_roadmap_router.py` (create)

**Interfaces:**
- Consumes: `DbProjectStateStore` (`api/app/agent_state.py`), `agent.roadmap.{ROADMAP, SUBSTEP_LABELS, derive_substep, next_action}`.
- Produces: `POST /api/v1/projects/{project_id}/roadmap` → the derived roadmap JSON (see spec §4). Errs safe (coarse status + empty next_action on failure).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_roadmap_router.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import roadmap as roadmap_mod


def _client(monkeypatch, state):
    class _FakeStore:
        def load(self): return state
    monkeypatch.setattr(roadmap_mod, "_store_for", lambda project_id: _FakeStore())
    app = FastAPI()
    app.include_router(roadmap_mod.router, prefix="/api/v1")
    return TestClient(app)


def test_roadmap_returns_derived_shape(monkeypatch):
    state = {"focus": "M1", "status": {"M1": "in_progress", "M2": "locked", "M3": "locked",
             "M4": "locked", "M5": "locked"}, "contextStore": {"research_title": "T"}}
    c = _client(monkeypatch, state)
    r = c.post("/api/v1/projects/abc/roadmap")
    assert r.status_code == 200
    body = r.json()
    assert body["next_action"]["substep"] == "derive_questions"
    m1 = next(m for m in body["modules"] if m["id"] == "M1")
    assert m1["current"] == "derive_questions"
    states = {s["id"]: s["state"] for s in m1["substeps"]}
    assert states["frame_topic"] == "done" and states["derive_questions"] == "current"


def test_roadmap_null_safe_on_headless_state(monkeypatch):
    c = _client(monkeypatch, {"focus": None, "status": {}, "contextStore": {}})
    assert c.post("/api/v1/projects/abc/roadmap").status_code == 200
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_roadmap_router.py -q`
Expected: FAIL — `ModuleNotFoundError: app.routers.roadmap`.

- [ ] **Step 3: Implement the router**

```python
# api/app/routers/roadmap.py
"""Derived coaching roadmap for the chat UI. POST-only (project convention).

Reads project state via DbProjectStateStore and computes the roadmap with the
same agent.roadmap functions the runtime injects each turn — one source of truth.
Errs safe: a load failure returns coarse module status with an empty next_action
rather than 500ing (mirrors the runtime's silent-omit state header).
"""
from __future__ import annotations

import logging

from fastapi import APIRouter

from agent.roadmap import ROADMAP, SUBSTEP_LABELS, derive_substep, next_action
from agent.state import MODULES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["roadmap"])


def _store_for(project_id: str):
    """Return the project's DbProjectStateStore. Isolated so tests can stub it.

    Mirrors chat_v3's construction: DbProjectStateStore(engine, project_id, workspace_dir)
    (`api/app/routers/chat_v3.py:159`, `:301`).
    """
    import uuid
    from ..agent_state import DbProjectStateStore
    from ..db import get_engine            # match the app's engine accessor
    from .chat_v3 import _workspace_dir    # reuse the existing workspace-path helper
    pid = uuid.UUID(project_id)
    return DbProjectStateStore(get_engine(), pid, _workspace_dir(pid))


def _substep_states(module: str, current: str | None, module_status: str) -> list[dict]:
    spine = ROADMAP[module]
    idx = spine.index(current) if current in spine else (len(spine) if module_status == "done" else 0)
    out = []
    for i, sid in enumerate(spine):
        state = "done" if i < idx else ("current" if i == idx else "upcoming")
        if module_status == "done":
            state = "done"
        out.append({"id": sid, "label": SUBSTEP_LABELS.get(sid, sid), "state": state})
    return out


@router.post("/projects/{project_id}/roadmap")
async def get_roadmap(project_id: str):
    try:
        state = _store_for(project_id).load()
    except Exception:
        logger.exception("roadmap: state load failed for %s", project_id)
        state = {"focus": None, "status": {}, "contextStore": {}}

    status = state.get("status") or {}
    modules = []
    for m in MODULES:
        cur = derive_substep(m, state)
        modules.append({"id": m, "status": status.get(m, "locked"), "current": cur,
                        "substeps": _substep_states(m, cur, status.get(m, "locked"))})
    return {
        "modules": modules,
        "tasks": [t for t in (state.get("contextStore", {}).get("roadmap_tasks") or [])
                  if t.get("status") == "open"],
        "next_action": next_action(state) or {},
    }
```

> **Note for implementer:** confirm the engine accessor name — `chat_v3.py:159` uses
> `db.bind` from a request-scoped `Session`, while `:301` uses a module-level `engine`. Use
> whichever the app exposes for a non-request context (a module-level engine/`get_engine`);
> if only a session dependency exists, inject `db: Session = Depends(get_db)` into the route
> and pass `db.bind`. Keep `_store_for` thin and separately stubbable (the test stubs it).

- [ ] **Step 4: Mount + run the test**

In `api/app/main.py`, include the router the same way the others are mounted (with the
`/api/v1` prefix). Then:

Run: `cd api && ./run.sh pytest tests/test_roadmap_router.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/roadmap.py api/app/main.py api/tests/test_roadmap_router.py
git commit -m "feat(api): POST /projects/{id}/roadmap derived-roadmap endpoint

Computes the roadmap from project state with the same agent.roadmap functions
the runtime injects — one source of truth. POST-only; errs safe.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: ContextPanel roadmap UI + Next card

**Files:**
- Create: `web/app/components/chat/RoadmapPanel.tsx`
- Modify: `web/app/components/chat/ContextPanel.tsx` (mount `RoadmapPanel` at top)
- Test: `web/app/components/chat/RoadmapPanel.test.tsx` (create)

**Interfaces:**
- Consumes: `POST /api/v1/projects/{id}/roadmap` (Task 6).
- Produces: `<RoadmapPanel projectId onSendMessage />` — renders the Next card + per-module sub-steps; a CTA button calls `onSendMessage(text)`.

- [ ] **Step 1: Read the integration points**

Read `web/app/components/chat/ContextPanel.tsx` for: how it fetches (the shared POST
helper), how it receives `projectId` and the "post a message to chat" callback, and where
module status currently renders — mount `RoadmapPanel` above that.

- [ ] **Step 2: Write the failing test**

```tsx
// web/app/components/chat/RoadmapPanel.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { RoadmapPanel } from "./RoadmapPanel";

const FIXTURE = {
  modules: [{ id: "M1", status: "in_progress", current: "derive_questions",
    substeps: [{ id: "frame_topic", label: "Frame the topic", state: "done" },
               { id: "derive_questions", label: "Derive research questions", state: "current" }] }],
  tasks: [],
  next_action: { module: "M1", substep: "derive_questions",
    title: "Derive research questions", why: "This is the next step.",
    cta_options: ["Derive research questions", "Skip to next module"] },
};

beforeEach(() => {
  global.fetch = jest.fn().mockResolvedValue({ ok: true, json: async () => FIXTURE }) as any;
});

test("renders the Next card and posts a CTA to chat", async () => {
  const onSend = jest.fn();
  render(<RoadmapPanel projectId="abc" onSendMessage={onSend} />);
  await waitFor(() => screen.getByText("Derive research questions"));
  fireEvent.click(screen.getByRole("button", { name: /Derive research questions/ }));
  expect(onSend).toHaveBeenCalledWith("Derive research questions");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npm test -- RoadmapPanel`
Expected: FAIL — no `RoadmapPanel`.

- [ ] **Step 4: Implement the component**

```tsx
// web/app/components/chat/RoadmapPanel.tsx
"use client";
import { useEffect, useState, useCallback } from "react";

type Sub = { id: string; label: string; state: "done" | "current" | "upcoming" };
type Mod = { id: string; status: string; current: string | null; substeps: Sub[] };
type NextAction = { module: string; substep: string; title: string; why: string; cta_options: string[] };
type Roadmap = { modules: Mod[]; tasks: any[]; next_action: NextAction | Record<string, never> };

/** Derived coaching roadmap. Fetches on mount and whenever `refreshKey` changes
 *  (parent bumps it on each turn's `done` SSE event). CTA buttons post their text
 *  straight into the chat via onSendMessage. */
export function RoadmapPanel({
  projectId, onSendMessage, refreshKey = 0,
}: { projectId: string; onSendMessage: (text: string) => void; refreshKey?: number }) {
  const [data, setData] = useState<Roadmap | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/v1/projects/${projectId}/roadmap`, { method: "POST" });
      if (r.ok) setData(await r.json());
    } catch { /* roadmap is non-critical; leave prior state */ }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (!data) return null;
  const na = data.next_action as NextAction;
  const hasNext = na && "title" in na;

  return (
    <div className="flex flex-col gap-3" data-testid="roadmap-panel">
      {hasNext && (
        <div className="rounded-xl border border-primary-200 bg-primary-50 p-3">
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-primary-700 font-semibold">Next</div>
          <div className="text-[13.5px] font-semibold text-ink-900 mt-1">{na.title}</div>
          <div className="text-[12px] text-ink-600 mt-0.5">{na.why}</div>
          <div className="flex flex-wrap gap-1.5 mt-2">
            {na.cta_options.map((c) => (
              <button key={c} type="button" onClick={() => onSendMessage(c)}
                className="px-2.5 py-1 rounded-full bg-primary-600 text-white text-[12px] font-semibold hover:bg-primary-700">
                {c}
              </button>
            ))}
          </div>
        </div>
      )}
      {data.modules.map((m) => (
        <div key={m.id} className="text-[12.5px]">
          <div className="font-semibold text-ink-800">{m.id} · {m.status}</div>
          <ul className="mt-1 ml-2 flex flex-col gap-0.5">
            {m.substeps.map((s) => (
              <li key={s.id} className={
                s.state === "done" ? "text-ink-400 line-through"
                : s.state === "current" ? "text-primary-700 font-semibold"
                : "text-ink-500"}>
                {s.state === "done" ? "✓ " : s.state === "current" ? "▸ " : "· "}{s.label}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
```

Mount it at the top of `ContextPanel.tsx`, passing the panel's existing `projectId` and its
chat-send callback, plus a `refreshKey` bumped on the `done` SSE event.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npm test -- RoadmapPanel`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add web/app/components/chat/RoadmapPanel.tsx web/app/components/chat/ContextPanel.tsx web/app/components/chat/RoadmapPanel.test.tsx
git commit -m "feat(web): roadmap panel + Next card in ContextPanel

Surfaces the derived roadmap and the single next action; CTA buttons post their
text into the chat so the student can act in one click.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] Backend: `cd api && ./run.sh pytest ../agent/tests/test_roadmap.py ../agent/tests/test_state.py ../agent/tests/test_state_tools.py ../agent/tests/test_runtime_header.py tests/test_roadmap_router.py -q` → all PASS.
- [ ] Frontend: `cd web && npm test -- RoadmapPanel` → PASS.
- [ ] Manual/`/run`: start the app, open a mid-project thesis, confirm the ContextPanel shows a Next card and the agent's reply ends by leading toward the same next step.
- [ ] Headless untouched: `cd api && ./run.sh pytest tests/test_partner_report.py -q` still green (no roadmap coupling leaked into partner/auto paths).

## Notes / spec deviations

- **Blocker write path is NOT `commit_slice`** (spec updated during planning): `commit_slice`
  shifts focus/status/downstream, which would corrupt state for an ephemeral coaching
  blocker. Tasks 3–4 add a dedicated `upsert/resolve_roadmap_task` path + `flag_blocker`/
  `resolve_blocker` tools instead.
- **Display spine is finer than persisted checkpoints** — `derive_substep` snaps to the
  nearest persisted artifact, so some spine steps (e.g. `propose_titles`) never show as
  "current" in isolation. Acceptable and deterministic; documented in `agent/roadmap.py`.
- The single completeness gate from **Spec 1** (`assess_export_readiness`) is available for
  `derive_substep` to reuse if a future refinement wants richer M4/M5 checkpoints; the
  initial derivation uses direct slice checks to stay pure and dependency-light.
