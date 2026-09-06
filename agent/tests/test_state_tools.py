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


# --- Phase 5: M5 coherence gate ---------------------------------------------

_M3_COH = {"hypotheses": ["H1: LS positively affects PI"],
           "conceptual_model": {"nodes": [{"id": "n1", "label": "LS"}, {"id": "n2", "label": "PI"}],
                                "edges": [{"id": "H1", "source": "n1", "target": "n2", "effect_type": "positive"}]}}
_M4_COH = {"hypothesis_tests": [{"id": "r-H1", "hypothesis": "H1", "path": "LS -> PI",
                                "numbers": {"beta": 0.3391, "p": "<0.001"}, "decision": "supported"}]}


def _coh_store(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{_uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    tools["commit_slice"].func(module="M3", writes=_M3_COH, reason="seed")
    tools["commit_slice"].func(module="M4", writes={"analysis_results": copy.deepcopy(_M4_COH)}, reason="seed")
    return store, tools


def _m5(tools, results):
    return json.loads(tools["commit_slice"].func(module="M5",
        writes={"final_sections": {"results": results,
                                   "discussion": "Hypothesis H1 is discussed thoroughly here. " * 3}},
        reason="write"))


def test_m5_gate_clean_commit(tmp_path):
    store, tools = _coh_store(tmp_path)
    out = _m5(tools, "Hypothesis H1 was supported (β = .34, p < .001) in the analysis.")
    assert "error" not in out and "coherence_warnings" not in out


def test_m5_gate_blocks_number_mismatch(tmp_path):
    store, tools = _coh_store(tmp_path)
    out = _m5(tools, "Hypothesis H1 was supported (β = .55, p < .001) in the analysis.")
    assert out["error"].startswith("coherence_failed")
    assert store.load()["contextStore"].get("final_sections") is None  # unchanged


def test_m5_gate_soft_decision_commits_with_warning(tmp_path):
    store, tools = _coh_store(tmp_path)
    out = _m5(tools, "Hypothesis H1 was not supported by the study, contrary to expectation here.")
    assert "error" not in out
    assert any(f["check"] == "coherence.decision_prose" for f in out.get("coherence_warnings", []))


def test_m5_gate_no_analysis_results_passes(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{_uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}
    tools["commit_slice"].func(module="M3", writes=_M3_COH, reason="seed")
    out = _m5(tools, "Hypothesis H1 will be examined (β = .34).")
    assert "error" not in out


# --- boundary hardening (gap 2): strict gate policy for headless/B2B ---------

def _strict_tools(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{_uuid.uuid4().hex}")
    return store, {t.name: t for t in make_state_tools(store, strict_gates=True)}


def test_strict_gate_refuses_commit_on_validator_crash(tmp_path, monkeypatch):
    store, tools = _strict_tools(tmp_path)
    import agent.stats_validation as sv
    monkeypatch.setattr(sv, "validate_analysis_results",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert out["error"].startswith("stats_gate_unavailable")
    assert store.load()["contextStore"].get("analysis_results") is None


def test_strict_gate_refuses_on_crashed_flag(tmp_path, monkeypatch):
    store, tools = _strict_tools(tmp_path)
    import agent.stats_validation as sv
    monkeypatch.setattr(sv, "validate_analysis_results",
                        lambda *a, **k: {"crashed": True, "hard": 0, "soft": 0,
                                         "findings": [], "findings_hard": [], "findings_soft": []})
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert out["error"].startswith("stats_gate_unavailable")


def test_strict_gate_refuses_m5_commit_on_coherence_crash(tmp_path, monkeypatch):
    store, tools = _strict_tools(tmp_path)
    tools["commit_slice"].func(module="M3", writes=copy.deepcopy(_M3_COH), reason="seed")
    tools["commit_slice"].func(module="M4", writes={"analysis_results": copy.deepcopy(_M4_COH)}, reason="seed")
    import agent.coherence as coh
    monkeypatch.setattr(coh, "validate_m5_sections",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    out = json.loads(tools["commit_slice"].func(
        module="M5", writes={"final_sections": {"results": "H1 supported (β = .34).", "discussion": "x" * 40}},
        reason="test"))
    assert out["error"].startswith("coherence_gate_unavailable")


def test_strict_gate_clean_and_hard_paths_unchanged(tmp_path):
    # strictness only changes the cannot-run branch: clean commits still succeed,
    # hard findings still return stats_validation_failed.
    store, tools = _strict_tools(tmp_path)
    assert "error" not in _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    bad = copy.deepcopy(_GOOD_M4)
    bad["measurement_model"][0]["ave"] = 1.4   # impossible
    out = _commit(tools, {"analysis_results": bad})
    assert out["error"].startswith("stats_validation_failed")


def test_provenance_records_gate_ran(tmp_path):
    store, tools = _tools(tmp_path)   # advisory (default)
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "error" not in out
    prov = store.load()["contextStore"]["analysis_provenance"]
    assert prov["gate"] == {"stats_validation": "ran", "policy": "advisory"}


def test_strict_provenance_records_strict_policy(tmp_path):
    store, tools = _strict_tools(tmp_path)
    _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    prov = store.load()["contextStore"]["analysis_provenance"]
    assert prov["gate"]["policy"] == "strict" and prov["gate"]["stats_validation"] == "ran"


# --- boundary hardening (gap 3): skill-read nudge at the commit gate ---------

def test_first_commit_without_skill_read_is_reminded_not_refused(tmp_path):
    """The commit LANDS and carries an internal reminder.

    It used to be refused with a `module_skill_not_read` error and the model was
    expected to read the skill and silently retry. It didn't: it reported the
    error and asked the student to press the confirm button a second time. The
    nudge also fires on the first COMMIT, when the work is already written, so
    blocking it cannot improve what is being committed — only what comes next.
    """
    import agent.skill_tracker as skt
    store, tools = _tools(tmp_path)
    skt.reset(); skt.arm(store.project_dir)          # simulate the agent's skill channel
    out = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "error" not in out
    assert "dothesis-m4-analysis" in out["skill_reminder"]
    assert "do not mention it to the student" in out["skill_reminder"]
    # The work is committed, not discarded.
    assert store.load()["contextStore"].get("analysis_results") is not None
    # Once only — a reminder on every commit is noise the model would start
    # reporting for the same reason it reported the error.
    out2 = _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})
    assert "skill_reminder" not in out2


def test_commit_after_skill_read_passes_first_time(tmp_path):
    import agent.skill_tracker as skt
    store, tools = _tools(tmp_path)
    skt.reset(); skt.arm(store.project_dir)
    skt.note_read(store.project_dir, "/skills/dothesis-m4-analysis/SKILL.md")
    assert "error" not in _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})


def test_unarmed_project_not_nudged(tmp_path):
    import agent.skill_tracker as skt
    store, tools = _tools(tmp_path)
    skt.reset()                                      # not armed → no nudge (test posture)
    assert "error" not in _commit(tools, {"analysis_results": copy.deepcopy(_GOOD_M4)})


# --- "done" has to mean the work happened ----------------------------------
#
# From a real 27-minute run that reported success: M4 wrote
#   analysis_results = [{"status": "not_run", "reason": "No real dataset …"}]
# committed itself with confirm_done=True, and the student was shown "Your
# thesis is ready" over an empty Results chapter and two untested hypotheses.
#
# Every M4 gate checks whether numbers CONTRADICT each other, so an analysis
# with no numbers passed all of them unchallenged, and the DoD that would have
# caught it was advisory: it attached `done_but_incomplete` to the payload and
# marked the module done anyway.

_NOT_RUN = [{"status": "not_run",
             "reason": "No real dataset or validated SPSS/SmartPLS output is available."}]


def _done_commit(tools, **kw):
    return json.loads(tools["commit_slice"].func(**kw))


def test_an_unattended_run_cannot_mark_a_module_done_on_no_results(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store, strict_gates=True)}

    out = _done_commit(tools, module="M4", writes={"analysis_results": _NOT_RUN},
                  reason="analysis could not run", confirm_done=True)

    assert store.load()["status"]["M4"] != "done"
    assert out.get("done_refused"), out


def test_the_refusal_names_what_is_missing(tmp_path):
    """The agent has to be able to act on it, and the student has to be able to
    read it — "incomplete" on its own is not a next step."""
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store, strict_gates=True)}

    out = _done_commit(tools, module="M4", writes={"analysis_results": _NOT_RUN},
                  reason="x", confirm_done=True)

    assert out["done_refused"], out
    assert any("results" in g or "data_type_detected" in g for g in out["done_refused"])


def test_the_work_is_still_saved_when_the_done_is_refused(tmp_path):
    """Refusing the claim must not throw away the turn: the agent spent real
    money producing this, and losing it guarantees it gets produced again."""
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store, strict_gates=True)}

    _done_commit(tools, module="M4", writes={"analysis_results": _NOT_RUN},
            reason="x", confirm_done=True)

    cs = store.load()["contextStore"]
    assert cs["analysis_results"] == _NOT_RUN
    assert store.load()["status"]["M4"] == "in_progress"


def test_a_complete_module_still_goes_done_in_an_unattended_run(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store, strict_gates=True)}

    out = _done_commit(tools, module="M4", reason="analysis complete", confirm_done=True,
                  writes={
                      "data_type_detected": "Quantitative",
                      "analysis_outline": [{"step": "reliability"}],
                      "results": {"cronbach_alpha": {"AA": 0.827}},
                      "analysis_results": [{"hypothesis": "H1", "supported": True,
                                            "beta": 0.412, "p": 0.003}],
                  })

    assert store.load()["status"]["M4"] == "done"
    assert "done_refused" not in out


def test_interactive_chat_is_not_tightened(tmp_path):
    """Deliberate asymmetry. A student working through M4 in chat commits as
    they go, and blocking that would stall them mid-flow — the advisory note is
    the right call there. It is an UNATTENDED run that must never report a done
    nobody can see is hollow."""
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {t.name: t for t in make_state_tools(store)}   # strict_gates=False

    out = _done_commit(tools, module="M4", writes={"analysis_results": _NOT_RUN},
                  reason="x", confirm_done=True)

    assert store.load()["status"]["M4"] == "done"
    assert out.get("done_but_incomplete")
