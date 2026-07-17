"""Deterministic M3 conceptual_model validate-and-repair.

A research model must be ONE connected graph. The guard catches disconnected
IV->DV pairs (the Duolingo order) and repairs additively — never deletes, never
LLM, never raises.
"""
import orchestrator.graph_guard as G
import orchestrator.tools.m5_writing as W

# Order B's exact broken model: two disconnected IV->DV pairs.
_BROKEN = {
    "nodes": [
        {"id": "PU", "label": "Perceived Usefulness"},
        {"id": "ATT", "label": "Attitude", "type": "dependent"},
        {"id": "AS", "label": "Autonomy Support"},
        {"id": "INT", "label": "Intention to Continue Use"},
    ],
    "edges": [
        {"from": "PU", "to": "ATT", "label": "H1: +"},
        {"from": "AS", "to": "INT", "label": "H2: +"},
    ],
}

# A connected valid model (constructs+relationships shape, all reach BI).
_VALID = {
    "constructs": [{"name": "Perceived Usefulness"}, {"name": "Perceived Ease of Use"},
                   {"name": "Attitude"}, {"name": "Behavioral Intention"}],
    "relationships": [
        {"from": "Perceived Usefulness", "to": "Attitude", "hypothesis": "H1"},
        {"from": "Perceived Ease of Use", "to": "Attitude", "hypothesis": "H2"},
        {"from": "Attitude", "to": "Behavioral Intention", "hypothesis": "H3"},
    ],
}


def test_broken_model_detected():
    rep = G.check_conceptual_model(_BROKEN)
    assert rep["applicable"] and not rep["ok"]
    assert rep["components"] == 2


def test_broken_model_repaired_to_one_component():
    fixed, rep = G.repair_conceptual_model(_BROKEN)
    assert rep["repaired"] and rep["edges_added"] >= 1
    # every original edge is still present (additive-only, strict superset)
    orig = {(e["from"], e["to"]) for e in _BROKEN["edges"]}
    got = {(e.get("from") or e.get("source"), e.get("to") or e.get("target")) for e in fixed["edges"]}
    assert orig <= got
    # now a single connected component
    assert G.check_conceptual_model(fixed)["components"] == 1


def test_repaired_model_is_renderable():
    fixed, _ = G.repair_conceptual_model(_BROKEN)
    assert W._conceptual_model_to_mermaid(fixed, "vi")  # non-None fenced block


def test_valid_model_untouched():
    fixed, rep = G.repair_conceptual_model(_VALID)
    assert fixed is _VALID           # same object, byte-identical
    assert rep["ok"] and not rep.get("repaired")


def test_thin_but_connected_not_rewritten():
    # connected 2-node model: too thin to satisfy min_nodes, but repair can't add
    # nodes → return original untouched (only flagged, not rewritten).
    thin = {"nodes": [{"id": "A", "label": "A"}, {"id": "B", "label": "B", "type": "dependent"}],
            "edges": [{"from": "A", "to": "B", "label": "H1"}]}
    fixed, rep = G.repair_conceptual_model(thin)
    assert fixed is thin and not rep.get("repaired")


def test_empty_and_garbage_pass_through():
    for cm in (None, {}, {"conceptual_model": "prose only"}, {"nodes": [], "edges": []}):
        fixed, rep = G.repair_conceptual_model(cm)
        assert fixed is cm and not rep.get("repaired")


def test_variable_decomposition_shape_ok():
    # star model via the decomposition shape → connected, passes untouched.
    cm = {"independent_variables": ["X", "Y", "Z"], "dependent_variable": "W"}
    rep = G.check_conceptual_model(cm)
    assert rep["ok"] and rep["components"] == 1
