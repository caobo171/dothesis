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


def _engine_model():
    """Native engine-shaped model for the citation pipeline.

    The engine's DeepResearchPlanner + CitationResearcher call
    `model.generate_content(prompt, generation_config=...)` (raw google-genai
    interface). LangChain's ChatGoogleGenerativeAI doesn't expose that
    method, so passing it crashed the planner and the engine silently fell
    back to 'standard mode with basic queries' — quality regression.

    GeminiModelWrapper IS the engine's native type. Constructing it directly
    here keeps the planner happy without changing engine internals.
    Resolves the API key via the same dual-name fallback the rest of the
    engine uses (B5 fix).
    """
    from engine.utils.gemini_client import create_gemini_client
    return create_gemini_client(
        model_name=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
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
    # Test seam: M2_SCOUT_TOPIC_COUNT caps how many topic variants we search.
    # Production default = 3 (broad coverage). The sim sets it to 1 because
    # each topic variant fans out to multiple citation APIs + an LLM synthesis
    # call, so dropping from 3->1 cuts M2 wall-clock ~3x without changing
    # behaviour for real users.
    _TOPIC_VARIANTS = [
        "{topic} current state of research",
        "{topic} fundamentals and background",
        "{topic} methodology and approaches",
    ]
    n_topics = max(1, min(3, int(os.getenv("M2_SCOUT_TOPIC_COUNT", "3"))))
    research_topics = [t.format(topic=topic) for t in _TOPIC_VARIANTS[:n_topics]]
    tmp = Path(os.getenv("ORCHESTRATOR_SCRATCH", "/tmp/orchestrator_scratch"))
    tmp.mkdir(parents=True, exist_ok=True)
    # ENGINE-native model — see _engine_model docstring. Reverted from
    # _get_llm (LangChain) because the planner's `.generate_content()` call
    # crashed and the engine fell back to a 10-basic-query mode that
    # under-cited every scout.
    llm = _engine_model()
    try:
        # B4 use_deep_research=True: matches upstream opendraft. Enables the
        # engine's DeepResearchPlanner which expands the topic into 50+ varied
        # queries (vs our hand-rolled 3), routes them through Crossref/OpenAlex/
        # Semantic Scholar/Gemini Grounded. The hand-rolled research_topics are
        # passed too as a seed (engine uses them if planner output is thin).
        result = research_citations_via_api(
            model=llm,
            research_topics=research_topics,
            output_path=tmp / "scout_raw.md",
            target_minimum=min_n,
            use_deep_research=True,
            topic=topic,
            scope=topic,
        )
    except ValueError:
        # The engine raises its quality gate (and discards results) when it finds
        # fewer than ~70% of target_minimum. The gate is only a threshold — it
        # doesn't change how hard the search ran — so retry with a minimal target
        # to RETURN whatever citations were found. A few real citations in the
        # lit review beat zero; the alternative was M2 silently degrading to none.
        result = research_citations_via_api(
            model=llm,
            research_topics=research_topics,
            output_path=tmp / "scout_raw.md",
            target_minimum=1,
            use_deep_research=True,
            topic=topic,
            scope=topic,
        )
    citations = result.get("citations", [])

    def _field(c, name):
        # Citations come back as Citation OBJECTS (not dicts). Reading a falsy
        # field with `getattr(...) or c.get(...)` crashed on objects (no .get),
        # raising AttributeError that bubbled up and made the WHOLE scout return
        # nothing — the real reason M2 degraded to zero citations.
        return c.get(name) if isinstance(c, dict) else getattr(c, name, None)

    return [
        {
            "title": _field(c, "title"),
            "authors": _field(c, "authors"),
            "year": _field(c, "year"),
            # The engine's Citation class exposes `.api_source` (the API the
            # citation came from — Crossref/OpenAlex/Semantic Scholar). Reading
            # `.source` always returned None and broke any downstream filter on
            # this field. Try api_source first; keep `source` as a back-compat
            # path in case anything else (or a dict ingest) uses it.
            "source": _field(c, "api_source") or _field(c, "source"),
            "url": _field(c, "url"),
            "doi": _field(c, "doi"),
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
    # supporting_papers carry reachability fields (doi / url / title) so
    # the frontend sidebar can render each citation as a click-to-open
    # link — without them, the M2 detail modal shows dead rows. Pull the
    # values from the citation payload that's already in `cites_block`.
    prompt = (
        "Analyze these citations and identify 2-4 specific research gaps. "
        "Respond with ONLY a JSON array, no prose. Schema: "
        '[{"description": "...", "relevance": "High|Medium|Low", '
        '"supporting_papers": [{"author": "first-author et al.", '
        '"year": 2020, "title": "...", "doi": "10.xxx/yyy", '
        '"url": "https://..."}]}]. '
        "For each supporting paper you MUST copy doi, url, and title "
        "from the matching citation in the list — do not invent values; "
        "omit a field only if it is genuinely missing from the citation.\n\n"
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
