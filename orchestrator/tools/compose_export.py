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

# The "[3]" / "[1, 4]" source markers a research brief leaves in a gap
# description. Compiled at module level rather than inline in the f-string
# below: the inline form was written as r'\\s*\\[[0-9,\\s]+\\]', where the raw
# string keeps BOTH backslashes — so the pattern demanded a literal backslash
# before "s" and never matched anything. Nothing caught it because
# `research_gaps` was unreachable until m2 joined the slice; the moment it went
# live it would have shipped dangling "[3]" markers into Chapter 1.
_SOURCE_MARKER_RE = re.compile(r"\s*\[[0-9,\s]+\]")


def wants_merged_conclusion(context_store: dict) -> bool:
    """Should this thesis end in ONE concluding chapter?

    Yes by default: Vietnamese universities set a five-chapter thesis and the
    discussion is written inside "Kết luận và khuyến nghị". An imported thesis
    reads "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU / CHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN NGHỊ",
    and the interactive export was handing back SIX chapters — pushing the
    student's conclusion to Chapter 6 and adding a Discussion chapter their
    supervisor never asked for. The partner pipeline has always merged; only
    this path did not, so the same product answered the same question two ways.

    No when the project genuinely HAS both chapters written out, which is how a
    thesis that really follows the six-chapter template keeps it. Follows the
    project's own evidence rather than a global switch.

    Deliberately NOT keyed on language: writing in English does not make it an
    Anglo thesis. A Vietnamese student writing in English still submits five
    chapters, because the university's template governs, not the prose.
    """
    m5 = (context_store or {}).get("m5_writing") or {}

    def _prose(v) -> str:
        if isinstance(v, dict):
            return str(v.get("prose") or v.get("body") or "")
        return str(v or "")

    chapters = m5.get("chapters") or {}
    if isinstance(chapters, dict):
        if _prose(chapters.get("discussion")).strip() and _prose(chapters.get("conclusion")).strip():
            return False
    names = set()
    for sec in m5.get("final_sections") or []:
        if not isinstance(sec, dict) or not _prose(sec).strip():
            continue
        title = (sec.get("title") or "").lower()
        name = (sec.get("chapter_name") or "").lower()
        if name == "discussion" or "discussion" in title or "thảo luận" in title:
            names.add("discussion")
        if name == "conclusion" or "conclusion" in title or "kết luận" in title:
            names.add("conclusion")
    return not {"discussion", "conclusion"} <= names


def merged_chapter_keys(chapters: list[str]) -> list[str]:
    """The chapter keys compose_sections(merge_conclusion=True) will actually
    write — `conclusion` folded into `discussion`.

    Public because a CALLER has to be able to report what was composed without
    re-deriving the rule: the partner response echoes its `chapters` list, and
    the old pipeline echoed the POST-merge keys because it merged before
    composing. Now that the merge happens inside compose_sections, a caller that
    restated the rule locally would be a second copy of it, free to drift — and
    the drift would only ever surface in a partner's JSON.
    """
    if "conclusion" not in set(chapters):
        return list(chapters)
    out = [c for c in chapters if c != "conclusion"]
    if "discussion" not in out:
        out.append("discussion")
    return out


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
        chapters = merged_chapter_keys(chapters)
        combined = ("Chương 5 — Kết luận" if str(language).lower().startswith("vi")
                    else "Chapter 5 — Conclusion")
        title_overrides = {**(title_overrides or {}), "discussion": combined}

    m1 = context_store.get("m1_topic") or {}
    m2 = context_store.get("m2_literature") or {}
    m3 = context_store.get("m3_design") or {}
    m4 = context_store.get("m4_analysis") or {}
    # m2 IS part of the slice. It was the one module left out, which made
    # `research_gaps` — an M2-OWNED key (agent/state.py SLICE_OWNERSHIP) that
    # intro.md/lit_review.md/discussion.md all interpolate and explicitly label
    # "from M2" — permanently empty, and the gap-rendering block below it dead.
    # The deleted partner_report_service hid the bug: it wrote the grounded
    # brief's gaps into a plain `m1_topic` dict with no ownership filter, so its
    # Introductions were the ONLY ones that ever saw a real gap. Once partner
    # started writing through commit_slice the gaps landed in m2 where they
    # belong and silently stopped reaching the composer — same prompt, less
    # grounded prose. Merging here fixes every surface at once: chat and
    # auto-mode have been composing Introductions against an empty
    # {research_gaps} this whole time, which is the bug, not a new feature.
    # Merge order follows READS (m1 < m2 < m3 < m4) so a downstream module's
    # value still wins any key collision.
    context_slice: dict = {**m1, **m2, **m3, **m4}
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
            f"- {_SOURCE_MARKER_RE.sub('', str(g.get('description', ''))).strip()}"
            for g in _gaps if isinstance(g, dict)
        )
    elif not isinstance(_gaps, str):
        context_slice["research_gaps"] = ""

    # Always compose in canonical order regardless of how the caller ordered them.
    ordered = [k for k in M5_CHAPTER_ORDER if k in set(chapters)]
    titles = {**_chapter_titles(language), **(title_overrides or {})}

    # Reuse chapters the deep agent already composed THIS run
    # (m5_writing.final_sections) instead of re-composing them — the partner
    # export otherwise pays for the same chapters a second time. Only real prose
    # is reused (stubs / "[Composition failed]" markers fall through to compose).
    from orchestrator.tools.m5_writing import chapters_from_final_sections  # noqa: PLC0415
    _m5 = context_store.get("m5_writing") or {}
    _reuse: dict[str, str] = {}
    for _k, _v in (chapters_from_final_sections(_m5.get("final_sections") or []) or {}).items():
        _p = ((_v or {}).get("prose") or "").strip()
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
        # The five-chapter Vietnamese template, which the partner pipeline has
        # always used and this path never did — so a student's interactive
        # export came back with six chapters and their conclusion at Chapter 6.
        merge_conclusion=wants_merged_conclusion(context_store),
    )
    # Call through the module so a test-time monkeypatch of m5_writing.run_export
    # (or any late rebinding) is honoured — a frozen import-time name would not be.
    return m5_writing.run_export(
        sections, str(project_id), references=references or None, language=language,
    )
