"""Canonical M3 (design) contract + a deterministic normalizer.

M3's `conceptual_model` and `instrument` have been persisted in ~6 different
shapes by different runtimes — interactive FlowChart widget (`source/target`
edges, per-node `questions`), the deep agent / headless tools (`from/to`
edges, a separate flat `instrument.items`), `build_conceptual_model`
(`constructs/paths`), and the import path (a prose-string conceptual_model +
`instrument={"raw": ...}`). Readers kept sprouting per-shape branches and
STILL missed shapes (the mermaid builder read `from/to` and went blank on a
widget-authored model). The cure is ONE canonical shape, coerced at write
time, instead of chased at every reader.

Canonical:
    conceptual_model = {
      "nodes": [{"id", "label", "type"?, "definition"?}],
      "edges": [{"id"?, "source", "target", "hypothesis"?, "effect"?}],
      "description"?: str,          # set when the source was prose only
    }
    instrument = {
      "items": [{"id", "text", "construct"?, "scale"?, "reverse_coded",
                 "attention_check", "source"?}],
      "preamble"?: str,
      "raw"?: str,                  # preserved when the upload was unparsed
    }

`normalize_m3(m3)` coerces every known legacy shape into the canonical pair and
is idempotent (canonical in → identical canonical out). It RAISES
`M3ShapeError` on a genuinely unrecognizable value — safe because every M3
producer is an LLM in a ReAct loop, so a `commit_slice` error reads as a retry
prompt, not a 500.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError


class M3ShapeError(ValueError):
    """A conceptual_model / instrument value could not be normalized."""


# --- canonical pydantic models (validate the normalizer's OUTPUT) -----------

class _Node(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    label: str
    type: str | None = None
    definition: str | None = None


class _Edge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = None
    source: str
    target: str
    hypothesis: str | None = None
    effect: str | None = None


class M3ConceptualModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nodes: list[_Node] = []
    edges: list[_Edge] = []
    description: str | None = None


class _Item(BaseModel):
    # NB: `construct` shadows pydantic's deprecated BaseModel.construct
    # classmethod (harmless UserWarning at import); the field name must stay to
    # match stored data.
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str
    construct: str | None = None
    scale: str | None = None
    reverse_coded: bool = False
    attention_check: bool = False
    source: str | None = None


class M3Instrument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[_Item] = []
    preamble: str | None = None
    raw: str | None = None


# --- coercion helpers -------------------------------------------------------

def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _norm_node(n: Any) -> tuple[dict | None, list[str]]:
    """Return (canonical node, questions-stripped-off-the-node)."""
    if not isinstance(n, dict):
        return None, []
    nid = _s(n.get("id") or n.get("label"))
    if not nid:
        return None, []
    node = {"id": nid, "label": _s(n.get("label") or n.get("id")) or nid}
    if n.get("type"):
        node["type"] = _s(n.get("type"))
    if n.get("definition"):
        node["definition"] = _s(n.get("definition"))
    questions = [_s(q) for q in (n.get("questions") or []) if _s(q)]
    return node, questions


def _norm_edge(e: Any) -> dict | None:
    if not isinstance(e, dict):
        return None
    source = _s(e.get("source") or e.get("from"))
    target = _s(e.get("target") or e.get("to"))
    if not source or not target:
        return None
    edge: dict = {"source": source, "target": target}
    if e.get("id"):
        edge["id"] = _s(e.get("id"))
    hyp = _s(e.get("hypothesis") or e.get("label"))
    if hyp:
        edge["hypothesis"] = hyp
    eff = _s(e.get("effect") or e.get("effect_type"))
    if eff:
        edge["effect"] = eff
    return edge


def _norm_item(it: Any, idx: int, construct: str | None = None) -> dict | None:
    if not isinstance(it, dict):
        return None
    text = _s(it.get("text") or it.get("q") or it.get("question"))
    if not text:
        return None
    item: dict = {
        "id": _s(it.get("id")) or f"I{idx + 1}",
        "text": text,
        "reverse_coded": bool(it.get("reverse_coded")),
        "attention_check": bool(it.get("attention_check")),
    }
    c = _s(it.get("construct")) or (construct or "")
    if c:
        item["construct"] = c
    if it.get("scale"):
        item["scale"] = _s(it.get("scale"))
    if it.get("source"):
        item["source"] = _s(it.get("source"))
    return item


# --- public API -------------------------------------------------------------

def normalize_conceptual_model(cm: Any) -> tuple[dict, list[dict]]:
    """Coerce any known conceptual_model shape → (canonical, extracted_items).

    `extracted_items` are questionnaire items that lived on `nodes[].questions`
    (the interactive shape) and must be moved to the instrument.
    """
    if cm is None:
        return {"nodes": [], "edges": []}, []
    if isinstance(cm, str):
        desc = cm.strip()
        return ({"nodes": [], "edges": [], "description": desc} if desc
                else {"nodes": [], "edges": []}), []
    if not isinstance(cm, dict):
        raise M3ShapeError(f"conceptual_model must be dict/str/None, got {type(cm).__name__}")

    out: dict = {"nodes": [], "edges": []}
    extracted: list[dict] = []

    # import_work nests a prose model under the same key name; canonical stores
    # it as `description`. Read both so re-normalizing is lossless (idempotent).
    nested = cm.get("conceptual_model")
    desc = nested if isinstance(nested, str) else cm.get("description")
    if isinstance(desc, str) and desc.strip():
        out["description"] = desc.strip()

    raw_nodes = cm.get("nodes")
    if not raw_nodes and cm.get("constructs"):
        raw_nodes = cm.get("constructs")
    for n in (raw_nodes or []):
        if isinstance(n, str):  # constructs: ["A", "B"]
            node, qs = {"id": _s(n), "label": _s(n)}, []
        else:
            node, qs = _norm_node(n)
        if not node:
            continue
        out["nodes"].append(node)
        for i, q in enumerate(qs):
            extracted.append({"id": f"{node['id']}{i + 1}", "text": q,
                              "reverse_coded": False, "attention_check": False,
                              "construct": node["id"]})

    raw_edges = cm.get("edges") or cm.get("paths") or []
    for e in raw_edges:
        edge = _norm_edge(e)
        if edge:
            out["edges"].append(edge)

    # An edge may reference a construct that was never declared as a node
    # (common when a producer emits only paths, or names a construct in a path
    # it forgot to list). Synthesize the missing node rather than DROP the edge
    # — dropping would silently lose a hypothesis; a bare node is lossless and
    # keeps the model valid (every edge endpoint exists).
    declared = {n["id"] for n in out["nodes"]}
    for edge in out["edges"]:
        for endpoint in (edge["source"], edge["target"]):
            if endpoint not in declared:
                out["nodes"].append({"id": endpoint, "label": endpoint})
                declared.add(endpoint)

    return out, extracted


def normalize_instrument(inst: Any, extracted_items: list[dict] | None = None) -> dict:
    """Coerce any known instrument shape → canonical. `extracted_items` (from
    conceptual_model nodes) are used only when the instrument carries no items
    of its own, so a re-run can't duplicate them."""
    out: dict = {"items": []}
    own: list[dict] = []
    if isinstance(inst, list):
        raw_items = inst
        raw = preamble = None
    elif isinstance(inst, dict):
        raw_items = inst.get("items") or []
        raw = inst.get("raw")
        preamble = inst.get("preamble")
        if raw and _s(raw):
            out["raw"] = _s(raw)
        if preamble and _s(preamble):
            out["preamble"] = _s(preamble)
    elif inst is None:
        raw_items = []
    else:
        raise M3ShapeError(f"instrument must be dict/list/None, got {type(inst).__name__}")

    for i, it in enumerate(raw_items):
        item = _norm_item(it, i)
        if item:
            own.append(item)

    out["items"] = own if own else list(extracted_items or [])
    return out


def normalize_m3(m3: dict | None) -> dict:
    """Normalize an M3 slice's conceptual_model + instrument to the canonical
    pair, validate, and return the slice with those two keys replaced (all
    other keys passed through untouched). Idempotent. Raises M3ShapeError on an
    unrecognizable shape."""
    if m3 is None:
        return {}
    if not isinstance(m3, dict):
        raise M3ShapeError(f"m3 slice must be a dict, got {type(m3).__name__}")

    out = dict(m3)
    has_cm = "conceptual_model" in m3
    has_inst = "instrument" in m3
    if not has_cm and not has_inst:
        return out  # nothing M3-shaped to normalize

    cm, extracted = normalize_conceptual_model(m3.get("conceptual_model"))
    inst = normalize_instrument(m3.get("instrument"), extracted)

    try:
        cm = M3ConceptualModel.model_validate(cm).model_dump(exclude_none=True)
        inst = M3Instrument.model_validate(inst).model_dump(exclude_none=True)
    except ValidationError as e:  # normalizer produced a non-canonical shape
        raise M3ShapeError(f"normalized M3 failed validation: {e}") from e

    if has_cm or cm.get("nodes") or cm.get("edges") or cm.get("description"):
        out["conceptual_model"] = cm
    if has_inst or inst.get("items") or inst.get("raw"):
        out["instrument"] = inst
    return out
