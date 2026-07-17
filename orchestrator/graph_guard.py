"""Deterministic validate-and-repair for the M3 conceptual_model.

A research model must be ONE connected graph converging on a single dependent
construct. The M3 skill's "parsimony" guidance sometimes makes the LLM emit two
disconnected IV->DV pairs (structurally invalid — see the Duolingo order). This
module catches that WITHOUT an LLM: it only ADDS edges (never deletes, never
regenerates), so a repaired model is a strict superset of the input and can never
be worse. Any unrecognizable / empty / description-only shape passes through
untouched, and every failure degrades to the original — this runs on the live
commit path and must never raise or reject a commit.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_MIN_NODES = 3
# Outcome/DV lexicon (EN + VI) — a fallback when there is no typed dependent node.
_DV_LEXICON = (
    "intention", "ý định", "satisfaction", "hài lòng", "adoption", "chấp nhận",
    "performance", "behavior", "hành vi", "outcome", "loyalty", "trung thành",
    "effectiveness", "hiệu quả", "continuance", "tiếp tục", "usage", "sử dụng",
)


def _src(e: dict) -> str:
    return str(e.get("from") or e.get("source") or "").strip()


def _tgt(e: dict) -> str:
    return str(e.get("to") or e.get("target") or "").strip()


def _is_moderation(e: dict, ntype: dict) -> bool:
    return (str(e.get("effect") or "").lower().startswith("moderat")
            or ntype.get(_src(e)) == "moderator")


def _coerce(cm) -> dict:
    # Reuse the renderer's normalizer so check + repair see one grammar and the
    # repaired output is renderable by construction. Lazy import (heavy module).
    from orchestrator.tools.m5_writing import _coerce_cm  # noqa: PLC0415
    return _coerce_cm(cm or {})


def check_conceptual_model(cm, min_nodes: int = _MIN_NODES) -> dict:
    """Return {applicable, ok, reasons, components, n_nodes, n_edges}. Never raises."""
    try:
        g = _coerce(cm)
        nodes = [n for n in (g.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "").strip()]
        edges = [e for e in (g.get("edges") or []) if isinstance(e, dict) and _src(e) and _tgt(e)]
        ids = [str(n["id"]).strip() for n in nodes]
        if len(ids) < 1 or not edges:
            return {"applicable": False, "ok": True, "reasons": ["empty/edgeless model"]}

        # Union-find over UNDIRECTED edges → connected components.
        parent = {i: i for i in ids}

        def find(x):
            while parent.get(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in edges:
            a, b = find(_src(e)), find(_tgt(e))
            if a in parent and b in parent and a != b:
                parent[a] = b
        roots = {find(i) for i in ids}

        reasons = []
        if len(roots) > 1:
            reasons.append(f"{len(roots)} disconnected components")
        if len(ids) < min_nodes:
            reasons.append(f"only {len(ids)} constructs (min {min_nodes})")
        return {"applicable": True, "ok": not reasons, "reasons": reasons,
                "components": len(roots), "n_nodes": len(ids), "n_edges": len(edges)}
    except Exception:
        logger.exception("graph_guard.check failed — treating as ok")
        return {"applicable": False, "ok": True, "reasons": ["check error"]}


def _pick_outcome(ids, nodes, edges, ntype) -> str | None:
    """Pick the dependent/outcome node: typed 'dependent' → unique sink → DV lexicon
    → sink with max in-degree → first node."""
    non_mod = [e for e in edges if not _is_moderation(e, ntype)]
    outdeg = {i: 0 for i in ids}
    indeg = {i: 0 for i in ids}
    for e in non_mod:
        s, t = _src(e), _tgt(e)
        if s in outdeg:
            outdeg[s] += 1
        if t in indeg:
            indeg[t] += 1
    typed = [i for i in ids if ntype.get(i) == "dependent"]
    if len(typed) == 1:
        return typed[0]
    sinks = [i for i in ids if outdeg.get(i, 0) == 0 and indeg.get(i, 0) >= 1]
    if len(sinks) == 1:
        return sinks[0]
    label = {str(n["id"]).strip(): str(n.get("label") or n["id"]).lower() for n in nodes}
    for i in (sinks or ids):
        if any(k in label.get(i, "") for k in _DV_LEXICON):
            return i
    if sinks:
        return max(sinks, key=lambda i: indeg.get(i, 0))
    return ids[0] if ids else None


def repair_conceptual_model(cm) -> tuple[dict, dict]:
    """Return (repaired_cm, report). If already valid → the ORIGINAL cm untouched.
    Repair is ADDITIVE only: connect every stray component / orphan to the outcome
    with a new hypothesis edge. Never raises; on any error returns the original."""
    report = check_conceptual_model(cm)
    if not report.get("applicable") or report.get("ok"):
        return cm, report
    # Deterministic repair can only ADD edges — it cannot invent constructs. A model
    # that is connected but merely thin (components == 1) is left as-is; the caller
    # keeps the report note. Only a DISCONNECTED model is rewritten.
    if report.get("components", 1) <= 1:
        return cm, report
    try:
        g = _coerce(cm)
        nodes = [n for n in (g.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "").strip()]
        edges = [dict(e) for e in (g.get("edges") or []) if isinstance(e, dict) and _src(e) and _tgt(e)]
        ids = [str(n["id"]).strip() for n in nodes]
        ntype = {str(n["id"]).strip(): str(n.get("type") or "").lower() for n in nodes}
        dv = _pick_outcome(ids, nodes, edges, ntype)
        if not dv:
            return cm, report

        # Components (undirected).
        parent = {i: i for i in ids}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for e in edges:
            a, b = find(_src(e)), find(_tgt(e))
            if a != b:
                parent[a] = b

        h = sum(1 for e in edges if str(e.get("label") or e.get("hypothesis") or "").strip()) + 1
        dv_root = find(dv)
        added = 0
        # For each component NOT containing the DV, connect its representative → DV.
        seen_roots = set()
        for i in ids:
            r = find(i)
            if r == dv_root or r in seen_roots:
                continue
            seen_roots.add(r)
            # representative = a non-DV node in this component with no outgoing edge, else i
            rep = next((n for n in ids if find(n) == r and n != dv), i)
            edges.append({"from": rep, "to": dv, "label": f"H{h}: +"})
            h += 1
            added += 1
            # merge so we don't double-link
            parent[find(rep)] = dv_root

        report = {**report, "repaired": True, "edges_added": added, "dv": dv}
        return {"nodes": nodes, "edges": edges}, report
    except Exception:
        logger.exception("graph_guard.repair failed — returning original")
        return cm, report
