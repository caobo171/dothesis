"""Tests for prerequisite reconstruction (the Phase 3 backfill spike)."""
from unittest.mock import MagicMock

from orchestrator.backfill import reconstruct_artifact
from orchestrator.state import ContextStore


def _fake_llm(content: str) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


def test_reconstruct_design_from_analysis_evidence():
    cs = ContextStore(
        m1_topic={"research_title": "TikTok & Gen Z", "research_type": "quantitative"},
        m4_analysis={"data_type_detected": "SmartPLS",
                     "results": {"path": {"step_name": "structural model"}}},
    )
    # 2026-06 design merge: scale_items dropped; conceptual_model carries
    # per-construct Likert items as node.questions, so the reconstructed JSON
    # ships the new nodes+edges shape (no separate scale_items key).
    llm = _fake_llm(
        '{"paradigm": "quantitative", "design": "PLS-SEM", "tool": "SmartPLS", '
        '"sampling_strategy": "convenience", "target_sample_size": 200, '
        '"conceptual_model": {"nodes": [{"id": "n0", "label": "A", '
        '"questions": ["q1"]}], "edges": []}}'
    )
    out = reconstruct_artifact("design", cs, llm=llm)
    assert out["paradigm"] == "quantitative"
    assert out["design"] == "PLS-SEM"
    # Candidate is tagged so downstream knows it was inferred, not user-given.
    assert out["_source"] == "reconstructed"


def test_reconstruct_with_no_evidence_returns_empty():
    # Nothing else filled → nothing to infer from → empty (don't fabricate).
    out = reconstruct_artifact("design", ContextStore(), llm=_fake_llm("{}"))
    assert out == {}


def test_reconstruct_malformed_llm_returns_empty():
    cs = ContextStore(m4_analysis={"data_type_detected": "SmartPLS"})
    assert reconstruct_artifact("design", cs, llm=_fake_llm("not json")) == {}


def test_reconstruct_excludes_target_slice_from_evidence():
    # Even if the design slice has stale junk, reconstruction infers fresh and
    # doesn't just echo it — the prompt is built from OTHER slices.
    cs = ContextStore(
        m1_topic={"research_title": "X", "research_type": "qualitative"},
        m3_design={"garbage": "ignore me"},
        m4_analysis={"data_type_detected": "Qualitative"},
    )
    captured = {}

    def fake_invoke(prompt):
        captured["prompt"] = prompt
        r = MagicMock(); r.content = '{"paradigm": "qualitative"}'
        return r
    llm = MagicMock(); llm.invoke = fake_invoke
    out = reconstruct_artifact("design", cs, llm=llm)
    assert out["paradigm"] == "qualitative"
    assert "ignore me" not in captured["prompt"]
