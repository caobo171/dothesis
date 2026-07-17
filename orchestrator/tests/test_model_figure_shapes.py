"""The research-model figure must render across every conceptual_model shape
the M3 module emits — not just nodes/edges. Regression for the constructs +
relationships shape (a TAM/SDT model) that rendered NO figure because the
renderer read `nodes`/`edges` and this shape uses `constructs`/`relationships`.
"""
import orchestrator.tools.m5_writing as W


_CONSTRUCTS_RELATIONSHIPS = {
    "constructs": [
        {"name": "Perceived Usefulness", "source": "TAM"},
        {"name": "Perceived Ease of Use", "source": "TAM"},
        {"name": "Attitude", "source": "TAM"},
        {"name": "Behavioral Intention", "source": "TAM"},
        {"name": "Autonomy", "source": "SDT"},
    ],
    "relationships": [
        {"from": "Perceived Usefulness", "to": "Behavioral Intention", "hypothesis": "H1"},
        {"from": "Perceived Ease of Use", "to": "Behavioral Intention", "hypothesis": "H2"},
        {"from": "Perceived Usefulness", "to": "Attitude", "hypothesis": "H3"},
        {"from": "Autonomy", "to": "Perceived Usefulness", "hypothesis": "H4"},
    ],
}


def test_coerce_constructs_relationships_to_graph():
    g = W._coerce_cm(_CONSTRUCTS_RELATIONSHIPS)
    assert len(g["nodes"]) == 5
    assert len(g["edges"]) == 4
    # ids must be mermaid-safe (no spaces) but labels keep the real construct name
    assert all(" " not in n["id"] for n in g["nodes"])
    assert {n["label"] for n in g["nodes"]} >= {"Perceived Usefulness", "Attitude"}
    # relationship endpoints resolve to the same safe ids
    ids = {n["id"] for n in g["nodes"]}
    for e in g["edges"]:
        assert e["from"] in ids and e["to"] in ids


def test_mermaid_renders_for_constructs_relationships():
    mm = W._conceptual_model_to_mermaid(_CONSTRUCTS_RELATIONSHIPS, "vi")
    assert mm and mm.startswith("```mermaid")
    # no spaced node id line like `Perceived Usefulness["..."]` (breaks mermaid parse)
    for line in mm.splitlines():
        stripped = line.strip()
        if stripped.startswith("N") and "[" in stripped:
            assert " " not in stripped.split("[", 1)[0]


def test_construct_labels_collected_for_localization():
    labels = W._collect_construct_labels(_CONSTRUCTS_RELATIONSHIPS, {"items": []})
    assert "Perceived Usefulness" in labels and "Attitude" in labels


def test_coerce_is_noop_for_nodes_edges():
    cm = {"nodes": [{"id": "A", "label": "A"}], "edges": [{"from": "A", "to": "A"}]}
    assert W._coerce_cm(cm) is cm


def test_coerce_handles_variable_decomposition_still():
    cm = {"independent_variables": ["X", "Y"], "dependent_variable": "Z", "moderator": "M"}
    g = W._coerce_cm(cm)
    assert g.get("nodes") and g.get("edges")
