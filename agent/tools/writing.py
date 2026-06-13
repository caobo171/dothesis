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
    def export_docx(citation_style: str = "apa7", force: bool = False) -> str:
        """Export the current thesis draft to Word + PDF.

        Renders every drafted chapter (read from this project's state) into a
        DOCX and a PDF through the engine's document pipeline — headings, TOC,
        citations, references — uploads them, and makes them downloadable from
        the Context store panel. Use this when the user wants the finished
        file. Do NOT paste whole chapters back into chat instead.

        If the project is missing data needed for a qualified thesis (e.g. no
        analysis results, no references), this returns
        {"error": "needs_data", "missing": [...]} WITHOUT exporting — ask the
        user to fill those gaps first. Only pass force=True after the user
        explicitly says to export with whatever data exists.

        Args:
            citation_style: apa7 (default), vancouver, ieee, …
            force: skip the missing-data check and export anyway (user opt-in).
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
                assess_export_readiness,
                compose_all_sections,
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

        # No draft yet → generate one from the upstream modules. But FIRST
        # check the project actually has the data a qualified thesis needs.
        # If not, don't compose a degraded document full of placeholder text —
        # return needs_data so the agent can ask the user to fill the gaps.
        if not sections:
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

        return json.dumps({
            "ok": True,
            "generated": generated,
            "artifacts": artifacts,
            # Instruction to the agent, NOT user-facing copy — the agent must
            # write its OWN confirmation in the conversation's language (the
            # user got an English message parroted from here before). A download
            # card is already rendered in the chat message, so keep it short.
            "instruction": "Export succeeded. Reply with a SHORT confirmation "
                           "in the user's language (Vietnamese if they wrote in "
                           "Vietnamese). Do NOT paste chapter text. The DOCX/PDF "
                           "download buttons are already shown in your message.",
        }, ensure_ascii=False)

    return [export_docx]
