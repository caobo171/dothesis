import pytest

from quality.rubric import score_thesis, deterministic_dimensions
from quality.rubric import results_validity_dimension, apply_institution_overlay, METHOD_CRITERIA


@pytest.fixture(autouse=True)
def _stub_judge_llm(monkeypatch):
    # F0: no test may hit a live model. score_thesis fires the LLM-judge dims,
    # so stub _get_llm module-wide with a benign valid-JSON response. The two
    # judge_dimension tests re-monkeypatch it in their own bodies (that wins).
    import orchestrator.tools.m5_writing as _m5

    class _Resp:
        content = '{"score": 0.7, "findings": []}'

    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())


_GOOD = {
    "m1_topic": {"research_title": "T", "research_questions": ["Q"]},
    "m2_literature": {"literature_sources": [{"title": "P", "authors": ["Smith"], "year": 2020}]},
    "m3_design": {"methodology": "PLS-SEM", "conceptual_model": {"nodes": []}, "hypotheses": ["H1"]},
    "m4_analysis": {"analysis_results": "AVE=0.62, HTMT ok, R2=.41, p<.05"},
    "m5_writing": {"final_sections": [{"title": "Results", "prose": "Real interpreted results. " * 20}]},
}


def test_structure_dimension_flags_missing_module():
    dims = {d["name"]: d for d in deterministic_dimensions({"m1_topic": {}})}
    assert dims["structure"]["score"] < 1.0
    assert any("M1" in f["issue"] for f in dims["structure"]["findings"])


def test_citation_integrity_flags_uncited():
    cs = {**_GOOD, "m5_writing": {"final_sections": [
        {"title": "Intro", "prose": "As shown (Ghost, 2099) this matters."}]}}
    dims = {d["name"]: d for d in deterministic_dimensions(cs)}
    assert any("Ghost" in f["issue"] for f in dims["citations"]["findings"])


def test_score_thesis_returns_overall_and_shape():
    r = score_thesis(_GOOD)
    assert 0.0 <= r["overall"] <= 1.0
    assert r["method"] and isinstance(r["dimensions"], list)
    assert r["advisor"] == {"total": 0, "addressed": 0, "open": []}


def test_pls_results_dimension_flags_missing_htmt():
    cs = {"m4_analysis": {"analysis_results": "AVE=0.6 CR=0.8 R2=0.4 p<.05"}}  # no HTMT
    d = results_validity_dimension(cs, "pls-sem")
    assert any("htmt" in f["issue"].lower() for f in d["findings"])


def test_spss_uses_different_criteria():
    assert set(METHOD_CRITERIA["spss"]) != set(METHOD_CRITERIA["pls-sem"])


def test_institution_min_references_adds_hard_finding():
    dims = [{"name": "citations", "weight": 0.2, "score": 1.0, "findings": []}]
    cs = {"m2_literature": {"literature_sources": [{"title": "a"}] * 12}}
    out = apply_institution_overlay(dims, {"min_references": 30}, cs)
    assert any("30" in f["issue"] for d in out for f in d["findings"])


import orchestrator.tools.m5_writing as m5
from quality.rubric import judge_dimension


def test_judge_dimension_parses_llm_json(monkeypatch):
    class _Resp:
        content = '{"score": 0.4, "findings": [{"issue": "H1 has no gap", ' \
                  '"fix": "Trace H1 to a gap", "chapter": "methodology", "severity": "soft"}]}'
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())
    d = judge_dimension("methodology", 0.15, "prompt", {})
    assert d["score"] == 0.4 and d["findings"][0]["issue"].startswith("H1")


def test_judge_dimension_survives_bad_json(monkeypatch):
    class _Resp:
        content = "not json at all"
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())
    d = judge_dimension("writing", 0.10, "prompt", {})
    assert 0.0 <= d["score"] <= 1.0
    assert any("could not evaluate" in f["issue"].lower() for f in d["findings"])


def test_preflight_dimension_flags_missing_design_items():
    # A thesis whose M3 design skipped the pre-flight items (sample/CMB/missing-
    # data plans) scores below 1.0 on the preflight dimension and surfaces the
    # gaps as soft findings — advisory, never blocking (F8 Task 3).
    from quality.rubric import preflight_dimension
    d = preflight_dimension(_GOOD)  # _GOOD's m3_design has no sample_plan/cmb_plan
    assert d["name"] == "preflight"
    assert d["score"] < 1.0
    assert d["findings"] and all(f["severity"] == "soft" for f in d["findings"])


def test_preflight_dimension_clean_when_ready():
    from quality.rubric import preflight_dimension
    cs = {"m3_design": {"methodology": "PLS-SEM",
                        "instrument": {"items": [{"reverse_coded": True}]},
                        "sample_plan": {"target_n": 200,
                                        "power_analysis": {"required_n": 160,
                                                           "justification": "Kock & Hadaya (2018)"}},
                        "cmb_plan": "Harman", "missing_data_plan": "listwise"}}
    d = preflight_dimension(cs)
    assert d["score"] == 1.0 and d["findings"] == []


def test_score_thesis_includes_preflight_dimension():
    r = score_thesis(_GOOD)
    assert any(d["name"] == "preflight" for d in r["dimensions"])


def test_instrument_quality_dimension_flags_double_barreled(monkeypatch):
    # A questionnaire with a double-barreled item and no reverse-coded/attention
    # coverage scores below 1.0 on the instrument_quality dimension, all soft
    # (F7 Task 1) — same lint the live audit_instrument tool runs.
    from quality.rubric import instrument_quality_dimension
    cs = {"m3_design": {"instrument": {"items": [
        {"id": "q1", "text": "The app is fast and reliable", "construct": "PE"}]}}}
    d = instrument_quality_dimension(cs)
    assert d["name"] == "instrument_quality"
    assert d["score"] < 1.0
    assert d["findings"] and all(f["severity"] == "soft" for f in d["findings"])
    assert any("double" in f["issue"].lower() for f in d["findings"])


def test_score_thesis_includes_instrument_quality_dimension():
    r = score_thesis(_GOOD)
    assert any(d["name"] == "instrument_quality" for d in r["dimensions"])


def test_open_advisor_directive_is_hard_finding():
    fb = [{"id": "1", "chapter": "results", "issue": "Report effect sizes",
           "required_change": "add Cohen's f2", "status": "open"},
          {"id": "2", "chapter": "intro", "issue": "narrow the scope",
           "required_change": "...", "status": "addressed"}]
    r = score_thesis(_GOOD, advisor_feedback=fb)
    assert r["advisor"] == {"total": 2, "addressed": 1, "open": [fb[0]]}
    adv = next(d for d in r["dimensions"] if d["name"] == "advisor")
    assert any(f["severity"] == "hard" and "effect sizes" in f["issue"] for f in adv["findings"])
