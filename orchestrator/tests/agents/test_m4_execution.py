"""Tests for M4Agent execution phase — per-step AIMessage emission."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_run_quant_execution_emits_one_message_per_step(monkeypatch):
    """After paste + outline are filled, _run_execution emits N step messages + 1 summary."""
    def fake_run_step(invoke_args):
        step_name = invoke_args.get("step_name") if isinstance(invoke_args, dict) else None
        return {
            "step_name": step_name,
            "table": [{"x": 1}],
            "thresholds_met": True,
            "interpretation": f"OK for {step_name}",
            "parser": "regex",
        }

    from orchestrator.agents import m4_analysis as m4_mod
    fake_tool = MagicMock()
    fake_tool.invoke.side_effect = lambda kw: fake_run_step(kw)
    monkeypatch.setattr(m4_mod, "run_analysis_step", fake_tool)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "SPSS", "paradigm": "quantitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "SPSS",
                "data_paste": "any spss output",
                "analysis_outline": {
                    "sections": [
                        {"name": "Descriptive Statistics"},
                        {"name": "Reliability (Cronbach's Alpha)"},
                    ],
                    "confirmed_by_user": True,
                },
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    # 2 step messages should be in extra_messages
    assert len(result.extra_messages) >= 2
    contents = [m.content for m in result.extra_messages]
    assert any("Descriptive Statistics" in c for c in contents)
    assert any("Reliability" in c for c in contents)
    # The marker is set so the walk advances
    assert result.context_patch.get("_run_execution_done") is True
    # results dict has both step entries
    assert "Descriptive Statistics" in result.context_patch.get("results", {})
    assert "Reliability (Cronbach's Alpha)" in result.context_patch.get("results", {})


def test_run_qual_pipeline_emits_codes_and_themes_messages(monkeypatch):
    """Qual pipeline emits step messages for codes + themes + a summary."""
    from orchestrator.agents import m4_analysis as m4_mod

    fake_codes = MagicMock()
    fake_codes.invoke.return_value = [
        {"code": "leadership vision", "quote": "..."},
        {"code": "engagement", "quote": "..."},
    ]
    fake_themes = MagicMock()
    fake_themes.invoke.return_value = [
        {"theme": "Leadership", "codes": ["leadership vision"]},
        {"theme": "Engagement", "codes": ["engagement"]},
    ]
    monkeypatch.setattr(m4_mod, "suggest_qual_codes", fake_codes)
    monkeypatch.setattr(m4_mod, "cluster_codes_into_themes", fake_themes)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "NVivo", "paradigm": "qualitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "Qualitative",
                "data_paste": "INTERVIEWER: ...\nPARTICIPANT: ...",
                "analysis_outline": {
                    "sections": [
                        {"name": "Initial coding (extract codes + verbatim quotes)"},
                        {"name": "Theme generation (cluster codes into themes)"},
                    ],
                    "confirmed_by_user": True,
                },
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    assert result.context_patch.get("_run_qual_pipeline_done") is True
    assert len(result.context_patch["qual_codes"]) == 2
    assert len(result.context_patch["qual_themes"]) == 2
    contents = [m.content for m in result.extra_messages]
    assert any("Initial coding" in c or "codes" in c.lower() for c in contents)
    assert any("Theme" in c or "themes" in c.lower() for c in contents)
