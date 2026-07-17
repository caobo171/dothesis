#!/usr/bin/env python3
"""
ABOUTME: Europe PMC API client for biomedical/medical literature search
ABOUTME: Covers PubMed/MEDLINE + full text + preprints, free REST/JSON, no key
"""

import logging
import os
import re
from typing import Optional, Dict, Any, List

from .base import BaseAPIClient, validate_author_name

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"<[^>]+>")


class EuropePmcClient(BaseAPIClient):
    """Europe PMC client for biomedical paper search.

    Europe PMC federates PubMed/MEDLINE, PMC full text, Agricola, patents and
    biomedical preprints behind one free REST/JSON API (no key required).
    Returns the SAME normalized metadata dict shape as OpenAlexClient so the M2
    scout can merge/dedup results without any downstream change.

    API docs: https://europepmc.org/RestfulWebService
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_per_second: float = 5.0,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        polite_email = os.getenv("OPENALEX_EMAIL", "dothesis@users.noreply.github.com")
        super().__init__(
            base_url="https://www.ebi.ac.uk/europepmc/webservices/rest",
            rate_limit_per_second=min(rate_limit_per_second, 5.0),
            timeout=timeout,
            max_retries=max_retries,
        )
        self.session.headers.update({
            "User-Agent": f"DoThesis/1.7 (mailto:{polite_email})",
        })

    def search_paper(self, query: str) -> Optional[Dict[str, Any]]:
        results = self.search_papers(query, limit=1)
        return results[0] if results else None

    def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        response = self._make_request(
            method="GET",
            endpoint="/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": min(max(1, limit), 100),
                "resultType": "core",
            },
        )
        if not response:
            return []

        out: List[Dict[str, Any]] = []
        for result in (response.get("resultList", {}) or {}).get("result", []) or []:
            meta = self._extract_metadata(result)
            if meta:
                out.append(meta)
        return out

    def _extract_metadata(self, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            title = (result.get("title") or "").strip().rstrip(".")
            if not title:
                return None

            # Authors — prefer structured authorList, fall back to authorString.
            authors: List[str] = []
            author_list = (result.get("authorList") or {}).get("author") or []
            for a in author_list:
                last = (a.get("lastName") or "").strip()
                if not last and a.get("fullName"):
                    last = str(a["fullName"]).split()[-1]
                if last:
                    is_valid, _ = validate_author_name(last)
                    if is_valid:
                        authors.append(last)
            if not authors and result.get("authorString"):
                # "Berube LT, Popp CJ, ..." -> family names are the first token.
                for chunk in str(result["authorString"]).split(","):
                    tok = chunk.strip().split()
                    if tok:
                        is_valid, _ = validate_author_name(tok[0])
                        if is_valid:
                            authors.append(tok[0])
            if not authors:
                return None

            year = 0
            try:
                year = int(str(result.get("pubYear") or "").strip() or 0)
            except (TypeError, ValueError):
                year = 0
            if not year:
                return None

            doi = (result.get("doi") or "").strip()
            if doi:
                url = f"https://doi.org/{doi}"
            else:
                url = f"https://europepmc.org/abstract/{result.get('source', 'MED')}/{result.get('id', '')}"

            journal_info = result.get("journalInfo") or {}
            journal = ((journal_info.get("journal") or {}).get("title") or "").strip()
            volume = str(journal_info.get("volume") or "")
            issue = str(journal_info.get("issue") or "")
            pages = str(result.get("pageInfo") or "")

            pub_types = (result.get("pubTypeList") or {}).get("pubType") or []
            source_type = self._map_source_type(pub_types)

            abstract = result.get("abstractText")
            if abstract:
                abstract = _TAG_RE.sub(" ", str(abstract)).strip()

            citation_count = int(result.get("citedByCount") or 0)

            confidence = self._calculate_confidence(
                has_doi=bool(doi),
                has_journal=bool(journal),
                citation_count=citation_count,
                author_count=len(authors),
            )

            return {
                "title": title,
                "authors": authors,
                "year": year,
                "doi": doi,
                "url": url,
                "journal": journal,
                "publisher": "",
                "volume": volume,
                "issue": issue,
                "pages": pages,
                "source_type": source_type,
                "confidence": confidence,
                "abstract": abstract,
                "citation_count": citation_count,
            }
        except Exception as e:  # noqa: BLE001 — one bad record must not kill the batch
            logger.error(f"EuropePMC: Error extracting metadata: {e}")
            return None

    def _map_source_type(self, pub_types: List[str]) -> str:
        low = {str(p).lower() for p in pub_types}
        if any("preprint" in p for p in low):
            return "report"
        if any("book" in p for p in low):
            return "book"
        if any("conference" in p or "proceedings" in p for p in low):
            return "conference"
        return "journal"

    def _calculate_confidence(
        self, has_doi: bool, has_journal: bool, citation_count: int, author_count: int
    ) -> float:
        score = 0.5
        if has_doi:
            score += 0.25
        if has_journal:
            score += 0.1
        if citation_count > 10:
            score += 0.1
        elif citation_count > 0:
            score += 0.05
        if author_count > 0:
            score += 0.05
        return min(score, 1.0)
