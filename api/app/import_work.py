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
import re

logger = logging.getLogger(__name__)

# Cheap pre-LLM signal: a doc mentioning these is almost certainly SmartPLS/SPSS output, so we
# skip the model call and classify it as analysis-output directly.
#
# Matched as whole words, not substrings. As bare substrings the short hints are
# far too greedy: "ave" alone matches "have"/"gave"/"average"/"wave", so any
# English prose at all took this branch and skipped classification entirely.
_STAT_HINTS = ("ave", "htmt", "cronbach", "r square", "path coefficient", "outer loading", "vif")
_STAT_HINT_RE = re.compile(
    r"(?<![a-z])(" + "|".join(re.escape(h) for h in _STAT_HINTS) + r")(?![a-z])")

_KINDS = {"proposal", "chapter", "questionnaire", "analysis-output", "dataset", "unknown"}


def _classify(filename: str, text: str) -> str:
    """proposal | chapter | questionnaire | analysis-output | dataset | unknown."""
    low = (text or "").lower()
    if not low.strip():
        return "unknown"
    if _STAT_HINT_RE.search(low):
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


def _infer_analysis_results(analysis_text: str, language: str) -> dict:
    """Extract the STRUCTURED analysis_results block from analysis output.

    Why this exists: storing the paste as a raw string made every downstream
    reader blind to it. `results_render.detect_family` and
    `render_results_tables` bail on a non-dict, `coherence.coverage_findings`
    coerces it to {} and then reports EVERY M3 hypothesis as having no result,
    and `stats_validation` can only say the numbers are unverifiable. A thesis
    whose Chapter 4 table listed H1-H3 in full still came out the far end as
    "no structured result entries for H1, H2, H3".

    The orchestrator's m4_parsers are deliberately NOT used here: they return
    per-step StepResult dicts for the interactive M4 walk, a different shape
    from the analysis_results block these consumers read, and their regexes
    target raw SPSS/SmartPLS console dumps rather than the narrative Word
    tables an imported thesis actually contains.

    Shape follows skills/dothesis-m4-analysis/SKILL.md. Best-effort and
    non-fabricating: keys with no evidence in the text are omitted, and any
    failure returns {} so the caller can fall back to the raw text.
    """
    import json as _json

    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415

    # Larger window than _infer_topic/_infer_model: those need only the framing,
    # which sits up front, whereas the results tables are usually deep in
    # Chapter 4 of an imported thesis and would fall outside a 6k snippet.
    snippet = (analysis_text or "")[:40000]
    lang = "Vietnamese" if str(language).lower().startswith("vi") else "English"
    prompt = (
        "Extract the statistical results from this thesis analysis output into "
        "STRICT JSON. Read tables as well as prose — hypothesis results are "
        f"often in a {lang} summary table (e.g. 'Bảng ... kiểm định giả thuyết').\n\n"
        "CRITICAL: copy every number EXACTLY as written. Do not compute, round, "
        "convert or infer any value. Omit any key you cannot evidence in the "
        "text — an absent key is correct, an invented number is not.\n\n"
        "For each hypothesis give the id as written (H1, H2, ...), the path, the "
        "numbers present, and decision as \"supported\" or \"not supported\" "
        "(map accepted/chấp nhận -> supported, rejected/bác bỏ -> not supported).\n"
        "Record the software and the estimation technique the document NAMES "
        "(e.g. tool \"SPSS\", method \"hồi quy tuyến tính đa biến\"). These carry "
        "the only evidence of how the analysis was actually run: without them a "
        "later step re-infers the method from the model shape and reports "
        "PLS-SEM/SmartPLS for a study done in SPSS. Omit them if unnamed — do "
        "not guess.\n"
        "Schema (include only the keys you have evidence for):\n"
        '{"hypothesis_tests":[{"id":"H1","hypothesis":"H1","path":"X → Y",'
        '"numbers":{"beta":0.0,"t":0.0,"p":"0.000"},"decision":"supported"}],'
        '"measurement_model":[{"construct":"","cronbach_alpha":0.0,'
        '"composite_reliability":0.0,"ave":0.0}],'
        '"structural_model":{"r2":{"OUTCOME":0.0},"tool":"","method":""},'
        '"descriptives":{"n":0}}\n\n'
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
        if not isinstance(data, dict):
            return {}
        # Drop empty containers so "extracted nothing" is falsy for the caller
        # rather than a dict of empty lists that reads as structured-but-blank.
        return {k: v for k, v in data.items() if v}
    except Exception:
        logger.exception("import: analysis-results extraction failed")
    return {}


def _preserve_chapters(text: str) -> list[dict]:
    """Carve an imported write-up into M5 `final_sections`, verbatim.

    The student's own results chapter is the best version of that chapter that
    will ever exist — it has the EFA table, the KMO/Bartlett figures, the
    correlation matrix and the regression output, none of which survive a
    round-trip through a summarised analysis_results block. Composing a
    replacement from that summary produced a Chapter 4 with the tables missing,
    captions stranded above nothing, and PLS metrics invented for an SPSS study.
    So: keep the prose, and let the composer write only what is genuinely absent.

    Returns [] when the document has no confident chapter boundary — leaving it
    alone beats misfiling someone's discussion chapter.
    """
    from orchestrator.chapter_split import split_final_chapter  # noqa: PLC0415

    split = split_final_chapter(text)
    if split is None:
        return []
    head, tail = split
    # chapter_name drives chapters_from_final_sections' mapping onto the
    # editor's canonical slots; `title` alone would need a title reverse-lookup
    # that a Vietnamese heading will not hit.
    return [
        {"chapter_name": "results",
         "title": head.splitlines()[0].strip()[:120] or "Results", "prose": head},
        {"chapter_name": "conclusion",
         "title": tail.splitlines()[0].strip()[:120] or "Conclusion", "prose": tail},
    ]


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
            # Structured if we can parse it, raw text if we can't. The fallback
            # deliberately keeps the string rather than storing {}: a string is
            # what makes stats_validation raise structure.unstructured ("results
            # are stored as free text, so the numbers cannot be verified"), and
            # an empty dict would silence that warning while leaving the results
            # just as unverified.
            parsed = _infer_analysis_results(text, language)
            slices.setdefault("M4", {})["analysis_results"] = parsed or text
            evidence["M4"] = fn
            # PRESERVE the chapters the document actually contains, here, where
            # the raw text still exists.
            #
            # This used to happen later, in backfill_tool._move_final_chapter_to_m5,
            # which re-read m4["analysis_results"] and split it. That worked only
            # while the value was the raw string; once it became the parsed dict
            # above, split_final_chapter's isinstance(str) test failed and the
            # split silently stopped happening — M5 got nothing, so the composer
            # REGENERATED chapters 4 and 5 from the extracted summary and the
            # student's tables vanished. Splitting at the source removes that
            # coupling entirely: M4 owns the structured numbers, M5 owns the
            # prose, and neither depends on the other's representation.
            for section in _preserve_chapters(text):
                slices.setdefault("M5", {}).setdefault("final_sections", []).append(section)
                evidence.setdefault("M5", fn)
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
