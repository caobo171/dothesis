"""Auto-mode roundtrip test for M3 agent — validates schema-driven auto-fill."""
from unittest.mock import MagicMock
from langchain_core.messages import HumanMessage
from orchestrator.agents.m3_design import M3Agent
from orchestrator.state import ContextStore


def test_m3_constructs_from_handles_list_and_dict():
    """Regression: a delegated conceptual_model can come back as a LIST of path
    strings instead of {constructs: [...]}, which used to crash step() with
    'list object has no attribute get'. Helper now also derives construct
    names from path endpoints across every plausible stored shape so
    scale_items can render with one row per construct.
    """
    # Ideal shape — explicit constructs key.
    assert M3Agent._constructs_from({"constructs": ["A", "B"]}) == ["A", "B"]
    # Paths-only dict — derive unique endpoints in insertion order.
    assert M3Agent._constructs_from({"paths": [
        {"from": "TL", "to": "EE"},
        {"from": "TL", "to": "Trust"},
        {"from": "Trust", "to": "EE"},
    ]}) == ["TL", "EE", "Trust"]
    # Bare list of path dicts — same derivation.
    assert M3Agent._constructs_from([
        {"from": "A", "to": "B"}, {"from": "B", "to": "C"},
    ]) == ["A", "B", "C"]
    # Bare list of path STRINGS (ASCII arrow + hypothesis label in parens).
    # Old behavior returned the raw strings as 'constructs'; new behavior
    # extracts endpoints and strips the (H<n>) tail.
    assert M3Agent._constructs_from(["PEU -> US (H1)", "PU -> US (H2)"]) == \
        ["PEU", "US", "PU"]
    # Bare list of construct names — pass through unchanged.
    assert M3Agent._constructs_from(["A", "B"]) == ["A", "B"]
    # None / empty.
    assert M3Agent._constructs_from(None) == []
    assert M3Agent._constructs_from({}) == []


def test_m3_auto_quantitative(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"paradigm":"quantitative","design":"PLS-SEM","tool":"SmartPLS",'
        '"sampling_strategy":"convenience","target_sample_size":300,'
        '"conceptual_model":{"constructs":["TL","EE"],"paths":[]},'
        '"constructs":[],"questionnaire_text":null,"interview_guide":null}'
    )
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="design")], "current_module": "M3",
        "context_store": ContextStore(m1_topic={"research_type": "quantitative",
                                                "confirmed_at": "2026-05-26"}),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M3Agent().step(state)
    assert res.transition is True
    assert res.context_patch["design"] == "PLS-SEM"
