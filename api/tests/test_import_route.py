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
    # to_reconstruct = every reconstructable module up to the highest imported
    # one that isn't `done`. M2 is empty; M1 and M3 were imported but landed
    # `in_progress` (partial slices), and a partial module is exactly the one
    # worth finishing — under the old "locked only" rule the modules carrying
    # the student's real content were the ones we refused to complete.
    assert body["to_reconstruct"] == ["M1", "M2", "M3"]


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


def _project_and_owner():
    """Same as _project, but hands back the owner too.

    The progress-run tests need a REAL user: begin_tool_run writes a ToolRun
    keyed on user.id, so the bare object() the other tests pass makes it fail
    open and return no run id — which is a fine stand-in for "no progress" but
    cannot test progress itself."""
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M4", status="draft")
        s.add(p); s.commit()
        return p.id, u.id


def _client(user_id=None):
    app = FastAPI()
    app.include_router(ir.router, prefix="/api/v1")
    # object() by default: every test that doesn't care about billing/progress
    # only needs `user` to be *something* the stubbed _authorize ignores.
    if user_id is None:
        app.dependency_overrides[ir.current_user] = lambda: object()
    else:
        def _user():
            with Session(get_engine()) as s:
                return s.get(User, user_id)
        app.dependency_overrides[ir.current_user] = _user

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


def test_confirm_splits_owned_and_nonowned_and_marks_done(monkeypatch):
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
    # Server-authoritative source tag; client junk stripped.
    assert col["_source"] == "reconstructed"
    assert "bogus" not in col
    # A reconstruction counts: `done`, with the store's OWN confirmed_at — the
    # client's claimed one was stripped before it ever reached the write path.
    assert state["status"]["M3"] == "done"
    assert col["confirmed_at"] and not col["confirmed_at"].startswith("2020")
    # The already-started downstream M4 is preserved, NOT flagged needs_review.
    assert state["status"]["M4"] == "in_progress"
    # Focus does not regress to the still-empty M1 just because it isn't done.
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


def _handing_over(entries, explode_after=None):
    """Stand in for reconstruct_upstream, which hands each module to the caller
    via on_module as it is produced rather than returning them in a batch.

    `explode_after` raises once that module has been handed over, standing in
    for a run that dies part-way (cancelled request, LLM timeout, killed worker).
    """
    def fake(cs, targets=None, language=None, on_module=None, **kw):
        for entry in entries:
            if on_module:
                on_module(entry)
            if explode_after and entry["module"] == explode_after:
                raise RuntimeError("reconstruction died mid-walk")
        return entries
    return fake


def test_reconstruct_endpoint_saves_every_candidate(monkeypatch):
    """The confirm/skip gate is gone: reconstructing IS saving.

    Pins the whole contract in one place because the parts only make sense
    together — a student who imported an M4 gets M1-M3 filled in, counted, and
    is put in front of M4 instead of back at the topic screen.
    """
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    # Handed over out of MODULES order on purpose — the real walk runs M4→M1,
    # and the route commits in that order now. It stays correct because
    # commit_reconstructed preserves the status of downstream modules that had
    # already started, so M1's commit must not knock the M3 above it back.
    monkeypatch.setattr(bf, "reconstruct_upstream", _handing_over([
        {"module": "M3", "artifact": "design",
         "candidate": {"conceptual_model": {"constructs": ["A", "B"]},
                       "paradigm": "quantitative"},
         "rationale": "from M4", "ready_to_confirm": False, "review": ["missing tool"]},
        {"module": "M1", "artifact": "topic",
         "candidate": {"research_title": "T", "research_questions": ["RQ1"],
                       "scope": "VN hotels"},
         "rationale": "from M4", "ready_to_confirm": True, "review": []},
    ]))
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200
    body = r.json()
    assert [s["module"] for s in body["saved"]] == ["M1", "M3"]   # MODULES order

    from app.agent_state import DbProjectStateStore
    state = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").load()
    assert state["status"]["M1"] == "done" and state["status"]["M3"] == "done"
    # Imported M4 is untouched by the upstream backfill, not knocked to needs_review.
    assert state["status"]["M4"] == "in_progress"
    # Focus advances past the reconstructed steps to the work that's actually left.
    assert state["focus"] == "M4" and body["focus"] == "M4"

    with Session(get_engine()) as s:
        row = s.get(DbContextStore, pid)
    # Owned keys AND the non-owned schema field both persisted.
    assert row.m3_design["conceptual_model"] == {"constructs": ["A", "B"]}
    assert row.m3_design["paradigm"] == "quantitative"
    assert row.m1_topic["research_title"] == "T" and row.m1_topic["scope"] == "VN hotels"


def test_reconstruct_survives_one_module_failing_to_commit(monkeypatch):
    """A module that can't be committed must not cost the student the others."""
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", _handing_over([
        {"module": "M2", "artifact": "literature",
         "candidate": {"research_gaps": [{"description": "gap"}]},
         "rationale": "", "ready_to_confirm": False, "review": []},
        {"module": "M3", "artifact": "design", "candidate": {"conceptual_model": {"c": ["A"]}},
         "rationale": "", "ready_to_confirm": False, "review": []},
    ]))

    # M2's write blows up (a bad slice, a DB hiccup — the reason doesn't matter).
    real_store = ir._store
    def _flaky(db, project_id):
        store = real_store(db, project_id)
        commit = store.commit_reconstructed
        store.commit_reconstructed = lambda m, s, **kw: (
            _raise() if m == "M2" else commit(m, s, **kw))
        return store
    def _raise():
        raise RuntimeError("commit exploded")
    monkeypatch.setattr(ir, "_store", _flaky)
    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200
    assert [s["module"] for s in r.json()["saved"]] == ["M3"]

    from app.agent_state import DbProjectStateStore
    assert DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").load()["status"]["M3"] == "done"


def test_a_reconstruction_that_dies_part_way_keeps_what_it_finished(monkeypatch):
    """The point of committing per module: a run that breaks off mid-walk must
    leave the finished modules SAVED.

    Everything used to be collected and committed after the walk returned, so a
    cancelled or timed-out reconstruction discarded every module it had already
    paid an LLM for and the student restarted from zero. The /new screen tells
    them a cancelled analysis can be carried on — this is what makes that true.
    """
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", _handing_over([
        {"module": "M3", "artifact": "design",
         "candidate": {"conceptual_model": {"constructs": ["A", "B"]}},
         "rationale": "", "ready_to_confirm": False, "review": []},
        {"module": "M2", "artifact": "literature",
         "candidate": {"research_gaps": [{"description": "gap"}]},
         "rationale": "", "ready_to_confirm": False, "review": []},
    ], explode_after="M2"))

    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200                      # a dead walk is not a 500
    assert [s["module"] for s in r.json()["saved"]] == ["M2", "M3"]

    # And it is really in the DB, not just in the response.
    with Session(get_engine()) as s:
        row = s.get(DbContextStore, pid)
    assert row.m3_design["conceptual_model"] == {"constructs": ["A", "B"]}
    assert row.m2_literature["research_gaps"]


def test_a_resumed_reconstruction_is_not_asked_to_redo_finished_modules(monkeypatch):
    """Resume, from the other side: what already landed is not targeted again.

    reconstruct_upstream auto-targets only modules that aren't COMPLETE, so the
    incremental commit above is what turns "run it again" into "carry on" —
    without it the second run pays for every module a second time.
    """
    pid = _project()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf

    # First run: M3 lands, then the walk dies.
    monkeypatch.setattr(bf, "reconstruct_upstream", _handing_over([
        {"module": "M3", "artifact": "design",
         "candidate": {"conceptual_model": {"constructs": ["A", "B"]},
                       "paradigm": "quantitative", "design": "survey",
                       "tool": "SmartPLS", "sampling_strategy": "purposive",
                       "target_sample_size": 200},
         "rationale": "", "ready_to_confirm": True, "review": []},
    ], explode_after="M3"))
    _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")

    # Second run: record what the REAL auto-targeting picks now.
    seen = {}

    def fake(cs, targets=None, language=None, on_module=None, **kw):
        from orchestrator.artifacts import dod_design_structural
        from orchestrator.state import _MODULE_TO_FIELD
        seen["m3_complete"] = dod_design_structural(
            getattr(cs, _MODULE_TO_FIELD["M3"], None) or {}).done
        return []

    monkeypatch.setattr(bf, "reconstruct_upstream", fake)
    _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    # M3 survived the first run's death, so the second run sees it as complete
    # and reconstruct_upstream's own auto-target will skip it.
    assert seen["m3_complete"] is True


def test_the_progress_run_is_opened_and_then_closed(monkeypatch):
    """The screen polls /runs/active, which answers from the newest row still
    marked `running`. A row left open would name this import as the caller's
    live job forever, so every later document walk would poll its stale
    numbers — and the import's own progress bar would never be seen to finish.
    """
    from app.models import ToolRun
    pid, uid = _project_and_owner()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf

    def fake(cs, targets=None, language=None, on_progress=None, on_module=None, **kw):
        if on_progress:
            on_progress(0, 2, "M3")          # the screen needs a denominator
            on_progress(2, 2, None)
        return []

    monkeypatch.setattr(bf, "reconstruct_upstream", fake)
    r = _client(uid).post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert run_id is not None                 # the screen has something to poll

    with Session(get_engine()) as s:
        row = s.get(ToolRun, run_id)
    assert row.status != "running"            # closed, not left dangling
    assert row.progress_total == 2 and row.progress_done == 2


def test_the_progress_run_is_closed_even_when_the_walk_dies(monkeypatch):
    """The dangling-row failure is worst on the path that already went wrong."""
    from app.models import ToolRun
    pid, uid = _project_and_owner()
    _seed_m4(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream", _handing_over([
        {"module": "M3", "candidate": {"conceptual_model": {"c": ["A"]}},
         "rationale": "", "ready_to_confirm": True, "review": []},
    ], explode_after="M3"))

    r = _client(uid).post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200
    with Session(get_engine()) as s:
        row = s.get(ToolRun, r.json()["run_id"])
    assert row.status != "running"
    assert row.ok is True                     # M3 landed, so the run did work


def _seed_full_thesis(project_id):
    """A finished thesis: chapters 4 AND 5 in one blob, which is how a .docx
    upload actually lands."""
    from app.agent_state import DbProjectStateStore
    blob = ("CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU\n"
            + ("Kết quả phân tích cho thấy mô hình phù hợp. " * 60)
            + "\nCHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN NGHỊ\n"
            + ("Nghiên cứu đóng góp vào lý thuyết hiện có. " * 60))
    store = DbProjectStateStore(get_engine(), project_id, f"/tmp/ws-{project_id}")
    store.commit_slice("M4", {"analysis_results": blob}, reason="import")
    return store


def test_the_web_import_reconstructs_in_the_students_language(monkeypatch):
    """language was hardcoded "vi" HERE too — the agent tool was fixed and this
    route, which is the one the /new screen actually calls, was not."""
    import app.routers.import_route as ir
    pid = _project()
    # Long enough to read: detect_language declines below 24 letters, and the
    # shared _seed_m4 blob ("PLS-SEM A->B, R2=0.41") is under that — it would
    # correctly fall back to "vi" and prove nothing.
    from app.agent_state import DbProjectStateStore
    DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").commit_slice(
        "M4", {"analysis_results": (
            "The survey instrument was distributed to hotel employees and 218 "
            "valid responses were retained for analysis using partial least "
            "squares structural equation modelling.")}, reason="import")
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    seen = {}

    def fake(cs, targets=None, language=None, **kw):
        seen["language"] = language
        return []

    monkeypatch.setattr(bf, "reconstruct_upstream", fake)
    _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    # The seeded evidence is English, so mirroring it must not yield "vi".
    assert seen["language"] == "en"


def test_the_web_import_moves_the_final_chapter_into_m5(monkeypatch):
    """The split lived only in the agent's backfill tool, so a student importing
    through the web screen kept chapter 5 buried in M4 and M5 locked."""
    import app.routers.import_route as ir
    pid = _project()
    _seed_full_thesis(pid)
    monkeypatch.setattr(ir, "_authorize", lambda db, user, pid: None)
    import orchestrator.backfill as bf
    monkeypatch.setattr(bf, "reconstruct_upstream",
                        lambda cs, targets=None, language=None, **kw: [])

    r = _client().post(f"/api/v1/projects/{pid}/mid-journey-import/reconstruct")
    assert r.status_code == 200

    from app.agent_state import DbProjectStateStore
    state = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").load()
    m5 = state["contextStore"].get("final_sections") or []
    assert isinstance(m5, list) and m5 and "CHƯƠNG 5" in m5[0]["prose"]
    assert "CHƯƠNG 5" not in state["contextStore"]["analysis_results"]
