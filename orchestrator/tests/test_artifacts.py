"""Tests for the artifact dependency DAG + definition-of-done validators."""
from orchestrator.artifacts import Artifact, DoD


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
