"""Tool bindings over the guarded store (F2 Task 4). The tools close over a
real file-backed ProjectStateStore so we exercise the actual upsert/resolve path,
not a mock — the blocker must persist and flip status without touching modules."""
import json
import uuid

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


def test_mark_feedback_addressed_clears_blocker(tmp_path, monkeypatch):
    import agent.feedback as fb
    monkeypatch.setattr(fb, "extract_directives", lambda t: [
        {"chapter": "results", "issue": "add effect sizes", "required_change": "Cohen f2"}])
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    tools["ingest_advisor_feedback"].func(feedback_text="x")
    fid = store.load()["contextStore"]["advisor_feedback"][0]["id"]
    out = json.loads(tools["mark_feedback_addressed"].func(feedback_id=fid))
    assert out["addressed"] is True
    cs = store.load()["contextStore"]
    assert cs["advisor_feedback"][0]["status"] == "addressed"
    assert cs["roadmap_tasks"][0]["status"] == "done"   # linked blocker cleared


def test_model_cannot_write_the_decision_audit_trail(tmp_path):
    # `decisions` is SLICE_OWNERSHIP-owned by every module (so both stores
    # persist it), which means the ownership check ALONE would let the model
    # author or clobber the trail that audits the model. An audit trail is only
    # worth something if the audited party can't write it. Mirrors the
    # client-side strip proven in api/tests/test_import_route.py.
    from agent.headless import record_decision

    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M3", {"conceptual_model": {"constructs": ["A"]}}, "seed")
    real = record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    tools = {t.name: t for t in make_state_tools(store)}

    out = json.loads(tools["commit_slice"].func(
        module="M3",
        writes={"hypotheses": ["H1: A->B"],
                "decisions": [{"ts": "2020-01-01", "module": "M3", "options": [],
                               "choice": "FORGED", "rationale": "model-supplied"}]},
        reason="write up the model"))
    assert "error" not in out

    cs = store.load()["contextStore"]
    assert cs["decisions"] == [real]              # genuine trail untouched
    assert cs["hypotheses"] == ["H1: A->B"]       # real content still committed


def test_model_read_slice_never_carries_the_audit_trail(tmp_path):
    # read_slice injects its result into model context on EVERY read (for the
    # module and each read-dependency). The trail only grows, and the model has
    # no use for it — keeping it out is context hygiene AND reinforces the
    # "audited party can't see/rewrite its own trail" boundary above.
    from agent.headless import record_decision

    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M1", {"research_title": "T"}, "seed")
    record_decision(store, options=["A", "B"], choice="A", rationale="auto")
    tools = {t.name: t for t in make_state_tools(store)}

    for module in ("M1", "M2"):   # M2 reads M1's slice as a dependency
        snap = json.loads(tools["read_slice"].func(module=module))
        assert "decisions" not in snap["slices"]


def test_set_defense_date_builds_timeline(tmp_path):
    # F11 Task 3 + F0 correction: the tool must read the project's REAL flat
    # contextStore (methodology + sample_plan.target_n) and actually reach
    # build_timeline — not fall back to defaults. A target_n of 350 sizes data
    # collection to 6 weeks (ceil(350/50)=7, capped 6); the default 200 would
    # give 4, so asserting 6 proves the real data flowed through.
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M3", {"methodology": "PLS-SEM", "sample_plan": {"target_n": 350}},
                       reason="x")
    tools = {t.name: t for t in make_state_tools(store)}
    assert "set_defense_date" in tools
    out = json.loads(tools["set_defense_date"].func(defense_date="2026-12-31"))
    assert out["feasible"] in (True, False)
    assert out["data_collection_weeks"] == 6          # reached build_timeline w/ real target_n
    # Persisted via the dedicated coaching path (not commit_slice).
    assert store.load()["contextStore"]["thesis_timeline"]["milestones"]


# --- Phase 6: M4 stats self-validation commit gate --------------------------

import copy  # noqa: E402
import uuid as _uuid  # noqa: E402

import pytest  # noqa: E402

pytest.importorskip("thesis_stats")

_GOOD_M4 = {
    "measurement_model": [
        {"construct": "LS",
         "items": [{"item": "LS1", "loading": 0.81}, {"item": "LS2", "loading": 0.78},
                   {"item": "LS3", "loading": 0.80}],
         "cronbach_alpha": 0.86, "composite_reliability": 0.90, "ave": 0.63},
        {"construct": "PI",
         "items": [{"item": "PI1", "loading": 0.80}, {"item": "PI2", "loading": 0.76},
                   {"item": "PI3", "loading": 0.74}],
         "cronbach_alpha": 0.84, "composite_reliability": 0.88, "ave": 0.58},
    ],
    "discriminant_validity": {"method": "HTMT", "matrix": [["LS", "PI"], [1.0, 0.42], [0.42, 1.0]]},
    "hypothesis_tests": [
        {"id": "r-H1", "hypothesis": "H1", "path": "LS → PI",
         "numbers": {"beta": 0.34, "t": 7.01, "p": "<0.001", "f2": 0.18}, "decision": "supported"},
    ],
    "structural_model": {"r2": {"PI": 0.56}},
}


def _tools(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{_uuid.uuid4().hex}")
    return store, {t.name: t for t in make_state_tools(store)}


def _commit(tools, writes, module="M4"):
    return json.loads(tools["commit_slice"].func(module=module, writes=writes, reason="test"))


def test_gate_clean_commit_succeeds_no_warnings(tmp_path):
    store, tools = _tools(tmp_path)
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "error" not in out
    assert "stats_validation_warnings" not in out
    assert store.load()["contextStore"].get("analysis_results") is not None


def test_gate_blocks_impossible_and_store_unchanged(tmp_path):
    store, tools = _tools(tmp_path)
    bad = copy.deepcopy(_GOOD_M4)
    bad["hypothesis_tests"][0]["numbers"]["p"] = 0.48  # with t=7.01
    out = _commit(tools, {"analysis_results": bad})
    assert out["error"].startswith("stats_validation_failed")
    assert any(f["check"] == "consistency.t_p" for f in out["findings"])
    assert store.load()["contextStore"].get("analysis_results") is None  # unchanged


def test_gate_soft_only_commits_with_warnings(tmp_path):
    store, tools = _tools(tmp_path)
    soft = copy.deepcopy(_GOOD_M4)
    soft["measurement_model"][0]["cronbach_alpha"] = 0.99  # suspiciously perfect (soft)
    out = _commit(tools, {"analysis_results": soft})
    assert "error" not in out
    assert out["stats_validation_warnings"]
    assert store.load()["contextStore"].get("analysis_results") is not None


def test_gate_ignores_non_m4_and_m4_without_results(tmp_path):
    store, tools = _tools(tmp_path)
    # M4 commit without analysis_results is untouched by the gate.
    out = _commit(tools, {"analysis_outline": {"steps": []}})
    assert "error" not in out and "stats_validation" not in out


def test_gate_fail_open_on_validator_crash(tmp_path, monkeypatch):
    store, tools = _tools(tmp_path)
    import agent.stats_validation as sv
    monkeypatch.setattr(sv, "validate_analysis_results",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "error" not in out
    assert out.get("stats_validation") == "unavailable"
    assert store.load()["contextStore"].get("analysis_results") is not None


def test_gate_x2_hypothesis_coverage_soft(tmp_path):
    store, tools = _tools(tmp_path)
    # Seed M3 hypotheses so X2 can run; H3 has no result -> soft warning, commit ok.
    tools["commit_slice"].func(module="M3", writes={"hypotheses": [{"id": "H1"}, {"id": "H3"}]}, reason="seed")
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "error" not in out
    warnings = out.get("stats_validation_warnings") or []
    assert any(f["check"] == "xtable.hypothesis_coverage" for f in warnings)
