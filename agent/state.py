"""ProjectStateStore — the guarded `context_store` behind read_slice/commit_slice.

This is the v3 architecture's enforcement point for the v2 brief's principles
(docs/architecture/2026-06-10-deepagent-skills-architecture.md §3): the agent is
free-roaming, but state changes are deterministic code — ownership validation,
version snapshot, focus shift, downstream needs_review propagation.

Scope: the store is **per project, not per thread**. Every chat session in a
project shares one context_store; the spike backs it with a JSON file in the
project directory, and the api integration swaps the load/save pair for the
projects.context_store JSONB column without touching the semantics.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODULES = ["M1", "M2", "M3", "M4", "M5"]

# Which context_store keys each module may write. Mirrors the slice map in
# skills/dothesis/SKILL.md — keep the two in sync.
SLICE_OWNERSHIP: dict[str, list[str]] = {
    # Topic-framing keys added for partner seeding + richer M1 commits: the
    # chapter composers read language/field/objectives/… from the m1_topic
    # column, and DbProjectStateStore only persists OWNED keys — without
    # ownership a partner-supplied framing would silently die before prod
    # (project_db_store_persistence_gap). Same mechanism as field_it_* in M4.
    # `user_context` is DELIBERATELY absent from SKILL.md's slice map, same
    # reasoning as `decisions` below: it holds what the USER (or partner) said
    # they want, so it must be writable by the seeding code but never advertised
    # to the model — an agent that can rewrite the steering input it is steered
    # by can talk itself into any brief. Don't "fix" that divergence either.
    "M1": ["research_title", "research_questions", "decisions",
           "language", "field", "research_type", "objectives",
           "target_population", "scope", "user_context",
           # advisory early sample-size/operationalizability estimate (vision
           # §3.1); advertised in the skill slice map, unlike `decisions`.
           "feasibility"],
    "M2": ["literature_sources", "research_gaps", "decisions"],
    # sample_plan / cmb_plan / missing_data_plan added for the F8 methods
    # pre-flight: commit_slice must be able to WRITE them (they're M3 design
    # decisions), and preflight_check reads them to gate M3->M4 readiness.
    "M3": ["conceptual_model", "hypotheses", "methodology", "instrument",
           "sample_plan", "cmb_plan", "missing_data_plan", "decisions"],
    # field_it_* added for F7 results ingestion: fielded survey responses +
    # quality flags land in M4 (where F8's Output Sanity Layer reads). Making
    # them M4-owned is what lets DbProjectStateStore._save persist them into the
    # m4_analysis column automatically — the same mechanism as analysis_results,
    # so there is no Db-specific write path to forget (project_db_store_persistence_gap).
    "M4": ["analysis_outline", "analysis_results",
           "field_it_collection_id", "field_it_responses", "field_it_quality",
           "analysis_provenance", "decisions"],
    "M5": ["final_sections", "decisions"],
}
# "decisions" (headless auto-decision audit trail, convergence spec §4) is
# owned by EVERY module: the runner records each choice under whichever module
# is in focus, and riding the slice map is what makes DbProjectStateStore
# persist it with no store-specific code — the same mechanism as field_it_*.
# The flat load() view holds ONE decisions list; _save mirrors it into every
# module column, so the five copies are redundant but always identical. That
# redundancy was accepted over a new top-level key, which would round-trip in
# file-store tests and silently VANISH in prod (the known CRITICAL gap).
# DELIBERATELY absent from SKILL.md's slice map despite the "keep in sync" note
# above: that map tells the AGENT what it may write, and `decisions` is written
# only by record_decision (deterministic code). Listing it would invite the model
# to author its own audit trail — the trail is only worth anything if the thing
# being audited can't write it. Don't "fix" the divergence.

# Which modules each module may additionally READ (context dependencies).
READS: dict[str, list[str]] = {
    "M1": [],
    "M2": ["M1"],
    "M3": ["M1", "M2"],
    "M4": ["M3"],
    "M5": ["M1", "M2", "M3", "M4"],
}

# Mutating a module flags these downstream modules for review.
DOWNSTREAM: dict[str, list[str]] = {
    "M1": ["M2", "M3", "M4", "M5"],
    "M2": ["M3", "M4", "M5"],
    "M3": ["M4", "M5"],
    "M4": ["M5"],
    "M5": [],
}

# Owned keys that are OUTPUT PREFERENCES, not research decisions.
#
# `language` lives on M1 only because M1 owns the key (agent/tools/writing.py's
# resolve_output_language reads m1_topic.language). What it actually controls is
# how M5 renders the document — "write this thesis in English" changes the
# output language, it does not change the literature, the design or the
# analysis. Writing one of these must therefore NOT propagate needs_review
# downstream; see the guard in commit_slice.
PREFERENCE_KEYS = frozenset({"language"})

# Owned keys that are BOOKKEEPING, not module output. They're in
# SLICE_OWNERSHIP so commit_slice can write them and both stores persist them,
# but they must never count as "this module produced something" — otherwise a
# module with nothing behind it passes the strict done-gate below the moment an
# audit row is appended, which is exactly the hallucinated-completion the gate
# exists to catch (and headless records a decision under every module it
# touches, so every module would become done-eligible while empty).
NON_CONTENT_KEYS = {"decisions", "analysis_provenance"}

# Owned, persisted, and VISIBLE — but caller-supplied INPUTS (locale, steering
# notes), never module output. Distinct from NON_CONTENT_KEYS, which are ALSO
# hidden from the model: the agent must SEE the language it writes in (the
# composers and the M5 auto-export read it) and the notes it is steered by; it
# just must not be able to cash them in for a `done`. Without this split,
# partner seeding — which sets a language on EVERY project at creation — would
# make every project M1-done-eligible on a 2-letter locale code, and under
# headless budget pressure the done-gate is the only thing between a stalling
# run and five hollow-green modules. Done must be earned, not narrated.
NON_EARNING_KEYS = {"language", "user_context"}

# Keep history bounded — old snapshots beyond this are dropped oldest-first.
# 50 commits ≈ a full thesis project's worth of confirmed decisions.
VERSION_HISTORY_CAP = 50

STATE_FILENAME = "context_store.json"

# Project-scoped coaching/memory keys that live OUTSIDE the module slice map.
# Persisted by DbProjectStateStore in the `coaching` JSONB column (see
# project_db_store_persistence_gap memory). Written via dedicated store paths,
# never commit_slice — commit_slice's ownership check is module-scoped and
# would reject them.
# NOTE: field-it results are NOT here — F7 writes them into the m4_analysis
# module column (where F8 reads), so they persist via normal ownership.
COACHING_KEYS = {"roadmap_tasks", "advisor_feedback", "institution_profile",
                 "thesis_timeline"}


def strip_reconstruction_meta(slice_: dict[str, Any] | None) -> dict[str, Any]:
    """Drop everything a reconstructed candidate carries that is NOT content.

    `_`-markers (`_source`) are the reconstructor's own bookkeeping and are
    re-applied at the write site; `confirmed_at` is the store's to set, never
    the caller's to claim; NON_CONTENT_KEYS (`decisions`,
    `analysis_provenance`) are the audit trail that exists to be trustworthy —
    a caller that could write them could forge it.

    Shared by the store's write path and the client-facing confirm endpoint so
    the two can't drift on what counts as content.
    """
    return {k: v for k, v in (slice_ or {}).items()
            if not str(k).startswith("_")
            and k != "confirmed_at"
            and k not in NON_CONTENT_KEYS}


def _earning_keys(module: str) -> list[str]:
    """The module's owned keys that can actually EARN a `done`.

    One definition shared by the gate and the gate's error message: the message
    exists to tell the agent how to pass the gate, so anything that drifts
    between the two is a lie the agent will act on.
    """
    return [k for k in SLICE_OWNERSHIP[module]
            if k not in NON_CONTENT_KEYS and k not in NON_EARNING_KEYS]


class SliceOwnershipError(ValueError):
    """A commit tried to write keys outside the module's owned slice."""


def _empty_state() -> dict[str, Any]:
    return {
        "status": {m: "locked" for m in MODULES},
        "focus": None,
        "contextStore": {},
        "versionHistory": [],
    }


def _dod_satisfied(module: str, context_store: dict) -> bool:
    """True when `module`'s definition-of-done is met by the content present.

    The context_store here is FLAT (every module's keys in one dict) while the
    DoD validators take a single module's slice, so the module's own keys are
    projected out first. Best-effort by construction: a missing validator or any
    failure means "not done", which is the safe direction — it can only leave a
    module in_progress, never claim work that was not done.
    """
    try:
        from orchestrator.state import dod_for_module  # noqa: PLC0415
    except Exception:
        return False
    dod = dod_for_module(module)
    if dod is None:
        return False
    keys = SLICE_OWNERSHIP.get(module, [])
    slice_ = {k: context_store[k] for k in keys if k in context_store}
    # M5's chapters live under keys the ownership map does not list (they are
    # written by the editor route, not commit_slice), so pass those through too.
    if module == "M5":
        for extra in ("chapters",):
            if extra in context_store:
                slice_[extra] = context_store[extra]
    try:
        return bool(dod(slice_).done)
    except Exception:
        return False


class ProjectStateStore:
    def __init__(self, project_dir: str | Path):
        self.project_dir = Path(project_dir)
        self.path = self.project_dir / STATE_FILENAME

    # -- persistence -------------------------------------------------------

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> dict[str, Any]:
        if not self.exists():
            return _empty_state()
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, state: dict[str, Any]) -> None:
        self.project_dir.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: temp file + replace, so a crash mid-write never
        # leaves a truncated store (it's the single source of truth).
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # -- coaching reads ------------------------------------------------------
    # Typed getters for the COACHING_KEYS (outside the M1-M5 slice map, see
    # note above). Consumers (e.g. F3's review_thesis) must read through
    # these instead of `getattr(store, "institution_profile", ...)` — that
    # pattern reads an attribute that is never set on the store and always
    # silently returns the default, which is the bug this fixes.
    def _cs(self) -> dict:
        return self.load().get("contextStore") or {}

    def get_institution_profile(self) -> dict:
        return self._cs().get("institution_profile") or {}

    def get_advisor_feedback(self) -> list:
        return self._cs().get("advisor_feedback") or []

    def get_roadmap_tasks(self) -> list:
        return self._cs().get("roadmap_tasks") or []

    def get_thesis_timeline(self) -> dict:
        return self._cs().get("thesis_timeline") or {}

    # -- reads -------------------------------------------------------------

    def read_slice(self, module: str) -> dict[str, Any]:
        """The module's owned slice + its read-dependencies + bookkeeping.

        Reading is free: no focus shift, no flags, no version entry.
        """
        _validate_module(module)
        if not self.exists():
            return {"exists": False, "module": module}
        state = self.load()
        # NON_CONTENT_KEYS stay out of the visible set: read_slice's result is
        # injected into the model's context on every read (for this module AND
        # each read-dependency), and the audit trail only grows — paying that
        # context cost buys the model nothing it can act on. It also keeps the
        # trail out of reach of the thing being audited, which is the point of
        # having one.
        visible_keys: list[str] = [k for k in SLICE_OWNERSHIP[module]
                                   if k not in NON_CONTENT_KEYS]
        for dep in READS[module]:
            visible_keys.extend(k for k in SLICE_OWNERSHIP[dep]
                                if k not in NON_CONTENT_KEYS)
        slices = {
            k: v for k, v in state["contextStore"].items() if k in visible_keys
        }
        return {
            "exists": True,
            "module": module,
            "slices": slices,
            "status": state["status"],
            "focus": state["focus"],
        }

    # -- mutations ---------------------------------------------------------

    def _has_done_content(self, module: str, context_store: dict[str, Any]) -> bool:
        """True when `module` has produced enough to be marked done.

        Baseline: at least one of the module's owned EARNING keys is non-empty
        (NON_CONTENT_KEYS are audit bookkeeping and NON_EARNING_KEYS are
        caller-supplied inputs — neither is evidence the module did any work).
        M5 is special — the finished chapters can live in the m5_writing
        column (auto-draft path) rather than the owned `final_sections` key,
        so we also accept chapters when the store exposes the full view. A
        read failure there errs open (we don't block a done on a flaky read).
        """
        content_keys = _earning_keys(module)
        if any(context_store.get(k) for k in content_keys):
            return True
        if module == "M5":
            loader = getattr(self, "load_full_context_store", None)
            if loader is None:
                return False
            try:
                chapters = (loader().get("m5_writing") or {}).get("chapters") or {}
            except Exception:
                return True
            return bool(chapters)
        return False

    def commit_slice(
        self,
        module: str,
        writes: dict[str, Any],
        reason: str,
        confirm_done: bool = False,
        status_overrides: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """The ONLY write path. Validates ownership, snapshots, applies,
        shifts focus, and propagates needs_review downstream.
        """
        _validate_module(module)
        if not writes and not confirm_done and not status_overrides:
            raise ValueError("commit_slice called with nothing to do")

        illegal = sorted(set(writes) - set(SLICE_OWNERSHIP[module]))
        if illegal:
            raise SliceOwnershipError(
                f"{module} does not own {illegal}; it owns {SLICE_OWNERSHIP[module]}"
            )

        state = self.load()

        # Strict done-gate: "done" must be earned, not narrated. A module can
        # only be marked done if it has actually produced its owned output —
        # otherwise the agent could flip a module green with nothing behind it
        # (the chat-says-done / state-says-needs_review drift). We check the
        # POST-write slice so a single commit that both writes and confirms is
        # fine. Intentionally lenient (owned slice non-empty, not per-key) so
        # bootstrap imports and qualitative designs that legitimately skip some
        # keys aren't blocked. Empty-done is rejected wholesale, with a message
        # telling the agent to commit progress first.
        if confirm_done and not self._has_done_content(module, {**state["contextStore"], **writes}):
            # List only EARNING keys: this message tells the agent what to commit
            # to earn the done, and neither audit bookkeeping nor caller-supplied
            # inputs satisfy the gate — advertising them would send it down a
            # route that can't work. Same filter as the gate itself, by
            # construction, so the two can't drift apart.
            owned = _earning_keys(module)
            raise ValueError(
                f"cannot mark {module} done: its slice is empty (owns {owned}). "
                f"Commit the module's content first with confirm_done=False, "
                f"then mark it done once there is something to show."
            )

        # Snapshot BEFORE applying — history answers "what did we change away
        # from", which is what an undo/review needs.
        state["versionHistory"].append({
            "ts": datetime.now(timezone.utc).isoformat(),
            "module": module,
            "reason": reason,
            "contextStore": dict(state["contextStore"]),
            "status": dict(state["status"]),
        })
        state["versionHistory"] = state["versionHistory"][-VERSION_HISTORY_CAP:]

        state["contextStore"].update(writes)
        state["focus"] = module
        # Status came from the confirm_done FLAG alone, so a module could be
        # demonstrably finished and still read in_progress forever. An imported
        # thesis is the case that exposed it: M4 satisfies dod_analysis the
        # moment the document lands, compute_status_map said "done", this said
        # "in_progress", and the UI reads THIS one — so the student was asked to
        # redo work the rest of the system agreed was complete.
        #
        # The flag still wins when set (it is the student's own sign-off, and
        # M1/M2/M3 carry DoDs that a conversational commit may not satisfy yet).
        # Absent it, the evidence decides.
        #
        # `was_done` stops a module FLAPPING BACK. Reading the evidence fixed
        # the "finished but reads in_progress" half and introduced the other
        # half: any later write to an already-done module re-ran the DoD, so an
        # imperfect-but-approved slice was demoted. Real case — the import
        # moves chapter 5 out of M4, that re-commit re-graded the trimmed M4,
        # and a done module the student had signed off went back to
        # in_progress with nothing about their work having changed.
        #
        # This mirrors compute_status_map, which has always held confirmed_at
        # authoritative ON TOP of the DoD "so a user-approved imperfect slice
        # doesn't flap back to in_progress" — the two disagreed, and the UI
        # reads this one. Invalidation has its own channel (needs_review); it
        # must not arrive disguised as in_progress.
        was_done = state["status"].get(module) == "done"
        state["status"][module] = (
            "done" if (confirm_done or was_done
                       or _dod_satisfied(module, state["contextStore"]))
            else "in_progress")

        # Flag only modules that have been started (or finished). Flagging an
        # untouched `locked` module is noise — there is nothing to re-review.
        # Bootstrap-style dependency holes are flagged explicitly via
        # status_overrides instead.
        overrides = status_overrides or {}
        flagged: list[str] = []
        # A write of nothing but OUTPUT PREFERENCES invalidates nothing.
        #
        # `language` is stored on M1 because M1 owns the key, but it is not a
        # research decision — it is how M5 renders the document. Saying "viết
        # bài này bằng tiếng Anh" was landing as a commit_slice on M1, which
        # flagged M2/M3/M4/M5 as needs_review and told a student whose thesis
        # had just been fully reconstructed that all four modules needed
        # re-reviewing. Nothing about their literature, design or analysis
        # changed; only the language the draft comes out in.
        #
        # Same principle as roadmap_tasks bypassing this path entirely: a
        # preference must never move the module state machine. Kept as a
        # key-set test rather than a new write path so it holds no matter which
        # tool the agent reaches for.
        if writes and set(writes).issubset(PREFERENCE_KEYS):
            pass
        else:
            for down in DOWNSTREAM[module]:
                if state["status"][down] != "locked":
                    state["status"][down] = "needs_review"
                    flagged.append(down)

        for mod, st in overrides.items():
            _validate_module(mod)
            state["status"][mod] = st

        # `flagged` is a REPORT of what this commit left at needs_review, not of
        # what the pass above proposed — status_overrides run after it and win.
        # Callers treat the list as the "a late upstream edit invalidated
        # finished work" signal (api/app/agent_state.py emits an analytics event
        # off it), so a module the overrides pinned back was never invalidated
        # and must not appear. Without this, record_decision — which snapshots
        # every status precisely so nothing moves — would report a false
        # invalidation on every single headless auto-decision.
        flagged = [m for m in flagged if m not in overrides]

        self._save(state)
        return {
            "module": module,
            "focus": state["focus"],
            "status": state["status"],
            "flagged": flagged,
            "version": len(state["versionHistory"]),
        }

    # -- reconstructed upstream modules -----------------------------------
    # Backfill (mid-journey import + the in-chat backfill tool) writes through
    # HERE rather than each caller assembling its own commit. It used to be a
    # student-facing confirm/skip card: the candidate sat unsaved until someone
    # clicked Confirm on every module. That gate is gone — a reconstruction is
    # saved the moment it exists, and the student changes it by asking, the
    # same way they change anything else in the thread. One write path also
    # means the headless/partner surfaces get the persistence the chat widget
    # used to be solely responsible for triggering.
    def commit_reconstructed(
        self,
        module: str,
        slice_: dict[str, Any],
        reason: str = "reconstructed from existing work",
    ) -> dict[str, Any]:
        """Commit a reconstructed candidate as EARNED, DONE state.

        `done`, not `in_progress`: the student's own work is what was
        reconstructed FROM, so treating it as an unfinished step drags them
        back through milestones they already passed. Downstream modules that
        had already started keep their status (an upstream backfill did not
        invalidate them), and focus moves forward to whatever is still unfinished
        (see _advance_focus).

        A reconstruction too thin to satisfy commit_slice's done-gate lands
        `in_progress` instead of failing — a partial backfill is still worth
        keeping, it just hasn't earned the tick.

        Only the module's OWNED keys survive here; the base store has nowhere
        else to put the rest. DbProjectStateStore overrides this to persist
        the non-owned schema fields too (project_db_store_persistence_gap).
        """
        _validate_module(module)
        clean = strip_reconstruction_meta(slice_)
        owned = {k: v for k, v in clean.items() if k in SLICE_OWNERSHIP[module]}

        state = self.load()
        # Read focus BEFORE committing: commit_slice parks focus on the module
        # it just wrote, so by the time we advance it the "where the student
        # was" signal is already gone.
        prev_focus = state["focus"]
        # Preserve, don't flag: a module the student already started is not
        # invalidated by filling in a step BELOW it.
        overrides = {d: state["status"][d] for d in DOWNSTREAM[module]
                     if state["status"].get(d) not in (None, "locked")}
        try:
            self.commit_slice(module, owned, reason=reason,
                              confirm_done=True, status_overrides=overrides)
            status = "done"
        except ValueError as e:
            if "cannot mark" not in str(e):
                raise
            # Nothing owned to show for it. Keep what we have, at in_progress —
            # status_overrides carries the commit so an empty `owned` doesn't
            # trip commit_slice's "nothing to do" guard.
            self.commit_slice(module, owned, reason=reason,
                              status_overrides={**overrides, module: "in_progress"})
            status = "in_progress"
        return {"module": module, "status": status,
                "focus": self._advance_focus(prev_focus)}

    def _advance_focus(self, prev_focus: str | None = None) -> str:
        """Move focus to the first module that isn't done — FORWARDS only.

        commit_slice parks focus on whatever it just wrote, which for a backfill
        is the wrong place: reconstructing M1 must not send a student who is
        mid-M4 back to the topic screen. But "first not done" alone has the same
        failure from the other side — backfilling only M3 while M1 is still
        empty would point them at M1.

        So the focus never regresses. It advances when a backfill genuinely
        completed the steps in front of the student (import M4, reconstruct
        M1-M3 → focus lands on M4 instead of sitting at M1), and otherwise
        stays where they were.
        """
        state = self.load()
        first_open = next((m for m in MODULES if state["status"].get(m) != "done"),
                          MODULES[-1])
        prev = prev_focus if prev_focus in MODULES else state["focus"]
        if prev not in MODULES:                       # fresh project: no focus yet
            prev = MODULES[0]
        focus = max(prev, first_open, key=MODULES.index)
        if state["focus"] != focus:
            state["focus"] = focus
            self._save(state)
        return focus

    # -- roadmap_tasks (coaching blockers) --------------------------------
    # Deliberately NOT commit_slice: blockers are ephemeral coaching aids, so
    # writing one must never shift focus, change module status, propagate
    # needs_review, or add a version snapshot. This keeps the module state
    # machine pristine while still funneling writes through the store.
    # roadmap_tasks is a COACHING_KEYS member, so DbProjectStateStore already
    # round-trips it (see F0 / project_db_store_persistence_gap).
    def upsert_roadmap_task(self, task: dict[str, Any]) -> dict[str, Any]:
        """Add or replace a blocker (by id). Only touches roadmap_tasks."""
        import uuid as _uuid
        state = self.load()
        tasks = list(state["contextStore"].get("roadmap_tasks") or [])
        stored = {**task}
        stored.setdefault("id", _uuid.uuid4().hex)
        stored.setdefault("status", "open")
        tasks = [t for t in tasks if t.get("id") != stored["id"]] + [stored]
        state["contextStore"]["roadmap_tasks"] = tasks
        self._save(state)
        return stored

    def resolve_roadmap_task(self, task_id: str) -> bool:
        """Flip a blocker to done. Returns False if the id wasn't found."""
        state = self.load()
        tasks = state["contextStore"].get("roadmap_tasks") or []
        hit = False
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = "done"
                hit = True
        if hit:
            self._save(state)
        return hit

    # -- cross-session memory (per-project) -------------------------------
    # Same rationale as roadmap_tasks: durable per-project data (advisor
    # directives, institution profile) that must NOT move module status/focus/
    # history, so it bypasses commit_slice. Both keys are COACHING_KEYS members,
    # so DbProjectStateStore already round-trips them (F0).
    def upsert_advisor_feedback(self, directive: dict[str, Any]) -> dict[str, Any]:
        """Add or update an advisor directive by id. Only touches advisor_feedback."""
        import uuid as _uuid
        state = self.load()
        items = list(state["contextStore"].get("advisor_feedback") or [])
        stored = {**directive}
        stored.setdefault("id", _uuid.uuid4().hex)
        stored.setdefault("status", "open")
        stored.setdefault("source", "professor")
        stored.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        items = [d for d in items if d.get("id") != stored["id"]] + [stored]
        state["contextStore"]["advisor_feedback"] = items
        self._save(state)
        return stored

    def mark_advisor_feedback_addressed(self, feedback_id: str) -> bool:
        """Flip a directive to addressed (with a timestamp). False if id not found."""
        state = self.load()
        hit = False
        for d in state["contextStore"].get("advisor_feedback") or []:
            if d.get("id") == feedback_id:
                d["status"] = "addressed"
                d["addressed_at"] = datetime.now(timezone.utc).isoformat()
                hit = True
        if hit:
            self._save(state)
        return hit

    def set_institution_profile(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Merge fields into the institution_profile key (never wipes prior fields)."""
        state = self.load()
        prof = {**(state["contextStore"].get("institution_profile") or {}), **fields}
        state["contextStore"]["institution_profile"] = prof
        self._save(state)
        return prof

    def set_thesis_timeline(self, timeline: dict[str, Any]) -> dict[str, Any]:
        """Store the backwards thesis timeline (F11). thesis_timeline is a
        COACHING_KEY, so this is a DEDICATED path (same rationale as
        set_institution_profile): recording a calendar is not a module design
        decision, so it must NEVER shift focus, flip module status, propagate
        needs_review, or add a version snapshot — hence not commit_slice, whose
        ownership check is module-scoped and would reject it. DbProjectStateStore
        round-trips it via the coaching JSONB column."""
        state = self.load()
        state["contextStore"]["thesis_timeline"] = timeline
        self._save(state)
        return timeline

    # -- field-it results ingestion (F7) ----------------------------------
    # Deliberately NOT commit_slice, same rationale as set_institution_profile:
    # ingesting collected survey data is not a design decision, so it must not
    # shift focus, flip module status, or flag M5 for review. The three keys are
    # M4-owned (SLICE_OWNERSHIP["M4"]), so DbProjectStateStore._save lifts them
    # into the m4_analysis column on the next save — the Output Sanity Layer (F8)
    # reads the quality flags from there.
    def set_field_it_results(self, data: dict[str, Any]) -> dict[str, Any]:
        """Write a fielded collection's raw responses + quality flags into M4."""
        state = self.load()
        cs = state["contextStore"]
        cs["field_it_collection_id"] = data.get("collection_id")
        cs["field_it_responses"] = data.get("responses") or []
        cs["field_it_quality"] = data.get("quality") or []
        self._save(state)
        return {"collection_id": cs["field_it_collection_id"],
                "n_responses": len(cs["field_it_responses"]),
                "n_quality": len(cs["field_it_quality"])}


def _validate_module(module: str) -> None:
    if module not in MODULES:
        raise ValueError(f"unknown module {module!r}; expected one of {MODULES}")
