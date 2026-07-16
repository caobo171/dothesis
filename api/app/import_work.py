"""Mid-journey import (API layer): classify a student's uploads and infer per-module slices from
the REAL artifacts so the agent can join a thesis in progress. May use app/orchestrator (this is
NOT the agent layer). Nothing is fabricated — only what an upload evidences.

Layering note: this lives in api/app precisely so it can reach the orchestrator LLM without agent/
ever importing app/. It used to reach the inference helpers too, by importing them from
partner_report_service; that module is gone (the partner endpoint is a headless client of the deep
agent now), so _infer_topic/_infer_model were moved down here VERBATIM — import-your-work is their
ONLY caller. Partner's inference is replaced by the agent's own backfill tool (convergence spec §3),
which is why these did not move into partner_run.
"""
from __future__ import annotations
import logging

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


def _infer_topic(analysis_text: str, language: str) -> dict:
    """Infer the study's framing from the raw analysis output.

    The partner flow only has statistical output (reliability, EFA/CFA, SEM/PLS
    paths, correlations) — no topic. Without a title/objectives/RQs the chapter
    composer emits bracketed "[fill this in]" stubs. This runs ONE cheap LLM
    call to infer research_title / field / objectives / research_questions /
    target_population / scope from the constructs & relationships in the data,
    so the composed prose is concrete. Best-effort: returns {} on any failure.
    """
    import json as _json

    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415 — heavy import

    snippet = (analysis_text or "")[:6000]
    lang_name = "Vietnamese" if str(language).lower().startswith("vi") else "English"
    prompt = (
        "You are a research methodologist. Below is the raw statistical analysis "
        "output of a quantitative study (reliability, EFA/CFA, SEM/PLS path "
        "results, correlations, etc.). Infer the study's most plausible framing "
        "from the CONSTRUCTS, VARIABLES and RELATIONSHIPS present in the data.\n\n"
        f"Write every value in {lang_name}. Be specific and realistic. Do NOT use "
        "bracketed placeholders like [ ... ]. Do NOT restate or verbalize any "
        "statistics/numbers (no coefficients, no p-values, no 'zero point eight "
        "seven') — describe the study's framing conceptually, not its results.\n\n"
        "Field meanings:\n"
        "- research_title: a concise academic title naming the constructs & outcome.\n"
        "- field: the academic discipline.\n"
        "- research_type: e.g. quantitative explanatory / survey-based SEM study.\n"
        "- objectives: the study's AIM/purpose in 1-2 sentences (no numbers).\n"
        "- research_questions: 2-3 questions about the relationships between constructs.\n"
        "- target_population: the likely respondents.\n"
        "- scope: the study's boundary in one phrase.\n\n"
        "Return STRICT JSON only (no prose, no code fence) with exactly these keys:\n"
        '{"research_title": "", "field": "", "research_type": "", "objectives": "", '
        '"research_questions": [], "target_population": "", "scope": ""}\n\n'
        f"ANALYSIS OUTPUT:\n{snippet}"
    )
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(
                str(p.get("text", "") if isinstance(p, dict) else p) for p in content
            )
        content = str(content).strip()
        start, end = content.find("{"), content.rfind("}")
        if start == -1 or end == -1:
            return {}
        data = _json.loads(content[start:end + 1])
        return data if isinstance(data, dict) else {}
    except Exception:
        logger.exception("import: topic inference failed (continuing without it)")
        return {}


def _infer_model(analysis_text: str, language: str) -> dict:
    """Infer the study's structural/conceptual model (constructs + directed
    paths) from the analysis output, for the M3 research-model diagram.

    Returns {"constructs":[{"id","label"}], "paths":[{"from","to"}]} or {}.
    """
    import json as _json

    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415

    snippet = (analysis_text or "")[:6000]
    lang = "Vietnamese" if str(language).lower().startswith("vi") else "English"
    prompt = (
        "From this statistical analysis output, extract the STRUCTURAL / CONCEPTUAL "
        "research model: the latent constructs and the DIRECTED relationships "
        "(which construct predicts which), based on the path/regression results.\n"
        f"Give each construct a short ascii id (no spaces) and a {lang} label.\n"
        "Return STRICT JSON only:\n"
        '{"constructs":[{"id":"","label":""}],"paths":[{"from":"id","to":"id"}]}\n\n'
        f"ANALYSIS OUTPUT:\n{snippet}"
    )
    try:
        resp = _get_llm().invoke(prompt)
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        if s == -1 or e == -1:
            return {}
        data = _json.loads(content[s:e + 1])
        if isinstance(data, dict) and data.get("constructs") and data.get("paths"):
            # The old partner gate (assess_export_readiness) required m3.methodology OR
            # m3.conceptual_model for the methodology chapter, and _infer_model only yields
            # constructs/paths — so a synthesized conceptual_model was needed to unblock it.
            # Kept on the move because import-your-work stores this whole dict as
            # M3.conceptual_model and the description is the only human-readable part of it.
            if not data.get("conceptual_model") and not data.get("methodology"):
                labels = {c.get("id"): (c.get("label") or c.get("id"))
                          for c in data["constructs"] if isinstance(c, dict)}
                rels = "; ".join(
                    f"{labels.get(p.get('from'), p.get('from'))} → "
                    f"{labels.get(p.get('to'), p.get('to'))}"
                    for p in data["paths"] if isinstance(p, dict))
                if str(language).lower().startswith("vi"):
                    data["conceptual_model"] = (
                        "Mô hình nghiên cứu đề xuất gồm các mối quan hệ giả thuyết: "
                        + rels + ".")
                else:
                    data["conceptual_model"] = (
                        "The proposed research model comprises the hypothesized "
                        "relationships: " + rels + ".")
            return data
    except Exception:
        logger.exception("import: model inference failed")
    return {}


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
