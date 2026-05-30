"""Tests for the artifact-DAG planner (deterministic next-best-action)."""
import pytest

from orchestrator.planner import Decision, plan_next
from orchestrator.state import ContextStore

_FULL_TOPIC = {
    "research_title": "X", "field": "Marketing", "research_type": "quantitative",
    "target_population": "Gen Z", "scope": "National",
    "objectives": ["o1"], "research_questions": ["q1"],
}
_FULL_LIT = {
    "research_state_summary": "s", "research_gaps": [{"description": "g"}],
    "theoretical_framework": "TPB", "literature_review_doc": "d",
    "citation_list": [{"author": "X"}],
}
_FULL_DESIGN = {
    "paradigm": "quantitative", "design": "PLS-SEM", "tool": "SmartPLS",
    "sampling_strategy": "convenience", "target_sample_size": 200,
    "conceptual_model": {"c": 1}, "scale_items": [{"i": 1}],
}
_FULL_ANALYSIS = {
    "data_type_detected": "SmartPLS", "analysis_outline": {"sections": ["d"]},
    "results": {"s1": {"step_name": "d"}},
}
_FULL_CHAPTERS = {"chapters": {n: {"prose": f"{n}"} for n in
                  ("intro", "lit_review", "methodology", "results",
                   "discussion", "conclusion")}}


def _full_cs() -> ContextStore:
    return ContextStore(
        m1_topic=_FULL_TOPIC, m2_literature=_FULL_LIT, m3_design=_FULL_DESIGN,
        m4_analysis=_FULL_ANALYSIS, m5_writing=_FULL_CHAPTERS,
    )


def test_plan_next_empty_works_on_topic():
    d = plan_next(ContextStore())
    assert isinstance(d, Decision)
    assert d.action == "work"
    assert d.artifact == "topic"


def test_plan_next_topic_done_works_on_literature():
    d = plan_next(ContextStore(m1_topic=_FULL_TOPIC))
    assert d.action == "work"
    assert d.artifact == "literature"


def test_plan_next_all_done_is_done():
    d = plan_next(_full_cs())
    assert d.action == "done"
    assert d.artifact is None


def test_plan_next_target_blocked_backfills_deepest_ready_prereq():
    # Student wants 'analysis' but nothing is done → backfill 'topic' first.
    d = plan_next(ContextStore(), target="analysis")
    assert d.action == "backfill"
    assert d.artifact == "topic"
    assert d.toward == "analysis"


def test_plan_next_target_blocked_backfills_design_when_upstream_done():
    cs = ContextStore(m1_topic=_FULL_TOPIC, m2_literature=_FULL_LIT)
    d = plan_next(cs, target="analysis")
    assert d.action == "backfill"
    assert d.artifact == "design"
    assert d.toward == "analysis"


def test_plan_next_target_ready_works_on_it():
    cs = ContextStore(m1_topic=_FULL_TOPIC, m2_literature=_FULL_LIT,
                      m3_design=_FULL_DESIGN)
    d = plan_next(cs, target="analysis")
    assert d.action == "work"
    assert d.artifact == "analysis"


def test_plan_next_target_already_done():
    d = plan_next(_full_cs(), target="topic")
    assert d.action == "already_done"
    assert d.artifact == "topic"


def test_plan_next_unknown_target_raises():
    with pytest.raises(KeyError):
        plan_next(ContextStore(), target="nonsense")
