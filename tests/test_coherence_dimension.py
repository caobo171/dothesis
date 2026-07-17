"""Coherence rubric dimension + score_thesis blocking wiring (roadmap #6)."""
import copy

import pytest

from quality import rubric
from quality.rubric import coherence_dimension, score_thesis

M3 = {"hypotheses": ["H1: LS has a positive effect on PI"],
      "conceptual_model": {"nodes": [{"id": "n1", "label": "LS"}, {"id": "n2", "label": "PI"}],
                           "edges": [{"id": "H1", "source": "n1", "target": "n2",
                                      "effect_type": "positive"}]}}
M4 = {"analysis_results": {"hypothesis_tests": [
    {"id": "r-H1", "hypothesis": "H1", "path": "LS -> PI",
     "numbers": {"beta": 0.3391, "p": "<0.001"}, "decision": "supported"}]}}


def _store(results_prose):
    return {"m3_design": copy.deepcopy(M3), "m4_analysis": copy.deepcopy(M4),
            "m5_writing": {"chapters": {"results": {"prose": results_prose},
                                        "discussion": {"prose": "Hypothesis H1 is discussed in depth here " * 3}}}}


def test_clean_coherence_scores_one():
    d = coherence_dimension(_store("Hypothesis H1 was supported (β = .34, p < .001) in the model."))
    assert d["name"] == "coherence" and d["weight"] == 0.10
    assert d["score"] == 1.0 and d["findings"] == []


def test_number_mismatch_is_hard():
    d = coherence_dimension(_store("Hypothesis H1 was supported (β = .55, p < .001) in the model."))
    assert any(f["severity"] == "hard" for f in d["findings"])
    assert d["score"] <= 0.5


def test_decision_prose_mismatch_soft():
    d = coherence_dimension(_store("Hypothesis H1 was not supported by the analysis here, sadly."))
    assert d["findings"] and all(f["severity"] == "soft" for f in d["findings"])
    assert d["score"] >= 0.8


def test_missing_m5_no_crash():
    assert coherence_dimension({"m3_design": M3, "m4_analysis": M4})["score"] == 1.0
    assert coherence_dimension({})["score"] == 1.0


def test_score_thesis_hard_coherence_blocks(monkeypatch):
    monkeypatch.setattr(rubric, "judge_dimension",
                        lambda name, weight, prompt, cs: {"name": name, "weight": weight,
                                                          "score": 0.6, "findings": []})
    out = score_thesis(_store("Hypothesis H1 was supported (β = .55, p < .001) in the model."))
    names = {d["name"] for d in out["dimensions"]}
    assert "coherence" in names
    assert 0.0 <= out["overall"] <= 1.0
    assert any("β = .55" in b or "0.3391" in b for b in out["blocking"])
