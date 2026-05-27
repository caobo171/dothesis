"""Round-trip tests: synthesized list-editor messages → _extract_answer
returns expected structured values for M4 outline fields."""
from unittest.mock import MagicMock
import json

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent


def _stub_extract_llm(monkeypatch, payload):
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(payload)
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake)


def test_analysis_outline_synthesized_message_extracts_to_dict(monkeypatch):
    """The bulleted 'My analysis outline:\n1. Descriptive Statistics\n2. ...'
    message should extract to a {sections: [...]} dict."""
    _stub_extract_llm(monkeypatch, {
        "field": "analysis_outline",
        "value": {
            "sections": [
                {"name": "Descriptive Statistics"},
                {"name": "Reliability (Cronbach's Alpha)", "thresholds": "α ≥ 0.7"},
            ],
            "confirmed_by_user": True,
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My analysis outline:\n"
            "1. Descriptive Statistics\n"
            "2. Reliability (Cronbach's Alpha) — α ≥ 0.7"
        ))],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "analysis_outline")
    assert isinstance(extracted, dict)
    assert "sections" in extracted
    assert extracted["sections"][1]["name"].startswith("Reliability")


def test_outline_quant_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "outline_quant",
        "value": {"sections": [{"name": "Outer Loadings"}], "confirmed_by_user": True},
    })
    state = {
        "messages": [HumanMessage(content="My analysis outline:\n1. Outer Loadings — ≥ 0.7")],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "outline_quant")
    assert extracted["sections"][0]["name"] == "Outer Loadings"


def test_outline_qual_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "outline_qual",
        "value": {"sections": [
            {"name": "Initial coding"},
            {"name": "Theme generation"},
        ], "confirmed_by_user": True},
    })
    state = {
        "messages": [HumanMessage(content=(
            "My analysis outline:\n1. Initial coding\n2. Theme generation"
        ))],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "outline_qual")
    assert len(extracted["sections"]) == 2


def test_data_paste_free_text_extracts_as_string(monkeypatch):
    """The data_paste field is free-text — the LLM extractor returns it as a string."""
    _stub_extract_llm(monkeypatch, {
        "field": "data_paste",
        "value": "Reliability Statistics\nCronbach's Alpha .840",
    })
    state = {
        "messages": [HumanMessage(content="Reliability Statistics\nCronbach's Alpha .840")],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "data_paste")
    assert "Cronbach" in extracted
