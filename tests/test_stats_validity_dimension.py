"""Phase 8: the stats_validity rubric dimension (correctness of the numbers)."""
import copy

import pytest

pytest.importorskip("thesis_stats")

from quality import rubric
from quality.rubric import score_thesis, stats_validity_dimension

GOOD = {
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


def test_clean_scores_one_no_findings():
    d = stats_validity_dimension({"m4_analysis": {"analysis_results": copy.deepcopy(GOOD)}})
    assert d["name"] == "stats_validity" and d["weight"] == 0.15
    assert d["score"] == 1.0 and d["findings"] == []


def test_impossible_number_is_hard_and_lowers_score():
    bad = copy.deepcopy(GOOD)
    bad["hypothesis_tests"][0]["numbers"]["p"] = 0.48  # with t=7.01
    d = stats_validity_dimension({"m4_analysis": {"analysis_results": bad}})
    assert any(f["severity"] == "hard" for f in d["findings"])
    assert d["score"] <= 0.5


def test_free_text_results_soft_no_crash():
    d = stats_validity_dimension({"m4_analysis": {"analysis_results": "all hypotheses supported"}})
    assert all(f["severity"] == "soft" for f in d["findings"])
    assert d["score"] >= 0.8


def test_missing_m4_scores_one():
    d = stats_validity_dimension({})
    assert d["score"] == 1.0 and d["findings"] == []


def test_orchestrator_results_shape():
    cs = {"m4_analysis": {"results": {"s1": {"data_type": "loadings",
                                             "table": [{"item": "X1", "loading": 1.4}]}}}}
    d = stats_validity_dimension(cs)
    assert any(f["severity"] == "hard" for f in d["findings"])


def test_score_thesis_hard_finding_lands_in_blocking(monkeypatch):
    # Stub the LLM judge so this stays offline + fast.
    monkeypatch.setattr(rubric, "judge_dimension",
                        lambda name, weight, prompt, cs: {"name": name, "weight": weight,
                                                          "score": 0.6, "findings": []})
    bad = copy.deepcopy(GOOD)
    bad["hypothesis_tests"][0]["numbers"]["p"] = 0.48
    out = score_thesis({"m4_analysis": {"analysis_results": bad}})
    assert 0.0 <= out["overall"] <= 1.0
    assert any("t=7.01" in b or "7.01" in b for b in out["blocking"])
