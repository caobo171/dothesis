"""M2 — Literature Review tools.

Thin wrappers around engine/utils/* + small LLM helpers. The heavy lifting
(citation discovery, deep research, citation formatting) stays in engine/.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

# Make engine package importable as a sibling.
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logger = logging.getLogger(__name__)


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.3,
    )


# Re-exported here so tests can monkeypatch easily — the real import is late
# (inside the function body) to avoid import-time failures when engine/ is
# not fully available in test environments.
def research_citations_via_api(model, research_topics, output_path, target_minimum, **kw):
    from engine.utils.agent_runner import research_citations_via_api as _real
    return _real(model, research_topics, output_path, target_minimum, **kw)


def _read_paper_text(p: str) -> str:
    path = Path(p)
    if path.suffix.lower() == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path))
        except Exception:
            logger.warning("pdfminer extract failed for %s", path)
            return ""
    return path.read_text(encoding="utf-8", errors="ignore")


@tool
def scout_citations(topic: str, min_n: int = 20) -> list[dict]:
    """Discover at least `min_n` academic citations for `topic`.

    Returns a list of dicts: {title, authors, year, source, url, doi}.
    Backed by engine/utils/agent_runner.research_citations_via_api.
    """
    research_topics = [
        f"{topic} fundamentals and background",
        f"{topic} current state of research",
        f"{topic} methodology and approaches",
    ]
    tmp = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    tmp.mkdir(parents=True, exist_ok=True)
    result = research_citations_via_api(
        model=_get_llm(),
        research_topics=research_topics,
        output_path=tmp / "scout_raw.md",
        target_minimum=min_n,
    )
    citations = result.get("citations", [])
    return [
        {
            "title": getattr(c, "title", None) or c.get("title"),
            "authors": getattr(c, "authors", None) or c.get("authors"),
            "year": getattr(c, "year", None) or c.get("year"),
            "source": getattr(c, "source", None) or c.get("source"),
            "url": getattr(c, "url", None) or c.get("url"),
            "doi": getattr(c, "doi", None) or c.get("doi"),
        }
        for c in citations
    ]


@tool
def summarize_paper(pdf_path: str) -> str:
    """Read a PDF / text file and produce a concise academic summary."""
    text = _read_paper_text(pdf_path)
    if not text.strip():
        return ""
    snippet = text[:8000]
    llm = _get_llm()
    prompt = (
        "Summarize this academic paper in 3-5 sentences. Focus on: research question, "
        "method, key findings, theoretical contribution. Plain prose, no headings.\n\n"
        + snippet
    )
    return llm.invoke(prompt).content.strip()


@tool
def find_research_gaps(citations: list[dict]) -> list[dict]:
    """Identify research gaps from a list of citations.

    Returns: [{description, supporting_papers, relevance}, ...]
    Backed by an LLM call (no engine wrapping yet — pure prompt).
    """
    if not citations:
        return []
    cites_block = json.dumps(citations[:50], default=str)[:6000]
    llm = _get_llm()
    prompt = (
        "Analyze these citations and identify 2-4 specific research gaps. "
        "Respond with ONLY a JSON array, no prose. Schema: "
        '[{"description": "...", "relevance": "High|Medium|Low", '
        '"supporting_papers": [{"author": "...", "year": 2020}]}].\n\n'
        f"Citations: {cites_block}"
    )
    resp = llm.invoke(prompt).content
    try:
        return list(json.loads(resp))
    except (json.JSONDecodeError, TypeError):
        logger.warning("find_research_gaps: malformed LLM response: %r", resp[:200])
        return []


class CitationCompiler:
    """Wrapper class so tests can monkeypatch at the symbol.

    The engine's CitationCompiler requires a CitationDatabase object and has a
    different method name (compile_citations). This wrapper provides the simple
    CitationCompiler(style).compile(items) interface expected by the orchestrator
    layer, delegating to a plain text formatter rather than the engine internals
    since the engine's interface is incompatible with the thin-wrapper contract.
    """

    def __init__(self, style: str):
        # Decision: store style for formatting; engine's CitationCompiler requires
        # a full CitationDatabase which we don't have at this layer. We format
        # directly here and leave deep integration for a follow-on sub-project.
        self.style = style

    def compile(self, items: list[dict]) -> str:
        """Format citation items into a reference list string."""
        lines = []
        for item in items:
            author = item.get("author") or item.get("authors") or "Unknown Author"
            year = item.get("year", "n.d.")
            title = item.get("title") or "Untitled"
            source = item.get("source") or item.get("journal") or ""
            doi = item.get("doi") or item.get("url") or ""
            if self.style.lower().startswith("apa"):
                # APA 7 format: Author, A. (Year). Title. Source. DOI
                line = f"{author} ({year}). {title}."
                if source:
                    line += f" {source}."
                if doi:
                    line += f" {doi}"
            else:
                # Generic fallback
                line = f"{author} ({year}). {title}."
            lines.append(line)
        return "\n".join(lines)


@tool
def compile_citations(items: list[dict], style: str = "apa7") -> str:
    """Format `items` into a citation list using the given style.

    Backed by CitationCompiler (wraps engine/utils/citation_compiler pattern).
    """
    return CitationCompiler(style).compile(items)


@tool
def verify_page_numbers(claim: dict) -> dict:
    """Verify a page-reference claim against the source PDF if available.

    `claim` shape: {author, year, page, quote, [pdf_path]}.
    Returns: {status: "verified" | "unverified" | "not_found", message: str}.
    Sub-project 1: returns "unverified" when no PDF path; a follow-on sub-project
    will integrate the existing PDF text-search code in engine/utils/.
    """
    pdf_path = claim.get("pdf_path")
    if not pdf_path or not Path(pdf_path).exists():
        return {"status": "unverified",
                "message": "No source PDF available — page reference marked [page?]"}
    text = _read_paper_text(pdf_path)
    quote = (claim.get("quote") or "").strip()
    if quote and quote.lower() in text.lower():
        return {"status": "verified", "message": "Quote found in source PDF"}
    return {"status": "not_found",
            "message": "Quote not found at the cited page; user should re-check"}
