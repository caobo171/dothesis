"""M2 research tools — the agent's hands into the EXISTING research strategy.

Architecture §2.1: the M2 skill keeps its procedure, the engine keeps the
muscle. `research_scout` reuses the same engine call path the graph_v2 M2
phase used (orchestrator/tools/m2_literature.scout_citations → engine
deep_research planner + api_citations orchestrator + validators), so the
agent pivot does not change research quality or progress streaming.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import httpx  # module-level so tests can monkeypatch research.httpx
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


# Wall-clock discipline promoted from partner's _budgeted_scout (spec §3): the
# deep scout can run minutes / rate-limit into a hang, and a hung tool is the
# stall mode headless cannot distinguish from thinking. Cap it, fall back to a
# direct Crossref query so a turn never hangs and never ships zero references.
# Default 120s (not partner's old 45s): chat's scout legitimately runs 30-90s,
# and the run-level wall clock now owns the per-report budget.
_SCOUT_FALLBACK_N = 8


def _search_query_en(topic: str, research_questions: list[str] | None) -> str:
    """One short ENGLISH bibliographic query from the (possibly Vietnamese) topic.

    Crossref indexes mostly English scholarship and our primary market writes in
    Vietnamese, so handing it the raw topic returns near-nothing for most of our
    users. A tiny LLM call turns the topic into an English keyword query.

    Bounded by its own wall clock: this runs *inside* the degraded path that
    exists because the deep scout already blew its budget, so a hung LLM here
    would just relocate the stall it is meant to rescue us from. On timeout or
    any failure we degrade to the raw topic — a weak query beats no sources.
    """
    import concurrent.futures as _fut

    def _translate() -> str:
        from orchestrator.tools.m5_writing import _get_llm  # agent -> orchestrator is allowed
        rq = ("; ".join(research_questions or []))[:300]
        prompt = (
            "Turn this research topic into ONE short English academic search query "
            "(5-10 keywords, no punctuation, no quotes). Topic: "
            f"{topic}\nQuestions: {rq}\nQuery:"
        )
        resp = _get_llm().invoke(prompt)
        q = getattr(resp, "content", resp)
        if isinstance(q, list):
            q = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in q)
        return str(q).strip().strip('"').splitlines()[0][:200]

    # Same no-wait executor discipline as the deep scout below: shutdown(wait=True)
    # would block on the runaway thread and void the cap.
    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        q = ex.submit(_translate).result(timeout=int(os.getenv("DOTHESIS_TRANSLATE_TIMEOUT_S", "15")))
        if q:
            return q
    except Exception:
        logger.exception("research_scout: query translation failed; using raw topic")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return (topic or "").strip()[:200]


def _crossref_fallback(query: str, n: int = _SCOUT_FALLBACK_N) -> list[dict]:
    """Direct Crossref query — real peer-reviewed sources + DOIs in ~2s."""
    try:
        r = httpx.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": query,
                "rows": n,
                "select": "title,author,issued,DOI,container-title,URL",
                "filter": "type:journal-article,has-abstract:true",
                "sort": "relevance",
            },
            timeout=20,
            headers={"User-Agent": "DoThesis/1.0 (mailto:cao.nv17@gmail.com)"},
        )
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        logger.exception("crossref fallback failed (returning no sources)")
        return []
    refs: list[dict] = []
    for it in items:
        title = (it.get("title") or [""])[0].strip()
        if not title:
            continue
        parts = (it.get("issued", {}).get("date-parts") or [[None]])
        refs.append({
            "title": title,
            "authors": [str(a.get("family")).strip() for a in it.get("author", []) if a.get("family")],
            "year": parts[0][0] if parts and parts[0] else None,
            "venue": (it.get("container-title") or [None])[0],
            "doi": it.get("DOI"),
            "url": it.get("URL"),
            "verified": bool(it.get("DOI")),
        })
    return refs[:n]


@tool
def research_scout(
    topic: str,
    research_questions: list[str] | None = None,
    seed_refs: list[str] | None = None,
    min_sources: int = 10,
) -> str:
    """Deep literature search through the DoThesis research pipeline.

    Plans queries from the topic + research questions, searches academic APIs
    (Semantic Scholar, Crossref, OpenAlex, grounded search), validates and
    quality-filters citations, and returns verified sources. Slow (30–90s);
    progress streams to the user automatically. Scope it tightly — see the M2
    skill's search playbook.

    Capped by a wall clock (DOTHESIS_SCOUT_TIMEOUT_S, default 120s). If the deep
    scout times out or fails, the result carries `note: "budgeted fallback
    (Crossref)"` and holds lighter, unvalidated-but-real Crossref sources — say
    so to the user and offer a retry rather than presenting them as the deep
    search's output.

    Args:
        topic: One narrow sentence (population + platform + context beats a bare construct).
        research_questions: The M1 RQs verbatim — drives query planning.
        seed_refs: Titles/DOIs of already-confirmed sources to expand from.
        min_sources: Minimum citations to aim for (default 10).
    """
    # Compose the scout topic the way the engine planner expects: a focused
    # statement, with RQs appended as context lines (the planner extracts
    # query families from them).
    composed = topic
    if research_questions:
        composed += "\nResearch questions:\n" + "\n".join(f"- {q}" for q in research_questions)
    if seed_refs:
        composed += "\nSeed references:\n" + "\n".join(f"- {r}" for r in seed_refs)

    import concurrent.futures as _fut

    # This tool is sync, so run_headless's asyncio.wait_for (agent/headless.py)
    # cannot interrupt a search in flight: a run can overrun its wall_clock_s by
    # up to this cap. Harmless at defaults (120s vs 1800s), but any profile with
    # wall_clock_s <= 120 is really governed by this number, not by its budget.
    timeout_s = int(os.getenv("DOTHESIS_SCOUT_TIMEOUT_S", "120"))
    citations = None
    # NOTE: do NOT use `with ThreadPoolExecutor(...)`. Its __exit__ calls
    # shutdown(wait=True), which BLOCKS until the (possibly runaway) scout
    # thread finishes — a result(timeout=...) that fires would still wait
    # minutes for the hung thread, defeating the cap entirely (the lesson
    # partner's _budgeted_scout learned on a Semantic Scholar 429 storm).
    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        # Reuse the proven graph_v2 wrapper (engine-native model, quality
        # gate, progress emitter chain) instead of re-wiring the engine here.
        from orchestrator.tools.m2_literature import scout_citations
        future = ex.submit(scout_citations.func, composed, min_n=min_sources)
        citations = future.result(timeout=timeout_s)
    except Exception:
        # TimeoutError, engine failure, rate limit — all degrade to Crossref.
        logger.exception("research_scout: deep scout failed/timed out; Crossref fallback")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)

    if not citations:
        # `composed` is scaffolding for the engine's *planner*, which reads the
        # "Research questions:" / "Seed references:" labels as structure. A
        # bibliographic index reads them as search terms, so Crossref gets the
        # bare topic, translated to English.
        refs = _crossref_fallback(_search_query_en(topic, research_questions))
        out = {
            "sources": refs, "count": len(refs),
            # Honesty marker: the agent should tell the user this was the
            # light fallback, not the deep validated scout.
            "note": "budgeted fallback (Crossref)",
        }
        if not refs:
            # A `count: 0` that reads identically to a successful fallback is
            # how a thesis ends up composed from stubs — on the headless
            # surface there is no human to notice the empty list. Say what
            # happened and what to do instead.
            out["note"] = "budgeted fallback (Crossref) returned NO sources — search failed"
            out["hint"] = (
                "Do NOT proceed as if literature was found and do not invent citations. "
                "Tell the user the search came back empty and offer to retry, narrow the "
                "topic, or add papers by upload/DOI instead."
            )
        return json.dumps(out, ensure_ascii=False)

    # Normalize to the M2 Source shape; ids are assigned when the agent
    # commits the user-curated selection to the slice.
    sources = [
        {
            "title": c.get("title"),
            "authors": c.get("authors"),
            "year": c.get("year"),
            "venue": c.get("source") or c.get("venue"),
            "doi": c.get("doi"),
            "url": c.get("url"),
            "verified": bool(c.get("verified", c.get("doi") is not None)),
        }
        for c in (citations or [])
    ]
    return json.dumps({"sources": sources, "count": len(sources)}, ensure_ascii=False)


@tool
def quick_sources(query: str, limit: int = 5) -> str:
    """Fast grounded lookup for early/topic-stage chat — a few real papers, no deep cascade.

    Use this in M1 (Topic Discovery) and any time you make a factual or
    landscape claim BEFORE the full M2 literature search has run. It hits
    OpenAlex directly (free, ~1-2s) and returns a handful of verified papers so
    early answers carry citations instead of reading like an ungrounded chatbot.
    This is NOT a substitute for `research_scout` (the real M2 search) — it is a
    lightweight grounding aid for conversation. Never invent citations; if this
    returns nothing, say so plainly.

    Args:
        query: A short, focused search phrase (the topic or the specific claim).
        limit: How many papers to return (default 5, keep it small).
    """
    try:
        # OpenAlex multi-result search: fast, free, no API key. Same validated
        # metadata path the engine's citation cascade trusts (verified DOIs).
        from engine.utils.api_citations.openalex import OpenAlexClient
        papers = OpenAlexClient().search_papers(query, limit=max(1, min(limit, 10)))
    except Exception as e:  # never kill the turn on a search hiccup
        logger.exception("quick_sources failed")
        return json.dumps({
            "error": f"quick search failed: {e}",
            "hint": "Tell the user grounding is briefly unavailable; answer cautiously or retry.",
        })

    # Rank by citation count so the most established work surfaces first.
    papers = sorted(papers or [], key=lambda p: p.get("citation_count", 0) or 0, reverse=True)
    sources = [
        {
            "title": p.get("title"),
            "authors": p.get("authors"),
            "year": p.get("year"),
            "venue": p.get("journal") or p.get("publisher"),
            "doi": p.get("doi"),
            "url": p.get("url"),
            "verified": bool(p.get("doi")),
        }
        for p in papers
    ]
    return json.dumps({"sources": sources, "count": len(sources)}, ensure_ascii=False)


@tool
def parse_reference(doi_or_path: str) -> str:
    """Resolve one reference into structured metadata.

    Accepts a DOI (or a title query) → Crossref lookup with standardized
    fields, or a path to an uploaded PDF → extracted text for the agent to
    read (metadata + page-anchored claims are then extracted conversationally).

    Args:
        doi_or_path: A DOI like "10.1016/j.jbusres.2018.08.032", a paper title,
            or a path to an uploaded PDF in the project workspace.
    """
    p = Path(doi_or_path)
    if p.suffix.lower() == ".pdf" and p.exists():
        try:
            from pdfminer.high_level import extract_text
            text = extract_text(str(p)) or ""
        except Exception as e:
            return json.dumps({"error": f"PDF extraction failed: {e}"})
        # Guardrail: the PDF body is untrusted user content. Frame it as data
        # and flag any prompt-injection so document text can't hijack the agent.
        from agent.guardrails import neutralize_document_text
        framed, hits = neutralize_document_text(text[:12_000])
        if hits:
            logger.warning("parse_reference: possible prompt-injection in %s: %s", p, hits)
        # Cap what goes back into context; the agent asks for more pages if needed.
        return json.dumps({
            "kind": "pdf",
            "path": str(p),
            "chars": len(text),
            "text_head": framed,
            "injection_flags": hits,
        }, ensure_ascii=False)

    try:
        from engine.utils.api_citations import CrossrefClient
        meta = CrossrefClient().search_paper(doi_or_path)
    except Exception as e:
        logger.exception("crossref lookup failed")
        return json.dumps({"error": f"Crossref lookup failed: {e}"})
    if not meta:
        return json.dumps({
            "error": f"no match for {doi_or_path!r}",
            "hint": "Ask the user to upload the PDF or double-check the DOI.",
        })
    meta["verified"] = True  # resolved via Crossref = real, citable metadata
    return json.dumps({"kind": "doi", "source": meta}, ensure_ascii=False)
