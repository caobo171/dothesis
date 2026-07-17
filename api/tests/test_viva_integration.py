"""Viva simulation end-to-end through the REAL score_thesis (judge stubbed).

Offline: the only LLM in score_thesis is the judge dims, stubbed here exactly as
test_defense.py does. Asserts the core contract — every rubric `blocking` entry
becomes a must_fix question, the power signal carries the achieved/required n,
readiness reflects the blockers, and a clean thesis drills only the staples.
"""
import copy
import json

import pytest

from agent.viva import generate_viva


@pytest.fixture(autouse=True)
def _stub_judge(monkeypatch):
    import orchestrator.tools.m5_writing as _m5

    class _Resp:
        content = '{"score": 0.9, "findings": []}'
    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())


DIRTY_STORE = {
    "m1_topic": {"target_population": "SME managers"},
    "m2_literature": {"literature_sources": [{"title": "Real", "authors": "A", "year": 2020}]},
    "m3_design": {"methodology": "PLS-SEM",
                  "sample_plan": {"target_n": 160,
                                  "power_analysis": {"required_n": 160,
                                                     "justification": "Kock & Hadaya (2018)"}}},
    "m4_analysis": {"analysis_results": {
        "descriptives": {"n": 95},
        "measurement_model": [{"construct": "X",
                               "items": [{"item": "x1", "loading": 0.9}, {"item": "x2", "loading": 0.9}],
                               "ave": 0.20}],
        "hypothesis_tests": [{"id": "H2", "path": "X->Y", "decision": "not supported",
                              "numbers": {"beta": 0.34, "p": 0.4}}]}},
    "m5_writing": {"final_sections": [{"title": "results",
        "prose": "H2 was supported with a strong effect (beta = .45) per (Ghost, 2099), "
                 "confirming the hypothesis clearly with adequate detail here."}]},
}


def _score(cs):
    from quality.rubric import score_thesis
    return score_thesis(cs)


def test_dirty_thesis_every_blocking_becomes_must_fix():
    rubric = _score(DIRTY_STORE)
    assert rubric["blocking"], "fixture should trigger hard findings"
    env = generate_viva(DIRTY_STORE, rubric)

    must_fix_issues = {q["grounding"]["issue"] for q in env["questions"]
                       if q["defensibility"] == "must_fix"}
    for blocking_issue in rubric["blocking"]:
        assert blocking_issue in must_fix_issues, f"unmatched blocking: {blocking_issue}"

    assert env["readiness"]["verdict"] == "not_ready"
    # the power signal (n=95 < required 160) rides as a disclosable question
    power = [q for q in env["questions"] if q["grounding"]["source"] == "state:power"]
    assert power and "95" in power[0]["model_answer_hint"] and "160" in power[0]["model_answer_hint"]
    # count consistency: must_fix == number of hard-grounded questions
    hard_q = sum(1 for q in env["questions"] if q["grounding"].get("severity") == "hard")
    assert env["readiness"]["must_fix"] == hard_q


def test_dirty_thesis_determinism():
    rubric = _score(DIRTY_STORE)
    a = generate_viva(copy.deepcopy(DIRTY_STORE), copy.deepcopy(rubric))
    b = generate_viva(copy.deepcopy(DIRTY_STORE), copy.deepcopy(rubric))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


CLEAN_STORE = {
    "m1_topic": {"research_title": "A Study of X on Y", "research_questions": ["RQ1"],
                 "target_population": "SME managers"},
    "m2_literature": {"literature_sources": [{"title": "Real", "authors": "A", "year": 2020,
                                              "doi": "10.1/x"}]},
    "m3_design": {"methodology": "PLS-SEM",
                  "sample_plan": {"target_n": 200,
                                  "power_analysis": {"required_n": 160, "justification": "Kock & Hadaya"}}},
    "m4_analysis": {"analysis_results": {
        "descriptives": {"n": 220},
        "measurement_model": [{"construct": "X",
                               "items": [{"item": "x1", "loading": 0.9}, {"item": "x2", "loading": 0.9}],
                               "ave": 0.81}],
        "hypothesis_tests": [{"id": "H1", "path": "X->Y", "decision": "supported",
                              "numbers": {"beta": 0.45, "p": 0.001}}]}},
}


def test_clean_thesis_ready_staples_only():
    rubric = _score(CLEAN_STORE)
    env = generate_viva(CLEAN_STORE, rubric)
    # no must_fix; the four staples always present
    assert env["readiness"]["must_fix"] == 0
    staples = [q for q in env["questions"] if q["grounding"]["source"] == "staple"]
    assert len(staples) == 4
    assert env["readiness"]["verdict"] in ("ready", "ready_with_disclosures")
