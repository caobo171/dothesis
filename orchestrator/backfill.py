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


# The prompt asks for ONE top-level `_rationale`, and the model sometimes
# generalises that into a per-field envelope: {"research_title": {"value": "...",
# "rationale": "..."}}. That shape was committed straight into the context store,
# where it corrupted state and surfaced much later — and somewhere else entirely
# — as React refusing to render an object as a child.
#
# Keyed on the envelope's EXACT shape, not on "it is a dict": conceptual_model,
# instrument and methodology are all legitimately dicts and must pass through.
_ENVELOPE_KEYS = ({"value", "rationale"}, {"value"})


def _unwrap_field(v):
    """Return the field's real value, unwrapping a {value, rationale} envelope."""
    if isinstance(v, dict) and set(v.keys()) in _ENVELOPE_KEYS:
        return v.get("value")
    return v


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
        out = {k: _unwrap_field(v) for k, v in data.items()
               if k in fields or k == "_rationale"}
        # A lone _rationale with no real inferred field is not a candidate.
        if not any(k in fields for k in out):
            return {}
        out["_source"] = "reconstructed"
        return out
    except Exception:  # noqa: BLE001 - best-effort; gated downstream anyway
        logger.exception("reconstruct_artifact failed for %s", artifact_key)
        return {}


_MODULE_ORDER = ("M1", "M2", "M3", "M4")  # M5 is never an upstream target


def _search_topic_of(context_store) -> str:
    """The research title the literature search would run on, or "" if there
    isn't one yet. Lets the walk tell "no topic" apart from "search found
    nothing" without paying for the search to discover it."""
    m1 = getattr(context_store, "m1_topic", None) or {}
    return str(m1.get("research_title") or "").strip()


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

    import concurrent.futures as _fut
    from orchestrator.tools.domain_sources import (
        classify_domain, dedup_sources, domain_supplement, search_query_en)

    # Search in ENGLISH. Crossref / OpenAlex / Semantic Scholar are English
    # catalogs and our students write Vietnamese titles, so the raw title
    # matches next to nothing — search_query_en's own docstring says exactly
    # this, but it was only ever applied to the domain supplement below while
    # the main scout kept getting the untranslated title. On a real thesis
    # ("Ảnh hưởng của ... KOLs trên TikTok ...") that was the difference between
    # one incidental hit and a usable set.
    #
    # Degrades to the raw topic on failure (it is self-bounded and returns the
    # topic unchanged), so this can only add.
    query = search_query_en(topic, rqs) or topic
    # Send the query ALONE. The research questions used to be appended as a
    # "Research questions:\n- ..." block, which pastes Vietnamese prose onto an
    # English keyword query and poisons it: measured on a real topic, the clean
    # query returned 7 sources in 10s and the same query with the block
    # appended returned 3 in 44s — half the results for four times the wait.
    #
    # Nothing is lost by dropping it: search_query_en already takes `rqs` and
    # folds them into the keywords it produces. The block was giving the search
    # the questions a second time, in the wrong language, as free text.
    composed = query

    citations = None
    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        from orchestrator.tools.m2_literature import scout_citations
        # Grounding here was silently DEAD before this. At the engine's
        # defaults the deep planner emitted 249 queries for one thesis title,
        # each allowed 90s, batched with rate-limit pauses — it could never
        # finish inside the deadline below, so the future timed out, the except
        # swallowed it, and every real DOI already found was discarded. On by
        # default, two minutes of the student's import wall-clock, always [].
        #
        # deep=False finishes (~35s) and returns real, DOI-bearing sources, but
        # only a handful: the three hand-rolled variants are a much weaker plan
        # than the deep one. Measured on a live project, deep found several
        # relevant papers before being cut off; shallow finds ~1.
        #
        # So this is the honest floor, not the ceiling. Bounding the deep plan
        # was tried and does NOT work — min_sources_deep does not size the
        # planner's query count, and deep=True still overran at 12. Getting
        # good M2 grounding needs the search moved OFF the request path into a
        # background job, where it can take the ten minutes it actually wants.
        citations = ex.submit(scout_citations.func, composed, min_n=10,
                              deep=False).result(
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
        # Europe PMC / ERIC are English indexes — reuse the query translated
        # above rather than paying for a second identical LLM call.
        # Base first so a paper found by both keeps its validated deep-scout row.
        sources = dedup_sources(sources + domain_supplement(query, domain))
    return dedup_sources(sources)


def _report_progress(cb, done: int, total: int, module: str | None) -> None:
    """Publish progress without letting a reporting failure kill the work.

    The callback crosses into the API layer (a DB write on its own session), and
    reconstruction is expensive enough that losing it to a progress bug would be
    a genuinely bad trade.
    """
    try:
        cb(done, total, module)
    except Exception:
        logger.exception("backfill: progress callback failed")


def _hand_over(cb, entry: dict) -> None:
    """Hand one finished module to the caller without letting a sink failure
    kill the rest of the walk.

    Same trade as _report_progress, and for a stronger reason: this callback is
    what PERSISTS the module, so it writes to the DB from inside an expensive
    LLM loop. One module failing to commit must cost that module, not the four
    the student already paid for.
    """
    try:
        cb(entry)
    except Exception:
        logger.exception("backfill: module callback failed for %s",
                         entry.get("module"))


def reconstruct_upstream(context_store, targets: list[str] | None = None,
                         llm=None, language: str | None = None,
                         ground_m2: bool | None = None,
                         on_progress=None, on_module=None) -> list[dict]:
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

    `on_module(entry)` is called with each entry the moment it is produced, in
    PRODUCTION order (M4→M1), i.e. before the walk finishes. Callers that
    persist should use it rather than the return value: a run that dies on the
    last module would otherwise throw away every module before it, and the
    student pays for the whole reconstruction again. Because the auto-target
    above skips modules that are already COMPLETE, a re-run then resumes from
    whatever landed instead of redoing it.

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

    # Ground M2 in a REAL literature search by default.
    #
    # This used to be opt-in, so the import path shipped whatever sources the
    # model recalled. Those are not citations — they are a language model's
    # recollection of citations, and a thesis is the last place to guess. The
    # reconstructed M2 is also what `citation_list` is filled from, so an
    # ungrounded backfill puts invented references into the bibliography of a
    # document a student submits under their own name.
    #
    # It costs a bounded search (_m2_real_sources: hard timeout, returns [] on
    # any failure and the LLM candidate stands). Set
    # DOTHESIS_BACKFILL_GROUND_M2=0 to go back to LLM-only.
    if ground_m2 is None:
        _env = os.getenv("DOTHESIS_BACKFILL_GROUND_M2", "").strip().lower()
        ground_m2 = _env not in ("0", "false", "no")

    llm = llm or _llm()
    cs = context_store
    out: list[dict] = []
    # Bottom-up: process the highest target first so lower ones see it as evidence.
    # Ordered work list, published BEFORE the first module so the caller can show
    # a real denominator rather than a spinner. Grounding turned this from a few
    # seconds into a minute-plus, and an unexplained wait is what makes a student
    # reload the page and pay for the whole thing twice.
    ordered = sorted(targets, key=_MODULE_ORDER.index, reverse=True)
    # Whether the search below already ran for M2. The post-walk grounding is a
    # RETRY for the no-topic case only — a search that ran and legitimately came
    # back empty (or blew up) must not be paid for a second time.
    m2_search_attempted = False
    for _idx, module in enumerate(ordered):
        # Reported at the TOP, not after the body: a module that yields no
        # candidate hits `continue` below, and a report placed after that would
        # stall the bar on exactly the modules that were skipped.
        if on_progress:
            _report_progress(on_progress, _idx, len(ordered), module)
        artifact = MODULE_TO_ARTIFACT[module]
        candidate = reconstruct_artifact(artifact, cs, llm=llm, language=language)
        if not candidate:
            continue
        if module == "M2" and ground_m2 and _search_topic_of(cs):
            m2_search_attempted = True
            # Replace the LLM-recalled sources with real, DOI-bearing ones. Both
            # keys carry the same normalized dicts: literature_sources is what the
            # report reads (agent SLICE_OWNERSHIP["M2"]); citation_list is what
            # dod_literature counts. Empty search → leave the LLM candidate as-is.
            #
            # Only when a topic already exists. This walk runs BOTTOM-UP, so on
            # the dominant real case — a finished thesis that imports as M4
            # analysis text and nothing else — M1 has not been reconstructed
            # yet when we get here, and the search has no title to search on.
            # It is grounded after the walk instead (see below).
            real = _m2_real_sources(cs)
            if real:
                candidate["literature_sources"] = real
                candidate["citation_list"] = real
        if module == "M2":
            # Mirror sources into the citation list when only one side is
            # filled. dod_literature counts `citation_list`, but the grounded
            # search that fills it is env-gated and OFF by default, so the LLM
            # candidate routinely arrived with real `literature_sources` and an
            # empty `citation_list`. M2 then sat in_progress behind a key
            # nothing was ever going to fill, while M3/M4/M5 read done — a
            # student cannot have a finished analysis and an unfinished
            # literature step, and the two keys are the same normalized dicts
            # (see above). Never overwrites a citation list that already exists.
            if not candidate.get("citation_list") and candidate.get("literature_sources"):
                candidate["citation_list"] = candidate["literature_sources"]
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
        entry = {
            "module": module, "artifact": artifact, "candidate": candidate,
            "rationale": rationale,
            "ready_to_confirm": result.done, "review": result.gaps,
        }
        out.append(entry)
        # Hand it over NOW, not at the end. This is the difference between a
        # cancelled import keeping its finished modules and losing all of them.
        if on_module:
            _hand_over(on_module, entry)
        # Feed forward on a COPY so the next (lower) module can lean on this one.
        cs = cs.model_copy(update={_MODULE_TO_FIELD[module]: candidate})

    # Ground M2 now that M1 exists.
    #
    # This is THE reason imported theses arrived with an empty citation_list. The
    # walk is bottom-up so M2 is reconstructed BEFORE M1, and _m2_real_sources
    # returns [] on the spot when there is no research_title. On the case that
    # actually happens — a finished thesis lands as M4 analysis text and nothing
    # else — that is every time: measured, the scout was called ZERO times. The
    # search wasn't slow or unlucky, it never ran.
    #
    # M1 is reconstructed by the end of the loop, so the title exists here. Only
    # for an M2 that still has no real sources, so a search that already
    # succeeded above is never paid for twice.
    if ground_m2 and not m2_search_attempted:
        m2_entry = next((e for e in out if e["module"] == "M2"), None)
        # Deliberately NOT gated on "the candidate has no literature_sources".
        # The sources it does have at this point are the ones the MODEL
        # recalled, and replacing exactly those is the entire point of
        # grounding — gating on them would let a fabricated bibliography block
        # the real search that was meant to overwrite it.
        if m2_entry is not None:
            real = _m2_real_sources(cs)
            if real:
                cand = m2_entry["candidate"]
                cand["literature_sources"] = real
                cand["citation_list"] = real
                # Re-grade: the slice changed, so the gaps reported with it must
                # be recomputed or the widget keeps saying "citation_list is
                # empty" over a list that is no longer empty.
                regraded = _gate_for(m2_entry["artifact"])(cand)
                m2_entry["ready_to_confirm"] = regraded.done
                m2_entry["review"] = regraded.gaps
                # Hand it over AGAIN so the caller persists the sources. Callers
                # key by module (see the route's _save_now), so this updates the
                # committed M2 rather than adding a second one.
                if on_module:
                    _hand_over(on_module, m2_entry)

    out.sort(key=lambda e: _MODULE_ORDER.index(e["module"]))
    # Close the bar. Without this it stops one short of the total, and a bar
    # that never reaches its end reads as a hang no matter what happened.
    if on_progress:
        _report_progress(on_progress, len(ordered), len(ordered), None)
    return out


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()
