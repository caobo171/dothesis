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


def _m2_real_sources(context_store) -> list[dict]:
    """A bounded REAL literature search to ground the M2 candidate — the deep
    scout (OpenAlex/Crossref/Semantic Scholar) plus the domain supplement
    (Europe PMC for medical, ERIC for education). Returns [] on any
    failure/timeout/no-topic; the caller then keeps the LLM candidate. Read-side
    only (no commit here). Same no-`with` executor discipline as research_scout:
    shutdown(wait=False) so a runaway scout thread never blocks the report."""
    m1 = getattr(context_store, "m1_topic", None) or {}
    topic = str(m1.get("research_title") or "").strip()
    if not topic:
        return []  # M1 not seeded/reconstructed yet — nothing to search on
    rqs = [str(q) for q in (m1.get("research_questions") or [])]
    composed = topic
    if rqs:
        composed += "\nResearch questions:\n" + "\n".join(f"- {q}" for q in rqs)

    import concurrent.futures as _fut
    from orchestrator.tools.domain_sources import (
        classify_domain, dedup_sources, domain_supplement, search_query_en)

    citations = None
    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        from orchestrator.tools.m2_literature import scout_citations
        citations = ex.submit(scout_citations.func, composed, min_n=10).result(
            timeout=int(os.getenv("DOTHESIS_SCOUT_TIMEOUT_S", "120")))
    except Exception:
        logger.exception("backfill: M2 deep scout failed/timed out — keeping LLM candidate")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    sources = [{
        "title": c.get("title"), "authors": c.get("authors"), "year": c.get("year"),
        "venue": c.get("source") or c.get("venue"),  # scout emits `source`
        "doi": c.get("doi"), "url": c.get("url"),
        "verified": bool(c.get("doi")),
    } for c in (citations or []) if (c.get("title") or "").strip()]

    domain = classify_domain(m1.get("field"), topic, rqs)
    if domain != "general":
        # Europe PMC / ERIC are English indexes — feed the translated query.
        # Base first so a paper found by both keeps its validated deep-scout row.
        sources = dedup_sources(sources + domain_supplement(search_query_en(topic, rqs), domain))
    return dedup_sources(sources)


def reconstruct_upstream(context_store, targets: list[str] | None = None,
                         llm=None, language: str | None = None,
                         ground_m2: bool | None = None) -> list[dict]:
    """Reconstruct the missing UPSTREAM modules from whatever evidence exists.

    Bottom-up (M4→…→M1) so each adjacent inference (the only reliable jump — see
    dod_design_structural) feeds the next: a fresh M3 candidate becomes evidence
    for M2, etc. The feed-forward is on an in-memory copy only — nothing is
    persisted here; every entry is a *candidate* the caller must gate behind an
    explicit user confirm.

    `targets` restricts which modules to attempt (e.g. ["M3"] for "just the
    design"); None ⇒ every M1-M4 module up to the highest one that already has
    content, that is not yet COMPLETE. Returns a list (display order M1→M4) of
    {module, artifact, candidate, rationale, ready_to_confirm, review}.
    Never raises — a per-module failure yields `{}` and is skipped.

    "Not complete" rather than "empty": a student who uploads a finished thesis
    lands their whole document in M4 as `analysis_results`, which is content —
    but the module still has no `analysis_outline` or `data_type_detected`, so
    it fails its DoD and the agent asks them to plan an analysis they already
    ran. Refusing to touch a partially-filled module meant the module with the
    MOST evidence was the only one we wouldn't finish. Values that are already
    there always win over the inference (see the merge below), so completing a
    module can only add.
    """
    from orchestrator.artifacts import (
        MODULE_TO_ARTIFACT, _ARTIFACT_BY_KEY, dod_design_structural,
    )
    from orchestrator.state import (
        _MODULE_TO_FIELD, _slice_has_content, get_module_slice,
    )

    def _gate_for(artifact: str):
        # design uses the structural gate (dod_design_structural) everywhere in
        # this module — keep the two selections identical or a module could be
        # targeted by one rule and graded by the other.
        return {"design": dod_design_structural}.get(
            artifact, _ARTIFACT_BY_KEY[artifact].dod)

    def _content(module: str) -> bool:
        v = getattr(context_store, _MODULE_TO_FIELD[module], None)
        return bool(v) and _slice_has_content(v)

    def _complete(module: str) -> bool:
        v = getattr(context_store, _MODULE_TO_FIELD[module], None) or {}
        if not (v and _slice_has_content(v)):
            return False
        return _gate_for(MODULE_TO_ARTIFACT[module])(v).done

    # Auto-target: everything up to the highest-with-content module that isn't
    # complete yet. Imported M4 holding only raw results → [M1, M2, M3, M4].
    if targets is None:
        filled = [m for m in _MODULE_ORDER + ("M5",) if _content(m)]
        if not filled:
            return []
        top = max(_MODULE_ORDER.index(m) for m in filled if m in _MODULE_ORDER) \
            if any(m in _MODULE_ORDER for m in filled) else len(_MODULE_ORDER)
        targets = [m for m in _MODULE_ORDER[:top + 1] if not _complete(m)]
    else:
        targets = [m for m in targets if m in MODULE_TO_ARTIFACT]

    # Report-only: ground M2 with a real literature search. Env carrier set by
    # api/app/headless_entry.py (report subprocess); chat/import backfill never
    # sets it → stays LLM-fast. Explicit kwarg wins (tests).
    if ground_m2 is None:
        ground_m2 = os.getenv("DOTHESIS_BACKFILL_GROUND_M2", "").strip().lower() in ("1", "true", "yes")

    llm = llm or _llm()
    cs = context_store
    out: list[dict] = []
    # Bottom-up: process the highest target first so lower ones see it as evidence.
    for module in sorted(targets, key=_MODULE_ORDER.index, reverse=True):
        artifact = MODULE_TO_ARTIFACT[module]
        candidate = reconstruct_artifact(artifact, cs, llm=llm, language=language)
        if not candidate:
            continue
        if module == "M2" and ground_m2:
            # Replace the LLM-recalled sources with real, DOI-bearing ones. Both
            # keys carry the same normalized dicts: literature_sources is what the
            # report reads (agent SLICE_OWNERSHIP["M2"]); citation_list is what
            # dod_literature counts. Empty search → leave the LLM candidate as-is.
            real = _m2_real_sources(cs)
            if real:
                candidate["literature_sources"] = real
                candidate["citation_list"] = real
        rationale = candidate.pop("_rationale", None)
        # Completing a partial module must never overwrite it. What is already
        # in the slice is the student's actual work (the imported results, a
        # questionnaire they wrote); the inference only gets the empty fields.
        existing = get_module_slice(cs, module)
        if existing:
            candidate = {**candidate,
                         **{k: v for k, v in existing.items()
                            if v not in (None, "", [], {})}}
        # Grade the MERGED slice — that's what gets persisted, so grading the
        # bare candidate would report gaps the student had already filled.
        result = _gate_for(artifact)(candidate)
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
