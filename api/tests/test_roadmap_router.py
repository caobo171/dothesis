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


# --- M3 "complete but 3/5" ------------------------------------------------
#
# Reported from a real project: the panel showed M3 at 3/5 with "Design the
# instrument" not started, while the NEXT card said "M3 has all its content —
# confirm it so we move on". Both read the same state, so one was lying.

def _m3(instrument):
    return {"focus": "M3",
            "status": {"M1": "done", "M2": "done", "M3": "in_progress",
                       "M4": "locked", "M5": "locked"},
            "contextStore": {
                "conceptual_model": {"constructs": ["ATT", "DEC"], "edges": [["ATT", "DEC"]]},
                "hypotheses": [{"id": "H1"}],
                "methodology": {"paradigm": "positivist", "design": "cross-sectional survey"},
                "instrument": instrument,
            }}


# What the real project holds: a DESCRIPTION of the questionnaire — how many
# items per construct, which scale, "source: user-provided Word document" —
# and not one item of actual text.
_SPEC_ONLY = {"scale": "Five-point Likert scale", "language": "vi-en",
              "constructs": ["ATT", "DEC"], "items_per_construct": {"ATT": 5, "DEC": 5},
              "source": "User-provided bilingual questionnaire in attached Word document"}

# The canonical shape m3_contract.normalize_instrument produces.
_WITH_ITEMS = {"scale": "Five-point Likert scale",
               "items": [{"construct": "ATT", "text": "Tôi thấy nội dung du lịch hấp dẫn."},
                         {"construct": "DEC", "text": "Tôi dự định đặt chuyến đi."}]}


def test_a_spec_without_items_is_not_a_finished_instrument():
    """Presence of the key is not the deliverable.

    A spec dict is truthy, so a bare `cs.get("instrument")` marked the step
    done — while preflight_check, reading the same slice, reported "M3 — no
    questionnaire instrument yet". The roadmap must use preflight's rule.
    """
    from agent.roadmap import satisfied_substeps
    assert "design_instrument" not in satisfied_substeps("M3", _m3(_SPEC_ONLY))


def test_real_items_do_finish_the_step():
    from agent.roadmap import satisfied_substeps
    assert "design_instrument" in satisfied_substeps("M3", _m3(_WITH_ITEMS))


def test_spec_only_keeps_designing_the_instrument_as_the_next_step(monkeypatch):
    """The honest rendering of the reported project: 4/5, with the instrument
    step current — NOT a card claiming M3 has all its content."""
    body = _client(monkeypatch, _m3(_SPEC_ONLY)).post("/api/v1/projects/abc/roadmap").json()
    m3 = next(m for m in body["modules"] if m["id"] == "M3")
    steps = {s["id"]: s["state"] for s in m3["substeps"]}
    assert steps["design_instrument"] == "current"
    assert body["next_action"]["title"] == "Design the instrument"
    assert "has all its content" not in body["next_action"]["why"]


def test_no_step_is_current_once_every_artifact_is_in(monkeypatch):
    """With nothing left to produce, no step may be painted "current".

    `_substep_states` fell back to idx=0 whenever `current` was None, which
    marked the FIRST step current — so "Define constructs" glowed as the next
    action while the three steps BELOW it were already ticked.
    """
    c = _client(monkeypatch, _m3(_WITH_ITEMS))
    m3 = next(m for m in c.post("/api/v1/projects/abc/roadmap").json()["modules"] if m["id"] == "M3")
    assert [s["state"] for s in m3["substeps"]].count("current") == 0
    assert m3["current"] is None


def test_the_panel_and_the_next_card_agree(monkeypatch):
    """The original bug in one assertion: "has all its content" must mean every
    step reads done, not "every step I happened to map an artifact for"."""
    body = _client(monkeypatch, _m3(_WITH_ITEMS)).post("/api/v1/projects/abc/roadmap").json()
    m3 = next(m for m in body["modules"] if m["id"] == "M3")
    done = sum(1 for s in m3["substeps"] if s["state"] == "done")
    assert body["next_action"]["title"] == "Confirm M3 is done"
    assert done == len(m3["substeps"]), f"card says complete, panel says {done}/{len(m3['substeps'])}"
