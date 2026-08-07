"""Backfill tool — reconstruct missing UPSTREAM modules from existing work.

A store-bound @tool the chat agent calls when a student wants earlier steps
inferred from what they already have (e.g. they imported an M4 analysis and want
the Topic/Literature/Design filled in). Each reconstruction is SAVED through
store.commit_reconstructed as it's produced; the widget the runtime renders from
this result shows what landed (mirroring export_docx → export_artifacts).

Persisting here, rather than in the widget's confirm click, is what makes the
headless and partner-API surfaces work: they run this same tool with no UI to
click (project_headless_surfaces). Mirrors make_sampling_plan_tool's store-bound
factory shape.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _language_of_existing_work(slices: dict) -> str | None:
    """Which language the student's own work is in, or None if unreadable.

    Read off the evidence rather than assumed. This used to be hardcoded "vi",
    so a student who asked for their thesis in English got every reconstructed
    field back in Vietnamese — the same defect detect_language() already
    documents for the humanize path, in a second place.

    Longest slice wins: the imported document lands as one large blob (usually
    M4 analysis_results) and that is the most reliable sample of how the student
    actually writes. detect_language returns None below its minimum length, so
    short stub values can't out-vote it.
    """
    from orchestrator.tools.humanize import detect_language  # noqa: PLC0415

    texts: list[str] = []
    for slice_ in (slices or {}).values():
        if isinstance(slice_, dict):
            texts.extend(v for v in slice_.values() if isinstance(v, str))
        elif isinstance(slice_, str):
            texts.append(slice_)
    if not texts:
        return None
    return detect_language(max(texts, key=len))


def _move_final_chapter_to_m5(store, slices: dict) -> bool:
    """Give M5 the final chapter that arrived buried in M4. True if moved.

    A finished thesis is written into `m4_analysis.analysis_results` as one
    string, chapters 4 and 5 together, so M5 receives nothing and stays locked
    behind work the student already did.

    Three ways this declines, all of them "leave the document exactly as it
    arrived", because misfiling someone's discussion chapter is worse than
    making them paste it across once:
      - M5 already has content — their own work outranks anything we carve out
      - no confident chapter boundary (see chapter_split's gates)
      - the commit fails, which must not take the rest of the backfill down
    """
    m5 = slices.get("m5_writing")
    if isinstance(m5, dict) and m5.get("final_sections"):
        return False
    m4 = slices.get("m4_analysis")
    if not isinstance(m4, dict):
        return False

    from orchestrator.chapter_split import split_final_chapter  # noqa: PLC0415

    split = split_final_chapter(m4.get("analysis_results"))
    if split is None:
        return False
    head, tail = split
    # final_sections is a LIST of {chapter_name, title, prose} — the shape
    # chapters_from_final_sections and sections_from_m5_slice both iterate.
    # A bare string is silently dropped: they `for sec in final_sections` and
    # skip anything that is not a dict, so a string yields characters and the
    # recovered chapter would vanish at export with nothing logged.
    #
    # "conclusion" rather than "discussion": the heading this splits on is the
    # thesis's FINAL chapter (KẾT LUẬN VÀ KHUYẾN NGHỊ / Conclusion and
    # Recommendations), and mapping it to discussion would put it under the
    # wrong canonical name in the editor rail.
    section = {"chapter_name": "conclusion",
               "title": tail.splitlines()[0].strip()[:120] or "Conclusion",
               "prose": tail}
    try:
        # M5 first: if the M4 rewrite failed after M5 landed we would have the
        # chapter in two places, which is recoverable. The reverse loses it.
        store.commit_slice("M5", {"final_sections": [section]},
                           "import: final chapter recovered from the uploaded document")
        # Trimming M4 is a RE-FILING of content that was already there, not new
        # upstream work — but commit_slice flags DOWNSTREAM["M4"] == ["M5"], so
        # without this it marks needs_review on the very chapter it just
        # recovered. A student importing a finished thesis was told the work
        # their import was reconstructed FROM needed re-reviewing.
        store.commit_slice("M4", {"analysis_results": head},
                           "import: final chapter moved to M5",
                           status_overrides={"M5": "in_progress"})
    except Exception:
        logger.exception("backfill: moving the final chapter to M5 failed")
        return False
    return True


def make_backfill_tool(store):
    @tool
    def backfill_upstream_modules(targets: list[str] | None = None,
                                  language: str | None = None) -> str:
        """Reconstruct earlier thesis steps the student SKIPPED, inferring each
        from the work they already have.

        Call this when the student wants to fill in / backfill / reconstruct
        earlier steps (Topic M1, Literature M2, Design M3, Analysis M4), or wants
        to jump ahead but is missing prerequisites. `targets` optionally limits
        the work to specific module ids (e.g. ["M3"] for just the research
        design); omit it to reconstruct every missing upstream module.

        `language` is the language to WRITE the reconstruction in — pass "en" or
        "vi" whenever the student has said which they want ("viết bằng tiếng
        Anh", "write this in English"). Omit it and the language is read off the
        student's own uploaded work. Their stated preference wins: a Vietnamese
        draft plus "write it in English" means English.

        Each reconstructed module is SAVED as done — tell the student what was
        filled in and that they can ask you to change any of it.
        """
        # store.load_full_context_store is DB-store-only (the api path). The CLI
        # file store can't supply per-module slices, so degrade gracefully.
        loader = getattr(store, "load_full_context_store", None)
        if loader is None:
            return json.dumps({"ok": False, "reconstructed": []})
        from orchestrator.backfill import reconstruct_upstream  # noqa: PLC0415 — orchestrator core, agent layer
        from orchestrator.state import ContextStore  # noqa: PLC0415
        from agent.state import MODULES  # noqa: PLC0415
        # Commit each module the MOMENT it is reconstructed, not after the walk.
        #
        # These surfaces (headless auto-mode, the partner API) have no user
        # sitting there to retry, so a walk that dies on the last module used to
        # throw away every module before it and the whole reconstruction was
        # re-paid from zero. reconstruct_upstream only targets modules that
        # aren't COMPLETE, so committing as we go is also what makes a re-run
        # resume rather than repeat.
        #
        # Out-of-MODULES-order commits are safe here: the walk runs M4→M1 and
        # commit_reconstructed preserves the status of downstream modules that
        # had already started (agent/state.py's `overrides`).
        items: list[dict] = []
        saved: list[dict] = []
        slices: dict = {}

        def _save_now(entry: dict) -> None:
            module = entry.get("module")
            if not module:
                return
            items.append(entry)
            try:
                saved.append(store.commit_reconstructed(module, entry.get("candidate") or {}))
            except Exception:
                logger.exception("backfill: commit_reconstructed %s failed", module)

        try:
            slices = loader()
            cs = ContextStore(**slices)
            # Caller's request first, then the evidence, then the house default.
            lang = language or _language_of_existing_work(slices) or "vi"
            reconstruct_upstream(cs, targets=targets, language=lang,
                                 on_module=_save_now)
        except Exception:
            # Whatever _save_now committed STAYS committed — report what landed.
            logger.exception("backfill_upstream_modules failed")

        items.sort(key=lambda e: MODULES.index(e["module"]) if e["module"] in MODULES else 99)
        saved.sort(key=lambda s: MODULES.index(s["module"]) if s.get("module") in MODULES else 99)

        split = _move_final_chapter_to_m5(store, slices)
        return json.dumps({"ok": True, "reconstructed": items, "saved": saved,
                           "final_chapter_moved": split}, ensure_ascii=False)

    return backfill_upstream_modules
