"""Qualitative transcript helpers + AI-driven coding/theming tools."""
from __future__ import annotations

import json
import logging
import os
import re

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    # Centralised LLM factory — monkeypatchable in tests.
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
        temperature=0.2,
    )


_SPEAKER_PATTERN = re.compile(r"^\s*([A-Z][A-Z _-]+):\s*", re.MULTILINE)


def split_transcript_into_segments(transcript: str) -> list[dict]:
    """Split a transcript into speaker turns. Returns [{speaker, text}, ...].

    Speakers are detected by ALL-CAPS prefix + colon at start of line
    (e.g. INTERVIEWER:, PARTICIPANT:, P1:).
    """
    matches = list(_SPEAKER_PATTERN.finditer(transcript))
    if not matches:
        return [{"speaker": "?", "text": transcript.strip()}]
    segments = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(transcript)
        text = transcript[start:end].strip()
        if text:
            segments.append({"speaker": m.group(1).strip(), "text": text})
    return segments


@tool
def suggest_qual_codes(transcript: str) -> list[dict]:
    """Extract initial codes from a qualitative interview transcript.

    Returns: [{code: str, quote: str}, ...]
    Each code is a short label; quote is the verbatim text the code applies to.
    Falls back to [] on malformed LLM response.
    """
    llm = _get_llm()
    prompt = (
        "Extract initial codes from this interview transcript (Braun & Clarke style "
        "line-by-line coding). For each code, give the verbatim quote it applies to. "
        "Aim for 5-12 codes total. Respond with ONLY a JSON array: "
        '[{"code":"<short label>","quote":"<verbatim>"}, ...].\n\n'
        f"Transcript:\n{transcript[:30000]}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_qual_codes: malformed LLM response, returning empty list")
        return []


@tool
def cluster_codes_into_themes(codes: list[dict]) -> list[dict]:
    """Cluster initial codes into themes.

    Input: [{code, quote}, ...]
    Returns: [{theme: str, codes: [str]}, ...]
    Falls back to [] on malformed.
    """
    llm = _get_llm()
    prompt = (
        "Cluster these initial codes into 3-5 themes for a thematic analysis "
        "(Braun & Clarke 2006). Each theme groups related codes. Respond with "
        'ONLY a JSON array: [{"theme":"<name>","codes":["<code>", "<code>"]}, ...].\n\n'
        f"Codes: {json.dumps(codes, ensure_ascii=False)}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("cluster_codes_into_themes: malformed LLM response, returning empty list")
        return []
