"""Round-trip tests: synthesized list-editor messages → _extract_answer
returns the expected structured list for each M3 list field."""
from unittest.mock import MagicMock
import json

from langchain_core.messages import HumanMessage

from orchestrator.agents.m3_design import M3Agent


def _stub_extract_llm(monkeypatch, payload):
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(payload)
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)


def test_themes_synthesized_message_extracts_to_list(monkeypatch):
    """Synthesized 'My themes are: ...' message → list of theme dicts."""
    _stub_extract_llm(monkeypatch, {
        "field": "themes",
        "value": [
            {"id": "t1", "theme": "Cách thức lãnh đạo",
             "sub_themes": ["Tầm nhìn", "Giao tiếp"]},
            {"id": "t2", "theme": "Biểu hiện gắn kết", "sub_themes": []},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My themes are:\n"
            "- Cách thức lãnh đạo (Sub: Tầm nhìn, Giao tiếp)\n"
            "- Biểu hiện gắn kết"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "themes")
    assert isinstance(extracted, list)
    assert extracted[0]["theme"] == "Cách thức lãnh đạo"


def test_purposive_criteria_extracts_to_list(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "purposive_criteria",
        "value": [
            {"criterion": "At SME"},
            {"criterion": "6mo+ tenure"},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My sampling criteria:\n- At SME\n- 6mo+ tenure"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "purposive_criteria")
    assert isinstance(extracted, list)
    assert extracted[0]["criterion"] == "At SME"


def test_conceptual_model_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "conceptual_model",
        "value": {
            "constructs": ["TL", "EE", "Trust"],
            "paths": [
                {"from": "TL", "to": "EE", "hypothesis": "H1: TL → EE positive"},
                {"from": "TL", "to": "Trust", "hypothesis": "H2: TL → Trust positive"},
            ],
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My conceptual model paths:\n"
            "- TL → EE (H1: TL → EE positive)\n"
            "- TL → Trust (H2: TL → Trust positive)"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "conceptual_model")
    assert isinstance(extracted, dict)
    assert len(extracted["paths"]) == 2


def test_scale_items_extracts_to_list_of_constructs(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "scale_items",
        "value": [
            {"construct": "TL", "items": ["TL1: ...", "TL2: ..."]},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My scale items:\nConstruct TL:\n- TL1: ...\n- TL2: ..."
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "scale_items")
    assert isinstance(extracted, list)
    assert extracted[0]["construct"] == "TL"


def test_interview_guide_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "interview_guide",
        "value": {
            "sections": [
                {"phase": "main", "questions": [
                    {"q": "How does your manager inspire you?",
                     "probes": ["Can you give an example?"]},
                ]},
            ],
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My interview guide:\n"
            "[main] How does your manager inspire you?\n"
            "  Probe: Can you give an example?"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "interview_guide")
    assert "sections" in extracted
