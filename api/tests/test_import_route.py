"""Route test for POST /projects/{id}/mid-journey-import (F12 Task 2).

The DB/S3/store seams (_authorize, _store_and_files, _set_focus) and the inference
(import_existing_work) are all stubbed so this test pins the route's contract only:
commits happen in MODULES order, and focus lands on the first NOT-imported module
(importing M1+M3 => focus M2, not M1 — the bug this feature exists to fix)."""
from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.routers import import_route as ir


def test_focus_is_first_not_imported(monkeypatch):
    monkeypatch.setattr(ir, "import_existing_work",
                        lambda files, language: {"slices": {"M1": {"research_title": "T"},
                        "M3": {"conceptual_model": {"x": 1}}}, "evidence": {}, "ambiguous": [], "unreadable": []})
    committed, focus_set = [], {}

    class _Store:
        def commit_slice(self, m, w, reason, confirm_done=False):
            committed.append(m)

        def load(self):
            return {"status": {"M1": "in_progress", "M2": "locked", "M3": "in_progress",
                               "M4": "locked", "M5": "locked"}}

    monkeypatch.setattr(ir, "_store_and_files", lambda db, pid: (_Store(), [{"filename": "p", "text": "x"}], "en"))
    monkeypatch.setattr(ir, "_set_focus", lambda db, pid, f: focus_set.update(f=f))
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    app = FastAPI()
    app.include_router(ir.router, prefix="/api/v1")
    app.dependency_overrides[ir.current_user] = lambda: object()
    r = TestClient(app).post("/api/v1/projects/abc/mid-journey-import")
    assert r.status_code == 200
    assert committed == ["M1", "M3"]          # MODULES order
    assert focus_set["f"] == "M2"             # first not-imported
    assert r.json()["focus"] == "M2"
