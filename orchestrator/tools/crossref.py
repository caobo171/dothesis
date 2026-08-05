"""CrossRef lookups — the one place that talks to the citation index.

Pulled out of api/app/routers/tools.py when the citation work grew past a single
endpoint: the router, the reference-list checker and the .docx citer all needed
the same three calls, and the router is the wrong home for something the
orchestrator has to import (api -> orchestrator is the allowed direction; the
reverse is the recurring architecture defect in this repo).

Nothing here decides anything. A caller gets the raw CrossRef `message` and
makes its own judgement, because the judgement — exact DOI hit vs. "CrossRef
returned its best guess for any query" — is what every citation surface in this
product must not flatten.
"""
from __future__ import annotations

import logging
import re
import time

import httpx

logger = logging.getLogger(__name__)

WORKS = "https://api.crossref.org/works"

# Identify ourselves. CrossRef's polite pool asks for it and gives better
# availability in return; an anonymous flood is how a free API gets closed.
_UA = "DoThesis/1.0 (citation tools)"

_TIMEOUT = 15

DOI_RE = re.compile(r"\b(10\.\d{4,9}/[-._;()/:A-Z0-9]+)\b", re.I)

# CrossRef matches on a bibliographic string, not a paragraph. Everything past
# this is noise that pulls the match away rather than sharpening it.
_QUERY_CHARS = 400

_RETRIES = 2


def _backoff(response, attempt: int) -> float:
    """Seconds to wait before retrying a throttled request.

    CrossRef sends Retry-After on the polite pool. Honoured, but capped: a
    student is waiting on this, and a long stall reads as a hang.
    """
    try:
        wait = float(response.headers.get("Retry-After") or 0)
    except ValueError:  # Retry-After may be an HTTP date
        wait = 0.0
    return min(wait, 5.0) if wait > 0 else 0.5 * (2 ** attempt)


def by_doi(doi: str) -> dict | None:
    """Exact lookup. None means CrossRef has no record of that DOI."""
    r = httpx.get(f"{WORKS}/{doi}", timeout=_TIMEOUT, headers={"User-Agent": _UA})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("message")


def by_text(text: str) -> dict | None:
    """Best bibliographic match, or None.

    FUZZY: CrossRef ranks and returns something for almost any query, so a
    result is evidence that a similar work exists — never proof that the
    caller's reference is real.
    """
    items = search(text, rows=1)
    return items[0] if items else None


def search(text: str, rows: int = 3) -> list[dict]:
    """Top `rows` bibliographic matches, best first.

    Used by the citer, which needs candidates to CHOOSE between rather than one
    answer to accept — picking the single top hit is how a plausible-looking
    wrong source gets attached to a student's claim.
    """
    params = {"query.bibliographic": text[:_QUERY_CHARS], "rows": rows,
              "select": "DOI,title,author,issued,container-title,URL,abstract,type"}
    for attempt in range(_RETRIES + 1):
        try:
            r = httpx.get(WORKS, timeout=_TIMEOUT, headers={"User-Agent": _UA},
                          params=params)
            # A whole thesis is 50-odd lookups in a burst, which is exactly what
            # CrossRef throttles. Without a retry a 429 reads as "no such work"
            # and the student is told their real reference could not be found.
            if r.status_code in (429, 503) and attempt < _RETRIES:
                time.sleep(_backoff(r, attempt))
                continue
            r.raise_for_status()
            return (r.json().get("message") or {}).get("items") or []
        except Exception:  # noqa: BLE001 — a search failure is "no candidate", not a crash
            logger.warning("crossref search failed for %r", text[:80], exc_info=True)
            return []
    return []
