"""Helpers for normalizing LangChain message content shapes.

LangChain messages carry their `content` in two shapes:
  - Plain string (what the FastAPI chat router produces): `"hello"`
  - List of content blocks (what LangSmith Studio submits, even for plain
    text input): `[{"type": "text", "text": "hello"}, ...]`

Most orchestrator code wants the text as a single string for `.lower()`,
intent matching, LLM prompt interpolation, etc. Centralizing the
normalization here means we don't have to litter every call site with
`isinstance(m.content, list)` branches.
"""
from __future__ import annotations

from langchain_core.messages import BaseMessage


def text_of(message: BaseMessage) -> str:
    """Return the textual content of a LangChain message as a plain string.

    Joins text blocks for multi-part content, ignores non-text blocks
    (images, tool calls). Returns "" when there's no recognizable text.
    """
    c = message.content
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts: list[str] = []
        for block in c:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(c)
