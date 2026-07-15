"""Prerequisite reconstruction — infer a SKIPPED upstream artifact from evidence.

The Phase 3 "backfill" piece (the research-novel, uncited part). When a student
enters mid-thesis (e.g. at `analysis`) without a prerequisite (`design`),
`reconstruct_artifact` reads everything else they HAVE done — the downstream work
they provided plus any upstream context — and asks the LLM to best-guess the
missing slice's fields.

CRITICAL: the result is a *candidate* tagged `_source="reconstructed"`. It must be
gated behind its DoD validator + an explicit user confirm before it is committed
— never silently fabricate a prerequisite. This module only produces the
proposal; the gating/commit lives at the call site.
"""
from __future__ import annotations

import json
import logging
import os

from orchestrator.artifacts import _ARTIFACT_BY_KEY

logger = logging.getLogger(__name__)

_SLICE_KEYS = ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing")


def _schema_for_slice(slice_name: str):
    from orchestrator.schemas.m1 import M1Output
    from orchestrator.schemas.m2 import M2Output
    from orchestrator.schemas.m3 import M3Output
    from orchestrator.schemas.m4 import M4Output
    from orchestrator.schemas.m5 import M5Output
    return {
        "m1_topic": M1Output, "m2_literature": M2Output, "m3_design": M3Output,
        "m4_analysis": M4Output, "m5_writing": M5Output,
    }[slice_name]


def _llm():
    # Route through the engine-wide factory (ORCHESTRATOR_LLM_ROUTE) so the whole
    # engine is switchable. temperature 0.3 + the per-request timeout are this
    # site's original settings, preserved so native behavior is unchanged.
    from orchestrator.llm import get_orchestrator_llm
    return get_orchestrator_llm(
        temperature=0.3,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def reconstruct_artifact(artifact_key: str, context_store, llm=None,
                         language: str | None = None) -> dict:
    """Infer a candidate slice for a skipped prerequisite from available evidence.

    Returns the inferred fields tagged `_source="reconstructed"` plus a
    `_rationale` (one-line "why", same-language) when the model supplies one, or
    `{}` when there is no evidence to infer from (don't fabricate) or on LLM/parse
    failure. `llm` is injectable for tests. `language` (e.g. "vi") localizes the
    inferred values + rationale; None keeps the original English-neutral prompt so
    existing callers are unchanged.
    """
    art = _ARTIFACT_BY_KEY.get(artifact_key)
    if art is None:
        return {}
    target_slice = art.slice

    # Evidence = every OTHER filled slice, stripped of internal markers. The
    # target's own slice is excluded so we infer fresh, not echo stale content.
    evidence: dict = {}
    for k in _SLICE_KEYS:
        if k == target_slice:
            continue
        v = getattr(context_store, k, None)
        if v:
            evidence[k] = {kk: vv for kk, vv in v.items() if not str(kk).startswith("_")}
    if not evidence:
        return {}

    schema = _schema_for_slice(target_slice)
    fields = [name for name in schema.model_fields if name != "confirmed_at"]
    field_hints = "\n".join(
        f"- {name}: "
        f"{schema.model_fields[name].description or schema.model_fields[name].annotation}"
        for name in fields
    )

    lang_line = (
        f"Write every field value AND the rationale in {language}.\n"
        if language else ""
    )
    llm = llm or _llm()
    prompt = (
        f"A student is writing a thesis but SKIPPED the '{artifact_key}' step. "
        f"Infer it from the work they HAVE done (below). Produce a best guess for "
        f"its fields that is CONSISTENT with the evidence — do not invent facts the "
        f"evidence contradicts, and omit any field you genuinely cannot infer.\n\n"
        f"{lang_line}"
        f"Fields to infer:\n{field_hints}\n\n"
        f"Also include a key `_rationale`: ONE short sentence naming which pieces "
        f"of the evidence you inferred this from.\n\n"
        f"Evidence (other completed parts of their thesis):\n"
        f"{json.dumps(evidence, default=str, ensure_ascii=False)[:6000]}\n\n"
        f"Respond with ONLY a JSON object of the inferred fields. "
        f"No prose, no markdown."
    )
    try:
        raw = llm.invoke(prompt).content
        data = json.loads(_strip_code_fence(raw))
        if not isinstance(data, dict):
            return {}
        # Keep the schema fields plus the meta rationale; drop everything else.
        out = {k: v for k, v in data.items() if k in fields or k == "_rationale"}
        # A lone _rationale with no real inferred field is not a candidate.
        if not any(k in fields for k in out):
            return {}
        out["_source"] = "reconstructed"
        return out
    except Exception:  # noqa: BLE001 - best-effort; gated downstream anyway
        logger.exception("reconstruct_artifact failed for %s", artifact_key)
        return {}


_MODULE_ORDER = ("M1", "M2", "M3", "M4")  # M5 is never an upstream target


def reconstruct_upstream(context_store, targets: list[str] | None = None,
                         llm=None, language: str | None = None) -> list[dict]:
    """Reconstruct the missing UPSTREAM modules from whatever evidence exists.

    Bottom-up (M4→…→M1) so each adjacent inference (the only reliable jump — see
    dod_design_structural) feeds the next: a fresh M3 candidate becomes evidence
    for M2, etc. The feed-forward is on an in-memory copy only — nothing is
    persisted here; every entry is a *candidate* the caller must gate behind an
    explicit user confirm.

    `targets` restricts which modules to attempt (e.g. ["M3"] for "just the
    design"); None ⇒ every M1-M4 module strictly below the highest module that
    already has content and itself still empty. Returns a list (display order
    M1→M4) of {module, artifact, candidate, rationale, ready_to_confirm, review}.
    Never raises — a per-module failure yields `{}` and is skipped.
    """
    from orchestrator.artifacts import (
        MODULE_TO_ARTIFACT, _ARTIFACT_BY_KEY, dod_design_structural,
    )
    from orchestrator.state import _MODULE_TO_FIELD, _slice_has_content

    def _content(module: str) -> bool:
        v = getattr(context_store, _MODULE_TO_FIELD[module], None)
        return bool(v) and _slice_has_content(v)

    # Auto-target: everything strictly below the highest-with-content module that
    # is itself still empty. With only M4 filled → [M1, M2, M3].
    if targets is None:
        filled = [m for m in _MODULE_ORDER + ("M5",) if _content(m)]
        if not filled:
            return []
        top = max(_MODULE_ORDER.index(m) for m in filled if m in _MODULE_ORDER) \
            if any(m in _MODULE_ORDER for m in filled) else len(_MODULE_ORDER)
        targets = [m for m in _MODULE_ORDER[:top + 1] if not _content(m)]
    else:
        targets = [m for m in targets if m in MODULE_TO_ARTIFACT]

    llm = llm or _llm()
    cs = context_store
    out: list[dict] = []
    # Bottom-up: process the highest target first so lower ones see it as evidence.
    for module in sorted(targets, key=_MODULE_ORDER.index, reverse=True):
        artifact = MODULE_TO_ARTIFACT[module]
        candidate = reconstruct_artifact(artifact, cs, llm=llm, language=language)
        if not candidate:
            continue
        rationale = candidate.pop("_rationale", None)
        gate = {"design": dod_design_structural}.get(
            artifact, _ARTIFACT_BY_KEY[artifact].dod)
        result = gate(candidate)
        out.append({
            "module": module, "artifact": artifact, "candidate": candidate,
            "rationale": rationale,
            "ready_to_confirm": result.done, "review": result.gaps,
        })
        # Feed forward on a COPY so the next (lower) module can lean on this one.
        cs = cs.model_copy(update={_MODULE_TO_FIELD[module]: candidate})
    out.sort(key=lambda e: _MODULE_ORDER.index(e["module"]))
    return out


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
