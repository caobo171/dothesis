"""Shared headless back half: compose a chapter SUBSET from a context_store and
export it. Extracted from partner_report_service._compose_chapters so the Partner
API stops owning a near-clone of compose_all_sections. Composition is sanitized in
compose_chapter (see m5_writing.sanitize_prose); this module only owns subset
selection, canonical ordering, and the run_export hand-off. It deliberately does
NOT gate — gating stays a caller decision (partner enforces, auto-mode does not),
so this never adds a blocking gate to a headless path.
"""
from __future__ import annotations

import logging
import re
from typing import Callable

# Import the module (not the bound name) so run_export is resolved at CALL time
# through m5_writing.run_export. That keeps the single export path patchable in
# tests (monkeypatch m5_writing.run_export) and honours any late rebinding, since
# a `from .m5_writing import run_export` would freeze the reference at import.
from . import m5_writing
from .m5_writing import (
    M5_CHAPTER_ORDER,
    _chapter_titles,
    _fallback_section,
    compose_chapter,
)

logger = logging.getLogger(__name__)

# progress(idx, chapter_key, title, phase) — phase is "start" or "end".
ProgressFn = Callable[[int, str, str, str], None]


def compose_sections(
    context_store: dict,
    chapters: list[str],
    language: str,
    references: list[dict] | None = None,
    progress: ProgressFn | None = None,
    title_overrides: dict[str, str] | None = None,
    merge_conclusion: bool = False,
) -> list[dict]:
    """Compose a requested subset of M5 chapters, in canonical order → [{title, prose}]."""
    if merge_conclusion and "conclusion" in set(chapters):
        # Presentation choice promoted from the partner pipeline (spec §3):
        # standard VN thesis structure has ONE concluding chapter ("Chương 5 —
        # Kết luận"), not Discussion + Conclusion. The discussion composer
        # already emits the full conclusion structure (summary → contributions
        # → limitations → future work), so drop `conclusion` and relabel
        # `discussion` — an export ARGUMENT, not a pipeline fork.
        chapters = [c for c in chapters if c != "conclusion"]
        if "discussion" not in chapters:
            chapters = [*chapters, "discussion"]
        combined = ("Chương 5 — Kết luận" if str(language).lower().startswith("vi")
                    else "Chapter 5 — Conclusion")
        title_overrides = {**(title_overrides or {}), "discussion": combined}

    m1 = context_store.get("m1_topic") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}
    context_slice: dict = {**m1, **m3, **m4}
    context_slice.setdefault("results", m4.get("analysis_results"))
    # Render grounded research gaps (list of {description, refs}) into a readable
    # block the Introduction prompt can ground its problem statement in. Always
    # set the key ("" when absent) so the `{research_gaps}` placeholder is safe.
    _gaps = context_slice.get("research_gaps")
    if isinstance(_gaps, list) and _gaps:
        # Prose only — DROP the brief's [n] source numbers. Those index the
        # brief's own scout, not this report's bibliography, so keeping them
        # would leave dangling "[3]" markers; the Introduction re-cites from the
        # report's reference pool as (Author, Year) instead.
        context_slice["research_gaps"] = "\n".join(
            f"- {re.sub(r'\\s*\\[[0-9,\\s]+\\]', '', str(g.get('description', ''))).strip()}"
            for g in _gaps if isinstance(g, dict)
        )
    elif not isinstance(_gaps, str):
        context_slice["research_gaps"] = ""

    # Always compose in canonical order regardless of how the caller ordered them.
    ordered = [k for k in M5_CHAPTER_ORDER if k in set(chapters)]
    titles = {**_chapter_titles(language), **(title_overrides or {})}

    out: list[dict] = []
    for idx, name in enumerate(ordered):
        if progress:
            progress(idx, name, titles[name], "start")
        try:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                "paradigm": "",
                "context_slice": context_slice,
                "references": references or [],
                "citation_style": "apa7",
                "language": language,
            })
            prose = (draft or {}).get("prose") or ""
        except Exception:
            logger.exception("compose_sections: compose_chapter failed for %s", name)
            prose = ""
        # compose_chapter already sanitizes; the fallback path does not go through
        # it, so a deterministic fallback keeps the section from being empty.
        if not prose.strip():
            prose = _fallback_section(name, context_store)
        if prose.strip():
            out.append({"title": titles[name], "prose": prose})
        if progress:
            progress(idx, name, titles[name], "end")
    return out


def compose_and_export(
    context_store: dict,
    project_id: str,
    *,
    chapters: list[str],
    language: str,
    references: list[dict] | None = None,
    progress: ProgressFn | None = None,
    title_overrides: dict[str, str] | None = None,
) -> list[dict]:
    """Compose the chapter subset and export via the shared run_export path."""
    sections = compose_sections(
        context_store, chapters, language,
        references=references, progress=progress, title_overrides=title_overrides,
    )
    # Call through the module so a test-time monkeypatch of m5_writing.run_export
    # (or any late rebinding) is honoured — a frozen import-time name would not be.
    return m5_writing.run_export(
        sections, str(project_id), references=references or None, language=language,
    )
