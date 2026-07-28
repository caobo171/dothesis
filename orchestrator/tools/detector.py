"""Pluggable AI-text detector — the "referee" in the humanize loop (v4).

WHY THIS EXISTS — the one gap v2/v3 admitted:

    The humanizer had no detector in the loop. It shifted phrasing away from the
    LLM default and *hoped*, but could not measure whether a rewrite actually
    reads as less AI-like. So it plateaued at cosmetic synonym-swaps: with no
    score to chase, there was nothing to tell "áp dụng vs sử dụng" (noise) apart
    from a genuine structural rewrite (signal).

This module supplies that score. `humanize_prose` calls a Scorer after each
rewrite and iterates — adversarial-paraphrasing style (Zhou et al., 2025):
rewrite → score → if still flagged, restructure harder, up to N rounds, keep
the lowest-scoring candidate that still passes the frozen-token gate.

DESIGN — pluggable on purpose (the "#3" decision):

    The score is only useful insofar as it CORRELATES with the detector the
    reader actually runs. A self-hosted model we train is free but transfers
    only ~60-70% to commercial detectors; a commercial API correlates but costs
    money per call. Rather than hard-wire either, the loop talks to a `Scorer`
    interface and the concrete backend is chosen by env:

        HUMANIZE_SCORER = none        -> no scoring, single-pass (v2 behavior)
        HUMANIZE_SCORER = videtect    -> local PhoBERT/mDeBERTa (free, no key)
        HUMANIZE_SCORER = originality -> Originality.ai API (correlates, costs)

Every backend DEGRADES TO None when its model/key/dependency is absent — so
this file is safe to ship before the model is trained or a key is bought. A
None score makes the loop fall back to single-pass, never crashes an export.

Score convention: `score(text)` returns AI-likelihood in [0.0, 1.0] (1.0 =
"definitely AI") or None when the backend can't answer. Lower is the goal.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


def ai_threshold() -> float:
    """Target ceiling — a candidate at or below this is "human enough" to stop.

    0.5 is the usual commercial-detector decision boundary; tune per backend via
    HUMANIZE_AI_THRESHOLD once you can see real scores on real chapters.
    """
    try:
        return float(os.getenv("HUMANIZE_AI_THRESHOLD", "0.5"))
    except ValueError:
        return 0.5


def max_rounds() -> int:
    """How many rewrite→score iterations before shipping the best-so-far.

    Adversarial paraphrasing converges in 3-5 rounds; more buys little and costs
    a rewrite + a score each. Clamped to >=1 so a bad env can't disable the pass.
    """
    try:
        return max(1, int(os.getenv("HUMANIZE_MAX_ROUNDS", "4")))
    except ValueError:
        return 4


@runtime_checkable
class Scorer(Protocol):
    """AI-likelihood scorer. `score` returns [0,1] or None when unavailable."""

    def score(self, text: str) -> float | None: ...


class ViDetectScorer:
    """Local Vietnamese AI-text classifier (PhoBERT / mDeBERTa on ViDetect).

    Free at inference (runs on CPU/MPS, ~50-300ms/passage, no per-call cost) but
    correlates only partially with commercial detectors — treat its score as a
    cheap in-house proxy, not a guarantee about the reader's detector.

    Lazy + defensive: the model loads on first use and, if transformers or the
    weights are missing, this permanently returns None (single-pass fallback)
    rather than raising. That is what lets the architecture ship before the model
    is trained — point HUMANIZE_VIDETECT_MODEL at the weights to light it up.
    """

    def __init__(self, model_path: str | None = None):
        self._model_path = model_path or os.getenv(
            "HUMANIZE_VIDETECT_MODEL", "")
        self._pipe = None
        self._broken = False

    def _ensure(self):
        if self._pipe is not None or self._broken:
            return
        if not self._model_path:
            logger.info("ViDetectScorer: no HUMANIZE_VIDETECT_MODEL set — "
                        "scoring disabled (loop falls back to single-pass).")
            self._broken = True
            return
        try:
            from transformers import pipeline  # noqa: PLC0415 — heavy, lazy
            self._pipe = pipeline("text-classification",
                                  model=self._model_path, truncation=True)
        except Exception:
            logger.exception("ViDetectScorer: could not load %s — disabling.",
                             self._model_path)
            self._broken = True

    def score(self, text: str) -> float | None:
        if not (text or "").strip():
            return None
        self._ensure()
        if self._pipe is None:
            return None
        try:
            # Convention: the fine-tuned head emits a label whose name contains
            # "ai"/"machine"/"1" for the AI class. Map to P(AI) so the caller
            # never depends on a particular label string.
            res = self._pipe(text[:4000])[0]
            label = str(res.get("label", "")).lower()
            p = float(res.get("score", 0.0))
            is_ai = any(k in label for k in ("ai", "machine", "generated", "1"))
            return p if is_ai else 1.0 - p
        except Exception:
            logger.exception("ViDetectScorer: scoring failed")
            return None


class OriginalityScorer:
    """Originality.ai API — the referee that CORRELATES with real graders.

    Costs per call and needs ORIGINALITY_API_KEY; returns None when the key is
    absent or the request fails, so enabling this backend without a key is a
    silent no-op, not a crash. Vietnamese is covered by Originality's
    multilingual model (30+ languages).
    """

    _ENDPOINT = "https://api.originality.ai/api/v1/scan/ai"

    def __init__(self, api_key: str | None = None):
        self._key = api_key or os.getenv("ORIGINALITY_API_KEY", "")
        self._endpoint = os.getenv("ORIGINALITY_ENDPOINT", self._ENDPOINT)

    def score(self, text: str) -> float | None:
        if not (text or "").strip():
            return None
        if not self._key:
            logger.info("OriginalityScorer: no ORIGINALITY_API_KEY — "
                        "scoring disabled (loop falls back to single-pass).")
            return None
        try:
            import requests  # noqa: PLC0415 — lazy, only when this backend runs
            resp = requests.post(
                self._endpoint,
                headers={"X-OAI-API-KEY": self._key,
                         "Accept": "application/json"},
                json={"content": text,
                      "aiModelVersion": os.getenv(
                          "ORIGINALITY_MODEL", "multilingual")},
                timeout=float(os.getenv("ORIGINALITY_TIMEOUT", "30")),
            )
            resp.raise_for_status()
            data = resp.json()
            # Originality returns {"score": {"ai": 0.xx, "original": 0.yy}, ...}
            ai = (data.get("score") or {}).get("ai")
            return float(ai) if ai is not None else None
        except Exception:
            logger.exception("OriginalityScorer: request failed")
            return None


def get_scorer() -> Scorer | None:
    """Build the configured scorer, or None when scoring is off (the default).

    None (not a null-object) on purpose: the caller's `if scorer is None` is the
    single switch between the v4 loop and the untouched v2 single-pass path, so
    an un-configured deployment behaves EXACTLY as before this module existed.
    """
    backend = (os.getenv("HUMANIZE_SCORER", "none") or "none").strip().lower()
    if backend in ("", "none", "off", "0", "false"):
        return None
    if backend == "videtect":
        return ViDetectScorer()
    if backend == "originality":
        return OriginalityScorer()
    logger.warning("Unknown HUMANIZE_SCORER=%r — scoring disabled.", backend)
    return None
