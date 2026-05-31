"""M3 — Research Design tools."""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    # Centralised LLM factory — allows monkeypatching in tests without touching each tool.
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.3,
    )


@tool
def recommend_methodology(research_question: str, paradigm: str) -> dict:
    """Suggest a research design + analysis tool for the given RQ and paradigm.

    Returns: {design, tool, rationale}.
    """
    llm = _get_llm()
    prompt = (
        "Given this research question and paradigm, recommend a specific research "
        "design and primary analysis tool. Respond with ONLY a JSON object: "
        '{"design": "<e.g. PLS-SEM>", "tool": "<e.g. SmartPLS>", '
        '"rationale": "<one sentence>"}.\n\n'
        f"Research question: {research_question}\nParadigm: {paradigm}"
    )
    try:
        return json.loads(llm.invoke(prompt).content)
    except (json.JSONDecodeError, TypeError):
        # Fallback to a safe default so callers always receive a valid dict.
        logger.warning("recommend_methodology: malformed LLM response, returning default")
        return {"design": "regression", "tool": "SPSS", "rationale": "fallback default"}


@tool
def build_conceptual_model(constructs: list[str], research_question: str) -> dict:
    """Build a conceptual model with paths between constructs.

    Returns: {constructs, paths: [{from, to, hypothesis}]}.

    User report: when `conceptual_model` is the next M3 field, the user
    hasn't yet given us any constructs — so render_hint_for_field calls
    this with constructs=[]. The old prompt phrased the task as 'given
    constructs and RQ, build paths', which the LLM took to mean 'no
    constructs → no paths', returning an empty model. The chat then
    claimed 'I've pre-filled a list of paths' with a blank widget below.
    Now: if constructs is empty we explicitly ask the LLM to PROPOSE 3-4
    constructs from the RQ and then connect them — so the list_editor
    arrives populated and the user can edit instead of starting blank.
    """
    llm = _get_llm()
    if constructs:
        task = (
            "Build a quantitative conceptual model. Given the user's constructs "
            "and research question, propose paths that connect them."
        )
        inputs = f"Constructs: {constructs}\nResearch question: {research_question}"
    else:
        task = (
            "Build a quantitative conceptual model from the research question "
            "alone. Propose 3-4 latent constructs that the RQ implies, then "
            "connect them with paths. Every construct must appear in at least "
            "one path (otherwise it's not part of the model)."
        )
        inputs = f"Research question: {research_question}"
    prompt = (
        f"{task} Return ONLY a JSON object: "
        '{"constructs": ["C1", "C2", ...], "paths": '
        '[{"from":"C1","to":"C2","hypothesis":"H1: C1 positively affects C2"}, '
        '...]}.\n\n'
        f"{inputs}"
    )
    try:
        return json.loads(llm.invoke(prompt).content)
    except (json.JSONDecodeError, TypeError):
        # Return a structurally valid empty-paths model so downstream steps don't crash.
        logger.warning("build_conceptual_model: malformed LLM response, returning empty paths")
        return {"constructs": constructs, "paths": []}


@tool
def suggest_scale_items(construct: str, n: int = 5) -> list[dict]:
    """Suggest `n` Likert items measuring the construct.

    Returns: [{id, text}, ...].
    """
    llm = _get_llm()
    prompt = (
        f"Write {n} validated-style Likert items (5-point) measuring the construct "
        f"'{construct}'. Respond with ONLY a JSON array: "
        f'[{{"id": "C1", "text": "..."}}, ...].'
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        # Return empty list rather than crashing; caller can decide whether to retry.
        logger.warning("suggest_scale_items: malformed LLM response, returning empty list")
        return []


@tool
def estimate_sample_size(model: dict) -> dict:
    """Estimate minimum and recommended sample sizes for a given design.

    Pure heuristic — no LLM call needed.  Rules applied in order:
      1. Qualitative designs (thematic, grounded theory, case study) → saturation range 8-15.
      2. PLS-SEM / CB-SEM → Hair et al. (2019) 10× rule on max arrows per construct, min 100.
      3. Regression / ANOVA → Cohen (1988) medium-effect heuristic, min 100.
      4. Generic quantitative default → 150/250.

    Returns: {min_size, recommended, rationale}.
    """
    design = (model.get("design") or "").lower()

    # Qualitative: purposive sampling to saturation
    if "qualitative" in design or "thematic" in design or "grounded" in design or "case" in design:
        return {
            "min_size": 8,
            "recommended": 15,
            "rationale": "Purposive sampling until data saturation (Braun & Clarke, 2006).",
        }

    # SEM variants: 10× max incoming arrows, floor at 100
    if "pls" in design or "sem" in design:
        arrows = int(model.get("max_arrows_per_construct", 3))
        n_min = max(100, 10 * arrows)
        return {
            "min_size": n_min,
            "recommended": int(n_min * 1.5),
            "rationale": f"10× max arrows rule (Hair et al., 2019), n_min = 10 × {arrows}.",
        }

    # Classic parametric designs
    if "regression" in design or "anova" in design:
        return {
            "min_size": 100,
            "recommended": 200,
            "rationale": "Cohen (1988) heuristic for medium effect, α=0.05, power=0.8.",
        }

    # Generic quantitative fallback
    return {
        "min_size": 150,
        "recommended": 250,
        "rationale": "Generic quantitative default.",
    }


@tool
def suggest_themes(research_question: str, paradigm: str,
                   gaps_summary: str = "") -> list[dict]:
    """Suggest 3-5 themes (with sub-themes) for qualitative analysis.

    Returns: [{id, theme, sub_themes: [str]}, ...]
    Falls back to [] on malformed LLM response so the agent can show an
    empty list_editor for the user to fill from scratch.
    """
    # Decision: Use LLM to generate thematic suggestions based on research question
    # and literature gaps, following same pattern as other tools in this module
    # (invoke -> json.loads -> safe fallback). This ensures consistency across the
    # M3 design workflow.
    llm = _get_llm()
    prompt = (
        "Suggest 3-5 themes for a qualitative analysis. For each theme, give 2-3 "
        "sub-themes. Respond with ONLY a JSON array: "
        '[{"id":"t1","theme":"<theme>","sub_themes":["<sub>","<sub>"]}, ...].\n\n'
        f"Research question: {research_question}\n"
        f"Paradigm: {paradigm}\n"
        f"Literature gaps summary (from M2): {gaps_summary or '(none provided)'}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_themes: malformed LLM response, returning empty list")
        return []


@tool
def compose_interview_guide(themes: list[dict], research_question: str) -> dict:
    """Build a semi-structured interview guide from themes.

    Returns: {sections: [{phase: "intro"|"main"|"closing", time_minutes,
              questions: [{q, probes: [str]}]}]}
    Falls back to a one-section minimal guide on malformed LLM response.
    """
    # Decision: Use LLM to generate structured interview guide with intro/main/closing
    # phases based on themes and research question. This follows the same pattern as
    # suggest_themes (invoke -> json.loads -> safe fallback) to maintain consistency
    # across M3 qualitative design tools.
    llm = _get_llm()
    prompt = (
        "Build a semi-structured interview guide. Three sections: intro (5 min, "
        "warm-up and consent), main (40-50 min, theme-driven questions with probes), "
        "closing (5 min, wrap-up). For each main-phase question, give 1-2 probes. "
        "Respond with ONLY a JSON object: "
        '{"sections":[{"phase":"intro","time_minutes":5,"questions":[{"q":"...","probes":[]}]},'
        '{"phase":"main","time_minutes":40,"questions":[{"q":"...","probes":["..."]}]},'
        '{"phase":"closing","time_minutes":5,"questions":[{"q":"...","probes":[]}]}]}.\n\n'
        f"Research question: {research_question}\n"
        f"Themes: {json.dumps(themes, ensure_ascii=False)}"
    )
    try:
        return dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("compose_interview_guide: malformed LLM response, returning fallback")
        return {
            "sections": [
                {"phase": "main", "time_minutes": 45,
                 "questions": [{"q": "Tell me about your experience.", "probes": []}]},
            ]
        }


@tool
def suggest_purposive_criteria(research_question: str,
                                paradigm: str) -> dict:
    """Propose sampling criteria and strategies for qualitative purposive sampling.

    Returns: {criteria: list[str], strategies: list[str],
              saturation_min: int, saturation_max: int}
    Falls back to a generic criteria list on malformed LLM response.
    """
    # Decision: Use LLM to generate purposive sampling criteria and strategies
    # based on research question and paradigm. This follows the same pattern as
    # suggest_themes and compose_interview_guide (invoke -> json.loads -> safe fallback)
    # to maintain consistency across M3 qualitative design tools.
    llm = _get_llm()
    prompt = (
        "Propose purposive sampling criteria and supplementary strategies for "
        "a qualitative study. Provide 3-5 criteria, 1-3 strategies, and a "
        "saturation range. Respond with ONLY a JSON object: "
        '{"criteria":["..."],"strategies":["Snowball","Maximum variation"],'
        '"saturation_min":10,"saturation_max":15}.\n\n'
        f"Research question: {research_question}\nParadigm: {paradigm}"
    )
    try:
        return dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_purposive_criteria: malformed LLM response, returning fallback")
        return {
            "criteria": ["Participants directly experience the phenomenon under study"],
            "strategies": ["Snowball", "Maximum variation"],
            "saturation_min": 10, "saturation_max": 15,
        }
