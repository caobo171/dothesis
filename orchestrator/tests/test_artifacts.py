"""Tests for the artifact dependency DAG + definition-of-done validators."""
from orchestrator.artifacts import (
    ARTIFACTS, Artifact, DoD, artifact_to_module, dod_analysis, dod_chapter,
    dod_design, dod_literature, dod_topic, readiness,
)
from orchestrator.state import ContextStore


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


_FULL_LITERATURE = {
    "research_state_summary": "Current research shows...",
    "research_gaps": [{"description": "no Gen Z studies"}],
    "theoretical_framework": "Theory of Planned Behavior",
    "literature_review_doc": "Chapter 2 draft...",
    "citation_list": [{"author": "Bass", "year": 1985}],
}


def test_dod_literature_complete_is_done():
    assert dod_literature(_FULL_LITERATURE).done is True


def test_dod_literature_missing_gaps_is_a_gap():
    result = dod_literature({**_FULL_LITERATURE, "research_gaps": []})
    assert result.done is False
    assert any("research_gaps" in g for g in result.gaps)


def test_dod_analysis_quant_complete_is_done():
    slice_ = {
        "data_type_detected": "SmartPLS",
        "analysis_outline": {"sections": ["descriptives"]},
        "results": {"step1": {"step_name": "descriptives"}},
    }
    assert dod_analysis(slice_).done is True


def test_dod_analysis_qualitative_requires_codes_and_themes():
    slice_ = {
        "data_type_detected": "Qualitative",
        "analysis_outline": {"sections": ["coding"]},
        "results": {"s1": {"step_name": "coding"}},
    }
    result = dod_analysis(slice_)
    assert result.done is False
    assert any("qual_codes" in g for g in result.gaps)


def test_dod_chapter_done_when_prose_present():
    slice_ = {"chapters": {"methodology": {"prose": "Our design uses..."}}}
    assert dod_chapter("methodology")(slice_).done is True


def test_dod_chapter_gap_when_missing_or_blank():
    assert dod_chapter("results")({"chapters": {}}).done is False
    assert dod_chapter("results")({"chapters": {"results": {"prose": "   "}}}).done is False


_FULL_ANALYSIS = {
    "data_type_detected": "SmartPLS",
    "analysis_outline": {"sections": ["descriptives"]},
    "results": {"step1": {"step_name": "descriptives"}},
}
_FULL_CHAPTERS = {
    "chapters": {
        name: {"prose": f"{name} text"}
        for name in ("intro", "lit_review", "methodology",
                     "results", "discussion", "conclusion")
    }
}


def test_readiness_empty_only_topic_ready():
    r = readiness(ContextStore())
    assert r["topic"] == "ready"
    assert r["literature"] == "blocked"
    assert r["design"] == "blocked"
    assert r["ch_methodology"] == "blocked"


def test_readiness_topic_done_unlocks_literature_only():
    r = readiness(ContextStore(m1_topic=_FULL_TOPIC))
    assert r["topic"] == "done"
    assert r["literature"] == "ready"
    assert r["design"] == "blocked"  # design needs literature too


def test_readiness_through_analysis_unlocks_early_chapters():
    cs = ContextStore(
        m1_topic=_FULL_TOPIC, m2_literature=_FULL_LITERATURE,
        m3_design=_FULL_DESIGN_QUANT, m4_analysis=_FULL_ANALYSIS,
    )
    r = readiness(cs)
    assert r["analysis"] == "done"
    assert r["ch_methodology"] == "ready"
    assert r["ch_results"] == "ready"
    assert r["ch_intro"] == "ready"
    assert r["ch_discussion"] == "blocked"  # needs ch_results first


def test_readiness_fully_populated_all_done():
    cs = ContextStore(
        m1_topic=_FULL_TOPIC, m2_literature=_FULL_LITERATURE,
        m3_design=_FULL_DESIGN_QUANT, m4_analysis=_FULL_ANALYSIS,
        m5_writing=_FULL_CHAPTERS,
    )
    assert set(readiness(cs).values()) == {"done"}


def test_artifact_to_module_maps_each_artifact():
    assert artifact_to_module("topic") == "M1"
    assert artifact_to_module("literature") == "M2"
    assert artifact_to_module("design") == "M3"
    assert artifact_to_module("analysis") == "M4"
    # Every chapter routes to M5 (M5 owns chapter composition).
    assert artifact_to_module("ch_methodology") == "M5"
    assert artifact_to_module("ch_conclusion") == "M5"


def test_artifact_to_module_every_registered_artifact_resolves():
    for a in ARTIFACTS:
        assert artifact_to_module(a.key) in {"M1", "M2", "M3", "M4", "M5"}


def test_artifacts_registry_keys_unique_and_deps_resolve():
    keys = [a.key for a in ARTIFACTS]
    assert len(keys) == len(set(keys))          # no duplicate keys
    known = set(keys)
    for a in ARTIFACTS:
        for dep in a.depends_on:
            assert dep in known, f"{a.key} depends on unknown artifact {dep}"


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
