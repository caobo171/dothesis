"""conceptual_model -> AdvanceModel adapter: three real shapes + error cases.

The adapter returns a plain dict (so the module imports even when thesis_stats
is absent); when thesis_stats is installed we assert the dict validates.
"""
import pytest

from agent.tools.model_adapter import to_advance_model


def _validates(model_dict):
    ts = pytest.importorskip("thesis_stats")
    ts.AdvanceModel.model_validate(model_dict)


# --- Shape 1: canonical nodes/edges -----------------------------------------

def test_nodes_edges_shape():
    cm = {
        "nodes": [
            {"id": "trust", "label": "Trust", "questions": ["T1", "T2", "T3"]},
            {"id": "sat", "label": "Satisfaction", "questions": ["S1", "S2", "S3"]},
        ],
        "edges": [{"id": "e1", "source": "trust", "target": "sat",
                   "hypothesis": "H1", "effect_type": "negative"}],
    }
    out = to_advance_model(cm)
    labels = {n["data"]["label"] for n in out["nodes"]}
    assert labels == {"Trust", "Satisfaction"}
    assert all(n["data"]["nodeType"] == "variable" for n in out["nodes"])
    assert out["edges"][0]["data"]["effectType"] == "negative"
    _validates(out)


def test_nodes_edges_measurement_overrides_questions():
    cm = {
        "nodes": [
            {"id": "t", "label": "Trust", "questions": ["I trust it", "It is reliable"]},
            {"id": "s", "label": "Sat", "questions": ["I am happy"]},
        ],
        "edges": [{"source": "t", "target": "s"}],
    }
    out = to_advance_model(cm, measurement={"Trust": ["T1", "T2"], "Sat": ["S1", "S2"]})
    trust = next(n for n in out["nodes"] if n["data"]["label"] == "Trust")
    assert trust["questions"] == ["T1", "T2"]  # columns, not item texts
    _validates(out)


# --- Shape 2: legacy constructs/paths ---------------------------------------

def test_constructs_paths_shape_requires_measurement():
    cm = {"constructs": ["Trust", "Satisfaction"],
          "paths": [{"from": "Trust", "to": "Satisfaction", "hypothesis": "H1"}]}
    with pytest.raises(ValueError):
        to_advance_model(cm)  # no questions anywhere
    out = to_advance_model(cm, measurement={"Trust": ["T1", "T2"], "Satisfaction": ["S1", "S2"]})
    assert len(out["nodes"]) == 2 and len(out["edges"]) == 1
    _validates(out)


def test_constructs_paths_case_insensitive_path_match():
    cm = {"constructs": ["Trust", "Satisfaction"],
          "paths": [{"from": "trust", "to": "satisfaction"}]}
    out = to_advance_model(cm, measurement={"Trust": ["T1", "T2"], "Satisfaction": ["S1", "S2"]})
    e = out["edges"][0]
    src = next(n for n in out["nodes"] if n["id"] == e["source"])
    assert src["data"]["label"] == "Trust"
    _validates(out)


# --- Shape 3: variable decomposition (with moderator) -----------------------

def test_decomposition_with_moderator_emits_moderate_effect_node():
    cm = {"dependent_variable": "Purchase", "independent_variables": ["Trust", "Price"],
          "moderator": "Income"}
    out = to_advance_model(cm, measurement={
        "Purchase": ["P1", "P2"], "Trust": ["T1", "T2"], "Price": ["PR1", "PR2"],
        "Income": ["I1", "I2"]})
    types = [n["data"]["nodeType"] for n in out["nodes"]]
    assert "moderate_effect" in types
    mod = next(n for n in out["nodes"] if n["data"]["nodeType"] == "moderate_effect")
    assert mod["data"]["moderateVariable"] and mod["data"]["independentVariable"]
    _validates(out)


def test_decomposition_without_moderator_is_star_graph():
    cm = {"dependent_variable": "Y", "independent_variables": ["A", "B"]}
    out = to_advance_model(cm, measurement={"Y": ["Y1", "Y2"], "A": ["A1", "A2"], "B": ["B1", "B2"]})
    assert all(n["data"]["nodeType"] == "variable" for n in out["nodes"])
    assert len(out["edges"]) == 2  # A->Y, B->Y
    _validates(out)


# --- Error cases ------------------------------------------------------------

def test_unknown_construct_in_edge_raises():
    cm = {"nodes": [{"id": "a", "label": "A", "questions": ["A1", "A2"]}],
          "edges": [{"source": "a", "target": "ghost"}]}
    with pytest.raises(ValueError):
        to_advance_model(cm)


def test_empty_or_unrecognized_shape_raises():
    with pytest.raises(ValueError):
        to_advance_model({})
    with pytest.raises(ValueError):
        to_advance_model({"something": "else"})
