"""Mid-journey import (API layer): classify a student's uploads and infer per-module slices from
the REAL artifacts so the agent can join a thesis in progress. May use app/orchestrator (this is
NOT the agent layer). Nothing is fabricated — only what an upload evidences.

Layering note: this lives in api/app precisely so it can reach the partner-report inference helpers
and the orchestrator LLM without agent/ ever importing app/.
"""
from __future__ import annotations
import logging

from .partner_report_service import _infer_topic, _infer_model   # api-layer import is fine here

logger = logging.getLogger(__name__)

# Cheap pre-LLM signal: a doc mentioning these is almost certainly SmartPLS/SPSS output, so we
# skip the model call and classify it as analysis-output directly.
_STAT_HINTS = ("ave", "htmt", "cronbach", "r square", "path coefficient", "outer loading", "vif")

_KINDS = {"proposal", "chapter", "questionnaire", "analysis-output", "dataset", "unknown"}


def _classify(filename: str, text: str) -> str:
    """proposal | chapter | questionnaire | analysis-output | dataset | unknown."""
    low = (text or "").lower()
    if not low.strip():
        return "unknown"
    if any(k in low for k in _STAT_HINTS):
        return "analysis-output"
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415 — orchestrator LLM, not agent layer
    prompt = ("Classify this thesis document as ONE of: proposal, chapter, questionnaire, "
              "analysis-output, dataset, unknown. Reply with one word only.\n\n" + text[:3000])
    try:
        word = str(getattr(_get_llm().invoke(prompt), "content", "")).strip().lower().split()[0]
        return word if word in _KINDS else "unknown"
    except Exception:
        # Classification is best-effort; a failure means we treat the file as unreadable, never crash.
        logger.exception("import: classify failed")
        return "unknown"


def import_existing_work(files: list[dict], language: str) -> dict:
    """Classify each uploaded file and infer the module slice it evidences.

    Returns {slices, evidence, ambiguous, unreadable}. Only evidenced slices appear; datasets are
    ambiguous (evidence only, no auto-slice) and unreadable files are surfaced for the UI.
    """
    slices: dict = {}
    evidence: dict = {}
    ambiguous: list = []
    unreadable: list = []
    for f in files:
        fn, text = f.get("filename", "?"), f.get("text", "")
        kind = _classify(fn, text)
        if kind == "unknown":
            unreadable.append(fn)
            continue
        if kind == "proposal":
            topic = _infer_topic(text, language)
            if topic.get("research_title"):
                slices.setdefault("M1", {}).update(
                    {k: topic[k] for k in ("research_title", "research_questions") if topic.get(k)})
                evidence["M1"] = fn
            model = _infer_model(text, language)
            if model.get("constructs"):
                slices.setdefault("M3", {})["conceptual_model"] = model
                evidence.setdefault("M3", fn)
        elif kind == "analysis-output":
            slices.setdefault("M4", {})["analysis_results"] = text
            evidence["M4"] = fn
        elif kind == "chapter":
            slices.setdefault("M5", {}).setdefault("final_sections", []).append(
                {"title": fn, "prose": text})
            evidence["M5"] = fn
        elif kind == "questionnaire":
            slices.setdefault("M3", {})["instrument"] = {"raw": text}
            evidence.setdefault("M3", fn)
        else:  # dataset — evidence only, no auto-slice (we can't infer a slice from raw data)
            ambiguous.append(fn)
    return {"slices": slices, "evidence": evidence, "ambiguous": ambiguous, "unreadable": unreadable}
