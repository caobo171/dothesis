#!/usr/bin/env python3
"""
ABOUTME: ERIC API client for education research literature search
ABOUTME: Education descriptors + grey literature (reports, dissertations), free JSON, no key
"""

import logging
from typing import Optional, Dict, Any, List

from .base import BaseAPIClient, validate_author_name

logger = logging.getLogger(__name__)

_DOI_PREFIXES = ("http://dx.doi.org/", "https://dx.doi.org/",
                 "http://doi.org/", "https://doi.org/")


class EricClient(BaseAPIClient):
    """ERIC (Education Resources Information Center) client.

    ERIC is the U.S. Dept. of Education's index of education research — journal
    articles (EJ ids) plus grey literature such as reports and dissertations
    (ED ids) that general indexes under-cover. Free JSON API, no key. Returns
    the SAME normalized metadata dict shape as OpenAlexClient.

    API docs: https://eric.ed.gov/?api
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        rate_limit_per_second: float = 2.0,
        timeout: int = 15,
        max_retries: int = 3,
    ):
        super().__init__(
            base_url="https://api.ies.ed.gov/eric",
            rate_limit_per_second=min(rate_limit_per_second, 2.0),
            timeout=timeout,
            max_retries=max_retries,
        )

    def search_paper(self, query: str) -> Optional[Dict[str, Any]]:
        results = self.search_papers(query, limit=1)
        return results[0] if results else None

    def search_papers(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        response = self._make_request(
            method="GET",
            endpoint="/",
            params={
                "search": query,
                "format": "json",
                "rows": min(max(1, limit), 50),
                "fields": ("id,title,author,source,publicationdateyear,"
                           "description,peerreviewed,publicationtype,url"),
            },
        )
        if not response:
            return []

        out: List[Dict[str, Any]] = []
        for doc in ((response.get("response") or {}).get("docs") or []):
            meta = self._extract_metadata(doc)
            if meta:
                out.append(meta)
        return out

    def _extract_metadata(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            title = (doc.get("title") or "").strip()
            if not title:
                return None

            authors: List[str] = []
            for name in (doc.get("author") or []):
                name = str(name).strip()
                if not name:
                    continue
                # ERIC mixes "Weasmer, Jerie" and "Elka Johansson".
                last = name.split(",")[0].strip() if "," in name else name.split()[-1]
                if last:
                    is_valid, _ = validate_author_name(last)
                    if is_valid:
                        authors.append(last)
            if not authors:
                return None

            year = doc.get("publicationdateyear") or 0
            try:
                year = int(year)
            except (TypeError, ValueError):
                year = 0
            if not year:
                return None

            raw_url = (doc.get("url") or "").strip()
            doi = self._doi_from_url(raw_url)
            url = raw_url or f"https://eric.ed.gov/?id={doc.get('id', '')}"

            journal = (doc.get("source") or "").strip()
            pub_types = doc.get("publicationtype") or []
            source_type = "journal" if any("journal" in str(p).lower() for p in pub_types) else "report"

            confidence = self._calculate_confidence(
                has_doi=bool(doi),
                has_journal=bool(journal),
                citation_count=0,
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
                "volume": "",
                "issue": "",
                "pages": "",
                "source_type": source_type,
                "confidence": confidence,
                "abstract": doc.get("description"),
                "citation_count": 0,
            }
        except Exception as e:  # noqa: BLE001
            logger.error(f"ERIC: Error extracting metadata: {e}")
            return None

    @staticmethod
    def _doi_from_url(url: str) -> str:
        low = url.lower()
        for pref in _DOI_PREFIXES:
            if low.startswith(pref):
                return url[len(pref):].strip()
        return ""

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
