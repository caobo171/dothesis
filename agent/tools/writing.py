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

# The language slice: what we WRITE in, which is not the same question as what
# language the student's existing draft is in. A student may upload a Vietnamese
# draft and ask for the thesis in English.
_LANG_KEY = "language"


def resolve_output_language(context_store: dict | None) -> str:
    """Which language to WRITE generated prose in.

    Precedence, and each rung exists because the one below it got something
    wrong in production:

    1. `m1_topic.language` — the student's stated choice. M1 owns this key, so
       the agent persists it with commit_slice when they say which they want.
       Nothing else may override it: "viết bằng tiếng Anh" on a Vietnamese draft
       means English, and inferring from the draft would silently overrule them.
    2. The language of their own work. A blind default is how an English
       dissertation came back in Vietnamese — the same failure detect_language()
       documents for the humanize path. If they never said, mirror what they
       wrote rather than guessing.
    3. "vi", the house default, only when there is nothing to read.

    Three call sites resolved this independently and disagreed: two defaulted
    "vi" and one "en", so the same project exported chapters in one language and
    limitations in the other.
    """
    cs = context_store if isinstance(context_store, dict) else {}
    m1 = cs.get("m1_topic")
    stated = (m1 or {}).get(_LANG_KEY) if isinstance(m1, dict) else None
    if isinstance(stated, str) and stated.strip():
        return stated.strip()

    from orchestrator.tools.humanize import detect_language  # noqa: PLC0415

    texts: list[str] = []
    for slice_ in cs.values():
        if isinstance(slice_, dict):
            texts.extend(v for v in slice_.values() if isinstance(v, str))
        elif isinstance(slice_, str):
            texts.append(slice_)
    if texts:
        # Longest wins: an imported thesis lands as one large blob and is the
        # most reliable sample of how this student actually writes.
        return detect_language(max(texts, key=len)) or "vi"
    return "vi"


def _maybe_humanize(sections: list[dict], enabled: bool,
                    language: str) -> tuple[list[dict], list[dict] | None]:
    """Optionally re-voice composed sections before rendering.

    Opt-in and best-effort by construction. This runs on the shared export path
    — the same one headless auto-mode and the partner API use — so it must not
    be able to change or fail an export nobody asked to humanize: `enabled` is
    False for every caller that doesn't pass it, and any failure inside the pass
    returns the sections untouched.

    Returns (sections, report) where report is None when the pass didn't run.
    """
    if not enabled:
        return sections, None
    try:
        from orchestrator.tools.humanize import humanize_sections  # noqa: PLC0415

        return humanize_sections(sections, language=language)
    except Exception:
        logger.exception("export_docx: humanize pass failed — exporting as composed")
        return sections, [{"ok": False, "error": "humanizer_failed"}]


def _backfill_legacy_m3_for_export(store, context_store: dict) -> tuple[dict, dict | None]:
    """Persist a recoverable prose-only M3 model in today's canonical shape.

    Export used to tolerate a malformed row only in-memory, so every retry paid
    the same failure again. This performs a one-time, evidence-preserving repair
    through the sole state write path. Only explicit relationships recoverable
    by the M3 contract are saved; free prose without a graph is left untouched.
    """
    cs = context_store if isinstance(context_store, dict) else {}
    m3 = cs.get("m3_design")
    if not isinstance(m3, dict) or not isinstance(m3.get("conceptual_model"), str):
        return cs, None

    from agent.m3_contract import normalize_conceptual_model  # noqa: PLC0415

    canonical, _ = normalize_conceptual_model(m3.get("conceptual_model"))
    if not canonical.get("nodes") or not canonical.get("edges"):
        return cs, None
    result = store.commit_slice(
        "M3", {"conceptual_model": canonical},
        "Backfilled legacy conceptual model schema before document export",
        confirm_done=False,
    )
    updated = dict(cs)
    updated["m3_design"] = {**m3, "conceptual_model": canonical}
    return updated, {
        "module": "M3",
        "nodes": len(canonical.get("nodes") or []),
        "edges": len(canonical.get("edges") or []),
        "commit": result,
    }


def make_writing_tools(store) -> list:
    """Build the writing/export tools bound to one project's state store.

    `store` is a ProjectStateStore; the DB-backed subclass carries
    `.project_id` (needed for the S3 export key) and may expose
    `persist_export_artifacts` so the artifacts land where the ContextPanel
    reads them. The file-backed CLI store has neither — export degrades to a
    clear "not available in this environment" message rather than crashing.
    """

    @tool
    def humanize_text(text: str, user_anchor: str = "") -> str:
        """Rewrite a passage so it reads as human-written rather than AI-drafted.

        Use when a supervisor / reviewer / detector flagged the writing as AI
        ("bị chê là toàn AI", "giống ChatGPT", "viết lại cho tự nhiên hơn").
        Read the `dothesis-humanize` skill before using this.

        Changes voice ONLY. Every number, p-value, β, table reference and
        citation is frozen and verified after the rewrite — if one moved, the
        rewrite is discarded and the ORIGINAL text is returned with
        `ok: false`. When that happens, say so; never report the passage as
        humanized.

        The rewrite is anchored on real human prose and will NOT run without an
        anchor (`error: "no_anchor"`): an unanchored "make it sound human" pass
        measurably does nothing while appearing to work.

        CALL IT WITHOUT `user_anchor` FIRST. If this student has already given a
        sample it is loaded automatically and you must not ask again. Only when
        you get back `error: "no_anchor"` should you ask for ~150 words they
        wrote themselves (an old essay, a report — anything pre-AI) and retry
        with `user_anchor`. It is then remembered, so you ask at most once ever.

        Works on ONE passage at a time — a section, not the whole thesis.

        Args:
            text: the passage to rewrite.
            user_anchor: ~150 words of the student's own writing (optional if a
                library anchor is installed for the project language).
        """
        try:
            from orchestrator.tools.humanize import humanize_prose  # noqa: PLC0415
        except Exception:
            logger.exception("humanize_text: engine import failed")
            return json.dumps({"ok": False, "error": "humanizer_unavailable"})

        # Language comes from project state, not from the caller: the agent
        # guessing "vi"/"en" per call is how the wrong anchor set gets loaded.
        language = "vi"
        try:
            loader = getattr(store, "load_full_context_store", None)
            if loader is not None:
                language = resolve_output_language(loader() or {})
        except Exception:
            logger.exception("humanize_text: language lookup failed, defaulting to vi")

        # Anchor persistence: ask the student ONCE, not once per project.
        #
        # Without this the tool returns no_anchor forever — the shipped anchor
        # library is empty on purpose (an anchor has to be off the LLM training
        # distribution, so it cannot be generated), so the student's own sample
        # is the only thing that makes humanize work at all. Re-asking for 150
        # words every time is how a working feature goes unused.
        #
        # Duck-typed via getattr because the file-backed CLI store has no user
        # to attach an anchor to — there, this degrades to today's behaviour
        # (ask each time) rather than crashing.
        anchor = user_anchor or ""
        if not anchor.strip():
            loader = getattr(store, "load_writing_anchor", None)
            if loader is not None:
                try:
                    anchor = loader() or ""
                except Exception:  # noqa: BLE001
                    logger.exception("humanize_text: stored anchor lookup failed")

        result = humanize_prose(text, language=language,
                                user_anchor=anchor.strip() or None)

        # Save only what the CALLER supplied and only once it actually worked:
        # persisting a sample that produced no_anchor/frozen_violation would
        # pin the student to a bad anchor they can never see or correct.
        if user_anchor.strip() and result.get("ok"):
            saver = getattr(store, "save_writing_anchor", None)
            if saver is not None:
                try:
                    saver(user_anchor)
                except Exception:  # noqa: BLE001
                    logger.exception("humanize_text: anchor save failed")

        return json.dumps(result, ensure_ascii=False)

    @tool
    def export_docx(citation_style: str = "apa7", force: bool = False, scope: str = "full",
                    humanize: bool = False) -> str:
        """Export thesis work to Word + PDF.

        `scope` controls WHAT is exported:
          - "full" (default): the whole thesis — every drafted chapter rendered
            with headings, TOC, citations, references.
          - a module or a comma-joined SET of modules ("M3", or "M1,M3,M4"):
            composes those module(s) into ONE professor-ready document, in
            M1→M4 order (M1=Introduction, M2=Literature, M3=Design/Methodology,
            M4=Analysis/Results). Use this when the user picks specific modules
            (e.g. "export my methodology + results" → scope "M3,M4").
            Exact content mapping: introduction/problem statement = M1;
            literature review/theoretical foundation = M2; conceptual model,
            research design, or methodology = M3; analysis/results = M4.
            Thus “problem statement + theoretical foundation + research
            proposal” MUST use "M1,M2,M3" so the theory chapter is not omitted.
          - named drafted chapters using "chapter:<names joined by |>", for
            example "chapter:intro|discussion". Valid canonical names are
            intro, lit_review, methodology, results, discussion, conclusion.
            Use this immediately after writing or revising named M5 chapters.

        The export is recorded in the project's Exports list tagged with `scope`,
        so a single-module export is labeled correctly (it does NOT get filed
        under M5). A download card is shown in your reply.

        If the project is missing data needed for a qualified thesis (e.g. no
        analysis results, no references), the full export returns
        {"error": "needs_data", "missing": [...]} WITHOUT exporting — ask the
        user to fill those gaps first. Only pass force=True after the user
        explicitly says to export with whatever data exists.

        Set `humanize=True` ONLY when the user asked for a version that doesn't
        read as AI-written (see the `dothesis-humanize` skill). It re-voices
        every chapter before rendering, costs ~2 extra LLM calls per chapter,
        and reports per-chapter results under `humanized` — chapters that
        failed verification are exported unchanged, so name them rather than
        claiming the whole document was rewritten.

        Args:
            citation_style: apa7 (default), vancouver, ieee, …
            force: skip the missing-data check and export anyway (user opt-in).
            scope: "full", module set, or "chapter:intro|discussion".
            humanize: re-voice the prose before rendering (opt-in, chat only).
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
                M5_CHAPTER_TITLES,
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
        backfilled = None
        if full_cs:
            try:
                full_cs, backfilled = _backfill_legacy_m3_for_export(store, full_cs)
            except Exception as exc:
                logger.exception("export_docx: legacy M3 backfill failed")
                return json.dumps({
                    "error": "state_backfill_failed",
                    "module": "M3",
                    "detail": str(exc),
                    "hint": "The legacy research model could not be safely saved. "
                            "Repair M3 before retrying export.",
                }, ensure_ascii=False)
        # m2_references, not the raw key: an inferred M2 fills `citation_list`
        # and leaves `literature_sources` empty, which read here as "this thesis
        # has no sources" and shipped a document with no bibliography.
        from orchestrator.tools.m5_writing import m2_references  # noqa: PLC0415
        references = m2_references((full_cs or {}).get("m2_literature"))
        language = resolve_output_language(full_cs or {})

        # --- Chapter-scoped export (newly written/revised M5 sections) -------
        _scope = (scope or "full").strip()
        if _scope.lower().startswith("chapter:"):
            aliases = {
                "introduction": "intro", "intro": "intro",
                "literature": "lit_review", "literature_review": "lit_review",
                "lit_review": "lit_review", "method": "methodology",
                "methodology": "methodology", "results": "results",
                "discussion": "discussion", "conclusion": "conclusion",
            }
            raw_names = [part.strip().lower() for part in _scope[8:].split("|") if part.strip()]
            names = [aliases.get(name, name) for name in raw_names]
            valid = set(M5_CHAPTER_ORDER)
            unknown = [name for name in names if name not in valid]
            if unknown or not names:
                return json.dumps({
                    "error": "bad_scope",
                    "hint": "chapter scope must use intro, lit_review, methodology, "
                            "results, discussion, or conclusion, joined with |.",
                })
            by_name = {(section.get("chapter_name") or "").lower(): section
                       for section in sections or []}
            by_title = {(section.get("title") or "").strip().lower(): section
                        for section in sections or []}
            selected = []
            missing = []
            for name in dict.fromkeys(names):
                title = (M5_CHAPTER_TITLES.get(name, name) or "").strip().lower()
                section = by_name.get(name) or by_title.get(title)
                if section and (force or not _is_stub_prose(section.get("prose", ""))):
                    selected.append(section)
                else:
                    missing.append(name)
            # Decision: a chapter request is itself authorization to compose
            # from completed upstream state. Requiring a prior M5 chat commit
            # made “write Chapters 1–3” refuse despite complete M1–M3 inputs.
            if missing and full_cs:
                readiness = assess_export_readiness(full_cs, chapters=missing)
                if not readiness or force:
                    composed = compose_all_sections(full_cs, chapters=missing)
                    composed_by_name = {
                        (section.get("chapter_name") or "").lower(): section
                        for section in composed
                        if section.get("chapter_name")
                    }
                    still_missing = []
                    for name in missing:
                        section = composed_by_name.get(name)
                        if section and (force or not _is_stub_prose(section.get("prose", ""))):
                            selected.append(section)
                        else:
                            still_missing.append(name)
                    missing = still_missing
            if missing and not force:
                return json.dumps({
                    "error": "needs_data", "missing_chapters": missing,
                    "hint": "Write and commit these chapters before exporting them.",
                }, ensure_ascii=False)
            if not selected:
                return json.dumps({"error": "no_content",
                                   "hint": "None of the selected chapters has exportable prose."})
            selected_by_name = {
                (section.get("chapter_name") or "").lower(): section
                for section in selected
            }
            selected = [selected_by_name[name] for name in dict.fromkeys(names)
                        if name in selected_by_name]

            # Persist chapters composed by this export so the editor and later
            # exports reuse the exact prose the student downloaded. Merge by
            # canonical chapter name; never discard unrelated existing chapters.
            if full_cs and any(name not in by_name for name in selected_by_name):
                merged = list(sections or [])
                positions = {
                    (section.get("chapter_name") or "").lower(): index
                    for index, section in enumerate(merged)
                    if section.get("chapter_name")
                }
                for name, section in selected_by_name.items():
                    if name in positions:
                        merged[positions[name]] = section
                    else:
                        merged.append(section)
                try:
                    store.commit_slice(
                        "M5", {"final_sections": merged},
                        "Composed requested chapters for targeted export",
                        confirm_done=False,
                    )
                except Exception:
                    logger.exception("export_docx: persisting targeted chapters failed")
            selected, _hum_report = _maybe_humanize(selected, humanize, language)
            title = ((full_cs or {}).get("m1_topic") or {}).get("research_title") or "Untitled thesis"
            scope_tag = "chapter:" + "|".join(dict.fromkeys(names))
            try:
                artifacts = run_export(selected, str(project_id), references=references,
                                       language=language, title=title, context_store=full_cs)
            except Exception as exc:
                logger.exception("export_docx(scope=%s): run_export failed", scope_tag)
                return json.dumps({"error": "export_failed", "detail": str(exc)})
            persist = getattr(store, "persist_export_artifacts", None)
            if persist:
                try:
                    persist(artifacts, scope=scope_tag)
                except Exception:
                    logger.exception("export_docx: persist chapter artifacts failed")
            return json.dumps({
                "ok": True, "scope": scope_tag, "artifacts": artifacts,
                "chapter_titles": [section.get("title") for section in selected],
                "backfilled": backfilled,
                "humanized": _hum_report,
                "instruction": "Chapter export succeeded. Confirm briefly in the "
                               "user's language; download buttons are already shown.",
            }, ensure_ascii=False)

        # --- Module-scoped export (scope = "M3" or a set "M1,M3,M4") --------
        # Compose ONE document from the selected module(s) — a standalone
        # academic write-up — and file it tagged with that scope (not M5). The
        # user can pick several modules; they're combined into one doc in M-order.
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
            built, _hum_report = _maybe_humanize(built, humanize, language)
            try:
                artifacts = run_export(
                    built, str(project_id), references=references, language=language,
                    # Without this the cover of a module-scoped export is built
                    # from title=None. `title` is already resolved above.
                    title=title,
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
                "humanized": _hum_report,
                "instruction": "Module export succeeded. Reply with a SHORT "
                               "confirmation in the user's language. The DOCX/PDF "
                               "download buttons are already shown."
                               + (" If `humanized` is present, state which "
                                  "sections were rewritten and which were kept "
                                  "unchanged — do not claim all of them."
                                  if _hum_report else ""),
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
        # "Complete" means every chapter the run is scoped to — the ORDERED set
        # for a partner order, the whole thesis otherwise. Using the full-6 count
        # here made a scoped 3-chapter draft look permanently incomplete and
        # recompose on every export.
        from agent.run_context import scoped_chapters  # noqa: PLC0415
        _needed = len(scoped_chapters(list(M5_CHAPTER_ORDER)))
        if not sections or _chapter_count < _needed:
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

        # A "full" export must never SILENTLY ship fewer chapters than a thesis
        # has. The composition branch above is best-effort in several places —
        # `full_cs` may be unreadable, and composition can return short — and
        # every one of those paths fell through to rendering whatever `sections`
        # happened to hold. A real export went out as a 35KB file containing
        # only the two imported chapters, no introduction / literature review /
        # methodology, while the reply told the student the thesis was complete.
        #
        # Shipping a partial thesis under the name of a full one is the worst
        # outcome here: the student cannot see what is missing, and the reply
        # says nothing is. Refuse and NAME the missing chapters instead — the
        # same contract as the stub check below. `force` still overrides, so an
        # intentional partial export stays possible.
        if _scope.lower() == "full":
            have = {(s.get("chapter_name") or "") for s in sections}
            titled = {(s.get("title") or "").strip().lower() for s in sections}
            missing_ch = [
                n for n in scoped_chapters(list(M5_CHAPTER_ORDER))
                if n not in have
                and (M5_CHAPTER_TITLES.get(n, n) or "").strip().lower() not in titled
            ]
            if missing_ch and not force:
                return json.dumps({
                    "error": "incomplete_export",
                    "missing_chapters": missing_ch,
                    "hint": "A full export needs every chapter. These were "
                            "neither stored nor composed — check the upstream "
                            "modules they are written from, then export again "
                            "(or export the partial document with force).",
                }, ensure_ascii=False)
            if missing_ch:
                logger.warning("export_docx: FORCED full export missing chapters %s", missing_ch)

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
            # A partner/report run (a chapter scope is set) must flip M5 to DONE
            # here: it's past the stub gate, so every ORDERED chapter is real, and
            # the headless agent otherwise never confirms M5 itself — _all_done
            # stays false and the run churns to the wall-clock even though the
            # chapters are finished (observed live on job 04c5b417: chapters
            # drafted, M5 stuck "in_progress", run heading for a 30-min timeout).
            # Interactive chat keeps confirm_done=False — there an export is a
            # preview and the student declares the module done.
            from agent.run_context import required_modules  # noqa: PLC0415
            _report_run = required_modules() is not None
            try:
                store.commit_slice(
                    "M5",
                    {"final_sections": sections},
                    "Drafted chapters to export the thesis",
                    confirm_done=_report_run,
                )
            except Exception:
                logger.exception("export_docx: persisting generated draft failed")

        # Humanize the RENDERED copy only — after the commit above, never before.
        # Persisting the rewrite would make it the new source of truth, and the
        # next export would humanize an already-humanized chapter, compounding
        # drift away from the composed text with every run.
        sections, _hum_report = _maybe_humanize(sections, humanize, language)

        try:
            # Pass the nested store so ensure_rendered weaves any missing
            # verified-state tables at export time (roadmap M5 renderer). Full
            # thesis only — the module-scoped path above deliberately does not.
            artifacts = run_export(sections, str(project_id), references=references,
                                   language=language, context_store=full_cs)
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
        # Similarity self-check (roadmap #11) — advisory, NEVER a gate: a report
        # failure must not fail an otherwise-good export. The web run drawer
        # renders this field (client wiring is a separate web change).
        _similarity = None
        try:
            from quality.similarity import similarity_report  # noqa: PLC0415
            _similarity = similarity_report(flat if isinstance(flat, dict) else {})
        except Exception:
            logger.exception("export_docx: similarity report failed (advisory)")
        # Committee-readiness certificate (roadmap #12) — advisory, NEVER a gate.
        # Deterministic + offline (include_judge=False): a failure must not fail
        # an otherwise-good export. Ships the bounded gate_summary; the full
        # certificate JSON + docx appendix are a separate web/export change.
        _certificate = None
        try:
            from quality.certificate import build_certificate, gate_summary  # noqa: PLC0415
            _cert = build_certificate(full_cs if isinstance(full_cs, dict) else {},
                                      project_id=str(project_id))
            _certificate = gate_summary(_cert)
        except Exception:
            logger.exception("export_docx: certificate build failed (advisory)")
        return json.dumps({
            "ok": True,
            "generated": generated,
            "artifacts": artifacts,
            "chapters": chapter_titles,
            "chapter_count": len(chapter_titles),
            "similarity": _similarity,
            "certificate": _certificate,
            "humanized": _hum_report,
            # Instruction to the agent, NOT user-facing copy — the agent must
            # write its OWN confirmation in the conversation's language (the
            # user got an English message parroted from here before). A download
            # card is already rendered in the chat message, so keep it short.
            "instruction": "Export succeeded. Reply with a SHORT confirmation "
                           "in the user's language (Vietnamese if they wrote in "
                           "Vietnamese). State the ACTUAL chapter_count above — do "
                           "NOT claim a number of chapters that isn't in `chapters`. "
                           "Do NOT paste chapter text. The DOCX/PDF download "
                           "buttons are already shown in your message."
                           + (" `humanized` lists per-chapter results: name the "
                              "chapters where ok=false — they were exported "
                              "UNCHANGED because the rewrite altered a number or "
                              "citation. Never claim the whole document was "
                              "rewritten." if _hum_report else ""),
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
        # Committee-readiness gate summary (roadmap #12) rides the review payload,
        # built from the SAME rubric result. Judge dims land under advisory only
        # and provably do not change any checklist status (deterministic spine).
        try:
            from quality.certificate import build_certificate, gate_summary  # noqa: PLC0415
            result = {**result, "gate_summary": gate_summary(
                build_certificate(cs, rubric=result))}
        except Exception:
            logger.exception("review_thesis: gate summary failed (advisory)")
        return json.dumps(result, ensure_ascii=False)

    @tool
    def render_verified_sections(kind: str) -> str:
        """Render a thesis section VERBATIM from the persisted, self-validated
        analysis results — so every number in Chapter 4 / the data-cleaning
        paragraph / the limitations is the computed number, never retyped.

        kind: "results_tables" (Chapter 4 measurement/discriminant/fit/path/R²
        tables), "data_cleaning" (Chapter 3 screening paragraph + summary), or
        "limitations" (Chapter 5 disclosed-weakness bullets). Returns
        {"ok": true, "markdown": ..., "kinds": [...]} — paste the markdown
        verbatim, sentinels included; write only the connective prose around it.
        Read-only, no LLM. Returns {"ok": false, "reason": "no_data"} when the
        state doesn't carry what that section needs."""
        try:
            from orchestrator.tools.results_render import (  # noqa: PLC0415
                render_cleaning_section, render_limitations, render_results_tables)
            cs = store.load_full_context_store() or {}
            ar = ((cs.get("m4_analysis") or {}).get("analysis_results")
                  if isinstance(cs.get("m4_analysis"), dict) else None)
            lang = resolve_output_language(cs)
            if kind == "results_tables":
                blocks = render_results_tables(ar, lang)
                if not blocks:
                    return json.dumps({"ok": False, "reason": "no_data"})
                return json.dumps({"ok": True, "kinds": [b["kind"] for b in blocks],
                                   "markdown": "\n\n".join(b["markdown"] for b in blocks)},
                                  ensure_ascii=False)
            if kind == "data_cleaning":
                b = render_cleaning_section(ar, lang)
                return json.dumps({"ok": True, "kinds": ["data_cleaning"], "markdown": b["markdown"]}
                                  if b else {"ok": False, "reason": "no_data"}, ensure_ascii=False)
            if kind == "limitations":
                b = render_limitations(cs, language=lang)
                return json.dumps({"ok": True, "kinds": ["limitations"], "markdown": b["markdown"]}
                                  if b else {"ok": False, "reason": "no_data"}, ensure_ascii=False)
            return json.dumps({"ok": False, "reason": f"unknown kind {kind!r}"})
        except Exception:
            logger.exception("render_verified_sections failed")
            return json.dumps({"ok": False, "reason": "no_data"})

    return [export_docx, review_thesis, render_verified_sections, humanize_text]
