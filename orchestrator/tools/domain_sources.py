"""Domain-routed academic sources — shared by the agent scout AND the report
backfill.

Lives in the orchestrator layer (may import engine) so BOTH `agent/tools/research.py`
(agent → orchestrator is allowed) and `orchestrator/backfill.py` can use it without
the illegal orchestrator → agent import. OpenAlex/Crossref/Semantic Scholar stay the
universal base; for two segments we ALSO query a specialized index — Europe PMC
(biomedical) and ERIC (education) — routed by the thesis domain.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from engine.utils.api_citations.europe_pmc import EuropePmcClient
from engine.utils.api_citations.eric import EricClient

logger = logging.getLogger(__name__)


# Deterministic keyword match (no LLM): the primary market writes Vietnamese, so
# both languages are covered. `sinh viên`/`student` is deliberately excluded from
# education — it saturates business/IS topics and would misroute them.
_MEDICAL_TERMS = (
    "medicine", "medical", "health", "clinical", "nursing", "pharmac",
    "epidemiolog", "dentist", "public health", "patient", "disease", "therapy",
    "y khoa", "y học", "y tế", "điều dưỡng", "dược", "sức khỏe", "lâm sàng",
    "bệnh nhân", "bệnh viện",
)
_EDUCATION_TERMS = (
    "education", "pedagog", "teaching", "curriculum", "classroom", "teacher",
    "e-learning", "literacy", "giáo dục", "sư phạm", "dạy học", "giảng dạy",
    "chương trình đào tạo", "giáo viên", "học sinh",
)


def classify_domain(field: str | None, topic: str = "",
                    research_questions: list[str] | None = None) -> str:
    """Return "medical" | "education" | "general" for source routing.

    `field` (the M1/project discipline) is the highest-precision signal; the
    topic + research-question text is the fallback. Ambiguous (both or neither)
    → "general": a missed supplement is cheap, a wrong one is noise.
    """
    field_l = (field or "").strip().lower()
    if field_l:
        med = any(t in field_l for t in _MEDICAL_TERMS)
        edu = any(t in field_l for t in _EDUCATION_TERMS)
        if med and not edu:
            return "medical"
        if edu and not med:
            return "education"
        if med or edu:  # explicit field but ambiguous — trust it over free text
            return "general"
    text = " ".join([topic or "", *(research_questions or [])]).lower()
    med = any(t in text for t in _MEDICAL_TERMS)
    edu = any(t in text for t in _EDUCATION_TERMS)
    if med and not edu:
        return "medical"
    if edu and not med:
        return "education"
    return "general"


def search_query_en(topic: str, research_questions: list[str] | None) -> str:
    """One short ENGLISH bibliographic query from the (possibly Vietnamese) topic.

    The domain indexes (Europe PMC / ERIC) are English catalogs and our primary
    market writes Vietnamese, so a raw topic returns near-nothing. A tiny LLM call
    turns it into an English keyword query, self-bounded by its own wall clock —
    on timeout/failure we degrade to the raw topic (a weak query beats none).
    """
    import concurrent.futures as _fut

    def _translate() -> str:
        from orchestrator.tools.m5_writing import _get_llm  # intra-layer
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

    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        q = ex.submit(_translate).result(timeout=int(os.getenv("DOTHESIS_TRANSLATE_TIMEOUT_S", "15")))
        if q:
            return q
    except Exception:
        logger.exception("domain_sources: query translation failed; using raw topic")
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return (topic or "").strip()[:200]


def norm_source(p: dict) -> dict:
    """OpenAlex/EuropePMC/ERIC client dict -> the M2 Source shape."""
    return {
        "title": p.get("title"),
        "authors": p.get("authors"),
        "year": p.get("year"),
        "venue": p.get("journal") or p.get("publisher"),
        "doi": p.get("doi"),
        "url": p.get("url"),
        "verified": bool(p.get("doi")),
    }


def domain_supplement(query: str, domain: str, n: int = 8,
                      clients: dict[str, type] | None = None) -> list[dict]:
    """One bounded query to the domain-specialized index, normalized to the M2
    Source shape. Any failure/timeout/rate-limit degrades to an empty list — the
    supplement NEVER hangs the scout or zeroes its results. [] for "general".

    `clients` lets a caller inject the class map (agent/tools/research.py passes
    its own module-level EuropePmcClient/EricClient so monkeypatch-based tests
    keep working); defaults to the classes imported here.
    """
    client_cls = (clients or {"medical": EuropePmcClient,
                              "education": EricClient}).get(domain)
    if client_cls is None or not (query or "").strip():
        return []

    import concurrent.futures as _fut

    def _fetch() -> list[dict]:
        papers = client_cls().search_papers(query, limit=n)
        return [norm_source(p) for p in (papers or [])]

    ex = _fut.ThreadPoolExecutor(max_workers=1)
    try:
        return ex.submit(_fetch).result(
            timeout=int(os.getenv("DOTHESIS_DOMAIN_SOURCE_TIMEOUT_S", "20")))
    except Exception:
        logger.exception("domain_sources: supplement (%s) failed/timed out", domain)
        return []
    finally:
        ex.shutdown(wait=False, cancel_futures=True)


_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/",
                 "https://dx.doi.org/", "http://dx.doi.org/")


def _doi_key(doi) -> str:
    d = str(doi or "").strip().lower()
    for pref in _DOI_PREFIXES:
        if d.startswith(pref):
            d = d[len(pref):]
            break
    return d


def _title_key(title) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title or "").lower()).strip()


def dedup_sources(sources: list[dict]) -> list[dict]:
    """First-wins dedup by DOI (fallback normalized title). Base sources should be
    listed FIRST so a paper found by both a validated base source and a supplement
    keeps the base row; a DOI-less kept row is backfilled from a later duplicate
    that does carry a DOI (keep-most-complete-metadata)."""
    out: list[dict] = []
    by_doi: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    for s in sources or []:
        dk = _doi_key(s.get("doi"))
        tk = _title_key(s.get("title"))
        keep = by_doi.get(dk) if dk else None
        if keep is None and tk:
            keep = by_title.get(tk)
        if keep is not None:
            if not _doi_key(keep.get("doi")) and dk:
                keep["doi"] = s.get("doi")
                keep["verified"] = True
                by_doi[dk] = keep
            continue
        out.append(s)
        if dk:
            by_doi[dk] = s
        if tk:
            by_title[tk] = s
    return out
