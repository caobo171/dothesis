"""M1 — Topic Discovery tools.

Sub-project 1 ships light LLM helpers; later sub-projects can swap in
domain-specific data sources (Semantic Scholar trending topics, etc.).
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    """Single chokepoint for LLM creation — easy to monkeypatch in tests."""
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.4,
    )


@tool
def suggest_topics(field: str) -> list[str]:
    """Return 5-10 currently-trending research topics in the given academic field.

    Returns an empty list if the LLM can't produce a JSON-parseable response.
    """
    llm = _get_llm()
    prompt = (
        f"List 5 to 10 currently-trending research topics in the field of {field}. "
        "Respond with ONLY a JSON array of strings, no prose."
    )
    resp = llm.invoke(prompt).content
    try:
        topics = json.loads(resp)
        if isinstance(topics, list):
            return [str(t) for t in topics]
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_topics: malformed LLM response: %r", resp[:200])
    return []


@tool
def refine_title(seed: str) -> str:
    """Polish a draft thesis title into academic phrasing.

    Returns the polished title verbatim from the LLM. Caller should validate.
    """
    llm = _get_llm()
    prompt = (
        f"You are an academic writing coach. Rewrite this draft research title in "
        f"clear, formal academic English. Return ONLY the polished title, no quotes "
        f"or explanation. Draft: {seed}"
    )
    return llm.invoke(prompt).content.strip()
