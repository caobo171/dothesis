"""M3 — Research Design tools."""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool
from orchestrator.llm import get_orchestrator_llm

# bounded_invoke wraps Gemini calls in a wall-clock timeout. Without it, a
# single hung Gemini call freezes the entire graph turn (Gemini occasionally
# blocks for 5+ minutes — see base.py:bounded_invoke docstring). User report
# was "typing dots stay forever" after confirming the conceptual_model card;
# render_hint_for_field('scale_items') fires N per-construct tool calls
# sequentially, so any one hang stalls every subsequent turn.
from orchestrator.agents.base import BoundedInvokeTimeout, bounded_invoke

logger = logging.getLogger(__name__)


# Per-call cap for the M3 tools. 30s is generous for a single JSON-shaped
# Gemini response and short enough that a stuck call surfaces as a fallback
# (not a UI hang). +1 retry gives transient blips one chance to succeed.
_TOOL_LLM_MAX_SECONDS = 30
_TOOL_LLM_RETRIES = 1


def _get_llm():
    # Delegates to the engine-wide factory (ORCHESTRATOR_LLM_ROUTE routes the
    # whole engine); temperature 0.3 is this tool's original per-site setting.
    # Kept as a module symbol because tests monkeypatch it.
    return get_orchestrator_llm(temperature=0.3)


def _invoke_json(llm, prompt: str):
    """Wall-clock-bounded LLM invoke + code-fence-tolerant JSON parse.

    Returns the parsed value on success. Raises on timeout / JSON failure so
    each tool's existing except block can return its field-shaped fallback
    (the shapes differ per tool — dict vs list vs nested — so a generic
    helper can't return the right empty default).
    """
    resp = bounded_invoke(
        llm, prompt,
        max_seconds=_TOOL_LLM_MAX_SECONDS,
        retries=_TOOL_LLM_RETRIES,
    )
    return json.loads(_strip_code_fence(resp.content))


def _strip_code_fence(s: str) -> str:
    """Strip ```json … ``` wrappers from a Gemini response before json.loads.

    Decision/reason: Gemini frequently wraps JSON in markdown code fences even
    when told "respond with ONLY a JSON object". Without this, json.loads
    raises → tool falls back to the empty-result default and the M3 widgets
    render with zero items (user report: M3 conceptual_model card shipped
    empty after the 7fd07db prompt fix). orchestrator/agents/base.py uses an
    identical helper for every LLM JSON call; this is the tool-side mirror —
    duplicated here rather than imported to avoid a tools→agents dependency
    cycle (agents already import tools).
    """
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


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
        return _invoke_json(llm, prompt)
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        # Fallback to a safe default so callers always receive a valid dict.
        # BoundedInvokeTimeout / generic Exception covers Gemini hangs and
        # transient API errors — without this the agent step blocks forever.
        logger.warning("recommend_methodology: LLM call failed/malformed, returning default")
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
        return _invoke_json(llm, prompt)
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        # Return a structurally valid empty-paths model so downstream steps don't crash.
        logger.warning("build_conceptual_model: LLM call failed/malformed, returning empty paths")
        return {"constructs": constructs, "paths": []}


@tool
def suggest_scale_items(construct_name: str, n: int = 5, language: str = "en") -> list[dict]:
    """Suggest `n` Likert items measuring the named construct, worded in
    `language` (e.g. "vi" → Vietnamese).

    Returns: [{id, text}, ...].

    Single-construct version, kept for backwards compatibility with the auto-
    fill schema path that may delegate one construct at a time. The widget
    render path uses `suggest_scale_items_batch` instead — one LLM call for
    all constructs rather than N. See that tool's docstring for the why.

    Parameter name: was `construct`, renamed to `construct_name` because the
    bare `construct` shadows pydantic.BaseModel.construct in the args-schema
    LangChain's @tool decorator builds from this signature, which throws a
    UserWarning on every server start. Semantics unchanged.
    """
    llm = _get_llm()
    prompt = (
        f"Write {n} validated-style Likert items (5-point) measuring the construct "
        f"'{construct_name}'. {_item_language_rule(language)} "
        "Respond with ONLY a JSON array: "
        f'[{{"id": "C1", "text": "..."}}, ...].'
    )
    try:
        return list(_invoke_json(llm, prompt))
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        # Return empty list rather than crashing; caller can decide whether to retry.
        logger.warning("suggest_scale_items: LLM call failed/malformed, returning empty list")
        return []


def _item_language_rule(language: str) -> str:
    """One instruction line pinning the item wording to the report's language.
    Defaults to English; Vietnamese reports were getting English items."""
    if str(language or "").lower().startswith("vi"):
        return "Write every item text in natural Vietnamese (tiếng Việt)."
    return "Write every item text in English."


@tool
def suggest_scale_items_batch(constructs: list[str], n: int = 5, language: str = "en") -> dict:
    """Suggest `n` Likert items for EACH construct — ONE LLM call total.

    `language` pins the item wording (e.g. "vi" → Vietnamese) so a Vietnamese
    report doesn't get English scale items.

    Returns: {<construct_name>: [{id, text}, ...], ...}. Every requested
    construct is guaranteed to appear as a key (mapped to [] if the LLM
    dropped it) so the caller can iterate `constructs` directly without
    key-existence checks.

    Why batch: the per-construct `suggest_scale_items` makes one LLM call per
    construct. With N=6 constructs that's 6 round trips, ~6× the tokens, and
    the user-reported 'typing dots forever' hang (any single hung call stalls
    the whole turn). Batching into one prompt also produces more coherent
    items because the LLM sees all constructs together and avoids overlapping
    wording across them.
    """
    if not constructs:
        return {}
    llm = _get_llm()
    prompt = (
        f"For EACH of the constructs below, write {n} validated-style 5-point "
        "Likert items measuring that construct. "
        f"{_item_language_rule(language)} "
        "Respond with ONLY a JSON object "
        "keyed by the EXACT construct name as it appears in the list, where "
        "each value is the array of items:\n"
        '{"<construct A>": [{"id":"A1","text":"..."}, ...], '
        '"<construct B>": [{"id":"B1","text":"..."}, ...]}\n\n'
        f"Constructs: {json.dumps(constructs, ensure_ascii=False)}"
    )
    try:
        out = _invoke_json(llm, prompt)
        if not isinstance(out, dict):
            raise TypeError(f"expected JSON object, got {type(out).__name__}")
        # Normalize: every requested construct gets a list (LLM may drop one
        # or rename a key; we re-key to the user's exact construct names so
        # the caller's iteration order matches the rendered widget rows).
        return {c: list(out.get(c) or []) for c in constructs}
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        logger.warning(
            "suggest_scale_items_batch: LLM call failed/malformed, "
            "returning empty per-construct lists for %d constructs", len(constructs))
        return {c: [] for c in constructs}


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
        return list(_invoke_json(llm, prompt))
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        logger.warning("suggest_themes: LLM call failed/malformed, returning empty list")
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
        return dict(_invoke_json(llm, prompt))
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        logger.warning("compose_interview_guide: LLM call failed/malformed, returning fallback")
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
        return dict(_invoke_json(llm, prompt))
    except (json.JSONDecodeError, TypeError, BoundedInvokeTimeout, Exception):  # noqa: BLE001
        logger.warning("suggest_purposive_criteria: LLM call failed/malformed, returning fallback")
        return {
            "criteria": ["Participants directly experience the phenomenon under study"],
            "strategies": ["Snowball", "Maximum variation"],
            "saturation_min": 10, "saturation_max": 15,
        }
