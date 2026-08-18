"""Route test for POST /projects/{id}/roadmap (F2 Task 6, authed per F0 Part B).

The DB/store/auth seams (_authorize, _store_for) are stubbed so this pins the
derived-shape contract and the ownership gate, not DB wiring."""
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from app.routers import roadmap as roadmap_mod


def _client(monkeypatch, state, authorize=lambda db, user, pid: None):
    class _FakeStore:
        def load(self):
            return state

    monkeypatch.setattr(roadmap_mod, "_store_for", lambda project_id: _FakeStore())
    monkeypatch.setattr(roadmap_mod, "_authorize", authorize)
    app = FastAPI()
    app.include_router(roadmap_mod.router, prefix="/api/v1")
    app.dependency_overrides[roadmap_mod.current_user] = lambda: object()
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


def test_roadmap_includes_timeline_status(monkeypatch):
    # F11 Task 5: the endpoint returns timeline_status alongside the roadmap so
    # the ContextPanel can render a you-are-here-vs-plan card every session.
    state = {"focus": "M2", "status": {"M1": "done", "M2": "in_progress", "M3": "locked",
             "M4": "locked", "M5": "locked"},
             "contextStore": {"thesis_timeline": {"milestones": [
                 {"module": "M4", "label": "Data analysis", "start": "2026-07-01",
                  "end": "2026-07-15"}]}}}
    c = _client(monkeypatch, state)
    body = c.post("/api/v1/projects/abc/roadmap").json()
    assert "timeline" in body and body["timeline"].get("this_week")


def test_roadmap_rejects_non_owner(monkeypatch):
    def _deny(db, user, pid):
        raise HTTPException(403, detail={"error": {"code": "forbidden"}})

    c = _client(monkeypatch, {"focus": None, "status": {}, "contextStore": {}}, authorize=_deny)
    assert c.post("/api/v1/projects/abc/roadmap").status_code == 403


def test_completed_substep_reads_done_even_when_an_earlier_one_is_current(monkeypatch):
    """Mid-journey import produces out-of-order artifacts, and the spine has to
    survive it.

    reconstruct_upstream can name the research gaps a finished thesis addresses
    but must never invent its source list, so a reconstructed M2 legitimately
    holds research_gaps with NO literature_sources. Completion used to be purely
    positional (`done if i < idx`), so the cursor sat on `familiarize` (index 0)
    and NOTHING was marked done — the roadmap rendered "Find research gaps" as
    pending while the M2 card beside it listed G1 and G2.
    """
    state = {
        "focus": "M1",
        "status": {m: "in_progress" for m in ("M1", "M2", "M3", "M4")} | {"M5": "locked"},
        "contextStore": {
            "research_title": "T",
            "research_questions": ["RQ1"],
            "research_gaps": [{"id": "G1"}, {"id": "G2"}],  # no literature_sources
        },
    }
    body = _client(monkeypatch, state).post("/api/v1/projects/abc/roadmap").json()
    m2 = next(m for m in body["modules"] if m["id"] == "M2")
    steps = {s["id"]: s["state"] for s in m2["substeps"]}

    assert steps["find_gaps"] == "done"          # evidenced — the actual fix
    assert steps["familiarize"] == "current"     # genuinely missing, still the cursor
    assert "confirm_refs" not in steps             # removed student chore

    # M1 has both of its backed artifacts, so neither may render as unfinished
    # and there is no current step left — the next action is "confirm it".
    m1 = next(m for m in body["modules"] if m["id"] == "M1")
    m1_steps = {s["id"]: s["state"] for s in m1["substeps"]}
    assert m1_steps["frame_topic"] == "done"
    assert m1_steps["derive_questions"] == "done"
    assert m1["current"] is None
