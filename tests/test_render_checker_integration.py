"""Phase 3: rendered blocks are authoritative-not-suspect to coherence/similarity."""
import pytest

from orchestrator.tools.results_render import render_results_tables, weave
from agent.coherence import validate_m5_sections
from tests.fixtures.renderer_blocks import PLS_BLOCK


def _flat_context():
    # flat store shaped as the coherence registry links it (string hyps +
    # hypothesis_tests carrying `hypothesis: "H1"`), mirroring agent/tests/test_coherence.py.
    ar = {**PLS_BLOCK, "hypothesis_tests": [
        {"id": "r-H1", "hypothesis": "H1", "path": "LS → PI",
         "numbers": {"beta": 0.34, "t": 7.01, "p": "<0.001", "f2": 0.18}, "decision": "supported"}]}
    return {"analysis_results": ar,
            "hypotheses": ["H1: LS has a positive effect on PI"],
            "conceptual_model": {"nodes": [{"id": "n1", "label": "LS"}, {"id": "n2", "label": "PI"}],
                                 "edges": [{"source": "n1", "target": "n2"}]}}


def _sections(results_prose, discussion_prose="H1 (LS -> PI) was supported and is discussed here."):
    # dict-of-chapters shape (auto-mode) — _resolve_chapters reads it directly.
    return {"results": results_prose, "discussion": discussion_prose}


def test_rendered_table_never_trips_coherence():
    blocks = render_results_tables(PLS_BLOCK)
    # narrative quotes the CORRECT number; the table is rendered (sentinels)
    narrative = "H1 was supported (β = .34, p < .001).\n\n[[DT:structural_paths]]\n"
    woven = weave(narrative, blocks)
    agg = validate_m5_sections(_sections(woven), _flat_context())
    assert not any(f.get("check") == "coherence.number_mismatch" and f.get("severity") == "hard"
                   for f in agg.get("findings", []))


def test_wrong_narrative_still_caught_around_rendered_block():
    blocks = render_results_tables(PLS_BLOCK)
    # the LLM narrative (OUTSIDE the sentinels) states a wrong beta for H1
    narrative = "H1 was supported (β = .55, p < .001).\n\n[[DT:structural_paths]]\n"
    woven = weave(narrative, blocks)
    agg = validate_m5_sections(_sections(woven), _flat_context())
    assert any(f.get("check") == "coherence.number_mismatch" and f.get("severity") == "hard"
               for f in agg.get("findings", []))


def test_strip_import_failure_fail_open(monkeypatch):
    import agent.coherence as coh
    monkeypatch.setattr(coh, "_strip_rendered", lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
    # even if strip itself raised, _resolve_chapters must not crash the gate;
    # (guard: our _strip_rendered swallows internally, but prove the gate returns)
    try:
        agg = validate_m5_sections(_sections("plain prose, β = 0.34."), _flat_context())
        assert "passed" in agg
    except Exception:
        pytest.fail("gate must not raise")
