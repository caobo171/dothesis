# Mid-Journey State Import Implementation Plan (F12) — API-layer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Let a mid-thesis student's uploads become earned state via a server-side `/import` route, so the agent joins where they actually are — the first-run activation moment.

**Architecture:** Runs in the **API layer** (respects `agent/`↛`app/`): `api/app/import_work.py` classifies + infers (may use `app`/`orchestrator`); `POST /projects/{id}/import` (authed) extracts+neutralizes uploads server-side, commits slices in `MODULES` order, and sets focus to the first not-imported module.

**Tech Stack:** FastAPI (POST-only, authed), `app.partner_report_service` inference, `app.pdf_extract`, `agent/guardrails`, pytest via `./run.sh`.

## Global Constraints

- **API-layer only** — do NOT import `app.*` from `agent/`. Import runs in `api/app`.
- **Evidence is server-side** — extract from real uploaded files, never a model-supplied string.
- **Earned:** commit only evidenced slices, `confirm_done=False`, in `MODULES` order (no spurious downstream `needs_review`). Report only slices that actually committed.
- **Focus = first NOT-imported module** (fixes "always M1").
- Auth + ownership on the route. Comment the decision behind each change.

---

### Task 1: `api/app/import_work.py` — classify + infer

**Files:**
- Create: `api/app/import_work.py`
- Test: `api/tests/test_import_work.py`

**Interfaces:**
- Produces: `import_existing_work(files: list[dict], language: str) -> dict` → `{slices, evidence, ambiguous, unreadable}`. `files = [{filename, text}]`.

- [ ] **Step 1: Write the failing test (stubs use the REAL 2-arg inference signature)**

```python
# api/tests/test_import_work.py
from app import import_work as iw


def test_classifies_and_infers(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output" if "AVE" in text else "proposal")
    monkeypatch.setattr(iw, "_infer_topic", lambda text, language: {"research_title": "T", "research_questions": ["Q"]})
    monkeypatch.setattr(iw, "_infer_model", lambda text, language: {"constructs": [{"id": "a"}]})
    files = [{"filename": "proposal.pdf", "text": "This study examines..."},
             {"filename": "results.pdf", "text": "AVE=0.62 HTMT ok"}]
    out = iw.import_existing_work(files, language="en")
    assert out["slices"]["M1"]["research_title"] == "T"
    assert out["slices"]["M4"]["analysis_results"]
    assert out["evidence"]["M4"] == "results.pdf"


def test_unreadable_file_skipped(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "unknown")
    out = iw.import_existing_work([{"filename": "x.bin", "text": ""}], language="en")
    assert "x.bin" in out["unreadable"]
```

- [ ] **Step 2: Run to verify it fails** → `cd api && ./run.sh pytest tests/test_import_work.py -q` → FAIL.

- [ ] **Step 3: Implement**

```python
# api/app/import_work.py
"""Mid-journey import (API layer): classify a student's uploads and infer per-module slices from
the REAL artifacts so the agent can join a thesis in progress. May use app/orchestrator (this is
NOT the agent layer). Nothing is fabricated — only what an upload evidences."""
from __future__ import annotations
import logging

from .partner_report_service import _infer_topic, _infer_model   # api-layer import is fine here

logger = logging.getLogger(__name__)

_STAT_HINTS = ("ave", "htmt", "cronbach", "r square", "path coefficient", "outer loading", "vif")


def _classify(filename: str, text: str) -> str:
    """proposal | chapter | questionnaire | analysis-output | dataset | unknown."""
    low = (text or "").lower()
    if not low.strip():
        return "unknown"
    if any(k in low for k in _STAT_HINTS):
        return "analysis-output"
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415
    prompt = ("Classify this thesis document as ONE of: proposal, chapter, questionnaire, "
              "analysis-output, dataset, unknown. Reply with one word only.\n\n" + text[:3000])
    try:
        word = str(getattr(_get_llm().invoke(prompt), "content", "")).strip().lower().split()[0]
        return word if word in {"proposal", "chapter", "questionnaire", "analysis-output",
                                "dataset", "unknown"} else "unknown"
    except Exception:
        logger.exception("import: classify failed")
        return "unknown"


def import_existing_work(files: list[dict], language: str) -> dict:
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
            topic = _infer_topic(text, language)
            if topic.get("research_title"):
                slices.setdefault("M1", {}).update(
                    {k: topic[k] for k in ("research_title", "research_questions") if topic.get(k)})
                evidence["M1"] = fn
            model = _infer_model(text, language)
            if model.get("constructs"):
                slices.setdefault("M3", {})["conceptual_model"] = model; evidence.setdefault("M3", fn)
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
git add api/app/import_work.py api/tests/test_import_work.py
git commit -m "feat(import): api-layer classify + infer per-module slices

Server-side inference (may use partner helpers) so agent/ never imports app/;
only evidenced slices, nothing fabricated.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `POST /projects/{id}/import` route

**Files:**
- Create: `api/app/routers/import_route.py`; mount in `api/app/main.py`
- Test: `api/tests/test_import_route.py`

**Interfaces:**
- `POST /api/v1/projects/{project_id}/import` (authed + ownership) → `{imported, ambiguous, unreadable, focus}`.

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_import_route.py
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import import_route as ir


def test_focus_is_first_not_imported(monkeypatch):
    # import M1 + M3 ⇒ focus must be M2, NOT M1 (the bug this feature exists to fix).
    monkeypatch.setattr(ir, "import_existing_work",
                        lambda files, language: {"slices": {"M1": {"research_title": "T"},
                        "M3": {"conceptual_model": {"x": 1}}}, "evidence": {}, "ambiguous": [], "unreadable": []})
    committed, focus_set = [], {}
    class _Store:
        def commit_slice(self, m, w, reason, confirm_done=False): committed.append(m)
        def load(self): return {"status": {"M1": "in_progress", "M2": "locked", "M3": "in_progress",
                                            "M4": "locked", "M5": "locked"}}
    monkeypatch.setattr(ir, "_store_and_files", lambda db, pid: (_Store(), [{"filename": "p", "text": "x"}], "en"))
    monkeypatch.setattr(ir, "_set_focus", lambda db, pid, f: focus_set.update(f=f))
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    app = FastAPI(); app.include_router(ir.router, prefix="/api/v1")
    # override the auth dependency for the test
    app.dependency_overrides[ir.current_user] = lambda: object()
    r = TestClient(app).post("/api/v1/projects/abc/import")
    assert r.status_code == 200
    assert committed == ["M1", "M3"]          # MODULES order
    assert focus_set["f"] == "M2"             # first not-imported
```

- [ ] **Step 2: Run to verify it fails** → FAIL.

- [ ] **Step 3: Implement the route**

```python
# api/app/routers/import_route.py
"""Mid-journey import route (POST-only, authed). Extracts the project's uploads server-side,
infers per-module slices, commits them as earned state in MODULES order, and lands focus on the
first not-imported module."""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import update

from ..deps import current_user, db_session
from ..import_work import import_existing_work
from ..models import Project, User
from agent.state import MODULES

logger = logging.getLogger(__name__)
router = APIRouter(tags=["import"])


def _authorize(db, user, project_id) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.user_id != user.id:
        raise HTTPException(403, detail={"error": {"code": "forbidden", "message": "not your project"}})
    return p


def _store_and_files(db, project_id):
    """Return (DbProjectStateStore, files, language). Reads the project's uploads' extracted text
    (uploads flow already stores extracted.txt per upload) and neutralizes each."""
    from ..agent_state import DbProjectStateStore
    from ..routers.chat_v3 import _workspace_dir
    from agent.guardrails import neutralize_document_text
    # NOTE: load the project's uploads from the uploads table / workspace; each has extracted text.
    files = []
    for up in _load_project_uploads(db, project_id):     # implement against the uploads model
        clean, _flags = neutralize_document_text(up.text or "")
        files.append({"filename": up.filename, "text": clean})
    store = DbProjectStateStore(db.bind, project_id, _workspace_dir(project_id))
    lang = "vi"  # or read from project/user prefs
    return store, files, lang


def _set_focus(db, project_id, focus: str) -> None:
    db.execute(update(Project).where(Project.id == project_id).values(focus=focus))
    db.commit()


@router.post("/projects/{project_id}/import")
def import_project(project_id: str, user: User = Depends(current_user), db=Depends(db_session)):
    _authorize(db, user, project_id)
    store, files, language = _store_and_files(db, project_id)
    res = import_existing_work(files, language)
    imported = []
    for module in MODULES:                        # MODULES order → no spurious needs_review
        if module in res["slices"]:
            try:
                store.commit_slice(module, res["slices"][module],
                                   reason=f"imported from {res['evidence'].get(module, 'upload')}")
                imported.append(module)
            except Exception:
                logger.exception("import: commit %s failed", module)   # skip, don't report
    focus = next((m for m in MODULES if m not in res["slices"]), MODULES[-1])
    _set_focus(db, project_id, focus)
    return {"imported": imported, "ambiguous": res["ambiguous"],
            "unreadable": res["unreadable"], "focus": focus}
```

> **Note for implementer:** implement `_load_project_uploads(db, project_id)` against the real
> uploads model (`api/app/models.py` + `routers/uploads.py`) — each upload already has extracted
> text (S3 `extracted.txt` / DB). Keep `_store_and_files`/`_set_focus`/`_authorize` thin so the
> test stubs them.

- [ ] **Step 4: Run to verify it passes** → PASS.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/import_route.py api/app/main.py api/tests/test_import_route.py
git commit -m "feat(import): POST /projects/{id}/import (authed, ordered commits, focus fix)

Server-side import commits evidenced slices in MODULES order and lands focus on
the first not-imported module (importing M1+M3 -> focus M2, not M1).

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `/new` activation summary card

**Files:**
- Modify: `web/app/(inapp)/new/page.tsx`; create `web/app/components/.../ImportSummary.tsx`
- Test: `web/app/components/.../ImportSummary.test.tsx` (**vitest**)

- [ ] **Step 1: Read the current `/new` drop-first flow** (uploads + fires `/bootstrap`).

- [ ] **Step 2: Write the failing vitest test** (`vi.fn()`, not jest) for `ImportSummary` rendering
  "Imported: M1, M3 · You're at M2 · Next: …" from a summary prop + ambiguous list.

- [ ] **Step 3: Implement** — after uploads, `/new` calls `POST /projects/{id}/import` (via the
  shared authed POST helper), shows "importing…" then the summary card; CTA continues into chat.

- [ ] **Step 4: Run** `cd web && npm test -- ImportSummary` → PASS.

- [ ] **Step 5: Commit**

```bash
git add -A web/
git commit -m "feat(import): /new activation summary card

First session ends with 'here's where you are, next do X'.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `cd api && ./run.sh pytest tests/test_import_work.py tests/test_import_route.py -q` → PASS.
- [ ] `cd web && npm test -- ImportSummary` → PASS.
- [ ] Focus fix proven: importing M1+M3 ⇒ focus M2 (not M1).
- [ ] Layering clean: `grep -rn "^from app\.\|^import app\." agent/` still returns nothing.

## Notes

- **API-layer by design** — the agent never imports `app`; the agent just reacts to the imported
  state on the next turn (F2 narrates the summary).
- Uses `commit_slice` (owned module keys), so F0 persistence isn't required here.
