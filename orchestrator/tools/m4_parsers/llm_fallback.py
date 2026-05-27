"""LLM extraction fallback for paste-text steps that regex can't parse.

Used by `dispatch_parse` when a format's regex parser returns None
(no match). The LLM is prompted to extract the same StepResult-shaped
dict the regex parsers produce. The `parser` field is always set to
`"llm_fallback"` so M5 and audit logs can tell the source apart.
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    """Factory function for LLM instance.

    Returns a ChatGoogleGenerativeAI instance configured with the
    ORCHESTRATOR_LLM_MODEL env var (defaults to gemini-2.0-flash-001).
    This function is mocked in tests to inject fake LLM responses.
    """
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.1,
    )


@tool
def extract_step_data(text: str, step_name: str, data_type: str) -> dict | None:
    """LLM extraction of a single outline step.

    Returns a StepResult dict with parser="llm_fallback", or None on
    malformed LLM response.

    The prompt instructs the LLM to return ONLY numbers present in the
    source text and to use null for any cell it cannot verify, to limit
    hallucinated values.

    Args:
        text: The raw output text to parse (e.g., SPSS/R output).
        step_name: The name of the analysis step being extracted.
        data_type: The format type (e.g., "SPSS", "R", "SmartPLS").

    Returns:
        A StepResult dict with parser="llm_fallback" if successful,
        None if the LLM response is malformed JSON.
    """
    llm = _get_llm()
    # Prompt design prioritizes accuracy: only extract numbers from source,
    # use null for unverifiable cells, never fabricate values.
    prompt = (
        f"Extract the data for the '{step_name}' analysis step from this "
        f"{data_type} output. Return ONLY a JSON object with this shape: "
        '{"step_name":"<step>","table":[{...}],"thresholds_met":<bool|null>,'
        '"interpretation":"<plain-language paragraph>"}. '
        "Critical: only include numbers that appear in the source text. For "
        "any cell you cannot verify, use null. Do NOT fabricate values.\n\n"
        f"Source text:\n{text[:20000]}"
    )
    try:
        result = dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "extract_step_data: malformed LLM response for step=%s, returning None",
            step_name,
        )
        return None
    # Force the parser tag — never trust what the LLM returned.
    # This ensures M5 and audit logs can always identify llm_fallback as source.
    result["parser"] = "llm_fallback"
    result.setdefault("step_name", step_name)
    return result
