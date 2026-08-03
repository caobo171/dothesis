"""Similarity ("plagiarism") checking — provider seam, no bundled provider.

Why there is no vendor client in here: a similarity check needs a corpus. Not a
model, a *corpus* — the web, a paper index, and every thesis previously
submitted to the institution. We have none of those, and no amount of prompting
substitutes for one. Anything that claimed to check plagiarism locally would be
guessing, and guessing at "is this plagiarised" is worse than refusing.

So this module is the seam only, deliberately shaped like
`orchestrator.tools.detector.get_scorer()`: `get_provider()` returns None until
a deployment configures one, and every caller branches on None rather than
receiving a null object that silently reports "no matches found" — that
particular lie would tell a student their thesis is clean when nothing looked.

Wiring a real provider (Copyleaks, Turnitin, PlagScan, …) means adding a class
here that implements `SimilarityProvider` against that vendor's documented API,
registering it in `_PROVIDERS`, and setting:

    PLAGIARISM_PROVIDER=<key from _PROVIDERS>
    PLAGIARISM_API_KEY=<vendor key>

It is intentionally left unimplemented rather than stubbed against a guessed
request shape.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class SimilarityProvider(Protocol):
    """One similarity backend.

    `check` returns the vendor's result normalised to:
        {
          "score": float,          # 0-1 overall similarity
          "matches": [             # highest overlap first
            {"source": str, "url": str | None, "overlap": float, "excerpt": str},
            ...
          ],
          "provider": str,
        }
    Raise on transport/auth failure; the caller converts that to an honest
    error rather than to "no matches".
    """

    name: str

    def check(self, text: str, *, language: str = "vi") -> dict[str, Any]: ...


# Populated when a vendor client is added. Empty is the correct default state:
# no configured provider means the feature reports itself unavailable.
_PROVIDERS: dict[str, type] = {}


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def get_provider() -> SimilarityProvider | None:
    """The configured provider, or None when similarity checking is off.

    None (not a null object) for the same reason as detector.get_scorer: the
    caller's `if provider is None` is the single switch, and an unconfigured
    deployment must degrade to "we can't check this" rather than to a clean bill
    of health.
    """
    key = (os.getenv("PLAGIARISM_PROVIDER", "") or "").strip().lower()
    if key in ("", "none", "off", "0", "false"):
        return None
    cls = _PROVIDERS.get(key)
    if cls is None:
        logger.warning(
            "Unknown PLAGIARISM_PROVIDER=%r (available: %s) — checking disabled.",
            key, available_providers() or "none built in",
        )
        return None
    if not (os.getenv("PLAGIARISM_API_KEY", "") or "").strip():
        logger.warning("PLAGIARISM_PROVIDER=%r set but PLAGIARISM_API_KEY is empty.", key)
        return None
    return cls()  # type: ignore[return-value]
