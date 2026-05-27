"""Tests for M4Agent ad-hoc analysis detection (Q4=B — NL intent)."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_ad_hoc_request_appends_to_custom_analyses(monkeypatch):
    """When the user requests an analysis outside the confirmed outline AND
    execution is already done, the agent calls run_extra_analysis and appends
    the result to custom_analyses."""
    from orchestrator.agents import m4_analysis as m4_mod

    fake_extra = MagicMock()
    fake_extra.invoke.return_value = {
        "step_name": "mediation H3",
        "table": [{"path": "TL → Trust → EE", "indirect": 0.113, "p": 0.004}],
        "thresholds_met": True,
        "interpretation": "Significant mediation effect.",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(m4_mod, "run_extra_analysis", fake_extra)

    # Stub the LLM so any fallback path in the base class doesn't hit the network.
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "ok"
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake_llm)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="also run a mediation test on H3")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "SmartPLS", "paradigm": "quantitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "SmartPLS",
                "data_paste": "any output",
                "analysis_outline": {"sections": [{"name": "Outer Loadings"}],
                                     "confirmed_by_user": True},
                "results": {"Outer Loadings": {"step_name": "Outer Loadings",
                                                "table": [], "parser": "regex"}},
                "_run_execution_done": True,
                # No _summary_done yet — agent is awaiting confirm.
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    # If ad-hoc was detected and dispatched, custom_analyses has the new entry.
    assert any(
        sr.get("step_name") == "mediation H3"
        for sr in result.context_patch.get("custom_analyses", [])
    )
