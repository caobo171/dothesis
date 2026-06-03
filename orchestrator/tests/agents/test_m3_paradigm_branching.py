"""Tests for M3Agent's paradigm-aware _next_missing_field override."""
from orchestrator.agents.m3_design import M3Agent


def test_quant_walk_order():
    agent = M3Agent()
    partial = {"paradigm": "quantitative"}
    # All quant required fields empty → first missing = "design"
    assert agent._next_missing_field(partial) == "design"

    partial["design"] = "PLS-SEM"
    assert agent._next_missing_field(partial) == "tool"

    partial["tool"] = "SmartPLS"
    assert agent._next_missing_field(partial) == "conceptual_model"

    # 2026-06 design merge: conceptual_model carries both paths and per-construct
    # Likert items as node.questions, so the walk skips the prior scale_items
    # step entirely and goes straight to target_sample_size.
    partial["conceptual_model"] = {
        "nodes": [{"id": "n0", "label": "TL", "questions": ["I1"]}],
        "edges": [],
    }
    assert agent._next_missing_field(partial) == "target_sample_size"

    partial["target_sample_size"] = 200
    assert agent._next_missing_field(partial) == "sampling_strategy"

    partial["sampling_strategy"] = "convenience"
    assert agent._next_missing_field(partial) is None  # all filled


def test_qual_walk_order():
    agent = M3Agent()
    partial = {"paradigm": "qualitative"}
    assert agent._next_missing_field(partial) == "design"

    partial.update({"design": "Thematic Analysis", "tool": "NVivo"})
    assert agent._next_missing_field(partial) == "themes"

    partial["themes"] = [{"id": "t1", "theme": "X"}]
    assert agent._next_missing_field(partial) == "interview_guide"

    partial["interview_guide"] = {"sections": [{"phase": "main"}]}
    assert agent._next_missing_field(partial) == "purposive_criteria"


def test_mixed_first_field_is_design_type():
    agent = M3Agent()
    partial = {"paradigm": "mixed"}
    assert agent._next_missing_field(partial) == "mixed_design_type"


def test_mixed_seq_explanatory_walk_switches_after_design_type():
    agent = M3Agent()
    partial = {"paradigm": "mixed", "mixed_design_type": "sequential_explanatory"}
    # After mixed_design_type is filled, walk starts with quant fields.
    assert agent._next_missing_field(partial) == "design"


def test_mixed_seq_exploratory_walk_starts_with_qual():
    """Exploratory order in _FIELDS_BY_PARADIGM is (post-2026-06 merge):
    [mixed_design_type, themes, interview_guide, purposive_criteria,
    design, tool, conceptual_model, target_sample_size, sampling_strategy].
    So after mixed_design_type is filled, the next missing field is 'themes'."""
    agent = M3Agent()
    partial = {"paradigm": "mixed", "mixed_design_type": "sequential_exploratory"}
    assert agent._next_missing_field(partial) == "themes"

    partial["themes"] = [{"id": "t1", "theme": "X"}]
    assert agent._next_missing_field(partial) == "interview_guide"
