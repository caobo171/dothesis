"""Adapt dothesis's `conceptual_model` (three shapes seen in the wild) to the
`AdvanceModel` dict shape the thesis-stats engine consumes.

Pure function, returns a plain dict — no thesis_stats import here, so this
module loads even when the engine isn't installed; thesis_stats validates the
dict on entry to the ops. Placeholders `average`/`standardDeviation` are only
read by fillform's data *generator*, never by the analyzers, so 0.0 is safe.

Shapes handled:
  1. canonical  {"nodes":[{id,label,questions}], "edges":[{source,target,effect_type}]}
  2. legacy     {"constructs":[str], "paths":[{from,to,hypothesis}]}       (measurement required)
  3. decomposed {"dependent_variable", "independent_variables":[...], "moderator"?}

`measurement` (construct label -> data-file column names) overrides node
`questions`; it is REQUIRED when the model carries no usable indicator columns
(e.g. legacy shape, or nodes whose questions are Likert item texts).
"""
from __future__ import annotations

from typing import Any


def _norm_effect(value: Any) -> str:
    return "negative" if str(value or "").strip().lower().startswith("neg") else "positive"


def _var_node(nid: str, label: str, questions: list[str], likert_scale: int) -> dict:
    return {
        "id": nid,
        "data": {
            "label": label,
            "nodeType": "variable",
            "likertScale": likert_scale,
            "average": 0.0,
            "standardDeviation": 0.0,
        },
        "questions": list(questions),
    }


def _questions_for(label: str, node_questions: Any, measurement: dict) -> list[str]:
    if measurement.get(label):
        return list(measurement[label])
    return list(node_questions or [])


def to_advance_model(conceptual_model: dict, *, measurement: dict[str, list[str]] | None = None,
                     likert_scale: int = 5) -> dict:
    measurement = measurement or {}
    if not isinstance(conceptual_model, dict):
        raise ValueError("conceptual_model must be a dict")

    if "nodes" in conceptual_model and "edges" in conceptual_model:
        return _from_nodes_edges(conceptual_model, measurement, likert_scale)
    if "constructs" in conceptual_model and "paths" in conceptual_model:
        return _from_constructs_paths(conceptual_model, measurement, likert_scale)
    if "dependent_variable" in conceptual_model:
        return _from_decomposition(conceptual_model, measurement, likert_scale)

    raise ValueError(
        "unrecognized conceptual_model shape: expected nodes/edges, "
        "constructs/paths, or dependent_variable/independent_variables"
    )


def _require_questions(missing: list[str]) -> None:
    if missing:
        raise ValueError(
            "constructs have no measurement columns: "
            + ", ".join(sorted(missing))
            + " — supply params.measurement mapping each construct to its data columns"
        )


def _from_nodes_edges(cm: dict, measurement: dict, likert_scale: int) -> dict:
    nodes_out: list[dict] = []
    id_set: set[str] = set()
    label_to_id: dict[str, str] = {}
    missing: list[str] = []

    for node in cm.get("nodes", []):
        label = node.get("label") or node.get("id")
        nid = node.get("id") or label
        qs = _questions_for(label, node.get("questions"), measurement)
        if not qs:
            missing.append(label)
        nodes_out.append(_var_node(nid, label, qs, likert_scale))
        id_set.add(nid)
        label_to_id[str(label).lower()] = nid
    _require_questions(missing)

    edges_out: list[dict] = []
    for i, edge in enumerate(cm.get("edges", [])):
        src = edge.get("source")
        tgt = edge.get("target")
        src = src if src in id_set else label_to_id.get(str(src).lower())
        tgt = tgt if tgt in id_set else label_to_id.get(str(tgt).lower())
        if src is None or tgt is None:
            raise ValueError(f"edge references a construct not present as a node: {edge}")
        et = edge.get("effect_type", edge.get("effectType"))
        edges_out.append({"id": edge.get("id") or f"e{i + 1}", "source": src, "target": tgt,
                          "data": {"effectType": _norm_effect(et)}})

    return {"name": cm.get("name", "conceptual_model"), "nodes": nodes_out, "edges": edges_out}


def _from_constructs_paths(cm: dict, measurement: dict, likert_scale: int) -> dict:
    constructs = cm.get("constructs", [])
    nodes_out: list[dict] = []
    label_to_id: dict[str, str] = {}
    missing: list[str] = []

    for label in constructs:
        qs = _questions_for(label, None, measurement)
        if not qs:
            missing.append(label)
        nodes_out.append(_var_node(label, label, qs, likert_scale))
        label_to_id[str(label).lower()] = label
    _require_questions(missing)

    edges_out: list[dict] = []
    for i, path in enumerate(cm.get("paths", [])):
        frm = label_to_id.get(str(path.get("from")).lower())
        to = label_to_id.get(str(path.get("to")).lower())
        if frm is None or to is None:
            raise ValueError(f"path references a construct not in constructs list: {path}")
        edges_out.append({"id": path.get("id") or f"e{i + 1}", "source": frm, "target": to,
                          "data": {"effectType": _norm_effect(path.get("effect_type"))}})

    return {"name": cm.get("name", "conceptual_model"), "nodes": nodes_out, "edges": edges_out}


def _from_decomposition(cm: dict, measurement: dict, likert_scale: int) -> dict:
    dv = cm.get("dependent_variable")
    ivs = list(cm.get("independent_variables", []))
    moderator = cm.get("moderator")
    if not dv or not ivs:
        raise ValueError("decomposition shape needs dependent_variable and independent_variables")

    labels = [dv] + ivs + ([moderator] if moderator else [])
    missing = [lab for lab in labels if not _questions_for(lab, None, measurement)]
    _require_questions(missing)

    nodes_out = [_var_node(lab, lab, measurement[lab], likert_scale) for lab in labels]
    edges_out = [{"id": f"e{i + 1}", "source": iv, "target": dv, "data": {"effectType": "positive"}}
                 for i, iv in enumerate(ivs)]

    if moderator:
        mod_node_id = f"mod_{moderator}_{ivs[0]}"
        nodes_out.append({
            "id": mod_node_id,
            "data": {
                "label": f"{moderator} x {ivs[0]}",
                "nodeType": "moderate_effect",
                "moderateVariable": moderator,
                "independentVariable": ivs[0],
                "effectType": "positive",
            },
        })
        edges_out.append({"id": f"e_mod", "source": mod_node_id, "target": dv,
                          "data": {"effectType": "positive"}})

    return {"name": cm.get("name", "conceptual_model"), "nodes": nodes_out, "edges": edges_out}
