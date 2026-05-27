"""M4 — Data Analysis tools.

Sub-project 1 ships file-type detection + outline generation as real logic,
but `run_analysis_step` and `interpret_result` are LLM-based stubs. A later
sub-project will replace them with proper SPSS/SmartPLS/CB-SEM parsers.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Literal

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from orchestrator.tools.m4_parsers import dispatch_parse
from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

logger = logging.getLogger(__name__)

DataType = Literal["SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"]

_SPSS_EXTS = {".sav", ".spv", ".sps"}
_SEM_HTML_MARKERS = ("smartpls", "pls algorithm", "outer loadings", "htmt", "amos output", "lavaan")


def _get_llm():
    # Centralised LLM factory — allows monkeypatching in tests without touching
    # tool internals; model is configurable via env var for staging vs. prod.
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.2,
    )


@tool
def detect_data_type(file_path: str) -> DataType:
    """Identify which analysis software / paradigm produced this file.

    Detection priority:
      1. file extension (.sav/.spv/.sps → SPSS)
      2. HTML signature (SmartPLS / AMOS / lavaan keywords)
      3. plain-text heuristic (interview transcript)
      4. Unknown
    """
    p = Path(file_path)
    if not p.exists():
        return "Unknown"
    # Priority 1: SPSS binary formats are unambiguously identified by extension.
    if p.suffix.lower() in _SPSS_EXTS:
        return "SPSS"
    try:
        head = p.read_text(encoding="utf-8", errors="ignore")[:8000].lower()
    except Exception:
        return "Unknown"
    # Priority 2: HTML/text output from SEM tools — check most-specific first
    # (SmartPLS before generic CB-SEM) to avoid mis-classification.
    for marker in _SEM_HTML_MARKERS:
        if marker in head:
            if "smartpls" in head or "pls algorithm" in head or "htmt" in head:
                return "SmartPLS"
            return "CB-SEM"
    # Priority 3: Qualitative transcript heuristic — speaker labels are a strong
    # signal for interview/focus-group data.
    if "interviewer:" in head or "participant:" in head or "p1:" in head:
        return "Qualitative"
    return "Unknown"


_OUTLINE_TEMPLATES: dict[str, list[str]] = {
    "SPSS": [
        "Descriptive Statistics", "Reliability (Cronbach's Alpha)",
        "EFA", "Correlation Matrix", "Regression Analysis", "ANOVA / t-tests",
    ],
    "SmartPLS": [
        "Measurement Model: Outer Loadings",
        "Convergent Validity: AVE & CR",
        "Discriminant Validity: HTMT & Fornell-Larcker",
        "Collinearity: VIF",
        "Path Coefficients (Bootstrap 5000)",
        "R² and Adjusted R²",
        "Effect size (f²)",
        "Predictive Relevance (Q²)",
    ],
    "CB-SEM": [
        "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
        "Discriminant Validity",
        "Structural Model",
        "Mediation/Moderation",
    ],
    "Qualitative": [
        "Familiarization with data",
        "Initial coding (line-by-line)",
        "Theme generation",
        "Theme review & refinement",
        "Theme definition & naming",
        "Writing results with verbatim quotes",
    ],
    "Mixed": ["Quantitative phase (see SPSS/SmartPLS outline)",
              "Qualitative phase (Thematic Analysis)",
              "Integration: convergence, divergence, expansion"],
}


@tool
def generate_analysis_outline(data_type: str, methodology: dict | None = None) -> dict:
    """Return a standard analysis outline for the given data type.

    Falls back to generic descriptive/inferential sections for unrecognised
    data types so the caller always receives a usable starting point.
    """
    # Copy to avoid mutating the template in-place across repeated calls.
    sections = list(_OUTLINE_TEMPLATES.get(data_type, ["Generic descriptive", "Generic inferential"]))
    return {"sections": sections, "data_type": data_type, "confirmed_by_user": False}


@tool
def run_analysis_step(step_name: str, data: dict) -> dict:
    """SP5: parse one outline step from the user's pasted analysis output.

    Hybrid extraction: regex-first via dispatch_parse, LLM fallback on miss,
    stub StepResult on both miss. The returned dict's `parser` field records
    the source path so M5 and audit logs can distinguish regex from LLM
    extraction.
    """
    # SP5 replaces the SP1 stub — dispatch_parse handles regex + LLM fallback
    # internally; we only need to handle the case where both fail (None return).
    text = data.get("paste", "")
    data_type = data.get("data_type", "Unknown")
    result = dispatch_parse(data_type, text, step_name)
    if result is not None:
        return result
    # Both regex and LLM fallback failed — return a stub so the walk continues.
    return {
        "step_name": step_name,
        "table": [],
        "thresholds_met": None,
        "interpretation": (
            "(unable to parse this step from the paste; please paste this step's "
            "output separately or describe the result)"
        ),
        "raw_paste_excerpt": text[:200],
        "parser": "stub",
    }


@tool
def interpret_result(result: dict, language: str = "en") -> str:
    """Plain-language interpretation of a statistical result.

    `language` ∈ {"en", "vi"}.

    Uses _get_llm() as an indirection point so unit tests can monkeypatch the
    LLM without network calls while production uses the real Gemini model.
    """
    llm = _get_llm()
    prompt = (
        f"Interpret this statistical result in academic prose (1-2 short paragraphs). "
        f"Language: {'Vietnamese' if language == 'vi' else 'English'}. "
        f"Mention thresholds where relevant.\n\nResult: {json.dumps(result, default=str)}"
    )
    return llm.invoke(prompt).content.strip()


@tool
def run_extra_analysis(step_description: str, data_paste: str) -> dict:
    """SP5: ad-hoc analysis requested via natural language (PRD §6.4.6).

    Routes to the LLM extractor with the user's free-text step description.
    The caller (M4Agent) appends the result to M4Output.custom_analyses.
    """
    # Delegate to the LLM extractor; step_description becomes the step_name so
    # the result is identifiable in M4Output.custom_analyses.
    result = extract_step_data.invoke({
        "text": data_paste,
        "step_name": step_description,
        "data_type": "AdHoc",
    })
    if result is None:
        return {
            "step_name": step_description,
            "table": [],
            "interpretation": "(unable to perform this ad-hoc analysis from the paste)",
            "parser": "stub",
        }
    return result
