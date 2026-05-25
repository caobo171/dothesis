import json
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m3_design import (
    build_conceptual_model, estimate_sample_size, recommend_methodology,
    suggest_scale_items,
)


def test_recommend_methodology_returns_structured(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "design": "PLS-SEM", "tool": "SmartPLS",
        "rationale": "latent variables + small sample"
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    out = recommend_methodology.invoke({
        "research_question": "Does TL affect EE?",
        "paradigm": "quantitative",
    })
    assert out["design"] == "PLS-SEM"
    assert out["tool"] == "SmartPLS"


def test_build_conceptual_model_returns_constructs_and_paths(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "constructs": ["TL", "EE", "Trust"],
        "paths": [
            {"from": "TL", "to": "EE", "hypothesis": "H1: TL → EE (+)"},
            {"from": "TL", "to": "Trust", "hypothesis": "H2: TL → Trust (+)"},
        ],
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    out = build_conceptual_model.invoke({
        "constructs": ["TL", "EE", "Trust"],
        "research_question": "Does TL affect EE?",
    })
    assert "TL" in out["constructs"]
    assert len(out["paths"]) == 2


def test_suggest_scale_items_returns_items(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"id": "TL1", "text": "My supervisor inspires me with a vision."},
        {"id": "TL2", "text": "My supervisor leads by example."},
    ])
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    items = suggest_scale_items.invoke({"construct": "Transformational Leadership"})
    assert len(items) == 2
    assert items[0]["id"] == "TL1"


def test_estimate_sample_size_quant_pls_sem():
    out = estimate_sample_size.invoke({
        "model": {"design": "PLS-SEM", "n_constructs": 4, "max_arrows_per_construct": 3},
    })
    assert isinstance(out, dict)
    assert out["min_size"] >= 100
    assert out["recommended"] >= out["min_size"]


def test_estimate_sample_size_qualitative():
    out = estimate_sample_size.invoke({
        "model": {"design": "Thematic Analysis"},
    })
    assert out["min_size"] <= 30
