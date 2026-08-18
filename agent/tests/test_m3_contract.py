"""Golden-fixture tests for the canonical M3 contract + normalizer.

Every M3 shape we've seen in the wild must normalize to the SAME canonical
pair, be idempotent, and validate. New drift must raise, not silently mangle.
"""
import pytest

from agent.m3_contract import (
    M3ShapeError,
    M3ConceptualModel,
    M3Instrument,
    normalize_m3,
)

# --- the six wild shapes ----------------------------------------------------

# 1) Interactive FlowChart widget: source/target edges + per-node questions.
INTERACTIVE = {
    "conceptual_model": {
        "nodes": [
            {"id": "PU", "label": "Perceived usefulness", "type": "independent",
             "questions": ["PU is useful", "PU helps me"]},
            {"id": "PI", "label": "Purchase intention", "type": "dependent",
             "questions": ["I will buy"]},
        ],
        "edges": [{"id": "H1", "source": "PU", "target": "PI",
                   "hypothesis": "H1: PU -> PI", "effect_type": "positive"}],
    },
}

# 2) Headless / deep agent: from/to edges, no node questions, flat instrument.
#    (This mirrors the real prod row for project 15dc3cd9.)
HEADLESS = {
    "conceptual_model": {
        "nodes": [
            {"id": "GO", "label": "Định hướng Mục tiêu", "type": "independent",
             "definition": "..."},
            {"id": "BO", "label": "Kết quả Hành vi", "type": "dependent"},
        ],
        "edges": [{"to": "BO", "from": "GO", "label": "H1: +"}],
    },
    "instrument": {
        "items": [
            {"id": "GO1", "text": "Tôi đặt mục tiêu.", "construct": "GO",
             "reverse_coded": False},
        ],
    },
}

# 3) build_conceptual_model output: constructs/paths.
CONSTRUCTS_PATHS = {
    "conceptual_model": {
        "constructs": ["Trust", "Loyalty"],
        "paths": [{"from": "Trust", "to": "Loyalty", "hypothesis": "H1: +"}],
    },
}

# 4) import_work: prose-string model nested under the same key + raw instrument.
IMPORT = {
    "conceptual_model": {
        "constructs": [{"id": "A", "label": "Alpha"}],
        "paths": [{"from": "A", "to": "B"}],  # B undeclared -> synthesized as a node
        "conceptual_model": "A model expressed only as prose.",
    },
    "instrument": {"raw": "Q1. Rate 1-5 ..."},
}

# 5) already canonical.
CANONICAL = {
    "conceptual_model": {
        "nodes": [{"id": "PU", "label": "Perceived usefulness"}],
        "edges": [{"source": "PU", "target": "PI", "hypothesis": "H1"}],
    },
    "instrument": {
        "items": [{"id": "PU1", "text": "useful", "construct": "PU",
                   "reverse_coded": False, "attention_check": False}],
    },
}

# 6) empty / missing.
EMPTY = {"methodology": {"paradigm": "quantitative"}}

# 7) variable-decomposition (headless variant, no nodes/edges).
VAR_DECOMP = {
    "conceptual_model": {
        "moderator": "Trust",
        "theoretical_bases": ["TAM", "UTAUT2"],
        "dependent_variable": "Behavioral Intention",
        "independent_variables": ["Perceived Usefulness", "Perceived Ease of Use"],
    },
}

ALL = {
    "interactive": INTERACTIVE, "headless": HEADLESS,
    "constructs_paths": CONSTRUCTS_PATHS, "import": IMPORT,
    "canonical": CANONICAL, "empty": EMPTY, "var_decomp": VAR_DECOMP,
}


def test_variable_decomposition_expands_to_graph():
    out = normalize_m3(VAR_DECOMP)
    cm = out["conceptual_model"]
    labels = {n["label"] for n in cm["nodes"]}
    assert {"Behavioral Intention", "Perceived Usefulness",
            "Perceived Ease of Use", "Trust"} <= labels
    # every independent var + the moderator points at the dependent var (DV)
    assert len(cm["edges"]) == 3
    assert all(e["target"] == "DV" for e in cm["edges"])


@pytest.mark.parametrize("name", list(ALL))
def test_normalizes_and_validates(name):
    out = normalize_m3(ALL[name])
    # Both canonical objects must pass their own schema.
    M3ConceptualModel.model_validate(out.get("conceptual_model") or {})
    M3Instrument.model_validate(out.get("instrument") or {})


@pytest.mark.parametrize("name", list(ALL))
def test_idempotent(name):
    once = normalize_m3(ALL[name])
    twice = normalize_m3(once)
    assert once == twice, f"{name} not idempotent"


def test_interactive_questions_move_to_instrument():
    out = normalize_m3(INTERACTIVE)
    # questions stripped off the nodes ...
    assert all("questions" not in n for n in out["conceptual_model"]["nodes"])
    # ... and became instrument items keyed by construct.
    items = out["instrument"]["items"]
    assert {i["id"] for i in items} == {"PU1", "PU2", "PI1"}
    assert all(i["construct"] in {"PU", "PI"} for i in items)


def test_headless_from_to_becomes_source_target():
    out = normalize_m3(HEADLESS)
    edge = out["conceptual_model"]["edges"][0]
    assert edge["source"] == "GO" and edge["target"] == "BO"
    assert edge["hypothesis"] == "H1: +"  # from the `label`
    # instrument items preserved, not clobbered by (empty) extracted list.
    assert out["instrument"]["items"][0]["id"] == "GO1"


def test_constructs_paths_becomes_nodes_edges():
    out = normalize_m3(CONSTRUCTS_PATHS)
    cm = out["conceptual_model"]
    assert {n["id"] for n in cm["nodes"]} == {"Trust", "Loyalty"}
    assert cm["edges"][0] == {"source": "Trust", "target": "Loyalty",
                              "hypothesis": "H1: +"}


def test_import_prose_and_raw_preserved():
    out = normalize_m3(IMPORT)
    assert out["conceptual_model"]["description"] == "A model expressed only as prose."
    # undeclared endpoint B is synthesized as a node so the edge stays valid.
    assert {n["id"] for n in out["conceptual_model"]["nodes"]} == {"A", "B"}
    assert out["conceptual_model"]["edges"] == [{"source": "A", "target": "B"}]
    assert out["instrument"]["raw"].startswith("Q1.")


def test_legacy_regression_prose_backfills_canonical_graph():
    prose = (
        "Quantitative branch. Regression model: Intention = β₀ + β₁·PB "
        "+ β₂·PD + β₃·PDT + ε."
    )
    out = normalize_m3({"conceptual_model": prose})
    cm = out["conceptual_model"]
    assert [node["id"] for node in cm["nodes"]] == ["PB", "PD", "PDT", "Intention"]
    assert [(edge["source"], edge["target"]) for edge in cm["edges"]] == [
        ("PB", "Intention"), ("PD", "Intention"), ("PDT", "Intention")
    ]
    assert cm["description"] == prose


def test_unstructured_legacy_prose_is_preserved_without_invented_edges():
    out = normalize_m3({"conceptual_model": "A broad conceptual discussion."})
    assert out["conceptual_model"] == {
        "nodes": [], "edges": [], "description": "A broad conceptual discussion."
    }


def test_unknown_shape_raises():
    with pytest.raises(M3ShapeError):
        normalize_m3({"conceptual_model": 42})
    with pytest.raises(M3ShapeError):
        normalize_m3({"instrument": 42})
