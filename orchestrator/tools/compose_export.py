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
) -> list[dict]:
    """Compose a requested subset of M5 chapters, in canonical order → [{title, prose}]."""
    # One slice construction, shared with compose_all_sections — see
    # m5_writing.compose_context_slice. This function used to build its own,
    # which is how the two composers ended up feeding the same templates
    # different `research_gaps` and `paradigm` for the same project.
    from .m5_writing import compose_context_slice  # noqa: PLC0415
    context_slice = compose_context_slice(context_store)
    # `research_gaps` is an M2-OWNED key (agent/state.py SLICE_OWNERSHIP) that
    # intro.md / lit_review.md / conclusion.md all interpolate and explicitly
    # label "from M2". The deleted partner_report_service hid its absence: it
    # wrote the grounded brief's gaps into a plain `m1_topic` dict with no
    # ownership filter, so its Introductions were the ONLY ones that ever saw a
    # real gap. Once partner started writing through commit_slice the gaps
    # landed in m2 where they belong — and the rendering that makes them
    # readable lived only here, so chat and auto-mode kept composing
    # Introductions against a raw list. It is shared now.

    # Always compose in canonical order regardless of how the caller ordered them.
    ordered = [k for k in M5_CHAPTER_ORDER if k in set(chapters)]
    titles = {**_chapter_titles(language), **(title_overrides or {})}

    # Reuse chapters that are already written instead of re-composing them — the
    # partner export otherwise pays for the same chapters a second time. Only
    # real prose is reused (stubs / "[Composition failed]" markers fall through
    # to compose).
    #
    # Via `chapter_prose`, which reads BOTH homes. This read was
    # `chapters_from_final_sections` alone, and `final_sections` is the one home
    # the editor never writes to: a student could edit their thesis, order a
    # partner report, and get either the pre-edit snapshot or a freshly
    # LLM-composed chapter that discarded their edits entirely — while the same
    # project's chat and editor exports both rendered the edits.
    from orchestrator.tools.m5_writing import chapter_prose  # noqa: PLC0415
    _m5 = context_store.get("m5_writing") or {}
    _reuse: dict[str, str] = {}
    for _k, _p in (chapter_prose(_m5) or {}).items():
        _p = (_p or "").strip()
        if _p and not _p.lstrip().startswith("["):
            _reuse[_k] = _p

    def _compose_one(idx_name):
        idx, name = idx_name
        if name in _reuse:
            if progress:
                progress(idx, name, titles[name], "end")
            return name, _reuse[name]
        if progress:
            progress(idx, name, titles[name], "start")
        try:
            draft = compose_chapter.invoke({
                "chapter_name": name,
                # Was hardcoded "". compose_chapter setdefaults this onto
                # `{paradigm}`, so a project that stores the paradigm nested
                # under `methodology` composed its partner chapters against a
                # blank one while the chat export filled it in.
                "paradigm": context_slice.get("paradigm") or "",
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
        if progress:
            progress(idx, name, titles[name], "end")
        return name, prose

    # Chapters are independent LLM calls — compose them concurrently (this is the
    # ~6-8 min bottleneck when done one-by-one). Cap workers so we don't hammer
    # the Ofox gateway; assemble the results back in canonical order.
    import concurrent.futures as _cf
    proses: dict[str, str] = {}
    workers = max(1, min(len(ordered), 5))
    with _cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for name, prose in ex.map(_compose_one, list(enumerate(ordered))):
            proses[name] = prose
    return [{"title": titles[name], "prose": proses[name]}
            for name in ordered if (proses.get(name) or "").strip()]


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
