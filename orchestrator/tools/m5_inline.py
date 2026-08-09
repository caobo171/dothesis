"""SP6.5: selection-scoped LLM tools used by the editor's inline AI features.

paraphrase_selection / translate_selection take a selection plus surrounding
context and return the rewritten selection only. The caller (API endpoint)
wraps the result in a PendingEdit and persists it to ChapterDraft.pending_edits.
"""
from __future__ import annotations

import logging
import os
import re
from collections import Counter
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "m5_inline"
_PARAPHRASE_PROMPT = (_PROMPTS_DIR / "paraphrase.md").read_text(encoding="utf-8")
_TRANSLATE_PROMPT = (_PROMPTS_DIR / "translate.md").read_text(encoding="utf-8")
_TRANSLATE_CHAPTER_PROMPT = (_PROMPTS_DIR / "translate_chapter.md").read_text(encoding="utf-8")


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


@tool
def translate_selection(
    chapter_name: str,
    target_lang: str,
    context_before: str,
    selection: str,
    context_after: str,
) -> str:
    """Translate a chapter selection into target_lang. Returns translated text only."""
    prompt = _TRANSLATE_PROMPT.format(
        chapter_name=chapter_name,
        target_lang=target_lang,
        context_before=context_before,
        selection=selection,
        context_after=context_after,
    )
    return _strip(_call_llm(prompt))


# --- whole-chapter translation ----------------------------------------------
#
# translate_selection is the editor's inline tool: a paragraph or two, plain
# text, one call. A PRESERVED chapter is a different animal — the student's own
# Chapter 4 out of an imported thesis runs to ~28,000 characters and is 17
# markdown tables interleaved with prose. Pushing that through the inline prompt
# risks the two failures that matter most here: the model reflowing the tables
# (the whole reason the chapter was preserved instead of recomposed), and the
# response being cut off mid-chapter with no error to notice.
#
# So: split on block boundaries, translate in batches, and check each batch came
# back with its structure and its numbers intact before accepting it.

# Batch size in characters. Small enough that a completion is never near a token
# ceiling, large enough that a table and the paragraph explaining it usually
# travel together. Blocks are never split, so a single huge table exceeds this.
_TRANSLATE_BATCH_CHARS = int(os.getenv("DOTHESIS_TRANSLATE_BATCH_CHARS", "3500"))
_TRANSLATE_WORKERS = int(os.getenv("DOTHESIS_TRANSLATE_WORKERS", "4"))

# A number: digits, with the separators that can sit BETWEEN digits, so
# "1670.497" and "0.000" are single tokens rather than three each.
#
# The trailing digit is load-bearing. Written `\d[\d.,]*` this also swallows the
# sentence punctuation after a number — "Sig. = 0.000." tokenises as "0.000."
# — and translation legitimately moves punctuation around, so four of nine
# batches of a real chapter were rejected for commas.
_NUM_RE = re.compile(r"\d(?:[\d.,]*\d)?")


def _batch_blocks(markdown: str, budget: int) -> list[str]:
    """Group blank-line-separated blocks into batches of at most `budget` chars.

    Splitting on blocks and never inside one is what keeps a table whole: half a
    table in one request and half in the next gives the model no header to line
    the rows up against, and it will invent one.
    """
    batches: list[str] = []
    cur: list[str] = []
    size = 0
    for block in markdown.split("\n\n"):
        if cur and size + len(block) > budget:
            batches.append("\n\n".join(cur))
            cur, size = [], 0
        cur.append(block)
        size += len(block) + 2
    if cur:
        batches.append("\n\n".join(cur))
    return batches


def _translation_defect(src: str, out: str) -> str | None:
    """None when `out` kept every table row and every number of `src`; otherwise
    a short description of what changed, NAMING the values.

    These are the two things a student cannot spot by reading: a dropped table
    row looks like a shorter table, and a changed coefficient looks like a
    result. Prose that reads a little differently after translation is fine and
    expected; a number that reads differently is a fabricated finding.

    Returns the reason rather than a bool so the log says which coefficient
    moved. "Something changed" is not something anyone can act on.
    """
    if not out.strip():
        return "empty response"
    def _rows(t):
        return sum(1 for line in t.splitlines() if line.lstrip().startswith("|"))
    if _rows(src) != _rows(out):
        return f"table rows {_rows(src)} -> {_rows(out)}"
    before, after = Counter(_NUM_RE.findall(src)), Counter(_NUM_RE.findall(out))
    if before == after:
        return None
    lost = sorted((before - after).elements())[:6]
    gained = sorted((after - before).elements())[:6]
    return f"numbers changed (lost {lost}, gained {gained})"


def translate_markdown(chapter_name: str, target_lang: str, markdown: str) -> str:
    """Translate a whole markdown chapter into `target_lang`.

    Fail-open per batch: a batch whose translation lost a table row or altered a
    number is discarded and the original text kept. A chapter that is partly in
    the source language is visible to the student and fixable; a chapter with a
    silently different R² is neither.
    """
    if not (markdown or "").strip():
        return markdown or ""
    batches = _batch_blocks(markdown, _TRANSLATE_BATCH_CHARS)

    def _one(src: str) -> str:
        try:
            out = _strip(_call_llm(_TRANSLATE_CHAPTER_PROMPT.format(
                chapter_name=chapter_name, target_lang=target_lang, selection=src)))
        except Exception:
            logger.exception("translate_markdown: batch failed for %s", chapter_name)
            return src
        defect = _translation_defect(src, out)
        if defect:
            logger.warning(
                "translate_markdown: %s batch rejected — %s; keeping the original "
                "(%d chars, starting %r)",
                chapter_name, defect, len(src), src[:60])
            return src
        return out

    if len(batches) == 1:
        return _one(batches[0])
    import concurrent.futures as _cf  # noqa: PLC0415
    with _cf.ThreadPoolExecutor(max_workers=max(1, min(len(batches), _TRANSLATE_WORKERS))) as ex:
        return "\n\n".join(ex.map(_one, batches))


def build_citation_text(reference: dict) -> str:
    """Derive canonical (Author, Year) text from an M2 reference record.

    M2 papers carry at least 'author' and 'year' under normal circumstances.
    Falls back to ('Anonymous', 'n.d.') on either missing piece so that
    malformed-but-present references still produce a usable citation rather
    than blowing up the API call.
    """
    author = str(reference.get("author") or "").strip() or "Anonymous"
    year_val = reference.get("year")
    year = str(year_val).strip() if year_val not in (None, "") else "n.d."
    return f"({author}, {year})"
