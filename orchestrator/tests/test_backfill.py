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


def test_reconstruct_artifact_extracts_rationale():
    cs = ContextStore(m4_analysis={"analysis_results": "PLS-SEM A->B"})
    out = reconstruct_artifact(
        "design", cs,
        llm=_fake_llm('{"paradigm": "quantitative", '
                      '"_rationale": "inferred from the PLS-SEM path"}'))
    # _rationale survives the field filter (so callers can surface the "why").
    assert out["_rationale"] == "inferred from the PLS-SEM path"
    assert out["paradigm"] == "quantitative"


def test_reconstruct_artifact_rationale_only_is_not_a_candidate():
    # A response with ONLY the meta rationale and no real field is not a slice.
    cs = ContextStore(m4_analysis={"analysis_results": "x"})
    assert reconstruct_artifact("design", cs,
                                llm=_fake_llm('{"_rationale": "hmm"}')) == {}


# --- reconstruct_upstream (the M4 -> M1/M2/M3 backfill loop) -----------------

def _routing_llm():
    """A fake whose reply depends on which artifact the prompt asks for, so one
    llm can serve the whole bottom-up loop."""
    captured = {"prompts": []}

    def invoke(prompt):
        captured["prompts"].append(prompt)
        r = MagicMock()
        if "'design'" in prompt:
            r.content = ('{"conceptual_model": {"constructs": ["A", "B"]}, '
                         '"hypotheses": ["H1: A->B"], '
                         '"_rationale": "from M4 path coefficients"}')
        elif "'literature'" in prompt:
            r.content = '{"research_gaps": ["gap X"], "_rationale": "from constructs"}'
        elif "'topic'" in prompt:
            r.content = ('{"research_title": "Effect of A on B", '
                         '"research_questions": ["RQ1"], "_rationale": "from gaps"}')
        else:
            r.content = "{}"
        return r
    llm = MagicMock(); llm.invoke = invoke
    return llm, captured


def test_reconstruct_upstream_targets_missing_below_imported():
    from orchestrator.backfill import reconstruct_upstream
    cs = ContextStore(m4_analysis={"analysis_results": "PLS-SEM A->B, R2=0.41"})
    llm, cap = _routing_llm()
    out = reconstruct_upstream(cs, llm=llm)
    # Only M4 filled → reconstruct M1, M2, M3, returned in display order.
    assert [e["module"] for e in out] == ["M1", "M2", "M3"]
    # Rationale is lifted out of the candidate to a top-level field.
    assert all("_rationale" not in e["candidate"] for e in out)
    assert next(e for e in out if e["module"] == "M3")["rationale"]
    # Every candidate is tagged reconstructed and carries review gaps.
    assert all(e["candidate"]["_source"] == "reconstructed" for e in out)


def test_reconstruct_upstream_feeds_forward_bottom_up():
    from orchestrator.backfill import reconstruct_upstream
    cs = ContextStore(m4_analysis={"analysis_results": "x"})
    llm, cap = _routing_llm()
    reconstruct_upstream(cs, llm=llm)
    m2_prompt = next(p for p in cap["prompts"] if "'literature'" in p)
    m1_prompt = next(p for p in cap["prompts"] if "'topic'" in p)
    # M2's inference sees the freshly-reconstructed M3; M1 sees M2.
    assert "constructs" in m2_prompt
    assert "gap X" in m1_prompt


def test_reconstruct_upstream_respects_explicit_targets():
    from orchestrator.backfill import reconstruct_upstream
    cs = ContextStore(m4_analysis={"analysis_results": "x"})
    llm, _ = _routing_llm()
    out = reconstruct_upstream(cs, targets=["M3"], llm=llm)
    assert [e["module"] for e in out] == ["M3"]


def test_reconstruct_upstream_skips_modules_with_content():
    from orchestrator.backfill import reconstruct_upstream
    # M1 already has content → never re-reconstructed; only M2, M3 targeted.
    cs = ContextStore(
        m1_topic={"research_title": "given"},
        m4_analysis={"analysis_results": "x"})
    llm, _ = _routing_llm()
    out = reconstruct_upstream(cs, llm=llm)
    assert [e["module"] for e in out] == ["M2", "M3"]


def test_reconstruct_upstream_empty_when_nothing_filled():
    from orchestrator.backfill import reconstruct_upstream
    assert reconstruct_upstream(ContextStore(), llm=_fake_llm("{}")) == []
