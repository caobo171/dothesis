"""M1 — Topic Discovery tools.

Sub-project 1 ships light LLM helpers; later sub-projects can swap in
domain-specific data sources (Semantic Scholar trending topics, etc.).
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.tools import tool
from orchestrator.llm import get_orchestrator_llm

logger = logging.getLogger(__name__)

# How many sources to ground a raw-idea brief on. Kept small: the brief is a
# fast "is this worth pursuing" step (one direct Crossref query), not the full
# minutes-long M2 review.
_BRIEF_SCOUT_MIN = 6


def _is_vietnamese(text: str) -> bool:
    """Cheap heuristic: any Vietnamese-specific diacritic → answer in Vietnamese."""
    return bool(re.search(r"[ăâđêôơưÀ-ỹ]", text or "", re.IGNORECASE))


def _quick_crossref(query_en: str, n: int = 8, timeout_s: int = 20) -> list[dict]:
    """Fast, direct Crossref search (~1-2s) → real peer-reviewed sources + DOIs.

    The full deep scout runs 100+ queries and rate-limits into minutes, which is
    overkill for a raw-idea brief. A single Crossref query gives ~8 verified
    sources fast. Best-effort: returns [] on any failure (grounding is a
    nice-to-have, never a hard blocker).
    """
    import httpx

    try:
        r = httpx.get(
            "https://api.crossref.org/works",
            params={
                "query.bibliographic": query_en,
                "rows": n,
                "select": "title,author,issued,DOI,container-title,URL",
                "filter": "type:journal-article,has-abstract:true",
                "sort": "relevance",
            },
            timeout=timeout_s,
            headers={"User-Agent": "DoThesis-M1Brief/1.0 (mailto:cao.nguyen@wele-learn.com)"},
        )
        items = r.json().get("message", {}).get("items", [])
    except Exception:
        logger.warning("research_brief: Crossref search failed", exc_info=True)
        return []

    out: list[dict] = []
    for it in items:
        title = (it.get("title") or [""])[0].strip()
        if not title:
            continue
        authors = [str(a.get("family")).strip() for a in it.get("author", []) if a.get("family")]
        parts = (it.get("issued", {}).get("date-parts") or [[None]])
        year = parts[0][0] if parts and parts[0] else None
        out.append({
            "title": title, "authors": authors, "year": year,
            "venue": (it.get("container-title") or [None])[0],
            "doi": it.get("DOI"), "url": it.get("URL"),
        })
    return out[:n]


def _get_llm():
    """Single chokepoint for LLM creation — easy to monkeypatch in tests.

    Delegates to the engine-wide factory so ORCHESTRATOR_LLM_ROUTE routes every
    tool at once; temperature 0.4 is this tool's original per-site setting.
    """
    return get_orchestrator_llm(temperature=0.4)


@tool
def suggest_topics(field: str) -> list[str]:
    """Return 5-10 currently-trending research topics in the given academic field.

    Returns an empty list if the LLM can't produce a JSON-parseable response.
    """
    llm = _get_llm()
    prompt = (
        f"List 5 to 10 currently-trending research topics in the field of {field}. "
        "Respond with ONLY a JSON array of strings, no prose."
    )
    resp = llm.invoke(prompt).content
    try:
        topics = json.loads(resp)
        if isinstance(topics, list):
            return [str(t) for t in topics]
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_topics: malformed LLM response: %r", resp[:200])
    return []


@tool
def research_brief(idea: str, field: str = "") -> dict:
    """Turn a raw research idea into a GROUNDED brief: clear context, the
    research gap, and suggested topics — each tied to REAL literature.

    Scouts a few real papers for the idea, then synthesizes:
      - context: 1-2 short paragraphs on the background / why it matters,
      - gaps: 2-4 specific research gaps, each citing the sources supporting it,
      - suggested_topics: 3-5 concrete, PICO-shaped research directions that
        target those gaps.
    Every gap/topic cites ONLY the numbered sources (no invented references).
    Returns {context, gaps, suggested_topics, sources, grounded}. Answers in
    Vietnamese when the idea is Vietnamese.
    """
    vi = _is_vietnamese(idea)

    # 1) Ground the brief in real literature. Peer-reviewed titles are English,
    # so translate a Vietnamese idea to English keywords first, then run ONE
    # fast Crossref query (not the minutes-long 100-query deep scout).
    query_en = idea
    if vi:
        try:
            query_en = (_get_llm().invoke(
                "Extract 4-8 English keywords for a bibliographic literature search "
                "from this research idea. Return ONLY the space-separated keywords, "
                "no prose, no punctuation.\n\n" + idea
            ).content or "").strip() or idea
        except Exception:
            query_en = idea
    sources = _quick_crossref(query_en, n=_BRIEF_SCOUT_MIN + 4)[:12]

    numbered = "\n".join(
        f"[{i + 1}] {s.get('authors') or s.get('author') or '?'} "
        f"({s.get('year', 'n.d.')}). {s.get('title', '')}"
        for i, s in enumerate(sources)
    ) or "(no sources found — omit the [n] citation markers)"
    lang_line = ("Viết TOÀN BỘ bằng tiếng Việt học thuật."
                 if vi else "Write everything in academic English.")
    prompt = (
        "You are a research advisor. Given a raw research IDEA and a numbered list "
        "of REAL papers found for it, produce a grounded research brief.\n"
        f"{lang_line}\n\n"
        "Rules:\n"
        "- Cite ONLY the numbered sources below, as [n]. NEVER invent a paper or a "
        "number not in the list. Drop any gap/topic with no supporting source (if "
        "there are no sources at all, omit the [n] markers entirely).\n"
        "- gaps must be SPECIFIC (what is missing / inconsistent / under-studied), "
        "not generic filler.\n"
        "- suggested_topics must be concrete, feasible, and target the gaps; phrase "
        "each as a researchable question (PICO-style when clinical).\n\n"
        f"IDEA:\n{idea}\n\nFIELD: {field or 'unspecified'}\n\nSOURCES:\n{numbered}\n\n"
        "Return STRICT JSON only:\n"
        '{"context":"...","gaps":[{"description":"...","refs":[1,2]}],'
        '"suggested_topics":[{"title":"...","rationale":"...","refs":[3]}]}'
    )
    raw = _get_llm().invoke(prompt).content
    if isinstance(raw, list):
        raw = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in raw)
    raw = str(raw)
    data: dict = {}
    try:
        s, e = raw.find("{"), raw.rfind("}")
        if s != -1 and e != -1:
            data = json.loads(raw[s:e + 1])
    except (json.JSONDecodeError, TypeError):
        logger.warning("research_brief: malformed LLM JSON: %r", raw[:200])

    src_out = [
        {"n": i + 1,
         "authors": s.get("authors") or s.get("author") or "",
         "year": s.get("year"),
         "title": s.get("title", ""),
         "url": s.get("url") or (f"https://doi.org/{s.get('doi')}" if s.get("doi") else "")}
        for i, s in enumerate(sources)
    ]
    return {
        "context": str(data.get("context") or ""),
        "gaps": data.get("gaps") or [],
        "suggested_topics": data.get("suggested_topics") or [],
        "sources": src_out,
        "grounded": bool(sources),
    }


@tool
def refine_title(seed: str) -> str:
    """Polish a draft thesis title into academic phrasing.

    Returns the polished title verbatim from the LLM. Caller should validate.
    """
    llm = _get_llm()
    prompt = (
        f"You are an academic writing coach. Rewrite this draft research title in "
        f"clear, formal academic English. Return ONLY the polished title, no quotes "
        f"or explanation. Draft: {seed}"
    )
    return llm.invoke(prompt).content.strip()
