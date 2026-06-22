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
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


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

    try:
        # Reuse the proven graph_v2 wrapper (engine-native model, quality
        # gate, progress emitter chain) instead of re-wiring the engine here.
        from orchestrator.tools.m2_literature import scout_citations
        citations = scout_citations.func(composed, min_n=min_sources)
    except Exception as e:  # engine failures must not kill the turn
        logger.exception("research_scout failed")
        return json.dumps({
            "error": f"scout failed: {e}",
            "hint": "Tell the user the search failed and offer to retry or to add papers by upload/DOI instead.",
        })

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
