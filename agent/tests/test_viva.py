"""Rubric-grounded viva simulation (roadmap #10) — pure, deterministic, offline."""
import copy
import json
import random

import pytest

from agent.viva import (
    generate_viva, readiness, rubric_questions, state_signal_questions,
)


def _rubric(dims):
    """dims: [(name, [(issue, severity, fix, chapter)])]  → rubric_result shape."""
    return {"overall": 0.5, "method": "pls-sem", "blocking": [],
            "dimensions": [{"name": n, "score": 0.5, "weight": 1.0,
                            "findings": [{"issue": i, "severity": s, "fix": f, "chapter": c}
                                         for (i, s, f, c) in fs]}
                           for n, fs in dims]}


# --- Task 1.1: rubric mapping -----------------------------------------------

def test_rubric_question_per_dimension():
    r = _rubric([
        ("coherence", [("β mismatch H2", "hard", "reconcile the numbers", "results")]),
        ("similarity", [("passage overlaps a source", "soft", "quote and cite", "lit_review")]),
    ])
    qs = rubric_questions(r)
    assert len(qs) == 2
    coh = next(q for q in qs if q["category"] == "coherence")
    assert coh["difficulty"] == "hard" and coh["defensibility"] == "must_fix"
    assert "reconcile the numbers" in coh["model_answer_hint"]      # fix verbatim
    assert "β mismatch H2" in coh["question"]
    assert coh["grounding"] == {"source": "rubric:coherence", "severity": "hard",
                                "issue": "β mismatch H2", "chapter": "results", "values": None}
    assert 2 <= len(coh["answer_criteria"]) <= 4
    sim = next(q for q in qs if q["category"] == "similarity")
    assert sim["difficulty"] == "medium" and sim["defensibility"] == "disclosable"


def test_unknown_dimension_generic_fallback():
    qs = rubric_questions(_rubric([("future_dim", [("weird thing", "soft", "fix it", "-")])]))
    assert len(qs) == 1 and "weird thing" in qs[0]["question"]


def test_judge_placeholder_skipped():
    qs = rubric_questions(_rubric([("structure", [
        ("Could not evaluate writing automatically.", "soft", "-", "-")])]))
    assert qs == []


def test_cap_and_dedup():
    dup = _rubric([("citations", [("same issue", "hard", "add ref", "-")] * 30)])
    assert len(rubric_questions(dup)) == 1  # dedup on (dim, issue)
    distinct = _rubric([("citations", [(f"issue {i}", "hard", "add ref", "-") for i in range(5)])])
    assert len(rubric_questions(distinct)) == 3  # per-dim cap


def test_missing_fix_chapter_still_emits():
    r = {"dimensions": [{"name": "citations", "findings": [{"issue": "x", "severity": "hard"}]}]}
    qs = rubric_questions(r)
    assert len(qs) == 1 and qs[0]["grounding"]["chapter"] is None


def test_import_purity_no_langchain_quality():
    import subprocess, sys
    code = ("import sys; import agent.viva; "
            "assert 'langchain' not in sys.modules and 'quality' not in sys.modules; "
            "print('ok')")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0 and "ok" in r.stdout, r.stderr


# --- Task 1.2: state-direct signals -----------------------------------------

def _cs(**kw):
    return kw


def test_power_shortfall_hard_with_grounded_hint():
    cs = {"m3_design": {"sample_plan": {"target_n": 160, "power_analysis": {
              "required_n": 160, "justification": "inverse square root (Kock & Hadaya, 2018)"}}},
          "m4_analysis": {"analysis_results": {"descriptives": {"n": 95}}}}
    qs = [q for q in state_signal_questions(cs) if q["grounding"]["source"] == "state:power"]
    assert len(qs) == 1
    q = qs[0]
    assert q["difficulty"] == "hard" and q["defensibility"] == "disclosable"
    assert "95" in q["model_answer_hint"] and "160" in q["model_answer_hint"]
    assert "Kock & Hadaya" in q["model_answer_hint"]
    assert q["grounding"]["values"] == {"n_achieved": 95, "required_n": 160}


def test_power_shortfall_small_is_medium():
    cs = {"m3_design": {"sample_plan": {"power_analysis": {"required_n": 160}}},
          "m4_analysis": {"analysis_results": {"descriptives": {"n": 150}}}}
    q = next(q for q in state_signal_questions(cs) if q["grounding"]["source"] == "state:power")
    assert q["difficulty"] == "medium"


def test_recommended_n_beats_required_n():
    cs = {"m3_design": {"sample_plan": {"power_analysis": {"required_n": 100, "recommended_n": 160}}},
          "m4_analysis": {"analysis_results": {"descriptives": {"n": 95}}}}
    q = next(q for q in state_signal_questions(cs) if q["grounding"]["source"] == "state:power")
    assert q["grounding"]["values"]["required_n"] == 160


def test_legacy_small_n_mutually_exclusive():
    cs = {"m3_design": {"sample_plan": {"target_n": 90}}}
    power = [q for q in state_signal_questions(cs)
             if q["grounding"]["source"] in ("state:power", "state:sample_size")]
    assert len(power) == 1 and power[0]["grounding"]["source"] == "state:sample_size"


def test_not_supported_hypotheses():
    cs = {"m4_analysis": {"analysis_results": {"hypothesis_tests": [
        {"id": "H1", "path": "A->B", "decision": "supported", "numbers": {"beta": 0.3, "p": 0.01}},
        {"id": "H2", "path": "C->D", "decision": "not supported", "numbers": {"beta": 0.05, "p": 0.4}},
        {"id": "H3", "path": "E->F", "decision": "Rejected", "numbers": {}}]}}}
    qs = [q for q in state_signal_questions(cs) if q["grounding"]["source"] == "state:hypothesis"]
    assert len(qs) == 2
    assert all(q["difficulty"] == "hard" and q["defensibility"] == "disclosable" for q in qs)
    h2 = next(q for q in qs if "H2" in q["question"])
    assert "0.05" in h2["question"] and "0.4" in h2["question"]


def test_legacy_string_results():
    cs = {"m4_analysis": {"analysis_results": "H1 not supported (p=0.21)"}}
    qs = [q for q in state_signal_questions(cs) if q["grounding"]["source"] == "state:hypothesis"]
    assert len(qs) == 1


def test_field_quality_flag():
    cs = {"m4_analysis": {"field_it_quality": [{"x": 1}, {"y": 2}]}}
    q = next(q for q in state_signal_questions(cs) if q["category"] == "data_quality")
    assert "2" in q["question"] and q["grounding"]["values"]["flag_count"] == 2


def test_staples_always_four():
    qs = state_signal_questions({})
    staples = [q for q in qs if q["grounding"]["source"] == "staple"]
    assert len(staples) == 4
    assert {q["category"] for q in staples} == {
        "contribution", "methodology", "limitations", "generalizability"}
    assert all(q["defensibility"] == "standard" for q in staples)


def test_generalizability_interpolates_population():
    cs = {"m1_topic": {"target_population": "SME managers in Hanoi"}}
    gen = next(q for q in state_signal_questions(cs) if q["category"] == "generalizability")
    assert "SME managers in Hanoi" in gen["question"]


# --- Task 1.3: envelope -----------------------------------------------------

def test_envelope_shape_and_ordering():
    r = _rubric([("coherence", [("m1", "hard", "fix1", "results")]),
                 ("similarity", [("s1", "soft", "fix2", "lit")])])
    cs = {"m4_analysis": {"analysis_results": {"hypothesis_tests": [
        {"id": "H2", "path": "C->D", "decision": "not supported", "numbers": {}}]}}}
    env = generate_viva(cs, r)
    defs = [q["defensibility"] for q in env["questions"]]
    assert defs == sorted(defs, key=lambda d: {"must_fix": 0, "disclosable": 1, "standard": 2}[d])
    assert all(q["id"] for q in env["questions"])
    assert env["meta"]["rubric_available"] is True and env["meta"]["method"] == "pls-sem"
    assert env["meta"]["generator"] == "viva-v2-deterministic"


def test_readiness_verdicts():
    r = _rubric([("coherence", [("m1", "hard", "f", "-"), ("m2", "hard", "f", "-")]),
                 ("similarity", [("s1", "soft", "f", "-"), ("s2", "soft", "f", "-"),
                                 ("s3", "soft", "f", "-")])])
    env = generate_viva({}, r)
    assert env["readiness"]["verdict"] == "not_ready" and env["readiness"]["must_fix"] == 2
    # staples only → ready
    assert generate_viva({})["readiness"]["verdict"] == "ready"
    # soft only → ready_with_disclosures
    env2 = generate_viva({}, _rubric([("similarity", [("s", "soft", "f", "-")])]))
    assert env2["readiness"]["verdict"] == "ready_with_disclosures"


def test_by_dimension_counts_all_findings_beyond_cap():
    r = _rubric([("citations", [(f"i{n}", "hard", "f", "-") for n in range(30)])])
    env = generate_viva({}, r)
    assert env["readiness"]["by_dimension"]["citations"] == 30
    assert sum(1 for q in env["questions"] if q["category"] == "citations") <= 3


def test_determinism():
    r = _rubric([("coherence", [("m1", "hard", "f", "-")]),
                 ("similarity", [("s1", "soft", "f", "-")])])
    cs = {"m3_design": {"sample_plan": {"power_analysis": {"required_n": 160}}},
          "m4_analysis": {"analysis_results": {"descriptives": {"n": 95}}}}
    a = generate_viva(copy.deepcopy(cs), copy.deepcopy(r))
    b = generate_viva(copy.deepcopy(cs), copy.deepcopy(r))
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# --- Task 2.1: never-crash --------------------------------------------------

@pytest.mark.parametrize("cs", [
    {}, None,
    {"m3_design": "oops", "m4_analysis": {"analysis_results": 42, "field_it_quality": "nope"}},
    {"m3_design": {"sample_plan": {"power_analysis": {"required_n": "many"}}}},
])
def test_never_crash(cs):
    env = generate_viva(cs)
    assert len(env["questions"]) >= 4 and env["readiness"]["verdict"] == "ready"


def test_malformed_rubric_degrades():
    env = generate_viva({}, {"dimensions": "x"})
    assert env["meta"]["rubric_available"] is False
    assert all(q["grounding"]["source"] == "staple" for q in env["questions"])


# --- Task 2.2: never-fabricate property -------------------------------------

def test_never_fabricate_property():
    rng = random.Random(0)
    dim_names = list(__import__("agent.viva", fromlist=["_DIM_TEMPLATES"])._DIM_TEMPLATES)
    for _ in range(50):
        dims = []
        input_issues = set()
        for name in rng.sample(dim_names, rng.randint(0, len(dim_names))):
            fs = []
            for k in range(rng.randint(0, 4)):
                issue = f"{name}-issue-{k}-{rng.random():.3f}"
                input_issues.add(issue)
                fs.append((issue, rng.choice(["hard", "soft"]), "fix", "-"))
            dims.append((name, fs))
        r = _rubric(dims)
        n = rng.choice([50, 95, 150, 200])
        cs = {"m3_design": {"sample_plan": {"power_analysis": {"required_n": 160}}},
              "m4_analysis": {"analysis_results": {"descriptives": {"n": n}}}}
        env = generate_viva(cs, r)
        for q in env["questions"]:
            src = q["grounding"]["source"]
            if src.startswith("rubric:"):
                assert q["grounding"]["issue"] in input_issues
            elif src == "state:power":
                assert q["grounding"]["values"]["n_achieved"] == n
                assert q["grounding"]["values"]["required_n"] == 160
