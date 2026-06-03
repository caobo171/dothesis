import json
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m3_design import (
    build_conceptual_model, estimate_sample_size, recommend_methodology,
    suggest_scale_items, suggest_scale_items_batch,
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


def test_build_conceptual_model_with_empty_constructs_asks_llm_to_propose_them(monkeypatch):
    """User-reported bug: M3 said 'I've pre-filled a list of paths' but the
    list_editor below was empty. Root cause: render_hint calls
    build_conceptual_model with constructs=[] (the user hasn't filled the
    model yet), and the old prompt phrased the task as 'given constructs',
    so the LLM took empty constructs → no model.

    Now: when constructs is empty the prompt explicitly asks the LLM to
    PROPOSE constructs from the RQ. Test pins that the prompt sent to the
    LLM in that case names the inference task."""
    captured = {}
    def fake_invoke(prompt):
        captured["prompt"] = prompt
        resp = MagicMock()
        resp.content = json.dumps({
            "constructs": ["TikTok use", "Brand perception", "Purchase intent"],
            "paths": [
                {"from": "TikTok use", "to": "Brand perception",
                 "hypothesis": "H1"},
                {"from": "Brand perception", "to": "Purchase intent",
                 "hypothesis": "H2"},
            ],
        })
        return resp
    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = fake_invoke
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = build_conceptual_model.invoke({
        "constructs": [],  # nothing prefilled — the failure case
        "research_question": "How does TikTok engagement affect Gen Z purchases?",
    })
    # Prompt must invite the LLM to invent constructs, not just paths.
    p = captured["prompt"].lower()
    assert ("propose" in p and "constructs" in p), (
        "empty-constructs prompt should ask the LLM to PROPOSE constructs, "
        f"got: {captured['prompt'][:300]}")
    # And the model returns a non-empty path list so the list_editor lands
    # populated, matching the user-facing 'pre-filled' message.
    assert len(out["paths"]) >= 2


def test_build_conceptual_model_returns_fallback_on_llm_timeout(monkeypatch):
    """Regression for the user-reported 'typing dots stay forever' hang.

    Gemini occasionally blocks for 5+ minutes on a single invoke; without a
    bounded wrapper the agent step freezes the whole graph turn. Tools must
    catch BoundedInvokeTimeout (and generic transient errors) and return
    their safe fallback so the user sees *something* instead of an infinite
    spinner.
    """
    from orchestrator.agents.base import BoundedInvokeTimeout

    def boom(*_a, **_kw):
        # Simulate Gemini hanging past the wall-clock cap.
        raise BoundedInvokeTimeout("simulated 30s cap exceeded")

    fake_llm = MagicMock()
    fake_llm.invoke.side_effect = boom
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)
    # Force bounded_invoke to surface the timeout immediately (bypass its
    # internal retry/backoff so the test doesn't wait).
    monkeypatch.setattr(
        "orchestrator.tools.m3_design.bounded_invoke",
        lambda *a, **kw: (_ for _ in ()).throw(BoundedInvokeTimeout("test")),
    )

    out = build_conceptual_model.invoke({
        "constructs": ["A"],
        "research_question": "Does X affect Y?",
    })
    # Fallback shape so downstream rendering keeps a stable schema.
    assert out == {"constructs": ["A"], "paths": []}


def test_build_conceptual_model_strips_markdown_code_fences(monkeypatch):
    """Regression for the user-reported 'still showing nothing' bug after
    commit 7fd07db. Gemini frequently wraps its JSON in ```json … ``` fences;
    json.loads on the raw fenced string raises JSONDecodeError, hits the
    except branch, and returns the empty-paths fallback. The UI then renders
    the conceptual_model card with zero items even though the LLM produced a
    perfectly fine model. Tools must strip code fences before parsing — the
    same pattern base.py already uses for every JSON call.
    """
    fenced = "```json\n" + json.dumps({
        "constructs": ["A", "B"],
        "paths": [{"from": "A", "to": "B", "hypothesis": "H1"}],
    }) + "\n```"
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = fenced
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = build_conceptual_model.invoke({
        "constructs": [],
        "research_question": "Does TL affect EE?",
    })
    # Without fence-stripping this asserts on the empty fallback and fails.
    assert out["paths"], "fenced LLM JSON should still produce non-empty paths"
    assert out["paths"][0]["from"] == "A"


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


def test_suggest_scale_items_batch_uses_single_llm_call(monkeypatch):
    """Batch tool must hit Gemini exactly once for N constructs (vs N calls
    in the legacy per-construct path). This is the whole point of the
    refactor — fixes the user-reported 'typing dots forever' bug and cuts
    token spend ~N×.
    """
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "TL":    [{"id": "TL1", "text": "My supervisor inspires me."},
                  {"id": "TL2", "text": "My supervisor articulates a clear vision."}],
        "EE":    [{"id": "EE1", "text": "I feel engaged at work."}],
        "Trust": [{"id": "TR1", "text": "I trust my supervisor."}],
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_scale_items_batch.invoke({
        "constructs": ["TL", "EE", "Trust"],
        "n": 5,
    })
    # Exactly ONE invoke, regardless of construct count.
    assert fake_llm.invoke.call_count == 1
    # Every requested construct is present as a key.
    assert set(out.keys()) == {"TL", "EE", "Trust"}
    assert out["TL"][0]["id"] == "TL1"
    assert out["Trust"][0]["text"].startswith("I trust")


def test_suggest_scale_items_batch_normalizes_dropped_constructs(monkeypatch):
    """If the LLM drops a construct from its response, the tool still ships
    that key mapped to [] so the caller can iterate the requested constructs
    without KeyError or skipped widget rows.
    """
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "TL": [{"id": "TL1", "text": "..."}],
        # EE missing entirely — LLM dropped it.
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_scale_items_batch.invoke({"constructs": ["TL", "EE"], "n": 3})
    assert out["TL"], "present construct keeps its items"
    assert out["EE"] == [], "missing construct is normalized to empty list"


def test_suggest_scale_items_batch_empty_input_skips_llm(monkeypatch):
    """No constructs = no LLM call. Avoids a wasted round trip when the
    conceptual_model is empty (e.g., user hasn't filled it yet)."""
    fake_llm = MagicMock()
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_scale_items_batch.invoke({"constructs": [], "n": 5})
    assert out == {}
    assert fake_llm.invoke.call_count == 0


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


def test_suggest_themes_returns_structured(monkeypatch):
    from orchestrator.tools.m3_design import suggest_themes

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"id": "t1", "theme": "Cách thức lãnh đạo",
         "sub_themes": ["Tầm nhìn", "Giao tiếp"]},
        {"id": "t2", "theme": "Biểu hiện gắn kết",
         "sub_themes": ["Nhận thức", "Cảm xúc"]},
    ])
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_themes.invoke({
        "research_question": "How does transformational leadership affect engagement?",
        "paradigm": "qualitative",
        "gaps_summary": "",
    })
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["theme"] == "Cách thức lãnh đạo"
    assert "Tầm nhìn" in out[0]["sub_themes"]


def test_suggest_themes_returns_empty_on_malformed(monkeypatch):
    from orchestrator.tools.m3_design import suggest_themes

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_themes.invoke({
        "research_question": "x", "paradigm": "qualitative", "gaps_summary": "",
    })
    assert out == []


def test_compose_interview_guide_returns_structured(monkeypatch):
    from orchestrator.tools.m3_design import compose_interview_guide

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "sections": [
            {"phase": "intro", "time_minutes": 5,
             "questions": [{"q": "Tell me about your role.", "probes": []}]},
            {"phase": "main", "time_minutes": 40,
             "questions": [
                 {"q": "How does your manager inspire you?",
                  "probes": ["Can you give an example?"]},
             ]},
            {"phase": "closing", "time_minutes": 5,
             "questions": [{"q": "Anything you'd like to add?", "probes": []}]},
        ]
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = compose_interview_guide.invoke({
        "themes": [{"theme": "Leadership style", "sub_themes": ["vision"]}],
        "research_question": "How does TL affect EE?",
    })
    assert "sections" in out
    assert len(out["sections"]) == 3
    assert out["sections"][1]["questions"][0]["probes"] == ["Can you give an example?"]


def test_compose_interview_guide_falls_back_on_malformed(monkeypatch):
    from orchestrator.tools.m3_design import compose_interview_guide

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "garbage"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = compose_interview_guide.invoke({
        "themes": [], "research_question": "x",
    })
    # Fallback: one minimal main-phase section
    assert "sections" in out
    assert len(out["sections"]) >= 1


def test_suggest_purposive_criteria_returns_structured(monkeypatch):
    from orchestrator.tools.m3_design import suggest_purposive_criteria

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "criteria": [
            "Employees at SMEs (< 300 staff)",
            "At least 6 months tenure",
            "Has a direct line manager",
        ],
        "strategies": ["Snowball", "Maximum variation"],
        "saturation_min": 10, "saturation_max": 15,
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_purposive_criteria.invoke({
        "research_question": "How does TL affect EE in Vietnamese SMEs?",
        "paradigm": "qualitative",
    })
    assert "criteria" in out
    assert len(out["criteria"]) == 3
    assert out["saturation_min"] == 10


def test_suggest_purposive_criteria_falls_back_on_malformed(monkeypatch):
    from orchestrator.tools.m3_design import suggest_purposive_criteria

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "{ broken"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_purposive_criteria.invoke({
        "research_question": "x", "paradigm": "qualitative",
    })
    assert "criteria" in out
    assert isinstance(out["criteria"], list)
