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
        try:
            slices = loader()
            cs = ContextStore(**slices)
            # Caller's request first, then the evidence, then the house default.
            lang = language or _language_of_existing_work(slices) or "vi"
            items = reconstruct_upstream(cs, targets=targets, language=lang)
        except Exception:
            logger.exception("backfill_upstream_modules failed")
            items = []

        # MODULES order so an upstream commit never flags a downstream module
        # it just wrote. One module failing to commit must not lose the others.
        saved: list[dict] = []
        by_module = {i["module"]: i for i in items if i.get("module")}
        for module in MODULES:
            item = by_module.get(module)
            if item is None:
                continue
            try:
                saved.append(store.commit_reconstructed(module, item.get("candidate") or {}))
            except Exception:
                logger.exception("backfill: commit_reconstructed %s failed", module)
        return json.dumps({"ok": True, "reconstructed": items, "saved": saved},
                          ensure_ascii=False)

    return backfill_upstream_modules
