"""Shared headless back half: compose a chapter SUBSET from a context_store and
export it.

Extracted from partner_report_service._compose_chapters so the Partner API
stopped owning a near-clone of compose_all_sections — and then spent a while as
a near-clone of it itself. Composition now lives entirely in
`m5_writing.compose_chapters`, the one chapter composer; what remains here is
the partner/headless ADAPTER over it (a caller-supplied language, references and
progress callback) plus the run_export hand-off.

It deliberately does NOT gate — gating stays a caller decision (partner
enforces, auto-mode does not), so this never adds a blocking gate to a headless
path.
"""
from __future__ import annotations

import logging
from typing import Callable

# Import the module (not the bound name) so run_export and compose_chapters are
# resolved at CALL time through m5_writing. That keeps the single export/compose
# path patchable in tests (monkeypatch m5_writing.run_export) and honours any
# late rebinding, since `from .m5_writing import run_export` would freeze the
# reference at import.
from . import m5_writing

# Re-exported: callers and tests read the canonical chapter order off this
# module as well as off m5_writing.
from .m5_writing import M5_CHAPTER_ORDER  # noqa: F401

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
) -> list[dict]:
    """Compose a requested subset of M5 chapters, in canonical order.

    A thin adapter over `m5_writing.compose_chapters`, which is now the only
    chapter composer. This function used to be a second implementation of it,
    and the two drifted exactly where you would expect two copies to: they fed
    the same orchestrator/prompts/m5/*.md templates different `research_gaps`
    and `paradigm`, only one of them reused prose the editor had saved, and only
    one carried `chapter_name` forward so the next compose could recognise its
    own output.

    `language` and `references` stay REQUIRED-ish here (the partner caller
    resolves both and passes them) rather than being derived, which is the one
    behavioural difference the signature still encodes. No bibliography section
    is appended: this path goes through run_export's citeproc, which generates
    its own.
    """
    return m5_writing.compose_chapters(
        context_store,
        chapters=chapters,
        language=language,
        references=references,
        progress=progress,
        title_overrides=title_overrides,
    )


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
        # run_export reads the thesis title off m1_topic when the caller does
        # not name one. Passing the store is what makes the cover page say
        # anything other than "None".
        context_store=context_store,
    )
