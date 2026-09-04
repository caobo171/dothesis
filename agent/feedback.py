"""Turn raw professor feedback into structured, trackable directives. Best-effort:
never drop a comment — a parse failure wraps the raw text as one directive.

Uses the orchestrator LLM (like agent/tools/writing.py and research.py already do),
so this stays within the agent layer's allowed dependencies (agent -> orchestrator,
never agent -> app).
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_PROMPT = (
    "You are parsing a thesis supervisor's feedback into discrete, actionable "
    "directives. For each distinct requested change, output one item. Map it to the "
    "most likely chapter (intro|lit_review|methodology|results|conclusion) "
    "when clear, else '-'.\nReturn STRICT JSON only:\n"
    '{"directives": [{"chapter": "", "section": "", "quote": "", "issue": "", '
    '"required_change": ""}]}\n\nFEEDBACK:\n'
)


def extract_directives(feedback_text: str) -> list[dict]:
    """Parse feedback into directives. On any failure, wrap the raw text as one
    directive so a professor comment is never silently lost."""
    from orchestrator.tools.m5_writing import _get_llm  # noqa: PLC0415 — orchestrator LLM, agent layer
    text = (feedback_text or "").strip()
    if not text:
        return []
    try:
        resp = _get_llm().invoke(_PROMPT + text[:8000])
        content = getattr(resp, "content", resp)
        if isinstance(content, list):
            # some providers return a list of content parts
            content = " ".join(str(p.get("text", "") if isinstance(p, dict) else p) for p in content)
        content = str(content)
        s, e = content.find("{"), content.rfind("}")
        data = json.loads(content[s:e + 1]) if s != -1 and e != -1 else {}
        directives = [d for d in (data.get("directives") or []) if isinstance(d, dict) and d.get("issue")]
        if directives:
            return directives
    except Exception:
        logger.exception("feedback: extraction failed; storing raw text as one directive")
    # Fallback: never lose the comment.
    return [{"chapter": "-", "issue": text[:500], "required_change": text[:500]}]
