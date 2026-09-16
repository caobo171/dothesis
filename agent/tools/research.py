"""M2 research tools — bounded shared discovery plus fast/read-only helpers.

The agent delegates broad M2 discovery to ``literature_discovery`` so chat and
backfill use the same provider fan-out, deadline, deduplication, and honest
partial-coverage contract. ``quick_sources`` and ``parse_reference`` retain
their narrow, existing roles.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from langchain_core.tools import tool

# Module-level so tests can monkeypatch research.EuropePmcClient / research.EricClient.
# These submodules import only from .base (requests) — no heavy engine graph — so
# importing them here does not inflate import cost the way pulling the orchestrator would.
from engine.utils.api_citations.europe_pmc import EuropePmcClient
from engine.utils.api_citations.eric import EricClient

logger = logging.getLogger(__name__)


# Domain routing + the specialized-source helpers now live in the shared
# orchestrator.tools.domain_sources (so the report backfill can use them too).
# Re-export under the historical private names so this module's call sites and the
# monkeypatch-based tests (which patch research.EuropePmcClient / research.EricClient)
# are unchanged.
from orchestrator.tools import domain_sources as _ds  # agent -> orchestrator is allowed

_MEDICAL_TERMS = _ds._MEDICAL_TERMS
_EDUCATION_TERMS = _ds._EDUCATION_TERMS
_classify_domain = _ds.classify_domain
_search_query_en = _ds.search_query_en
_norm_source = _ds.norm_source
_dedup_sources = _ds.dedup_sources
_doi_key = _ds._doi_key
_title_key = _ds._title_key


def _domain_supplement(query: str, domain: str, n: int = 8) -> list[dict]:
    """Wrapper (not a bare alias): the client classes are resolved from THIS
    module's globals at call time, so tests monkeypatching research.EuropePmcClient
    / research.EricClient keep intercepting."""
    return _ds.domain_supplement(query, domain, n=n,
                                 clients={"medical": EuropePmcClient, "education": EricClient})


from orchestrator.tools.literature_discovery import discover_literature




@tool
def research_scout(
    topic: str,
    research_questions: list[str] | None = None,
    seed_refs: list[str] | None = None,
    min_sources: int = 24,
) -> str:
    """Deep literature search through the DoThesis research pipeline.

    Plans bounded query facets from the topic + research questions and searches
    OpenAlex, Crossref, and Semantic Scholar concurrently within a shared budget.
    It returns metadata candidates, their provider provenance, and abstract text
    when a provider supplies it. An exact identity check may mark metadata as
    verified; that still does NOT establish support for a particular thesis claim.

    Args:
        topic: One narrow sentence (population + platform + context beats a bare construct).
        research_questions: The M1 RQs verbatim — drives query planning.
        seed_refs: Titles/DOIs of already-confirmed sources to expand from.
        min_sources: Broad discovery target (default 24; partial results report a shortfall).
    """
    return _research_scout_impl(topic, research_questions, seed_refs, min_sources)


def _research_scout_impl(
    topic: str,
    research_questions: list[str] | None = None,
    seed_refs: list[str] | None = None,
    min_sources: int = 24,
    domain: str | None = None,
) -> str:
    # Medical/education theses ALSO get a domain-specialized index (Europe PMC /
    # ERIC) merged into the universal base. `domain` comes from the M1 field when
    # a store-bound tool supplies it; otherwise classify from the topic text.
    domain = domain or _classify_domain(None, topic, research_questions)

    target = max(1, int(min_sources or 24))
    try:
        discovered = discover_literature(
            topic, research_questions=research_questions, min_sources=target,
            # Seed papers are additional facets, not asserted evidence. The
            # helper deduplicates provider output against the search itself.
            concepts=seed_refs,
            # Keep the shared helper bounded even when an agent turn is otherwise
            # long. It returns honest partial coverage instead of a second fallback.
            budget_s=float(os.getenv("DOTHESIS_SCOUT_TIMEOUT_S", "120")),
            # The collector owns specialized provider work too, so every
            # provider shares one deadline and verification policy.
            domain=domain,
        )
    except Exception as exc:
        logger.exception("research_scout: bounded discovery failed")
        return json.dumps({
            "sources": [], "count": 0, "target": target, "shortfall": target,
            "verified_count": 0, "relevant_verified_count": 0, "new_count": 0,
            "unverified_count": 0, "existing_needs_review": [],
            "coverage": {"queries": [], "query_coverage": {}, "complete": False,
                         "warnings": ["Không thể kết nối dịch vụ tìm kiếm."]},
            "hint": "Không tìm thấy nguồn. Không được viết như đã có literature; hãy thử lại hoặc thêm DOI/PDF.",
            "detail": str(exc),
        }, ensure_ascii=False)
    sources = [dict(source) for source in (discovered.get("sources") or []) if isinstance(source, dict)]
    # Preserve the shared resolver's exact-identity result and its richer
    # abstracts/provider fields. Verification means metadata identity only; it
    # is never evidence that this paper supports a thesis claim.
    # `complete` and `shortfall` are grounded in the collector's verified,
    # facet-balanced result. Display rows alone can include existing sources,
    # so never recompute those decisions here.
    count = int(discovered.get("count", len(sources)))
    verified_count = int(discovered.get("verified_count", sum(source.get("verified") is True for source in sources)))
    relevant_verified_count = int(discovered.get("relevant_verified_count", verified_count))
    shortfall = int(discovered.get("shortfall", max(0, target - relevant_verified_count)))
    out = {
        "sources": sources, "count": count,
        "verified_count": verified_count,
        "relevant_verified_count": relevant_verified_count,
        "new_count": int(discovered.get("new_count", 0)),
        "unverified_count": int(discovered.get("unverified_count", len(discovered.get("unverified_candidates") or []))),
        "existing_needs_review": discovered.get("existing_needs_review") or [],
        "target": int(discovered.get("target", target)), "shortfall": shortfall,
        "coverage": {
            "queries": discovered.get("queries") or [],
            "query_coverage": discovered.get("coverage") or {},
            "query_hits": discovered.get("query_hits") or {},
            "complete": bool(discovered.get("complete", False)),
            "warnings": discovered.get("warnings") or [],
            "requests_completed": int(discovered.get("requests_completed", 0)),
            "providers": discovered.get("providers") or [],
        },
    }
    if count == 0:
        out["hint"] = "Không tìm thấy nguồn. Không được viết như đã có literature; hãy thử lại, thu hẹp chủ đề, hoặc thêm DOI/PDF."
    return json.dumps(out, ensure_ascii=False)


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
    return _quick_sources_impl(query, limit)


def _quick_sources_impl(query: str, limit: int = 5, domain: str | None = None) -> str:
    domain = domain or _classify_domain(None, query, None)
    _lim = max(1, min(limit, 10))
    try:
        # OpenAlex multi-result search: fast, free, no API key. Same validated
        # metadata path the engine's citation cascade trusts (verified DOIs).
        from engine.utils.api_citations.openalex import OpenAlexClient
        papers = OpenAlexClient().search_papers(query, limit=_lim)
    except Exception as e:  # never kill the turn on a search hiccup
        logger.exception("quick_sources failed")
        return json.dumps({
            "error": f"quick search failed: {e}",
            "hint": "Tell the user grounding is briefly unavailable; answer cautiously or retry.",
        })

    # Rank by citation count so the most established work surfaces first.
    papers = sorted(papers or [], key=lambda p: p.get("citation_count", 0) or 0, reverse=True)
    sources = [_norm_source(p) for p in papers]
    # Medical/education: append a few specialized rows (Europe PMC / ERIC), base
    # (cited) papers first. Self-bounded + degrades to [] — never breaks the hot path.
    if domain != "general":
        sources = _dedup_sources(sources + _domain_supplement(query, domain, n=_lim))
    sources = sources[:_lim]
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
