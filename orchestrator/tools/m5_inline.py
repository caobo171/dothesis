"""SP6.5: selection-scoped LLM tools used by the editor's inline AI features.

paraphrase_selection / translate_selection take a selection plus surrounding
context and return the rewritten selection only. The caller (API endpoint)
wraps the result in a PendingEdit and persists it to ChapterDraft.pending_edits.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "m5_inline"
_PARAPHRASE_PROMPT = (_PROMPTS_DIR / "paraphrase.md").read_text()


def _call_llm(prompt: str) -> str:
    """Real implementation routes through the project's Gemini wrapper.

    Tests monkeypatch this function. Keeping it as a module-level function
    (not an inline lambda) makes it patchable.
    """
    from orchestrator.tools.m5_writing import _get_llm  # reuse existing wrapper
    llm = _get_llm()
    return llm.invoke(prompt).content


def _strip(text: str) -> str:
    """Trim whitespace + paired surrounding quotes that LLMs sometimes emit."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
        t = t[1:-1].strip()
    return t


@tool
def paraphrase_selection(
    chapter_name: str,
    language: str,
    context_before: str,
    selection: str,
    context_after: str,
    style: str = "",
) -> str:
    """Paraphrase a chapter selection. Returns the rewritten selection only."""
    prompt = _PARAPHRASE_PROMPT.format(
        chapter_name=chapter_name,
        language=language,
        context_before=context_before,
        selection=selection,
        context_after=context_after,
        style=style or "(none — use a natural academic register)",
    )
    return _strip(_call_llm(prompt))
