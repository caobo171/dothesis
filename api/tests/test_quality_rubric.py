from quality.rubric import score_thesis, deterministic_dimensions
from quality.rubric import results_validity_dimension, apply_institution_overlay, METHOD_CRITERIA

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
