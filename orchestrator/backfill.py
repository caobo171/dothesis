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
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.3,
        timeout=int(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "20")),
    )


def reconstruct_artifact(artifact_key: str, context_store, llm=None) -> dict:
    """Infer a candidate slice for a skipped prerequisite from available evidence.

    Returns the inferred fields tagged `_source="reconstructed"`, or `{}` when
    there is no evidence to infer from (don't fabricate) or on LLM/parse failure.
    `llm` is injectable for tests.
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

    llm = llm or _llm()
    prompt = (
        f"A student is writing a thesis but SKIPPED the '{artifact_key}' step. "
        f"Infer it from the work they HAVE done (below). Produce a best guess for "
        f"its fields that is CONSISTENT with the evidence — do not invent facts the "
        f"evidence contradicts, and omit any field you genuinely cannot infer.\n\n"
        f"Fields to infer:\n{field_hints}\n\n"
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
        out = {k: v for k, v in data.items() if k in fields}
        if not out:
            return {}
        out["_source"] = "reconstructed"
        return out
    except Exception:  # noqa: BLE001 - best-effort; gated downstream anyway
        logger.exception("reconstruct_artifact failed for %s", artifact_key)
        return {}


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
