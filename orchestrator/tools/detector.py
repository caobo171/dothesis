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
        HUMANIZE_SCORER = stylometric -> pure-Python burstiness proxy (0 deps)
        HUMANIZE_SCORER = perplexity  -> VN language-model perplexity (free, torch)
        HUMANIZE_SCORER = videtect    -> local PhoBERT/mDeBERTa (free, needs data)
        HUMANIZE_SCORER = originality -> Originality.ai API (correlates, costs)

The backends form a cost/signal ladder. `stylometric` needs nothing installed
and runs instantly, but measures only burstiness — a weak lone signal (Pangram
2025), useful to wire and observe the loop today, not to trust as a verdict.
`perplexity` adds the real DetectGPT-style signal but pulls torch + a VN LM.
`videtect` is a trained classifier (best in-house signal, but needs a labeled
corpus to train — see scripts/train_videtect.py). `originality` is the only one
that correlates with the detector a reader actually runs, and it costs money.

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


class StylometricScorer:
    """Training-free, dependency-free burstiness proxy — runs anywhere, instantly.

    Detectors lean on two statistics: perplexity and BURSTINESS (variance in
    sentence length/structure). This measures the second one cheaply — human
    academic prose alternates short and long sentences, LLM drafts land on a
    metronome. It cannot see perplexity, so on its own it is a WEAK signal
    (Pangram 2025) and must not be read as a verdict; its job is to give the v4
    loop a real, observable score today, with zero install, so the escalation
    ladder can be driven and watched before heavier backends are wired.

    Score = blend of (1 - normalized burstiness) and formulaic-connector density,
    in [0,1], higher = more machine-even.
    """

    # Sentence-length coefficient of variation (stdev/mean) typical of varied
    # human academic prose. Scores at/above this read as "human-bursty" (-> 0).
    _CV_HUMAN = 0.6
    _CONNECTORS = ("hơn nữa", "bên cạnh đó", "đồng thời", "đáng chú ý",
                   "nhìn chung", "không những vậy", "có thể nói", "ngoài ra",
                   "furthermore", "moreover", "additionally", "in conclusion")

    def score(self, text: str) -> float | None:
        import re  # noqa: PLC0415 — stdlib, kept local for symmetry with siblings
        if not (text or "").strip():
            return None
        sents = [s for s in re.split(r"[.!?…]+\s+", text.strip()) if s.strip()]
        if len(sents) < 3:
            return None                       # too short to judge rhythm
        lens = [len(s.split()) for s in sents]
        mean = sum(lens) / len(lens)
        if mean <= 0:
            return None
        var = sum((n - mean) ** 2 for n in lens) / len(lens)
        cv = (var ** 0.5) / mean              # burstiness
        burstiness_ai = max(0.0, 1.0 - cv / self._CV_HUMAN)
        low = text.lower()
        starts = sum(low.count(c) for c in self._CONNECTORS)
        connector_ai = min(1.0, starts / max(1, len(sents)) * 3)
        # Burstiness is the primary signal; connectors nudge it.
        return round(0.75 * burstiness_ai + 0.25 * connector_ai, 4)


class PerplexityScorer:
    """VN language-model perplexity — the DetectGPT-style signal, training-free.

    LLM text is low-perplexity under an LM (the model wrote what the model
    expected); human text is bumpier. This scores a passage by its mean token
    negative-log-likelihood under a small Vietnamese causal LM, squashed to
    [0,1]. Needs torch + transformers + one model download (~0.5-2GB), so it is
    lazy and degrades to None when the stack or model is absent.

    Free (local inference) and needs no labeled data — the pragmatic step up from
    StylometricScorer when the ML deps can be installed. Still a proxy: it does
    not know the reader's detector, only whether the text looks model-typical.
    """

    def __init__(self, model_path: str | None = None):
        # A SMALL VN causal LM by default: perplexity is scored 1-4x per section
        # inside the loop, so a 4B model (slow on CPU, ~8GB download) is the wrong
        # trade — a ~124M GPT-2 gives a usable perplexity signal in tens of ms.
        # Override with HUMANIZE_PERPLEXITY_MODEL for a stronger (heavier) LM.
        self._model_path = model_path or os.getenv(
            "HUMANIZE_PERPLEXITY_MODEL", "NlpHUST/gpt2-vietnamese")
        self._tok = None
        self._model = None
        self._broken = False
        # Perplexity range to normalize into [0,1]; low ppl -> AI (score ->1).
        # Defaults are CALIBRATED for the default NlpHUST/gpt2-vietnamese, whose
        # ppl runs ~15 (AI-typical) to ~30 (human) on academic VN prose — measured
        # on this repo's sample results text. A different --model has a different
        # range; recalibrate HUMANIZE_PPL_LOW/HIGH (decision boundary ~ppl 22).
        try:
            self._lo = float(os.getenv("HUMANIZE_PPL_LOW", "12"))
            self._hi = float(os.getenv("HUMANIZE_PPL_HIGH", "35"))
        except ValueError:
            self._lo, self._hi = 12.0, 35.0

    def _ensure(self):
        if self._model is not None or self._broken:
            return
        try:
            import torch  # noqa: F401,PLC0415
            from transformers import (AutoModelForCausalLM,  # noqa: PLC0415
                                      AutoTokenizer)
            self._tok = AutoTokenizer.from_pretrained(
                self._model_path, trust_remote_code=True)
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_path, trust_remote_code=True)
            self._model.eval()
        except Exception:
            logger.exception("PerplexityScorer: could not load %s — disabling.",
                             self._model_path)
            self._broken = True

    def score(self, text: str) -> float | None:
        if not (text or "").strip():
            return None
        self._ensure()
        if self._model is None:
            return None
        try:
            import torch  # noqa: PLC0415
            enc = self._tok(text[:4000], return_tensors="pt", truncation=True,
                            max_length=1024)
            with torch.no_grad():
                out = self._model(**enc, labels=enc["input_ids"])
            ppl = float(torch.exp(out.loss))
            # Low perplexity -> model-typical -> AI. Linear squash lo..hi -> 1..0.
            frac = (ppl - self._lo) / max(1e-6, self._hi - self._lo)
            return round(min(1.0, max(0.0, 1.0 - frac)), 4)
        except Exception:
            logger.exception("PerplexityScorer: scoring failed")
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
    if backend == "stylometric":
        return StylometricScorer()
    if backend == "perplexity":
        return PerplexityScorer()
    if backend == "videtect":
        return ViDetectScorer()
    if backend == "originality":
        return OriginalityScorer()
    logger.warning("Unknown HUMANIZE_SCORER=%r — scoring disabled.", backend)
    return None
