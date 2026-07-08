# Cross-Session Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the advisor-feedback loop — ingest professor feedback, remember it as directives, surface open ones as coaching blockers, track addressed, and learn recurring themes across projects — plus a per-project institution profile.

**Architecture:** Per-project keys (`advisor_feedback`, `institution_profile`) live in the context store, written through a dedicated lightweight path (like Spec 2's `roadmap_tasks`, NOT `commit_slice`). Agent tools ingest/track feedback; each open directive becomes a `flag_blocker` (Spec 2) so `next_action` leads the revision. Per-user cross-project learning extends the existing `api/app/user_memory.py`.

**Tech Stack:** Python 3, LangChain `@tool`, engine LLM (`_get_llm`), SQLAlchemy (`user_memory`), pytest via `./run.sh`.

## Global Constraints

- **Dedicated write path, not `commit_slice`** (it shifts focus/status/downstream). Per-project memory keys use their own store methods.
- **Never drop a professor comment.** A failed extraction stores the raw feedback as one directive.
- **Chat-only, no headless coupling** (`project_headless_surfaces` memory).
- **Depends on Spec 2** (`flag_blocker`/`resolve_blocker`, `roadmap_tasks` path) and is consumed by **Spec 3** (quality-evals). Do Spec 2 first.
- **Comment the decision behind each change** (project convention).
- Directive shape: `{id, source, chapter, section?, quote?, issue, required_change, status: "open"|"addressed", created_at, addressed_at?}`.

---

### Task 1: Per-project store methods (advisor_feedback + institution_profile)

**Files:**
- Modify: `agent/state.py` (add three methods to `ProjectStateStore`)
- Test: `agent/tests/test_state.py`

**Interfaces:**
- Produces (on `ProjectStateStore`, all writing only their own context-store key — no focus/status/version change):
  - `upsert_advisor_feedback(directive: dict) -> dict` (adds/updates by id; generates id/created_at/status).
  - `mark_advisor_feedback_addressed(feedback_id: str) -> bool`.
  - `set_institution_profile(fields: dict) -> dict` (merges into the `institution_profile` key).

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_state.py (append)
def test_advisor_feedback_roundtrip(tmp_path):
    s = _store(tmp_path)   # helper from Spec-2 Task 3 tests
    d = s.upsert_advisor_feedback({"chapter": "results", "issue": "report effect sizes",
                                   "required_change": "add Cohen's f2"})
    assert d["status"] == "open" and d["id"]
    before = s.load()
    assert s.mark_advisor_feedback_addressed(d["id"]) is True
    after = s.load()
    assert after["contextStore"]["advisor_feedback"][0]["status"] == "addressed"
    assert after["focus"] == before["focus"] and after["status"] == before["status"]


def test_set_institution_profile_merges(tmp_path):
    s = _store(tmp_path)
    s.set_institution_profile({"citation_style": "apa7"})
    s.set_institution_profile({"min_references": 30})
    prof = s.load()["contextStore"]["institution_profile"]
    assert prof == {"citation_style": "apa7", "min_references": 30}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state.py -k "advisor or institution" -q`
Expected: FAIL — no `upsert_advisor_feedback`.

- [ ] **Step 3: Implement the three methods**

Add to `ProjectStateStore` in `agent/state.py`, next to the `roadmap_tasks` methods (Spec 2):

```python
    # -- cross-session memory (per-project) -------------------------------
    # Same rationale as roadmap_tasks: durable per-project data that must NOT
    # move module status/focus/history, so it bypasses commit_slice.
    def upsert_advisor_feedback(self, directive: dict[str, Any]) -> dict[str, Any]:
        import uuid as _uuid
        from datetime import datetime, timezone
        state = self.load()
        items = list(state["contextStore"].get("advisor_feedback") or [])
        stored = {**directive}
        stored.setdefault("id", _uuid.uuid4().hex)
        stored.setdefault("status", "open")
        stored.setdefault("source", "professor")
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        items = [d for d in items if d.get("id") != stored["id"]] + [stored]
        state["contextStore"]["advisor_feedback"] = items
        self._save(state)
        return stored

    def mark_advisor_feedback_addressed(self, feedback_id: str) -> bool:
        from datetime import datetime, timezone
        state = self.load()
        hit = False
        for d in state["contextStore"].get("advisor_feedback") or []:
            if d.get("id") == feedback_id:
                d["status"] = "addressed"
                d["addressed_at"] = datetime.now(timezone.utc).isoformat()
                hit = True
        if hit:
            self._save(state)
        return hit

    def set_institution_profile(self, fields: dict[str, Any]) -> dict[str, Any]:
        state = self.load()
        prof = {**(state["contextStore"].get("institution_profile") or {}), **fields}
        state["contextStore"]["institution_profile"] = prof
        self._save(state)
        return prof
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state.py -k "advisor or institution" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/state.py agent/tests/test_state.py
git commit -m "feat(memory): per-project advisor_feedback + institution_profile store paths

Dedicated lightweight writes (like roadmap_tasks) — never touch module
status/focus/history.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `extract_directives` — feedback text → structured directives

**Files:**
- Create: `agent/feedback.py`
- Test: `api/tests/test_feedback_extract.py`

**Interfaces:**
- Consumes: `orchestrator.tools.m5_writing._get_llm`.
- Produces: `extract_directives(feedback_text: str) -> list[dict]` — each `{chapter, section?, quote?, issue, required_change}`. Best-effort: malformed LLM output ⇒ one directive wrapping the raw text.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_feedback_extract.py
import orchestrator.tools.m5_writing as m5
from agent.feedback import extract_directives


def test_extract_parses_directives(monkeypatch):
    payload = ('{"directives": [{"chapter": "results", "issue": "no effect sizes", '
               '"required_change": "add Cohen f2"}]}')
    monkeypatch.setattr(m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p:
                        type("R", (), {"content": payload})()})())
    out = extract_directives("Prof: please add effect sizes to chapter 4")
    assert out[0]["chapter"] == "results" and out[0]["required_change"] == "add Cohen f2"


def test_extract_falls_back_to_raw_on_bad_json(monkeypatch):
    monkeypatch.setattr(m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p:
                        type("R", (), {"content": "not json"})()})())
    out = extract_directives("some professor comment")
    assert len(out) == 1 and "some professor comment" in out[0]["issue"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_feedback_extract.py -q`
Expected: FAIL — no `agent.feedback`.

- [ ] **Step 3: Implement `extract_directives`**

```python
# agent/feedback.py
"""Turn raw professor feedback into structured, trackable directives. Best-effort:
never drop a comment — a parse failure wraps the raw text as one directive."""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are parsing a thesis supervisor's feedback into discrete, actionable "
    "directives. For each distinct requested change, output one item. Map it to the "
    "most likely chapter (intro|lit_review|methodology|results|discussion|conclusion) "
    "when clear, else '-'.\nReturn STRICT JSON only:\n"
    '{"directives": [{"chapter": "", "section": "", "quote": "", "issue": "", '
    '"required_change": ""}]}\n\nFEEDBACK:\n'
)


def extract_directives(feedback_text: str) -> list[dict]:
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    text = (feedback_text or "").strip()
    if not text:
        return []
    try:
        resp = _get_llm().invoke(_PROMPT + text[:8000])
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        data = json.loads(content[s:e + 1]) if s != -1 and e != -1 else {}
        directives = [d for d in (data.get("directives") or []) if isinstance(d, dict) and d.get("issue")]
        if directives:
            return directives
    except Exception:
        logger.exception("feedback: extraction failed; storing raw text as one directive")
    # Fallback: never lose the comment.
    return [{"chapter": "-", "issue": text[:500], "required_change": text[:500]}]
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_feedback_extract.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/feedback.py api/tests/test_feedback_extract.py
git commit -m "feat(memory): extract_directives — professor feedback -> directives

Best-effort LLM parse; a failure wraps raw text as one directive so no comment
is ever dropped.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ingest_advisor_feedback` + `mark_feedback_addressed` tools

**Files:**
- Modify: `agent/tools/state_tools.py` (two tools inside `make_state_tools`, closing over `store`)
- Test: `agent/tests/test_state_tools.py`

**Interfaces:**
- Consumes: `extract_directives` (Task 2); store methods (Task 1); `store.upsert_roadmap_task`/`resolve_roadmap_task` (Spec 2).
- Produces (returned from `make_state_tools(store)`):
  - `ingest_advisor_feedback(feedback_text: str) -> str` — extract → persist each directive → `flag_blocker` per open directive; returns json `{added, blockers}`.
  - `mark_feedback_addressed(feedback_id: str) -> str` — status=addressed + resolve the linked blocker.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_state_tools.py (append)
import json, uuid
from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


def test_ingest_creates_feedback_and_blockers(tmp_path, monkeypatch):
    import agent.feedback as fb
    monkeypatch.setattr(fb, "extract_directives", lambda t: [
        {"chapter": "results", "issue": "add effect sizes", "required_change": "Cohen f2"}])
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["ingest_advisor_feedback"].func(feedback_text="please add effect sizes"))
    assert out["added"] == 1
    cs = store.load()["contextStore"]
    assert cs["advisor_feedback"][0]["issue"] == "add effect sizes"
    assert len(cs["roadmap_tasks"]) == 1              # a blocker was created
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state_tools.py -k ingest -q`
Expected: FAIL — no `ingest_advisor_feedback`.

- [ ] **Step 3: Implement the tools inside the factory**

Inside `make_state_tools(store)` in `agent/tools/state_tools.py`:

```python
    @tool
    def ingest_advisor_feedback(feedback_text: str) -> str:
        """Record a thesis supervisor's feedback. Extracts each requested change into a
        tracked directive, persists it, and raises a roadmap blocker per open item so the
        student is led to address it. Use whenever the user pastes/relays professor comments.
        """
        from agent.feedback import extract_directives  # noqa: PLC0415
        directives = extract_directives(feedback_text)
        added = 0
        for d in directives:
            stored = store.upsert_advisor_feedback(d)
            store.upsert_roadmap_task({
                "module": _chapter_to_module(stored.get("chapter")),
                "substep": "", "title": f"Advisor: {stored.get('issue')}",
                "why": stored.get("required_change") or "Address this advisor comment.",
                "status": "open", "feedback_id": stored["id"]})
            added += 1
        return json.dumps({"added": added}, ensure_ascii=False)

    @tool
    def mark_feedback_addressed(feedback_id: str) -> str:
        """Mark an advisor directive addressed once the revision is done; clears its blocker."""
        ok = store.mark_advisor_feedback_addressed(feedback_id)
        for t in (store.load()["contextStore"].get("roadmap_tasks") or []):
            if t.get("feedback_id") == feedback_id:
                store.resolve_roadmap_task(t["id"])
        return json.dumps({"addressed": ok}, ensure_ascii=False)
```

Add a module-level helper in `state_tools.py`:

```python
_CHAPTER_TO_MODULE = {"intro": "M5", "lit_review": "M2", "methodology": "M3",
                      "results": "M4", "discussion": "M5", "conclusion": "M5"}


def _chapter_to_module(chapter: str | None) -> str:
    return _CHAPTER_TO_MODULE.get((chapter or "").lower(), "M5")
```

Add `ingest_advisor_feedback, mark_feedback_addressed` to the factory's returned list.

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest ../agent/tests/test_state_tools.py -k "ingest or addressed" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/state_tools.py agent/tests/test_state_tools.py
git commit -m "feat(memory): ingest_advisor_feedback + mark_feedback_addressed tools

Ingest extracts directives, persists them, and raises a roadmap blocker per open
item so next_action leads the revision; marking addressed clears the blocker.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Per-user cross-project keys + distillation

**Files:**
- Modify: `api/app/user_memory.py` (extend `USER_MEMORY_KEYS`; add a distill helper)
- Modify: project-create path to seed `institution_profile` from `institution_default` (find via `grep -rn "create.*project" api/app/routers`)
- Test: `api/tests/test_user_memory.py`

**Interfaces:**
- Produces:
  - `USER_MEMORY_KEYS` gains `"institution_default"`, `"recurring_advisor_themes"`.
  - `distill_advisor_themes(db, user_id, advisor_feedback, source_project_id) -> None` — summarize recurring addressed-directive themes into `recurring_advisor_themes` via `write_user_prefs`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_user_memory.py (append or create)
from app import user_memory as um


def test_new_keys_allowed():
    assert {"institution_default", "recurring_advisor_themes"} <= um.USER_MEMORY_KEYS


def test_distill_writes_themes(monkeypatch):
    calls = {}
    monkeypatch.setattr(um, "write_user_prefs",
                        lambda db, uid, updates, **k: calls.update(updates))
    fb = [{"issue": "report effect sizes", "status": "addressed"},
          {"issue": "report effect sizes", "status": "addressed"}]
    um.distill_advisor_themes(db=None, user_id="u", advisor_feedback=fb, source_project_id=None)
    assert "recurring_advisor_themes" in calls
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_user_memory.py -k "new_keys or distill" -q`
Expected: FAIL — keys missing / no `distill_advisor_themes`.

- [ ] **Step 3: Implement**

In `api/app/user_memory.py`: add the two keys to the `USER_MEMORY_KEYS` set, then:

```python
def distill_advisor_themes(db, user_id, advisor_feedback, source_project_id=None) -> None:
    """Summarize recurring ADDRESSED advisor directives into cross-project memory so a
    new project starts pre-warned. Cheap heuristic: issues that recurred (>=2) become
    themes. Best-effort — never breaks the caller."""
    from collections import Counter
    try:
        addressed = [d.get("issue", "").strip().lower()
                     for d in (advisor_feedback or []) if d.get("status") == "addressed"]
        themes = [issue for issue, n in Counter(addressed).items() if issue and n >= 2]
        if themes:
            write_user_prefs(db, user_id, {"recurring_advisor_themes": themes},
                             source_project_id=source_project_id, confidence=0.7)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("distill_advisor_themes failed")
```

Seed on project create: where a new project is created, if the user has
`institution_default`, call `store.set_institution_profile(institution_default)` for the new
project (read via `load_user_prefs`).

- [ ] **Step 4: Run to verify it passes**

Run: `cd api && ./run.sh pytest tests/test_user_memory.py -k "new_keys or distill" -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/user_memory.py api/tests/test_user_memory.py
git commit -m "feat(memory): cross-project advisor themes + institution default

Recurring addressed directives distill into user_memory (allowlisted, with
provenance) so a new project starts pre-warned; institution_default seeds new
projects' profile.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Root-skill documentation of the loop

**Files:**
- Modify: `skills/dothesis/SKILL.md`
- Test: none (docs) — verify the file mentions the tools.

- [ ] **Step 1: Add an "Advisor feedback loop" section**

Document, in `skills/dothesis/SKILL.md`: when the user relays professor comments, call
`ingest_advisor_feedback`; open directives become roadmap blockers that `[NEXT]` will lead
toward; after revising a chapter to a directive, call `mark_feedback_addressed(id)`; the
quality `review_thesis` tool reports N-of-M addressed.

- [ ] **Step 2: Verify**

Run: `grep -n "ingest_advisor_feedback\|mark_feedback_addressed" skills/dothesis/SKILL.md`
Expected: both present.

- [ ] **Step 3: Commit**

```bash
git add skills/dothesis/SKILL.md
git commit -m "docs(skill): advisor feedback loop guidance

Tell the agent to ingest professor feedback, let open directives drive [NEXT],
and mark them addressed after revising.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest ../agent/tests/test_state.py ../agent/tests/test_state_tools.py tests/test_feedback_extract.py tests/test_user_memory.py -q` → all PASS.
- [ ] Loop integration (manual/`/run`): paste a professor comment → confirm an `advisor_feedback` entry + a roadmap blocker appear and `[NEXT]` points at it; `mark_feedback_addressed` clears both.
- [ ] Headless untouched: `cd api && ./run.sh pytest tests/test_partner_report.py -q` still green.

## Notes / spec deviations

- **Per-project memory reuses Spec 2's dedicated-write-path pattern** (not `commit_slice`) —
  the same correctness reason (blockers/feedback must not shift module status/focus).
- **`distill_advisor_themes` is a cheap recurrence heuristic**, not an LLM summarizer, to keep
  cross-project writes deterministic and safe; can be upgraded later.
- Quality-evals (Spec 3) already reads `advisor_feedback`/`institution_profile` with empty
  defaults, so it lights up automatically once this spec populates them.
