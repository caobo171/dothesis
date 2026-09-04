"""LangChain tool bindings for the guarded project state.

Factory pattern (tools close over a ProjectStateStore) because the store is
per-project: the runtime builds one tool set per project/turn, while the
semantics live in agent/state.py where they're unit-tested.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

from agent.state import NON_CONTENT_KEYS, ProjectStateStore, SliceOwnershipError

# An advisor directive names a thesis chapter; map it to the DoThesis module that
# owns that chapter's work so the raised blocker lands on the right roadmap step.
_CHAPTER_TO_MODULE = {"intro": "M5", "lit_review": "M2", "methodology": "M3",
                      "results": "M4", "discussion": "M5", "conclusion": "M5"}


# Below this fraction of the stored length, a replacement for an IMPORTED
# chapter is a summary of it rather than an edit to it. Deliberately generous:
# a vi→en translation runs slightly LONGER, a heavy edit might cut a quarter,
# and the case this exists for cut 28,144 characters to 575 — two percent.
_IMPORTED_CHAPTER_MIN_RATIO = 0.5


def _protect_imported_chapters(incoming: list, stored: list) -> tuple[list, list[str]]:
    """Keep the student's imported chapter when the model tries to replace it
    with a much shorter one. Returns (sections, notes).

    An imported thesis lands its real Chapter 4 in `final_sections` — 28,144
    characters and 17 tables on the project this was written for. Nothing stopped
    the model from reading that, condensing it to a 575-character paragraph, and
    committing the condensation over the original. The student's EFA, KMO,
    correlation and regression tables were gone, and the only trace was a
    Chapter 4 that had become one paragraph.

    Only IMPORTED prose is protected (`source == "import"`, set by
    api.app.import_work._preserve_chapters and carried through compose). Prose we
    generated is ours to rewrite at any length. Matching is by chapter_name, then
    title, so a section that lost its canonical name is still covered.
    """
    if not isinstance(incoming, list) or not isinstance(stored, list):
        return incoming, []

    def _keys(sec):
        if not isinstance(sec, dict):
            return ()
        return tuple(k for k in ((sec.get("chapter_name") or "").strip().lower(),
                                 (sec.get("title") or "").strip().lower()) if k)

    guarded: dict[str, dict] = {}
    for sec in stored:
        if isinstance(sec, dict) and sec.get("source") == "import" and (sec.get("prose") or ""):
            for k in _keys(sec):
                guarded.setdefault(k, sec)
    if not guarded:
        return incoming, []

    out, notes = [], []
    for sec in incoming:
        if not isinstance(sec, dict):
            out.append(sec)
            continue
        prior = next((guarded[k] for k in _keys(sec) if k in guarded), None)
        new_len = len(sec.get("prose") or "")
        if prior is None or new_len >= len(prior["prose"]) * _IMPORTED_CHAPTER_MIN_RATIO:
            out.append(sec)
            continue
        out.append({**sec, "prose": prior["prose"], "source": "import"})
        notes.append(
            f"{sec.get('chapter_name') or sec.get('title') or 'a chapter'}: kept the "
            f"student's imported prose ({len(prior['prose'])} chars) — the version you "
            f"committed was {new_len} chars, which discards their tables and figures. "
            f"An imported chapter may be translated or extended, not summarised. If the "
            f"student explicitly asked you to shorten it, say so and edit it in place.")
    return out, notes


def chapter_to_module(chapter: str | None) -> str:
    """Which module owns a chapter's work. PUBLIC because it has a second caller
    outside this module (app.partner_run.required_modules_for decides what a
    headless run must finish for a chapter request). Reaching across for a
    leading-underscore name is a promise nobody made — the alternative was a
    second copy of the map, and two maps of the same fact drift silently."""
    return _CHAPTER_TO_MODULE.get((chapter or "").lower(), "M5")


def make_state_tools(store: ProjectStateStore, *, strict_gates: bool = False) -> list:
    """`strict_gates` (boundary hardening, gap 2): when True (headless/B2B), a
    validation/coherence gate that CANNOT RUN (crash/exception) refuses the commit
    instead of committing "unverified" — the fabrication boundary fails CLOSED
    where the gate is the product. Default False keeps interactive chat fail-open
    (a validator hiccup must never block a real thesis)."""
    @tool
    def read_slice(module: str) -> str:
        """Read a module's slice of the project context_store.

        Returns the module's owned keys plus its read-dependencies (per the
        slice map), the per-module status map, and the current focus. Reading
        is free: it never shifts focus or flags anything.

        Args:
            module: One of M1, M2, M3, M4, M5.
        """
        return json.dumps(store.read_slice(module), ensure_ascii=False)

    @tool
    def commit_slice(
        module: str,
        writes: dict[str, Any],
        reason: str,
        confirm_done: bool = False,
        status_overrides: dict[str, str] | None = None,
    ) -> str:
        """Write to a module's slice of the context_store. The ONLY write path.

        Deterministically: validates `writes` against the module's owned keys,
        snapshots the previous version, applies the writes, sets focus to the
        module, and marks finished downstream modules STALE
        (M1→M2..M5, M2→M3..M5, M3→M4,M5, M4→M5). Stale is a note that their
        content predates this edit — their status is untouched and nothing is
        blocked. Never tell the student they must go back and fix a module
        before continuing.

        Args:
            module: One of M1..M5 — the module whose slice is being written.
            writes: The slice keys to set. Must be keys the module owns.
            reason: One short sentence for the version history (shown to the user).
            confirm_done: True only on the final commit after the user confirmed
                the module's done-criteria — marks the module `done` instead of
                `in_progress`.
            status_overrides: Bootstrap only — explicit status flags for
                dependency holes (e.g. {"M2": "in_progress"}). Values must be
                one of locked / in_progress / done.

        LANGUAGE. The moment a student says which language they want the thesis
        WRITTEN in — "viết full bài này bằng tiếng Anh", "write this in
        English", "làm bằng tiếng Việt" — commit it immediately as
        M1 {"language": "en"} (or "vi"). It is the one instruction that decides
        every chapter we generate later, and a chat message does not survive the
        session. Left unset, the writer mirrors the language of their uploaded
        draft — which is wrong precisely when they asked for the other one.

        Do this even mid-conversation, even if you are working in another
        module: it is one key and it costs the student nothing to be wrong about
        later, whereas a whole thesis in the wrong language costs them a rewrite.

        COVER PAGE. M1 owns a `cover` dict for the title page: author,
        institution, faculty, department, degree, project_type, advisor,
        second_examiner, student_id, location. Record whatever the student
        mentions in passing — their name, their university, their supervisor —
        as M1 {"cover": {...}}; it merges, so you can add fields one at a time.

        NEVER invent one. A plausible-looking wrong university on a submitted
        cover page is worse than a missing line, and the exporter simply omits
        what it does not have. Before the first full export, ask once for the
        pieces you are missing — name, university, department, degree,
        supervisor — in a single question, not one at a time.
        """
        # This wrapper is the MODEL-facing edge, so strip NON_CONTENT_KEYS here
        # — the same guard import_route.py applies at the client-facing edge.
        # `decisions` is owned by every module (so both stores persist it),
        # which means commit_slice's ownership check alone would happily let the
        # model author or overwrite the trail that audits the model. An audit
        # trail is only worth something if the audited party can't write it.
        # record_decision calls store.commit_slice directly and is unaffected:
        # it's deterministic code, not the model.
        writes = {k: v for k, v in (writes or {}).items()
                  if k not in NON_CONTENT_KEYS}
        # Skill-adherence nudge (gap 3): the first commit of a module in a
        # session without a recorded read of that module's skill.
        #
        # This used to REFUSE the commit and ask the model to read the skill and
        # retry. It was meant to be invisible — nudge once, model re-runs the
        # same commit, student sees nothing. In practice the model reported it:
        # the payload was shaped as an `error`, and the nearest instruction
        # (skills/dothesis/SKILL.md, "What you do NOT do") is followed
        # immediately by "One message → one module's work → report → stop".
        # Nothing told it to retry silently. A real thread ended with the
        # student being asked to press "Xác nhận M5 hoàn tất" a second time to
        # satisfy a bookkeeping requirement, which is the opposite of the point.
        #
        # It also cannot do the job it was designed for. It fires on the first
        # COMMIT, by which time the module's work is already written — reading
        # the skill afterwards cannot change what is being committed, only what
        # comes next. So carry it on the successful result instead: the model
        # still learns to read the skill for the rest of the module, and no
        # student pays a round trip for it. Never blocks, never surfaces.
        _skill_nudge = None
        try:
            from agent.skill_tracker import should_nudge, skill_path  # noqa: PLC0415
            _pk = getattr(store, "project_dir", "")
            if should_nudge(_pk, module):
                _skill_nudge = (
                    f"You committed {module} without reading {skill_path(module)} this "
                    f"session. Read it before your next {module} step. Internal note — "
                    f"do not mention it to the student and do not re-ask them to confirm.")
        except Exception:
            logger.debug("commit_slice: skill nudge skipped", exc_info=True)
        # M3 model guard: a research model must be an explicit graph, not merely
        # a prose methodology. Valid graphs are repaired deterministically; a
        # finalize/methodology commit without one is rejected so incomplete M3
        # state cannot later render as a model-free proposal.
        _repair_note = None
        if module == "M3":
            _requires_model = confirm_done or any(
                key in writes for key in ("methodology", "hypotheses"))
            try:
                from agent.m3_contract import normalize_conceptual_model  # noqa: PLC0415
                from orchestrator.graph_guard import repair_conceptual_model  # noqa: PLC0415

                # Decision: prose-only methodology is not a complete research
                # design. Validate the merged slice because a later methodology
                # edit may legitimately rely on a model committed earlier.
                _stored_m3 = (store.load() or {}).get("contextStore", {})
                _raw_model = writes.get(
                    "conceptual_model", _stored_m3.get("conceptual_model"))
                _model, _ = normalize_conceptual_model(_raw_model)
                if _requires_model and (
                    len(_model.get("nodes") or []) < 2
                    or not (_model.get("edges") or [])
                ):
                    return json.dumps({
                        "error": "m3_model_required — methodology cannot be finalized "
                                 "without a structured conceptual model with at least "
                                 "two constructs and one relationship",
                        "hint": "Build the parsimonious model now, include explicit nodes "
                                "and edges, then retry this commit in the same turn.",
                    }, ensure_ascii=False)
                if "conceptual_model" in writes:
                    fixed, rep = repair_conceptual_model(_model)
                    writes = {**writes, "conceptual_model": fixed}
                    if rep.get("repaired"):
                        _repair_note = rep
            except Exception as exc:
                logger.debug("commit_slice: M3 model guard skipped", exc_info=True)
                if _requires_model:
                    return json.dumps({
                        "error": "m3_model_invalid — the conceptual model could not "
                                 "be normalized into constructs and relationships",
                        "hint": f"Rebuild the model with explicit nodes and edges, then "
                                f"retry this commit in the same turn ({type(exc).__name__}).",
                    }, ensure_ascii=False)
        # M4 stats self-validation gate (deterministic, fail-open). Hard findings
        # — numbers that are mathematically impossible or self-contradictory —
        # block the commit so a wrong number never becomes product state. Soft
        # findings never block; they ride the success payload as warnings the
        # agent must acknowledge. A validator crash fails open (commit proceeds,
        # marked unverified). See design §7.4.
        _stats_warnings = None
        if module == "M4" and "analysis_results" in writes:
            try:
                from agent.stats_validation import validate_analysis_results  # noqa: PLC0415
                try:
                    _m3 = (store.load() or {}).get("contextStore", {}).get("hypotheses")
                except Exception:
                    _m3 = None
                _v = validate_analysis_results(writes["analysis_results"], _m3)
                if _v.get("crashed"):
                    if strict_gates:
                        return json.dumps({
                            "error": "stats_gate_unavailable — the numbers could not be verified "
                                     "(the validator did not run) and this run requires verification "
                                     "before committing analysis results.",
                            "hint": "Retry; if it persists, the analysis results cannot be attested.",
                        }, ensure_ascii=False)
                    _stats_warnings = "unavailable"
                elif _v["hard"]:
                    return json.dumps({
                        "error": "stats_validation_failed — these numbers are mathematically "
                                 "impossible or self-contradictory and cannot be committed",
                        "findings": _v["findings_hard"],
                        "hint": "Re-run the analysis, fix the parsed/typed values, or drop the "
                                "impossible entries. Explain the finding to the student in both registers.",
                    }, ensure_ascii=False)
                elif _v["soft"]:
                    _stats_warnings = _v["findings_soft"]
            except Exception:
                logger.debug("commit_slice: M4 stats validation skipped", exc_info=True)
                if strict_gates:
                    return json.dumps({
                        "error": "stats_gate_unavailable — the numbers could not be verified "
                                 "(the validator raised) and this run requires verification before "
                                 "committing analysis results.",
                        "hint": "Retry; if it persists, the analysis results cannot be attested.",
                    }, ensure_ascii=False)
                _stats_warnings = "unavailable"
        # Imported-chapter shrink guard. Runs BEFORE coherence so the checked
        # prose is the prose that will actually be stored. Deterministic, never
        # blocks: it substitutes the student's own text back in and tells the
        # model what it did.
        _kept_imported = None
        if module == "M5" and isinstance(writes.get("final_sections"), list):
            try:
                _stored = (store.load() or {}).get("contextStore", {}).get("final_sections") or []
                _fixed, _notes = _protect_imported_chapters(writes["final_sections"], _stored)
                if _notes:
                    writes = {**writes, "final_sections": _fixed}
                    _kept_imported = _notes
            except Exception:
                logger.debug("commit_slice: imported-chapter guard skipped", exc_info=True)
        # Coherence (M3↔M4↔M5). M4: advisory direction check only (no prose yet).
        # M5: a prose number contradicting the persisted analysis_results HARD-
        # blocks (the single source of truth already passed the M4 gate); soft
        # findings ride the payload. Fail-open. See design §7.2-7.3.
        _coherence_warnings = None
        if module == "M4" and "analysis_results" in writes:
            try:
                from agent.coherence import m4_commit_findings  # noqa: PLC0415
                _flat = (store.load() or {}).get("contextStore", {})
                _cv = m4_commit_findings(writes["analysis_results"], _flat)
                if _cv.get("soft"):
                    _coherence_warnings = _cv["findings_soft"]
            except Exception:
                logger.debug("commit_slice: M4 coherence advisory skipped", exc_info=True)
        elif module == "M5" and "final_sections" in writes:
            try:
                from agent.coherence import validate_m5_sections  # noqa: PLC0415
                _flat = (store.load() or {}).get("contextStore", {})
                _cv = validate_m5_sections(writes["final_sections"], _flat)
                if _cv.get("crashed"):
                    if strict_gates:
                        return json.dumps({
                            "error": "coherence_gate_unavailable — the chapter prose could not be "
                                     "checked against the persisted results (the gate did not run) and "
                                     "this run requires the check before committing final sections.",
                            "hint": "Retry; if it persists, the sections cannot be attested.",
                        }, ensure_ascii=False)
                    _coherence_warnings = "unavailable"
                elif _cv["hard"]:
                    return json.dumps({
                        "error": "coherence_failed — this prose quotes statistics that contradict the "
                                 "persisted analysis_results and cannot be committed",
                        "findings": _cv["findings_hard"],
                        "hint": "Quote the persisted value exactly (re-read the M4 slice), or recommit M4 "
                                "if the analysis changed. Never adjust the prose number to something in "
                                "between. Explain in both registers.",
                    }, ensure_ascii=False)
                elif _cv["soft"]:
                    _coherence_warnings = _cv["findings_soft"]
            except Exception:
                logger.debug("commit_slice: M5 coherence gate skipped", exc_info=True)
                if strict_gates:
                    return json.dumps({
                        "error": "coherence_gate_unavailable — the chapter prose could not be checked "
                                 "against the persisted results (the gate raised) and this run requires "
                                 "the check before committing final sections.",
                        "hint": "Retry; if it persists, the sections cannot be attested.",
                    }, ensure_ascii=False)
                _coherence_warnings = "unavailable"
        # Provenance injection (roadmap #12): after the model-edge strip (so a
        # forged analysis_provenance is already gone) and after the hard gate (so
        # only committable numbers are attributed), deterministic code matches the
        # committed numbers against the stats ledger and writes the summary. The
        # model can never author it; the matcher only upgrades tiers. Fail-open.
        if module == "M4" and "analysis_results" in writes:
            try:
                from agent.provenance import load_ledger_rows, match_claims  # noqa: PLC0415
                from agent.stats_validation import claims_from_analysis_results  # noqa: PLC0415
                _pdir = getattr(store, "project_dir", None)
                if _pdir:
                    _rows = load_ledger_rows(str(_pdir))
                    _summary = match_claims(
                        claims_from_analysis_results(writes["analysis_results"]), _rows)
                    from datetime import datetime, timezone  # noqa: PLC0415
                    _summary["captured_at"] = datetime.now(timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%SZ")
                    _summary["numbers"] = _summary.pop("coverage")
                    # Attest whether the verification gate actually RAN (gap 2) so
                    # the certificate can say "all gates ran", not just "no gate
                    # failed". In strict mode an unavailable gate already refused
                    # above, so reaching here means it ran.
                    _summary["gate"] = {
                        "stats_validation": "unavailable" if _stats_warnings == "unavailable" else "ran",
                        "policy": "strict" if strict_gates else "advisory"}
                    writes = {**writes, "analysis_provenance": _summary}
            except Exception:
                logger.debug("commit_slice: provenance injection skipped", exc_info=True)
        try:
            result = store.commit_slice(
                module, writes, reason,
                confirm_done=confirm_done,
                status_overrides=status_overrides,
            )
        except (SliceOwnershipError, ValueError) as e:
            # Surface the violation to the model so it can correct course —
            # a raise would abort the whole turn instead of one tool call.
            return json.dumps({"error": str(e)})
        if _repair_note is not None and isinstance(result, dict):
            result = {**result, "conceptual_model_repaired": _repair_note}
        if _stats_warnings is not None and isinstance(result, dict):
            key = "stats_validation" if _stats_warnings == "unavailable" else "stats_validation_warnings"
            result = {**result, key: _stats_warnings}
        if _coherence_warnings is not None and isinstance(result, dict):
            key = "coherence" if _coherence_warnings == "unavailable" else "coherence_warnings"
            result = {**result, key: _coherence_warnings}
        # A module can be `done` by two different definitions and nobody says so.
        #
        # commit_slice's own gate is _has_done_content: any one owned earning key
        # is enough. The DoD in orchestrator/artifacts.py is far stricter — M2
        # wants a synthesis, a framework, a Chapter 2 draft, a gap and a citation
        # — and it is the definition the backfill, the roadmap and the export
        # readiness check all use. So chat could mark M2 done on research_gaps
        # alone and the student would meet the strict definition later, as a
        # refusal, with no idea the two ever disagreed.
        #
        # Both gates stay as they are: tightening the interactive one would stall
        # students mid-flow, and loosening the DoD would let a hollow module
        # through to the export. What was missing is anyone SAYING it. Advisory,
        # on success only.
        if confirm_done and isinstance(result, dict):
            try:
                from orchestrator.artifacts import MODULE_TO_ARTIFACT, gate_for  # noqa: PLC0415
                artifact = MODULE_TO_ARTIFACT.get(module)
                if artifact:
                    _flat = (store.load() or {}).get("contextStore", {})
                    _dod = gate_for(artifact)(_flat)
                    if not _dod.done:
                        result = {**result, "done_but_incomplete": _dod.gaps}
            except Exception:
                logger.debug("commit_slice: DoD advisory skipped", exc_info=True)
        if _kept_imported is not None and isinstance(result, dict):
            result = {**result, "imported_chapters_kept": _kept_imported}
        if _skill_nudge is not None and isinstance(result, dict):
            result = {**result, "skill_reminder": _skill_nudge}
        return json.dumps(result, ensure_ascii=False)

    @tool
    def flag_blocker(module: str, substep: str, title: str, why: str) -> str:
        """Record a student-specific blocker under a roadmap sub-step (e.g. a
        failed discriminant-validity check). Use ONLY for a concrete obstacle
        that must be cleared before the student can proceed — not for normal
        steps. Does NOT change module status. Returns the stored task (with id).
        """
        task = store.upsert_roadmap_task(
            {"module": module, "substep": substep, "title": title, "why": why, "status": "open"})
        return json.dumps(task, ensure_ascii=False)

    @tool
    def resolve_blocker(task_id: str) -> str:
        """Mark a previously flagged blocker resolved once the student fixed it."""
        return json.dumps({"resolved": store.resolve_roadmap_task(task_id)}, ensure_ascii=False)

    @tool
    def ingest_advisor_feedback(feedback_text: str) -> str:
        """Record a thesis supervisor's feedback. Extracts each requested change into a
        tracked directive, persists it, and raises a roadmap blocker per open item so the
        student is led to address it. Use whenever the user pastes/relays professor comments.
        """
        from agent.feedback import extract_directives  # noqa: PLC0415
        directives = extract_directives(feedback_text)
        added = 0
        for d in directives:
            stored = store.upsert_advisor_feedback(d)
            # Each open directive becomes a blocker (F2), linked by feedback_id so
            # mark_feedback_addressed can clear exactly the right one.
            store.upsert_roadmap_task({
                "module": chapter_to_module(stored.get("chapter")),
                "substep": "", "title": f"Advisor: {stored.get('issue')}",
                "why": stored.get("required_change") or "Address this advisor comment.",
                "status": "open", "feedback_id": stored["id"]})
            added += 1
        # F5: advisor-loop signal — how many directives were captured this turn.
        from agent.analytics import emit  # noqa: PLC0415 — no-op until app wires it
        emit("advisor_feedback_ingested", None, {"count": added})
        return json.dumps({"added": added}, ensure_ascii=False)

    @tool
    def mark_feedback_addressed(feedback_id: str) -> str:
        """Mark an advisor directive addressed once the revision is done; clears its blocker."""
        ok = store.mark_advisor_feedback_addressed(feedback_id)
        for t in (store.load()["contextStore"].get("roadmap_tasks") or []):
            if t.get("feedback_id") == feedback_id:
                store.resolve_roadmap_task(t["id"])
        # When every directive is now addressed, distill recurring themes into
        # cross-project memory (F0 correction: trigger lives here). Best-effort via
        # the app-wired hook — the agent layer must not import app.user_memory.
        fb = store.load()["contextStore"].get("advisor_feedback") or []
        if fb and all(d.get("status") == "addressed" for d in fb):
            try:
                from agent.memory_hook import distill_advisor_themes  # noqa: PLC0415
                distill_advisor_themes(store, fb)
            except Exception:
                pass  # distillation is a nicety; never break the turn
        # F5: advisor-loop signal — the "addressed" side of ingested-vs-addressed.
        from agent.analytics import emit  # noqa: PLC0415 — no-op until app wires it
        emit("advisor_feedback_addressed", None, {})
        return json.dumps({"addressed": ok}, ensure_ascii=False)

    @tool
    def set_defense_date(defense_date: str) -> str:
        """Record the student's target defense/submission date (YYYY-MM-DD) and build a
        realistic backwards timeline (M1->defense) they can pace against. Reads the
        project's chosen method and planned sample size to size data collection."""
        from datetime import date  # noqa: PLC0415

        from agent.timeline import build_timeline  # noqa: PLC0415

        # Read the project's LIVE FLAT contextStore (F0 correction: the store's
        # load() returns flat keys — methodology, sample_plan — NOT the nested
        # m3_design shape the plan literal assumed; reading m3_design here would
        # always miss and silently fall back to defaults, never reaching
        # build_timeline with the real data). Mirrors make_sampling_plan_tool.
        cs = (store.load() or {}).get("contextStore") or {}
        method = cs.get("methodology") or "regression"
        target_n = (cs.get("sample_plan") or {}).get("target_n") or 200
        tl = build_timeline(date.fromisoformat(defense_date), method, target_n, date.today())
        # Persist via the dedicated coaching path — never commit_slice (a
        # calendar is not a module design decision).
        store.set_thesis_timeline(tl)
        return json.dumps(tl, ensure_ascii=False)

    return [read_slice, commit_slice, flag_blocker, resolve_blocker,
            ingest_advisor_feedback, mark_feedback_addressed, set_defense_date]
