"""M5 writing/export tools for the v3 deep agent.

`export_docx` is a factory tool (closes over the project's ProjectStateStore)
so it can read the current draft and ship it to the REAL engine exporter in
orchestrator/tools/m5_writing — the same renderer the Auto-draft run uses.
Earlier this was a `not_wired` stub that always failed; that was the source of
the "công cụ export_docx vẫn đang gặp lỗi kỹ thuật" apology.

`write_pipeline` is intentionally NOT exposed anymore: bulk chapter generation
runs through the server-side Auto-draft button (deterministic), and targeted
single-section drafting is something the agent does conversationally + commits
via commit_slice. A stubbed pipeline tool only ever produced confusing
"pipeline broken" messages.
"""
from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def make_writing_tools(store) -> list:
    """Build the writing/export tools bound to one project's state store.

    `store` is a ProjectStateStore; the DB-backed subclass carries
    `.project_id` (needed for the S3 export key) and may expose
    `persist_export_artifacts` so the artifacts land where the ContextPanel
    reads them. The file-backed CLI store has neither — export degrades to a
    clear "not available in this environment" message rather than crashing.
    """

    @tool
    def export_docx(citation_style: str = "apa7", force: bool = False, scope: str = "full") -> str:
        """Export thesis work to Word + PDF.

        `scope` controls WHAT is exported:
          - "full" (default): the whole thesis — every drafted chapter rendered
            with headings, TOC, citations, references.
          - a module or a comma-joined SET of modules ("M3", or "M1,M3,M4"):
            composes those module(s) into ONE professor-ready document, in
            M1→M4 order (M1=Introduction, M2=Literature, M3=Design/Methodology,
            M4=Analysis/Results). Use this when the user picks specific modules
            (e.g. "export my methodology + results" → scope "M3,M4").

        The export is recorded in the project's Exports list tagged with `scope`,
        so a single-module export is labeled correctly (it does NOT get filed
        under M5). A download card is shown in your reply.

        If the project is missing data needed for a qualified thesis (e.g. no
        analysis results, no references), the full export returns
        {"error": "needs_data", "missing": [...]} WITHOUT exporting — ask the
        user to fill those gaps first. Only pass force=True after the user
        explicitly says to export with whatever data exists.

        Args:
            citation_style: apa7 (default), vancouver, ieee, …
            force: skip the missing-data check and export anyway (user opt-in).
            scope: "full" (default) or "M1".."M4" for a single-module export.
        """
        project_id = getattr(store, "project_id", None)
        if project_id is None:
            return json.dumps({
                "error": "no_project",
                "hint": "Export isn't available in this environment. In the "
                        "app, the user can also click the Auto-draft button.",
            })

        try:
            from orchestrator.tools.m5_writing import (
                M5_CHAPTER_ORDER,
                assess_export_readiness,
                compose_all_sections,
                compose_module_prose,
                run_export,
                sections_from_m5_slice,
                _is_stub_prose,
            )
        except Exception:
            logger.exception("export_docx: could not import engine exporter")
            return json.dumps({"error": "exporter_unavailable"})

        # Read the M5 slice straight from state. `load()` returns the flat
        # contextStore; final_sections is the v3 owned key, chapters is the
        # auto-mode shape — sections_from_m5_slice tolerates both.
        try:
            state = store.load()
        except Exception:
            logger.exception("export_docx: store.load() failed")
            return json.dumps({"error": "state_read_failed"})

        flat = state.get("contextStore", {}) or {}
        m5_slice = {
            "final_sections": flat.get("final_sections"),
            "chapters": flat.get("chapters"),
        }
        sections = sections_from_m5_slice(m5_slice)
        generated = False

        # Load the full nested context store once — needed both for the
        # readiness check and to pull M2 references for clickable citations.
        full_cs = None
        loader = getattr(store, "load_full_context_store", None)
        if loader is not None:
            try:
                full_cs = loader()
            except Exception:
                logger.exception("export_docx: load_full_context_store failed")
        references = ((full_cs or {}).get("m2_literature") or {}).get("literature_sources") or []
        language = ((full_cs or {}).get("m1_topic") or {}).get("language") or "vi"

        # --- Module-scoped export (scope = "M3" or a set "M1,M3,M4") --------
        # Compose ONE document from the selected module(s) — a standalone
        # academic write-up — and file it tagged with that scope (not M5). The
        # user can pick several modules; they're combined into one doc in M-order.
        _scope = (scope or "full").strip()
        if _scope.lower() != "full":
            _COLUMN = {"M1": "m1_topic", "M2": "m2_literature",
                       "M3": "m3_design", "M4": "m4_analysis"}
            _LABEL = {"M1": "Introduction", "M2": "Literature Review",
                      "M3": "Research Design", "M4": "Data Analysis"}
            # Parse + de-dup the requested modules, keep canonical M1→M4 order.
            requested = {m.strip().upper() for m in _scope.split(",") if m.strip()}
            mods = [m for m in ("M1", "M2", "M3", "M4") if m in requested]
            unknown = requested - set(_COLUMN)
            if unknown or not mods:
                return json.dumps({
                    "error": "bad_scope",
                    "hint": "scope must be 'full' or a comma-joined set of "
                            "M1, M2, M3, M4 (e.g. 'M1,M3').",
                })
            title = ((full_cs or {}).get("m1_topic") or {}).get("research_title") or "Untitled thesis"
            built: list[dict] = []
            thin: list[str] = []
            for _mod in mods:
                slice_ = (full_cs or {}).get(_COLUMN[_mod]) or {}
                prose = compose_module_prose(_mod, slice_, title)
                if not prose.strip() or _is_stub_prose(prose):
                    thin.append(_mod)
                    continue
                built.append({"title": _LABEL[_mod], "prose": prose})
            # If some picked modules have no real content, stop (unless forced)
            # so we don't ship a doc full of placeholders.
            if thin and not force:
                return json.dumps({
                    "error": "needs_data",
                    "modules": thin,
                    "hint": f"These modules don't have enough committed content "
                            f"to write yet: {', '.join(thin)}. Ask the user to "
                            f"fill them in, or export anyway with force.",
                }, ensure_ascii=False)
            if not built:
                return json.dumps({
                    "error": "no_content",
                    "hint": "None of the selected modules have content to export.",
                })
            scope_tag = ",".join(mods)
            try:
                artifacts = run_export(
                    built, str(project_id), references=references, language=language,
                )
            except Exception as e:
                logger.exception("export_docx(scope=%s): run_export failed", scope_tag)
                return json.dumps({"error": "export_failed", "detail": str(e)})
            persist = getattr(store, "persist_export_artifacts", None)
            if persist:
                try:
                    persist(artifacts, scope=scope_tag)
                except Exception:
                    logger.exception("export_docx: persist (scope=%s) failed", scope_tag)
            # F5: chat-surface export completed (module-scoped). Best-effort.
            from agent.analytics import emit  # noqa: PLC0415
            emit("export_completed", None,
                 {"scope": scope_tag, "surface": "chat", "project_id": str(project_id)})
            return json.dumps({
                "ok": True,
                "scope": scope_tag,
                "artifacts": artifacts,
                "instruction": "Module export succeeded. Reply with a SHORT "
                               "confirmation in the user's language. The DOCX/PDF "
                               "download buttons are already shown.",
            }, ensure_ascii=False)

        # A FULL thesis export needs every chapter. Compose when there's NO
        # draft OR when the stored draft is INCOMPLETE — e.g. only the
        # methodology was committed to final_sections, which made a "full"
        # export silently ship a 1-chapter document while the reply claimed 6.
        # (A complete committed draft — chapter_count >= the full order — is
        # reused as-is.)
        _chapter_count = len([
            s for s in (sections or []) if (s.get("title") or "") != "References"
        ])
        if not sections or _chapter_count < len(M5_CHAPTER_ORDER):
            if full_cs:
                missing = assess_export_readiness(full_cs)
                if missing and not force:
                    return json.dumps({
                        "error": "needs_data",
                        "missing": missing,
                        "hint": "The project is missing data needed for a "
                                "qualified thesis. Ask the user whether they want "
                                "to fill these (run the relevant module) or export "
                                "anyway with what exists (call again with force).",
                    }, ensure_ascii=False)
                sections = compose_all_sections(full_cs)
                generated = True

        if not sections:
            return json.dumps({
                "error": "no_content",
                "hint": "There isn't enough upstream work (M1–M4) to build the "
                        "thesis yet. Complete the research modules first.",
            })

        # Never export placeholder/failure stubs. If any chapter came out as a
        # stub (transient LLM failure, or thin source data the readiness check
        # didn't catch), refuse and report which — so the weird "[Composition
        # failed]" / "[Auto-generated for …]" text never reaches the document.
        chapter_secs = [s for s in sections if s.get("title") != "References"]
        incomplete = [s["title"] for s in chapter_secs if _is_stub_prose(s.get("prose", ""))]
        if incomplete and not force:
            return json.dumps({
                "error": "needs_data",
                "incomplete_chapters": incomplete,
                "hint": "These chapters couldn't be written from the current "
                        "data. Ask the user to fill the gaps, then export again "
                        "(or export anyway with force).",
            }, ensure_ascii=False)

        # Only persist once we know the draft is worth keeping (no stubs).
        if generated:
            try:
                store.commit_slice(
                    "M5",
                    {"final_sections": sections},
                    "Drafted chapters to export the thesis",
                    confirm_done=False,
                )
            except Exception:
                logger.exception("export_docx: persisting generated draft failed")

        try:
            artifacts = run_export(sections, str(project_id), references=references, language=language)
        except Exception as e:
            logger.exception("export_docx: run_export failed")
            return json.dumps({"error": "export_failed", "detail": str(e)})

        # Persist so the ContextPanel + header Download button light up. The
        # DB store exposes this; the file store doesn't (export still
        # succeeded, just not surfaced in the web panel).
        persist = getattr(store, "persist_export_artifacts", None)
        if persist:
            try:
                persist(artifacts)
            except Exception:
                logger.exception("export_docx: persist_export_artifacts failed")

        # Report what was ACTUALLY exported so the agent doesn't claim "6
        # chapters" when fewer were produced. chapter_titles excludes the
        # auto-appended References section.
        chapter_titles = [s.get("title") for s in sections if (s.get("title") or "") != "References"]
        # F5: chat-surface full-thesis export completed. Best-effort.
        from agent.analytics import emit  # noqa: PLC0415
        emit("export_completed", None,
             {"scope": "full", "surface": "chat", "project_id": str(project_id)})
        return json.dumps({
            "ok": True,
            "generated": generated,
            "artifacts": artifacts,
            "chapters": chapter_titles,
            "chapter_count": len(chapter_titles),
            # Instruction to the agent, NOT user-facing copy — the agent must
            # write its OWN confirmation in the conversation's language (the
            # user got an English message parroted from here before). A download
            # card is already rendered in the chat message, so keep it short.
            "instruction": "Export succeeded. Reply with a SHORT confirmation "
                           "in the user's language (Vietnamese if they wrote in "
                           "Vietnamese). State the ACTUAL chapter_count above — do "
                           "NOT claim a number of chapters that isn't in `chapters`. "
                           "Do NOT paste chapter text. The DOCX/PDF download "
                           "buttons are already shown in your message.",
        }, ensure_ascii=False)

    @tool
    def review_thesis() -> str:
        """Grade the current thesis against a committee-readiness rubric (structure,
        citations, method-specific results, methodology, writing, and any open advisor
        comments). Returns per-dimension scores plus specific fixes. Advisory — it does
        not block export."""
        from quality.rubric import score_thesis  # noqa: PLC0415

        cs = store.load_full_context_store()
        # F0: read the coaching keys through the store's TYPED getters (empty
        # defaults), never getattr(store, "institution_profile", ...) — that
        # attribute is never set and would silently mask a real profile. Passing
        # the empty dict/list through keeps F3 working without F4 present.
        profile = store.get_institution_profile() or None
        feedback = store.get_advisor_feedback() or []
        result = score_thesis(cs, institution_profile=profile, advisor_feedback=feedback)
        # F5: emit the quality-trend signal (overall score, detected method,
        # blocking-finding count). No user id at the tool layer — pass None; the
        # dashboard trends on properties, not per-person. Best-effort hook.
        from agent.analytics import emit  # noqa: PLC0415 — no-op until app wires it
        emit("quality_reviewed", None, {
            "overall": result.get("overall"),
            "method": result.get("method"),
            "blocking_count": len(result.get("blocking") or []),
        })
        return json.dumps(result, ensure_ascii=False)

    return [export_docx, review_thesis]
