"""Tests for the artifact dependency DAG + definition-of-done validators."""
from orchestrator.artifacts import Artifact, DoD, dod_topic


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
