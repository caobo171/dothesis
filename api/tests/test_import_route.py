"""Route test for POST /projects/{id}/mid-journey-import (F12 Task 2).

The DB/S3/store seams (_authorize, _store_and_files, _set_focus) and the inference
(import_existing_work) are all stubbed so this test pins the route's contract only:
commits happen in MODULES order, and focus lands on the first NOT-imported module
(importing M1+M3 => focus M2, not M1 — the bug this feature exists to fix)."""
import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.db import get_engine
from app.models import ContextStore as DbContextStore, Project, User
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
    body = r.json()
    assert body["focus"] == "M2"
    # to_reconstruct = upstream-of-imported, still locked, reconstructable (M1-M4).
    # imported M1+M3, M2 is locked and below M3 → suggested for reconstruction.
    assert body["to_reconstruct"] == ["M2"]


# --- reconstruct + confirm endpoints (real Postgres via conftest) -----------

def _project(owner_id=None):
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M4", status="draft")
        s.add(p); s.commit()
        return p.id


def _client():
    app = FastAPI()
    app.include_router(ir.router, prefix="/api/v1")
    app.dependency_overrides[ir.current_user] = lambda: object()

    def _db():
        with Session(get_engine()) as s:
            yield s
    app.dependency_overrides[ir.db_session] = _db
    return TestClient(app)


def _seed_m4(project_id):
    """Commit a real M4 slice so the project looks mid-journey (M4 in_progress)."""
    from app.agent_state import DbProjectStateStore
    store = DbProjectStateStore(get_engine(), project_id, f"/tmp/ws-{project_id}")
    store.commit_slice("M4", {"analysis_results": "PLS-SEM A->B, R2=0.41"},
                       reason="import")
    return store


def test_confirm_splits_owned_and_nonowned_no_confirmed_at(monkeypatch):
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    # A candidate mixing OWNED (conceptual_model, hypotheses), NON-OWNED schema
    # (paradigm, design), and junk the server must strip (_source, confirmed_at).
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/confirm", json={
        "module": "M3",
        "slice": {"conceptual_model": {"constructs": ["A", "B"]},
                  "hypotheses": ["H1: A->B"],
                  "paradigm": "quantitative", "design": "PLS-SEM",
                  "_source": "client-junk", "confirmed_at": "2020-01-01", "bogus": 1},
    })
    assert r.status_code == 200 and r.json()["module"] == "M3"

    from app.agent_state import DbProjectStateStore
    store = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}")
    state = store.load()
    with Session(get_engine()) as s:
        col = s.get(DbContextStore, pid).m3_design
    # Both owned AND non-owned fields landed in the column.
    assert col["conceptual_model"] == {"constructs": ["A", "B"]}
    assert col["paradigm"] == "quantitative" and col["design"] == "PLS-SEM"
    # Server-authoritative source tag; client junk stripped; NOT marked done.
    assert col["_source"] == "reconstructed"
    assert "confirmed_at" not in col and "bogus" not in col
    assert state["status"]["M3"] == "in_progress"
    # The already-started downstream M4 is preserved, NOT flagged needs_review.
    assert state["status"]["M4"] == "in_progress"
    # Focus is restored — confirming an upstream backfill doesn't move the student.
    assert state["focus"] == "M4"


def test_confirm_cannot_forge_the_decision_audit_trail(monkeypatch):
    # `decisions` is SLICE_OWNERSHIP-owned by every module (headless audit
    # trail), which would otherwise let an import payload overwrite it through
    # commit_slice. The trail is only worth anything if it's system-generated —
    # a client-supplied one must be stripped like any other junk key, while the
    # real content in the same payload still commits.
    pid = _project()
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    from agent.headless import record_decision
    from app.agent_state import DbProjectStateStore
    store = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}")
    store.commit_slice("M3", {"conceptual_model": {"constructs": ["A"]}}, "seed")
    real = record_decision(store, options=["A", "B"], choice="A", rationale="auto")

    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/confirm", json={
        "module": "M3",
        "slice": {"hypotheses": ["H1: A->B"],
                  "decisions": [{"ts": "2020-01-01", "module": "M3",
                                 "options": [], "choice": "FORGED",
                                 "rationale": "client-supplied"}]},
    })
    assert r.status_code == 200
    state = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").load()
    # The genuine trail survives untouched; the forged entry never landed.
    assert state["contextStore"]["decisions"] == [real]
    # ...and the legitimate content in the same payload still committed.
    assert state["contextStore"]["hypotheses"] == ["H1: A->B"]


def test_confirm_unknown_module_422(monkeypatch):
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    pid = _project()
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/confirm",
                       json={"module": "M9", "slice": {"x": 1}})
    assert r.status_code == 422


def test_confirm_empty_after_sanitize_422(monkeypatch):
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    pid = _project()
    # Only junk keys → nothing valid to commit → 422 (never a no-op 200).
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/confirm",
                       json={"module": "M3", "slice": {"_source": "x", "nope": 1}})
    assert r.status_code == 422


def test_reconstruct_endpoint_returns_candidates_and_writes_nothing(monkeypatch):
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", lambda cs, language=None: [
        {"module": "M3", "artifact": "design", "candidate": {"paradigm": "quantitative"},
         "rationale": "from M4", "ready_to_confirm": False, "review": ["missing tool"]}])
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200
    assert r.json()["reconstructed"][0]["module"] == "M3"
    # Dry-run: M3 column stayed empty (nothing persisted by reconstruct).
    with Session(get_engine()) as s:
        row = s.get(DbContextStore, pid)
        assert row is None or not (row.m3_design or {})
