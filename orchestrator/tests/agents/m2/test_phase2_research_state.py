"""Tests for Phase 2 — Research_State."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2.state import fresh_state


def _state(mode="interactive", user_msg="continue", **overrides):
    s = fresh_state(
        project_id="p", thread_id="t", research_title="TL → EE",
        research_type="quantitative", language="en",
        paper_uris=[], mode=mode,
    )
    s["messages"] = [HumanMessage(content=user_msg)]
    s.update(overrides)
    return s


def test_phase2_blocks_with_clear_message_when_scout_empty_and_no_papers(monkeypatch):
    """B1: when scout returns [] AND no papers uploaded, phase2 must NOT
    advance to gap_analysis. It must emit a clear 'couldn't find citations'
    message + set _citation_search_failed=True so phase3 never runs with no
    sources (which led to the LLM fabricating 'Author (Year) page?')."""
    from orchestrator.agents.m2.phases import phase2_research_state as p2
    monkeypatch.setattr(p2, "_scout", lambda *a, **kw: [])
    monkeypatch.setattr(p2, "_get_llm", lambda: MagicMock())  # must NOT be called

    s = _state(user_msg="continue")
    s["paper_uris"] = []
    patch = p2.run(s)

    assert patch.get("_citation_search_failed") is True
    assert patch.get("research_state_confirmed") is False
    # Did NOT advance to gap_analysis.
    assert patch.get("current_phase") in (None, "research_state")
    # User-visible message is helpful, not silent.
    msg = (patch.get("messages") or [MagicMock(content="")])[0].content
    assert "couldn't find" in msg.lower() or "no citations" in msg.lower()
    assert "TL → EE" in msg or "your topic" in msg.lower() or "title" in msg.lower()


def test_phase2_with_uploaded_papers_skips_gate(monkeypatch):
    """If user uploaded papers, an empty scout is fine — we have content to
    work with. Skip the gate and proceed with synthesis."""
    from orchestrator.agents.m2.phases import phase2_research_state as p2
    monkeypatch.setattr(p2, "_scout", lambda *a, **kw: [])

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Synthesis based on uploaded papers."
    monkeypatch.setattr(p2, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="continue")
    s["paper_uris"] = ["s3://b/paper1.pdf"]
    patch = p2.run(s)

    assert patch.get("_citation_search_failed") is not True
    assert "Synthesis" in patch.get("research_state_draft", "")


def test_phase2_recovers_when_refine_with_new_terms_finds_citations(monkeypatch):
    """After a failed scout, the user can provide new search terms via 'refine'.
    Phase2 re-runs scout with those terms; on success, clears the flag and
    synthesizes normally."""
    from orchestrator.agents.m2.phases import phase2_research_state as p2
    from orchestrator.agents.m2 import intent as m2_intent

    # Topic-keyed: only the refined terms succeed.
    def fake_scout(topic, *a, **kw):
        if "tiktok marketing" in topic.lower():
            return [{"title": "P1", "authors": "Bass", "year": 2020}]
        return []
    monkeypatch.setattr(p2, "_scout", fake_scout)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Refined synthesis."
    monkeypatch.setattr(p2, "_get_llm", lambda: fake_llm)

    # Mock the intent classifier to return refine
    fake_struct = MagicMock()
    fake_struct.invoke.return_value = m2_intent.PhaseIntent(
        action="refine", refinement_text="TikTok marketing Gen Z")
    fake_int_llm = MagicMock()
    fake_int_llm.with_structured_output.return_value = fake_struct
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_int_llm)

    # State: prior scout failed, _citation_search_failed=True, research_state_draft
    # set to the error message so we're in the second-call branch.
    s = _state(user_msg="try TikTok marketing Gen Z")
    s["research_state_draft"] = "I couldn't find citations..."
    s["_citation_search_failed"] = True
    s["research_state_citations"] = []
    patch = p2.run(s)

    assert patch.get("_citation_search_failed") is False
    assert "Refined" in patch.get("research_state_draft", "")
    assert len(patch.get("research_state_citations", [])) == 1


def test_phase2_synthesize_falls_back_to_template_on_llm_timeout(monkeypatch):
    """When the synthesize LLM call exceeds the wall-clock budget, phase2 must
    still produce a research_state_draft (templated from citations) so M2
    doesn't hang the graph turn."""
    from orchestrator.agents.base import BoundedInvokeTimeout
    from orchestrator.agents.m2.phases import phase2_research_state as p2

    monkeypatch.setattr(p2, "_scout", lambda *a, **kw: [
        {"authors": "Wang", "year": 2011, "title": "Trust"},
        {"authors": "Bass", "year": 1985, "title": "Leadership"},
    ])
    # Force the bounded synthesize call to raise a timeout (simulates Gemini
    # hanging past the wall-clock cap).
    monkeypatch.setattr(p2, "bounded_invoke",
                        lambda *a, **kw: (_ for _ in ()).throw(BoundedInvokeTimeout("test")))

    patch = p2.run(_state())
    draft = patch.get("research_state_draft") or ""
    assert draft, "must produce a draft even on LLM timeout"
    assert "Wang" in draft or "Bass" in draft, "templated fallback should cite the scout finds"


def test_phase2_first_call_scouts_and_synthesizes(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state

    fake_scout = MagicMock(return_value=[
        {"title": "P1", "authors": "Bass", "year": 1985,
         "source": "Journal", "url": None, "doi": None},
    ])
    monkeypatch.setattr(phase2_research_state, "_scout", fake_scout)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Synthesis with (Bass, 1985)."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    patch = phase2_research_state.run(_state())
    assert "Bass" in patch["research_state_draft"]
    assert patch["research_state_citations"] == [
        {"title": "P1", "authors": "Bass", "year": 1985,
         "source": "Journal", "url": None, "doi": None},
    ]
    assert patch.get("research_state_confirmed") is False
    msgs = patch.get("messages", [])
    assert len(msgs) == 1


def test_phase2_refine_appends_and_regenerates_with_cached_citations(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state

    scout_calls = {"n": 0}
    def fake_scout(*a, **kw):
        scout_calls["n"] += 1
        return []
    monkeypatch.setattr(phase2_research_state, "_scout", fake_scout)

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Refined synthesis focusing on SDT."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo focusing on Self-Determination Theory")
    s["research_state_draft"] = "old synthesis"
    s["research_state_citations"] = [{"title": "P1"}]
    patch = phase2_research_state.run(s)
    assert scout_calls["n"] == 0
    assert "SDT" in patch["research_state_draft"]
    assert patch.get("research_state_refinements") == ["redo focusing on Self-Determination Theory"]
    assert patch["regeneration_count"]["research_state"] == 1


def test_phase2_confirm_advances_to_gap_analysis(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    from orchestrator.agents.m2 import intent as m2_intent
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: MagicMock())

    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(action="confirm")
    fake_intent = MagicMock()
    fake_intent.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent)

    s = _state(user_msg="looks good, continue")
    s["research_state_draft"] = "synthesis"
    patch = phase2_research_state.run(s)
    assert patch.get("research_state_confirmed") is True
    assert patch.get("current_phase") == "gap_analysis"


def test_phase2_regen_cap_blocks_6th_iteration(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    fake_llm = MagicMock()
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    s = _state(user_msg="redo with a different lens")
    s["research_state_draft"] = "synthesis"
    s["regeneration_count"] = {"research_state": 5}
    patch = phase2_research_state.run(s)
    assert patch.get("research_state_draft") == "synthesis" or patch.get("research_state_draft") is None
    fake_llm.invoke.assert_not_called()
    msgs = patch.get("messages", [])
    assert any("lock" in m.content.lower() or "5" in m.content for m in msgs)


def test_phase2_navigate_back_to_familiarize(monkeypatch):
    from orchestrator.agents.m2.phases import phase2_research_state
    from orchestrator.agents.m2 import intent as m2_intent
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: MagicMock())

    fake_structured = MagicMock()
    fake_structured.invoke.return_value = m2_intent.PhaseIntent(
        action="navigate", target_phase="familiarize",
    )
    fake_intent = MagicMock()
    fake_intent.with_structured_output.return_value = fake_structured
    monkeypatch.setattr(m2_intent, "_intent_llm", lambda: fake_intent)

    s = _state(user_msg="redo familiarize")
    s["research_state_draft"] = "synthesis"
    patch = phase2_research_state.run(s)
    assert patch.get("current_phase") == "familiarize"


def test_phase2_auto_mode_one_shot(monkeypatch):
    """Auto mode happy path: scout finds citations → synthesize → advance."""
    from orchestrator.agents.m2.phases import phase2_research_state
    # Scout returns real citations — without them, B1 gate (correctly) blocks.
    monkeypatch.setattr(phase2_research_state, "_scout",
                        lambda *a, **kw: [{"title": "P1", "authors": "Bass", "year": 2020}])
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Auto synthesis."
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: fake_llm)

    patch = phase2_research_state.run(_state(mode="auto"))
    assert patch.get("research_state_confirmed") is True
    assert patch.get("current_phase") == "gap_analysis"


def test_phase2_auto_mode_halts_on_empty_scout_no_papers(monkeypatch):
    """Auto mode B1 gate: empty scout + no papers → halt before gap_analysis."""
    from orchestrator.agents.m2.phases import phase2_research_state
    monkeypatch.setattr(phase2_research_state, "_scout", lambda *a, **kw: [])
    monkeypatch.setattr(phase2_research_state, "_get_llm", lambda: MagicMock())

    patch = phase2_research_state.run(_state(mode="auto"))
    assert patch.get("_citation_search_failed") is True
    assert patch.get("research_state_confirmed") is False
    # Did NOT advance phase — auto chain stops here.
    assert patch.get("current_phase") in (None, "research_state")
