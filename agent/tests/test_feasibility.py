"""M1 topic feasibility (vision §3.1) — pure sample-size + operationalizability."""
import uuid

import pytest

from agent.feasibility import (
    check_operationalizability, estimate_sample_size, make_feasibility_tool,
)

pytest.importorskip("thesis_stats")


# --- Phase 1: sample-size ----------------------------------------------------

def test_pls_hint_three_constructs():
    r = estimate_sample_size({"research_type": "quantitative"}, expected_constructs=3, method_hint="PLS-SEM")
    assert r["status"] == "estimate" and r["basis"] == "power"
    e = r["estimates"][0]
    assert e["analysis"] == "pls_sem" and e["required_n"] == 155 and "Kock & Hadaya" in e["justification"]
    assert r["assumed"] == {"predictors": 2, "predictors_source": "student_stated"}


def test_regression_hint_k3():
    r = estimate_sample_size({}, expected_constructs=4, method_hint="SPSS regression")
    e = r["estimates"][0]
    assert e["analysis"] == "regression" and e["required_n"] == 77 and "Cohen" in e["justification"]


def test_no_hints_range():
    rqs = ["To what extent does price affect loyalty?",
           "How does service quality influence satisfaction?",
           "Does trust impact repurchase intention?"]
    r = estimate_sample_size({"research_questions": rqs})
    assert r["status"] == "range"
    assert r["assumed"] == {"predictors": 3, "predictors_source": "inferred_from_rqs"}
    assert len(r["estimates"]) == 2
    assert r["range"] == [min(e["required_n"] for e in r["estimates"]),
                          max(e["required_n"] for e in r["estimates"])]
    assert r["headline_n"] == max(r["range"])


def test_default_k_when_empty():
    r = estimate_sample_size({})
    assert r["status"] == "range" and r["assumed"] == {"predictors": 4, "predictors_source": "default"}
    assert "your intended population" in r["message"]


def test_population_interpolated():
    r = estimate_sample_size({"target_population": "Gen Z bank customers in Hanoi"})
    assert "Gen Z bank customers in Hanoi" in r["message"]


def test_qualitative_skipped():
    r = estimate_sample_size({"research_type": "qualitative"})
    assert r["status"] == "skipped" and r["skipped_reason"] and not r["estimates"]


def test_cbsem_hint_heuristic():
    r = estimate_sample_size({}, expected_constructs=3, method_hint="CB-SEM (AMOS)")
    assert r["basis"] == "heuristic" and r["headline_n"] >= 200


def test_deterministic():
    a = estimate_sample_size({"research_questions": ["does x affect y"]}, expected_constructs=3)
    b = estimate_sample_size({"research_questions": ["does x affect y"]}, expected_constructs=3)
    assert a == b


def test_fail_open_power_raises(monkeypatch):
    import thesis_stats as ts
    monkeypatch.setattr(ts, "run_power", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    r = estimate_sample_size({}, expected_constructs=3, method_hint="PLS")
    assert r["basis"] == "heuristic" and r["headline_n"] and r["status"] in ("estimate", "range")


def test_power_justification_verbatim():
    import thesis_stats as ts
    r = estimate_sample_size({}, expected_constructs=3, method_hint="PLS-SEM")
    engine = ts.run_power("pls_sem", "apriori", effect_size="medium", predictors=2)
    assert r["estimates"][0]["justification"] == (engine.get("justification") or "")


# --- Phase 2: operationalizability ------------------------------------------

def test_definitional_flagged():
    r = check_operationalizability("What is the meaning of leadership?")
    assert len(r["findings"]) == 1
    assert r["findings"][0]["kind"] == "definitional" and r["findings"][0]["reframe_hint"]


def test_mixed_only_definitional_flagged():
    r = check_operationalizability(["What is the meaning of leadership?",
                                    "To what extent does transformational leadership affect employee engagement?"])
    flagged = [f for f in r["findings"] if f["kind"] == "definitional"]
    assert len(flagged) == 1 and r["testable_count"] == 1 and r["total"] == 2


def test_normative():
    r = check_operationalizability("Should companies ban remote work?")
    assert any(f["kind"] == "normative" for f in r["findings"])


def test_topic_not_testable_only_when_quantitative():
    descr = ["What is leadership?", "What is the definition of trust?"]
    q = check_operationalizability(descr, research_type="quantitative")
    assert any(f["kind"] == "topic_not_testable" for f in q["findings"])
    ql = check_operationalizability(descr, research_type="qualitative")
    assert not any(f["kind"] == "topic_not_testable" for f in ql["findings"])


def test_vietnamese():
    ok = check_operationalizability("Chuyển đổi số ảnh hưởng như thế nào đến hiệu quả làm việc?")
    assert not ok["findings"]
    bad = check_operationalizability("Lãnh đạo là gì?")
    assert any(f["kind"] == "definitional" for f in bad["findings"])


def test_no_measurable_relationship_soft():
    r = check_operationalizability("A study of employee wellbeing in startups")
    assert any(f["kind"] == "no_measurable_relationship" for f in r["findings"])


def test_operationalizability_defensive():
    assert check_operationalizability(None)["findings"] == []
    r = check_operationalizability([None, 42, ""])
    assert r["total"] == 0 and r["findings"] == []


# --- Phase 3: tool + ownership ----------------------------------------------

def test_ownership():
    from agent.state import SLICE_OWNERSHIP
    assert "feasibility" in SLICE_OWNERSHIP["M1"]


def test_tool_persists_and_returns(tmp_path):
    from agent.state import ProjectStateStore
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    store.commit_slice("M1", {"research_title": "T", "research_type": "quantitative",
                              "target_population": "SME managers",
                              "research_questions": ["What is leadership?",
                                                     "Does trust affect loyalty?"]},
                       reason="seed")
    import json
    out = json.loads(make_feasibility_tool(store)[0].func(expected_constructs=3, method_hint="PLS"))
    assert out["advisory"] is True and out["sample_size"]["headline_n"] == 155
    assert out["operationalizability"]["findings"]
    assert store.load()["contextStore"]["feasibility"]["inputs"]["predictors_source"] == "student_stated"


def test_tool_no_args_empty_store(tmp_path):
    from agent.state import ProjectStateStore
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    import json
    out = json.loads(make_feasibility_tool(store)[0].func())
    assert out["sample_size"]["status"] == "range"
