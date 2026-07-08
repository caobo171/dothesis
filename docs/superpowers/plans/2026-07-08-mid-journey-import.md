# Mid-Journey State Import Implementation Plan (F12)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let a student who arrives mid-thesis upload what they have; the agent classifies it, infers per-module state from the real artifacts, commits it as earned state, and opens at the right next step — the first-run activation moment.

**Architecture:** `import_existing_work` reuses `partner_report_service` inference + a cheap classifier to produce per-module slices; the bootstrap skill commits evidenced slices via `commit_slice` (earned, not narrated) and asks on ambiguity; `/new` shows an import summary.

**Tech Stack:** Python, engine LLM, `pdf_extract`/docx extract, `agent/guardrails.py`, pytest via `./run.sh`.

## Global Constraints

- **Earned, not narrated:** only commit slices an uploaded artifact evidences; the `commit_slice` done-gate still applies. Ambiguous → ask.
- **Best-effort per file:** an unreadable upload is skipped, never blocks import.
- **No PII leakage:** neutralize extracted file text (`guardrails`).
- **Comment the decision behind each change.**

---

### Task 1: `import_existing_work` — classify + infer

**Files:**
- Create: `agent/import_work.py`
- Test: `api/tests/test_import_work.py`

**Interfaces:**
- Produces: `import_existing_work(files: list[dict], notes: str | None) -> dict` → `{slices: {M1..M5: {...}}, evidence: {module: filename}, ambiguous: list, unreadable: list}`. `files` = `[{filename, text}]` (already extracted by the caller).

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_import_work.py
import agent.import_work as iw


def test_classifies_and_infers(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output" if "AVE" in text else "proposal")
    monkeypatch.setattr(iw, "_infer_topic", lambda text, lang: {"research_title": "T", "research_questions": ["Q"]})
    monkeypatch.setattr(iw, "_infer_model", lambda text, lang: {"constructs": [{"id": "a"}]})
    files = [{"filename": "proposal.pdf", "text": "This study examines..."},
             {"filename": "results.pdf", "text": "AVE=0.62 HTMT ok"}]
    out = iw.import_existing_work(files, notes=None)
    assert out["slices"]["M1"]["research_title"] == "T"
    assert out["slices"]["M4"]["analysis_results"]
    assert out["evidence"]["M4"] == "results.pdf"


def test_unreadable_file_is_skipped(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "unknown")
    out = iw.import_existing_work([{"filename": "x.bin", "text": ""}], notes=None)
    assert "x.bin" in out["unreadable"]
```

- [ ] **Step 2: Run to verify it fails** → FAIL (no module).

- [ ] **Step 3: Implement**

```python
# agent/import_work.py
"""Mid-journey import: classify a student's existing uploads and infer per-module slices from the
REAL artifacts, so the agent can join a thesis already in progress. Inference reuses the partner
report helpers; nothing is fabricated — only what an upload evidences."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)


def _classify(filename: str, text: str) -> str:
    """proposal | chapter | questionnaire | analysis-output | dataset | unknown. Cheap LLM+heuristics."""
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    low = (text or "").lower()
    if not low.strip():
        return "unknown"
    if any(k in low for k in ("ave", "htmt", "cronbach", "r square", "path coefficient", "loading")):
        return "analysis-output"
    prompt = ("Classify this thesis document as one of: proposal, chapter, questionnaire, "
              "analysis-output, dataset, unknown. Reply with ONE word.\n\n" + text[:3000])
    try:
        resp = _get_llm().invoke(prompt)
        word = str(getattr(resp, "content", resp)).strip().lower().split()[0]
        return word if word in {"proposal", "chapter", "questionnaire", "analysis-output",
                                "dataset", "unknown"} else "unknown"
    except Exception:
        logger.exception("import: classify failed")
        return "unknown"


def _infer_topic(text, lang="en"):
    from app.partner_report_service import _infer_topic as f  # noqa: PLC0415
    return f(text, lang)


def _infer_model(text, lang="en"):
    from app.partner_report_service import _infer_model as f  # noqa: PLC0415
    return f(text, lang)


def import_existing_work(files: list[dict], notes: str | None) -> dict:
    slices: dict = {}
    evidence: dict = {}
    ambiguous: list = []
    unreadable: list = []
    for f in files:
        fn, text = f.get("filename", "?"), f.get("text", "")
        kind = _classify(fn, text)
        if kind == "unknown":
            unreadable.append(fn); continue
        if kind == "proposal":
            topic = _infer_topic(text)
            if topic.get("research_title"):
                slices.setdefault("M1", {}).update(
                    {k: topic[k] for k in ("research_title", "research_questions") if topic.get(k)})
                evidence["M1"] = fn
            model = _infer_model(text)
            if model.get("constructs"):
                slices.setdefault("M3", {})["conceptual_model"] = model; evidence["M3"] = fn
        elif kind == "analysis-output":
            slices.setdefault("M4", {})["analysis_results"] = text; evidence["M4"] = fn
        elif kind == "chapter":
            slices.setdefault("M5", {}).setdefault("final_sections", []).append(
                {"title": fn, "prose": text}); evidence["M5"] = fn
        elif kind == "questionnaire":
            slices.setdefault("M3", {})["instrument"] = {"raw": text}; evidence.setdefault("M3", fn)
        else:  # dataset — evidence only, no auto-slice
            ambiguous.append(fn)
    return {"slices": slices, "evidence": evidence, "ambiguous": ambiguous, "unreadable": unreadable}
```

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/import_work.py api/tests/test_import_work.py
git commit -m "feat(import): classify uploads + infer per-module slices (mid-journey)

Reuses partner inference to derive earned state from a student's existing work
so the agent can join a thesis in progress. Only evidenced slices; nothing faked.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Bootstrap commits imported slices as earned state

**Files:**
- Modify: `skills/dothesis-bootstrap/SKILL.md`
- Modify: `agent/tools/state_tools.py` (an `import_work` tool that runs the import + commits)
- Test: `agent/tests/test_state_tools.py`

**Interfaces:**
- Produces: `import_work(files_json) -> str` tool (inside `make_state_tools`) — runs `import_existing_work`, `commit_slice`s each evidenced slice (reason `"imported from <file>"`), sets focus, returns a summary `{imported, ambiguous, unreadable, focus}`.

- [ ] **Step 1: Write the failing test**

```python
# agent/tests/test_state_tools.py (append)
def test_import_work_commits_earned_slices(tmp_path, monkeypatch):
    import uuid, json
    from agent.state import ProjectStateStore
    from agent.tools.state_tools import make_state_tools
    import agent.import_work as iw
    monkeypatch.setattr(iw, "import_existing_work", lambda files, notes=None: {
        "slices": {"M1": {"research_title": "T", "research_questions": ["Q"]}},
        "evidence": {"M1": "p.pdf"}, "ambiguous": [], "unreadable": []})
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    out = json.loads(tools["import_work"].func(files_json='[{"filename":"p.pdf","text":"..."}]'))
    assert out["imported"]
    assert store.load()["status"]["M1"] in ("in_progress", "done")   # earned from the artifact
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement the tool + skill**

Inside `make_state_tools(store)`:

```python
    @tool
    def import_work(files_json: str) -> str:
        """Import the student's EXISTING thesis work (uploaded proposal/chapters/output) into
        earned project state so the agent joins the journey where they actually are. Commits only
        what an upload evidences; ambiguous items are returned for you to ask about."""
        import json as _json  # noqa: PLC0415
        from agent.import_work import import_existing_work  # noqa: PLC0415
        files = _json.loads(files_json)
        res = import_existing_work(files, notes=None)
        for module, writes in res["slices"].items():
            try:
                store.commit_slice(module, writes,
                                   reason=f"imported from {res['evidence'].get(module, 'upload')}")
            except Exception:
                pass  # a slice that can't commit (e.g. empty) is skipped, not fatal
        state = store.load()
        # focus = first module not done
        from agent.state import MODULES  # noqa: PLC0415
        focus = next((m for m in MODULES if state["status"].get(m) != "done"), "M1")
        return _json.dumps({"imported": list(res["slices"].keys()), "ambiguous": res["ambiguous"],
                            "unreadable": res["unreadable"], "focus": focus}, ensure_ascii=False)
```

Add to the returned tool list. In `skills/dothesis-bootstrap/SKILL.md`: "If the student uploaded
existing work, call `import_work` FIRST; report what was imported, ask about ambiguous items, then
open at the imported focus with the roadmap."

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add agent/tools/state_tools.py skills/dothesis-bootstrap/SKILL.md agent/tests/test_state_tools.py
git commit -m "feat(import): import_work tool commits evidenced slices as earned state

Bootstrap joins a mid-thesis student at their real position; ambiguous uploads
are asked, not assumed.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `/new` import summary card (activation)

**Files:**
- Modify: `web/app/(inapp)/new/page.tsx` (import progress), a small `ImportSummary.tsx`
- Test: `web/app/components/.../ImportSummary.test.tsx` (vitest)

- [ ] **Step 1: Read the current `/new` drop-first flow** (it already uploads + fires `/bootstrap`).

- [ ] **Step 2: Write the failing vitest test** for an `ImportSummary` component that renders
  "Imported: M1, M4 · You're at M4 · Next: …" from a summary prop and shows ambiguous items.

- [ ] **Step 3: Implement** the progress state ("importing your work…") and the summary card fed by
  the `import_work` tool result surfaced in the first assistant turn; CTA continues into chat.

- [ ] **Step 4: Run** `cd web && npm test -- ImportSummary` → PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app api/tests 2>/dev/null; git add -A web/
git commit -m "feat(import): /new activation summary card

First session ends with 'here's where you are, next do X' instead of a blank M1.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_import_work.py ../agent/tests/test_state_tools.py -q` → PASS.
- [ ] `cd web && npm test -- ImportSummary` → PASS.
- [ ] Earned-gate holds: importing an empty chapter does NOT mark M5 done.

## Notes

- **Uses `commit_slice`** (module slices), so F0 persistence isn't required here — the imported
  data lands in owned module keys that already round-trip.
- Depends on `partner_report_service` inference + **F2** for focus/roadmap. This is also the
  first-run activation the program otherwise lacked.
