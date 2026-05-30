"""Tests for the artifact dependency DAG + definition-of-done validators."""
from orchestrator.artifacts import Artifact, DoD, dod_design, dod_topic


_FULL_TOPIC = {
    "research_title": "TikTok & Gen Z", "field": "Communication Studies",
    "research_type": "quantitative", "target_population": "Gen Z students",
    "scope": "National", "objectives": ["Measure X"],
    "research_questions": ["How does X?"],
}


def test_dod_topic_complete_is_done():
    result = dod_topic(_FULL_TOPIC)
    assert result.done is True
    assert result.gaps == []


def test_dod_topic_missing_fields_reports_gaps():
    result = dod_topic({"research_title": "X"})
    assert result.done is False
    assert any("objectives" in g for g in result.gaps)
    assert any("research_questions" in g for g in result.gaps)


def test_dod_topic_empty_objectives_list_is_a_gap():
    slice_ = {**_FULL_TOPIC, "objectives": []}
    result = dod_topic(slice_)
    assert result.done is False
    assert any("objectives" in g for g in result.gaps)


_FULL_DESIGN_QUANT = {
    "paradigm": "quantitative", "design": "PLS-SEM", "tool": "SmartPLS",
    "sampling_strategy": "convenience", "target_sample_size": 200,
    "conceptual_model": {"constructs": ["A", "B"]}, "scale_items": [{"item": "q1"}],
}


def test_dod_design_quantitative_complete_is_done():
    assert dod_design(_FULL_DESIGN_QUANT).done is True


def test_dod_design_quantitative_missing_scale_items_is_gap():
    result = dod_design({**_FULL_DESIGN_QUANT, "scale_items": []})
    assert result.done is False
    assert any("scale_items" in g for g in result.gaps)


def test_dod_design_qualitative_complete_is_done():
    slice_ = {
        "paradigm": "qualitative", "design": "Thematic Analysis", "tool": "NVivo",
        "sampling_strategy": "purposive", "target_sample_size": 20,
        "themes": [{"t": "trust"}], "interview_guide": {"q1": "..."},
        "purposive_criteria": [{"c": "5+ yrs"}],
    }
    assert dod_design(slice_).done is True


def test_dod_design_mixed_missing_design_type_is_gap():
    slice_ = {
        "paradigm": "mixed", "design": "Sequential", "tool": "SPSS+NVivo",
        "sampling_strategy": "mixed", "target_sample_size": 100,
        "conceptual_model": {"x": 1}, "scale_items": [{"i": 1}],
        "themes": [{"t": 1}], "interview_guide": {"q": 1},
        "purposive_criteria": [{"c": 1}],  # mixed_design_type absent
    }
    result = dod_design(slice_)
    assert result.done is False
    assert any("mixed_design_type" in g for g in result.gaps)


def test_dod_design_empty_slice_reports_paradigm_gap():
    result = dod_design({})
    assert result.done is False
    assert any("paradigm" in g for g in result.gaps)


def test_dod_and_artifact_dataclasses():
    dod = DoD(done=True, gaps=[])
    assert dod.done is True
    assert dod.gaps == []

    art = Artifact(
        key="topic", slice="m1_topic", depends_on=(),
        dod=lambda s: DoD(done=True, gaps=[]),
    )
    assert art.key == "topic"
    assert art.slice == "m1_topic"
    assert art.depends_on == ()
    assert art.dod({}).done is True
