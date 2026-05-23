#!/usr/bin/env python3
"""
ABOUTME: Titlemaker utility — generates a scholarly paper title from research context
ABOUTME: Called during compile phase, before filename and YAML metadata are built
"""

import re
import logging
from typing import TYPE_CHECKING, Callable, Any

if TYPE_CHECKING:
    from phases.context import DraftContext

logger = logging.getLogger(__name__)


def generate_paper_title(ctx: "DraftContext", run_agent_func: Callable) -> str:
    """
    Generate a scholarly paper title from the research context using an LLM agent.

    Takes topic, academic_level, outline summary, and language from ctx.
    Returns a clean scholarly title string. Falls back to ctx.topic on any failure.

    Args:
        ctx: DraftContext with topic, academic_level, formatter_output, language
        run_agent_func: The run_agent function from utils.agent_runner

    Returns:
        str: Scholarly title, or ctx.topic if generation fails or returns empty
    """
    try:
        # Build a concise outline snippet (first 500 chars) for context
        outline_snippet = ""
        if ctx.formatter_output:
            outline_snippet = ctx.formatter_output[:500].strip()
            if len(ctx.formatter_output) > 500:
                outline_snippet += "..."

        user_input = f"""Generate a scholarly academic title for the following paper.

**Topic:** {ctx.topic}

**Academic Level:** {ctx.academic_level}

**Language:** {ctx.language}

**Outline (first 500 chars):**
{outline_snippet if outline_snippet else "(outline not available)"}
"""

        raw_title = run_agent_func(
            model=ctx.model,
            name="Titlemaker (Agent #6.4)",
            prompt_path="prompts/06_enhance/titlemaker.md",
            user_input=user_input,
            verbose=ctx.verbose,
            skip_validation=True,
        )

        if not raw_title:
            logger.warning("Titlemaker returned empty output — falling back to topic")
            return ctx.topic

        title = _clean_title(raw_title)

        if not title:
            logger.warning("Titlemaker returned unparseable output — falling back to topic")
            return ctx.topic

        if ctx.verbose:
            print(f"\n   📌 Generated title: {title}")

        logger.info(f"Titlemaker generated: {title}")
        return title

    except Exception as e:
        logger.warning(f"Titlemaker failed ({e}) — falling back to topic")
        return ctx.topic


def _clean_title(raw: str) -> str:
    """
    Strip common LLM preambles and formatting artifacts from a title response.

    Handles patterns like:
      - "Title: Foo Bar"
      - '"Foo Bar"'
      - "Here is the title: Foo Bar"
      - "**Foo Bar**"
      - Leading/trailing whitespace and newlines
    """
    title = raw.strip()

    # Remove markdown bold/italic wrappers
    title = re.sub(r"^\*{1,3}(.*?)\*{1,3}$", r"\1", title, flags=re.DOTALL)

    # Remove surrounding quotes (straight or curly)
    title = re.sub(r'^["\u201c\u2018](.*)["\u201d\u2019]$', r"\1", title)

    # Strip common preamble prefixes (case-insensitive)
    preamble_patterns = [
        r"^(?:here\s+is\s+(?:the\s+)?(?:scholarly\s+)?title\s*[:\-–—]?\s*)",
        r"^(?:title\s*[:\-–—]\s*)",
        r"^(?:suggested\s+title\s*[:\-–—]\s*)",
        r"^(?:generated\s+title\s*[:\-–—]\s*)",
        r"^(?:paper\s+title\s*[:\-–—]\s*)",
    ]
    for pattern in preamble_patterns:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)

    # If multiple lines, take only the first non-empty line
    lines = [line.strip() for line in title.split("\n") if line.strip()]
    title = lines[0] if lines else ""

    # Final strip and validation
    title = title.strip().strip('"').strip("'").strip()

    # Sanity: title should be at least 10 chars and not longer than 300
    if len(title) < 10 or len(title) > 300:
        return ""

    return title
