"""Headless-run subprocess entrypoint — the auto-mode pattern for the deep agent.

    python -m app.headless_entry --project-id <uuid> --job-id <uuid> \
        --workdir <path> --params-json <path>

Mirrors orchestrator/__main__.py: stream events to <workdir>/events.jsonl so
the API's existing job_runner._monitor tails them and updates Job rows — this
process NEVER writes Job rows itself (the API is the single Job writer).
Project state is written only through DbProjectStateStore.commit_slice by the
agent's own tools; a crash or budget failure keeps everything committed so far.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
import traceback
from pathlib import Path
from uuid import UUID

logger = logging.getLogger("headless_entry")

# The runner's only prompt — a USER-turn instruction, not a new system prompt:
# the brain's behavior still comes from SYSTEM_PROMPT + skills (spec §1 "no new
# prompts" for the spine; the student's opening message is the one thing a
# headless run must say itself). The per-turn [NEXT] header steers direction.
KICKOFF_PROMPT = (
    "Generate the complete work for this project from its current state. "
    "Work through every module in roadmap order without waiting for me; "
    "reconstruct missing upstream modules from what already exists (backfill) "
    "instead of asking me for inputs."
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m app.headless_entry")
    p.add_argument("--project-id", required=True)
    p.add_argument("--job-id", required=True)
    p.add_argument("--workdir", required=True)
    p.add_argument("--params-json", required=True)
    return p.parse_args()


# Budgets for a whole thesis, not a 4-chapter report. RunProfile's defaults
# (40 turns / 1800s) were measured against analysis_report; a full run adds a
# real literature pass and full-length M5 composition. These numbers are an
# ESTIMATE pending the first production run — the 30-minute ceiling that
# shapes the report path is fillform's axios timeout, which the consumer flow
# (SSE-polled) does not have. Both stay overridable via job params.
_FULL_THESIS_MAX_TURNS = 120
_FULL_THESIS_WALL_CLOCK_S = 7200


def _is_full_thesis(params: dict) -> bool:
    return (params.get("mode") or "") == "full_thesis"


def _seed_brief(store, params: dict) -> bool:
    """Commit the consumer brief into M1 before the first turn.

    Replaces the orchestrator's `_seed` graph node. Goes into the STORE rather
    than the kickoff prompt because _state_header re-injects store state on
    every turn — a prompt-only topic is one the model has to remember for 40
    turns, and it does not.

    Refuses to overwrite an existing research_title: resume re-runs this path
    over a project that already has work, and the student's own title outranks
    the brief that started the run.

    The title guard protects the TITLE ONLY. It used to abort the whole
    function, which quietly took the LANGUAGE with it — and the export reads
    the language from this very slice (agent_state.py:407 reads
    m1_topic["language"], defaulting to "vi"). So a project that got its title
    from an import or backfill and then started auto-draft never had a language
    committed, and an English thesis exported with Vietnamese scaffolding. The
    two are separate decisions and are now guarded separately.
    """
    cs = store.load().get("contextStore") or {}
    writes: dict = {}

    topic = (params.get("topic") or "").strip()
    if topic and not cs.get("research_title"):
        writes["research_title"] = topic
        # user_context is the seeding-only key (agent/state.py:30-34): the agent
        # must not be able to rewrite the brief it is steered by. citation_style
        # rides here as an audit record of what was asked for — the Project row
        # is what exporters actually read (models.py:245).
        writes["user_context"] = {k: v for k, v in {
            "topic": topic,
            "citation_style": params.get("citation_style"),
        }.items() if v}

    # Never overwrite a language already chosen: like the title, an existing
    # value is the student's, not this run's opening brief.
    if params.get("language") and not cs.get("language"):
        writes["language"] = params["language"]

    if not writes:
        return False
    store.commit_slice("M1", writes, reason="auto-draft brief")
    return True


def _build_profile(params: dict):
    """The run's budgets + what "done" means for THIS request, as data.

    required_modules is derived from the REQUESTED chapters (partner_run owns the
    single chapter->module map): without it `done` meant all five modules, so a
    4-chapter analysis_report on a seeded project — M2 empty, because payloads
    rarely carry literature — had to drive a full literature review to completion
    or the partner got a hard error for work they never asked for.
    """
    from agent.headless import RunProfile  # noqa: PLC0415

    if _is_full_thesis(params):
        # No chapter scoping: "done" means all five modules. required_modules
        # stays None, which RunProfile documents as "every module".
        return RunProfile(
            interactive=False,
            max_turns=int(params["max_turns"]) if params.get("max_turns")
            else _FULL_THESIS_MAX_TURNS,
            wall_clock_s=int(params["wall_clock_s"]) if params.get("wall_clock_s")
            else _FULL_THESIS_WALL_CLOCK_S,
            required_modules=None,
        )

    from app.partner_run import required_modules_for, resolve_chapters  # noqa: PLC0415

    chapters = resolve_chapters(params.get("depth") or "analysis_report",
                                params.get("chapters"))
    return RunProfile(
        interactive=False,
        # Budgets have ONE home: RunProfile's defaults. This used to double
        # max_turns to 80 with no stated basis, and a second unexplained number
        # in a spend cap is how the cap stops meaning anything. A caller that
        # genuinely needs a bigger budget passes it in the job params.
        max_turns=int(params["max_turns"]) if params.get("max_turns")
        else RunProfile.max_turns,
        wall_clock_s=int(params["wall_clock_s"]) if params.get("wall_clock_s")
        else RunProfile.wall_clock_s,
        required_modules=required_modules_for(chapters),
    )


# The flat default the retry budget used to be, kept as the ANCHOR rather than
# as the answer: 1200s was chosen against the report path's wall clock, so what
# it really encodes is a RATIO (1200/1800 = two thirds of the window), i.e.
# "only start another attempt while at least a third of the time remains".
_RETRY_BUDGET_ANCHOR_S = 1200


def _retry_budget_s(profile) -> int:
    """Seconds into the run after which no NEW attempt starts.

    Scales with the mode, for the same reason max_turns and wall_clock_s do
    (spec §Budgets). Left flat at 1200s it was dead weight on the consumer path:
    full_thesis runs to wall_clock_s=7200, so the budget expired at minute 20
    and a run that ended `max_stalls` at minute 45 could never retry with 75
    minutes still on its own clock — the retry loop existed and could not fire.
    Expressed as the anchor's share of the wall clock it was chosen for, so the
    ratio follows RunProfile's default if that ever moves.

    DOTHESIS_HEADLESS_RETRY_BUDGET_S still overrides, as an ABSOLUTE number of
    seconds — an operator setting it is naming a wall-clock ceiling (fillform's
    axios timeout is one), not a share of anything.
    """
    override = os.getenv("DOTHESIS_HEADLESS_RETRY_BUDGET_S")
    if override:
        return int(override)
    from agent.headless import RunProfile  # noqa: PLC0415
    return int(profile.wall_clock_s * (_RETRY_BUDGET_ANCHOR_S / RunProfile.wall_clock_s))


def _install_pause_handler(appender) -> None:
    """SIGTERM -> write `paused`, then exit 0.

    Mirrors orchestrator/__main__.py:60,78 (the process this one retires).
    job_runner.cancel_job pauses a run by sending SIGTERM (job_runner.py:327);
    the monitor (job_runner.py:298-301,321) turns a `paused` event into a
    resumable Job status and treats it as terminal for the tail loop. Without
    this handler the process just dies and the run sits at `running` forever.
    Progress is whatever commit_slice has already persisted, so exiting here
    loses nothing that was committed.
    """
    import signal  # noqa: PLC0415 — only needed here, mirrors orchestrator's lazy import style

    def _on_term(_signum, _frame):
        try:
            appender.write({"type": "paused", "agent": "headless",
                            "text": "run paused by request"})
        except Exception:  # noqa: BLE001 — never block the exit path
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _on_term)


def _make_progress_hook(appender, store):
    """Per-turn progress beats over the events.jsonl → JobEvent → SSE pipe —
    the durable replacement for the deleted in-memory _PROGRESS dict. Module
    granularity: `done`/`total` count finished modules, `phase` is the focus."""
    from agent.state import MODULES

    def on_event(ev: dict) -> None:
        try:
            if ev.get("type") == "tool_start":
                appender.write({"type": "activity", "agent": "headless",
                                "text": f"tool: {ev.get('name')}"})
            elif ev.get("type") == "done":  # one per turn (stream_turn's last event)
                state = store.load()
                done_n = sum(1 for m in MODULES if state["status"].get(m) == "done")
                appender.write({"type": "phase_progress",
                                "phase": state.get("focus") or "M1",
                                "progress": done_n / len(MODULES),
                                "total": len(MODULES), "done": done_n})
        except Exception:  # noqa: BLE001 — progress beats must never kill the run
            pass

    return on_event


class _PhaseTimer:
    """Accumulate wall time per module phase (M1..M5) from phase_progress beats,
    across retries. Phase i duration = start(phase i+1) - start(phase i); the last
    phase runs to `now`. Informative, not exact — enough to see where a report
    spends its minutes (the M1-M3 backfill vs the M5 compose split)."""

    def __init__(self, clock=time.monotonic):
        import time as _t  # noqa: PLC0415
        self._clock = clock or _t.monotonic
        self.t0 = self._clock()
        self._order: list[str] = []
        self._first: dict[str, float] = {}

    def mark(self, phase) -> None:
        """Record the first time we see each phase (module focus)."""
        try:
            ph = str(phase or "").strip()
            if ph and ph not in self._first:
                self._first[ph] = self._clock()
                self._order.append(ph)
        except Exception:  # noqa: BLE001 — timing must never kill the run
            pass

    def summary(self, extra: dict | None = None, end: float | None = None) -> dict:
        end = end if end is not None else self._clock()
        secs: dict[str, float] = {}
        for i, ph in enumerate(self._order):
            nxt = self._first[self._order[i + 1]] if i + 1 < len(self._order) else end
            secs[ph] = round(nxt - self._first[ph], 1)
        out = {"phases": secs, "total_s": round(end - self.t0, 1)}
        if extra:
            out.update(extra)
        return out


class _UsageMeter:
    """Turn the agent's `usage` events into `token_usage` events for the API.

    The API is the single DB writer (module docstring), so this emits on the
    events.jsonl contract and job_runner._ingest_event (job_runner.py:215-236)
    creates the token_ledger row — the same path orchestrator/__main__.py:82-97
    uses. _charge_auto_run then prices each row at ITS OWN model's rate, which
    is why usage is grouped by the model that actually served the step:
    OpenRouter can fail over to a pricier fallback mid-run and runtime.py
    reports the served model on the event — but ONLY when that served id is one
    the price table knows (see _billable_model).

    Buffered per turn so a long turn emits one event per model, not one per
    LLM step.
    """

    def __init__(self, project_id, appender):
        self.project_id = project_id
        self._appender = appender
        self._buf: dict[str, list[int]] = {}
        self._configured: str | None = None
        self._warned: set[str] = set()

    def _configured_model(self) -> str:
        """The model this run was CONFIGURED to run on, from the same resolver
        that actually chose the brain (build_agent -> _default_model ->
        make_model -> spec_from_env). Resolved once — it cannot change mid-run."""
        if self._configured is None:
            try:
                from agent.model_factory import spec_from_env  # noqa: PLC0415
                self._configured = spec_from_env().model
            except Exception:  # noqa: BLE001 — metering must never kill the run
                logger.exception("could not resolve the configured model for billing")
                self._configured = os.getenv("DOTHESIS_AGENT_MODEL", "unknown")
        return self._configured

    def _billable_model(self, served: str | None) -> str:
        """The id these tokens are LABELLED with — i.e. the id _charge_auto_run
        will price the resulting ledger row at.

        Keep the SERVED model when quality/model_prices.py actually prices it:
        an OpenRouter failover to a pricier fallback is real money, and the
        per-model split is the only place it shows up.

        An id the table does NOT price must never reach the ledger under its own
        name. credit_multiplier bills an unpriced id at UNKNOWN_MODEL_MULTIPLIER
        (4.0x), so a dated snapshot id (`gpt-5.6-luna-2026-05-13`) or a missing
        `model_name` on response_metadata would bill a WHOLE THESIS at 4.0x
        instead of the configured model's true rate — 7.6x on the openai route
        (luna blends to 0.53x) and ~21x on ofox/qwen-plus. The OTHER charge site,
        `_finalize` in the v3 chat router (grep `_credit_multiplier(spec_from_env`),
        rejected per-served-model billing outright for this exact reason, and
        pricing.py:225-228 requires the two not to drift. (Named, not imported:
        this subprocess must never pull the chat router in — see
        test_headless_entry_profile.) Falling back to the CONFIGURED model keeps
        the per-model accuracy where it is REAL and bills the id chat bills where
        it is not.
        """
        from app.pricing import UNKNOWN_MODEL_MULTIPLIER, is_priced  # noqa: PLC0415

        served = (served or "").strip()
        if served and is_priced(served):
            return served
        configured = self._configured_model()
        if served and served not in self._warned:
            # Once per distinct id: an unpriced served model is either a real
            # failover we are now mis-splitting, or a missing table row. Both are
            # operator-fixable and neither should be silent.
            self._warned.add(served)
            logger.warning(
                "usage reported model %r, which quality/model_prices.py does not "
                "price — billing as the configured %r instead of the %.1fx "
                "unknown-model fallback. Add the id to the table.",
                served, configured, UNKNOWN_MODEL_MULTIPLIER,
            )
        return configured

    def observe(self, ev: dict) -> None:
        if ev.get("type") != "usage":
            return
        # runtime.py:846 only sets `model` when OpenRouter reports the served
        # model on response_metadata, and what it reports is not necessarily an
        # id the price table carries — _billable_model decides what bills.
        model = self._billable_model(ev.get("model"))
        slot = self._buf.setdefault(model, [0, 0])
        slot[0] += int(ev.get("input_tokens") or 0)
        slot[1] += int(ev.get("output_tokens") or 0)

    def flush(self) -> int:
        if not self._buf:
            return 0
        buf, self._buf = self._buf, {}
        for model, (prompt, completion) in buf.items():
            self._appender.write({
                "type": "token_usage",
                "action_kind": "deep_agent_turn",
                "model": model,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                # NOT NULL on token_ledger. token_meter's reserve-then-reconcile
                # loop has no analogue here: the agent reports true usage, so
                # there is nothing reserved and no separate call to time.
                "reserved": 0,
                "duration_ms": 0,
                "project_id": str(self.project_id),
            })
        return len(buf)


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = _parse_args()
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    # engine/ is not an installed package — same repo-root sys.path trick as
    # orchestrator/__main__.py (agent/app/orchestrator are editable-installed).
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from engine.job_io import JsonlAppender

    appender = JsonlAppender(workdir / "events.jsonl")
    # Installed immediately: cancel_job can SIGTERM at any point after spawn,
    # including before the try-block below does anything committable.
    _install_pause_handler(appender)
    try:
        params = json.loads(Path(args.params_json).read_text("utf-8"))
        project_id = UUID(args.project_id)

        from langgraph.checkpoint.memory import InMemorySaver

        from agent.headless import run_headless
        from agent.runtime import build_agent
        from app.agent_state import DbProjectStateStore
        from app.db import get_engine
        from app.workspace import workspace_dir

        # Same dir chat would use — a later chat handoff sees the same files.
        workspace = workspace_dir(project_id)
        store = DbProjectStateStore(get_engine(), project_id, workspace)
        # Seed BEFORE the profile/agent so the first _state_header already
        # carries the topic (see _seed_brief). No-ops on resume: it refuses to
        # overwrite an existing research_title, so a project with prior work
        # keeps the student's own title instead of the brief that started the run.
        _seed_brief(store, params)
        # InMemorySaver: the conversation only needs to outlive THIS run —
        # durable progress is whatever commit_slice wrote, and a failed run
        # "resumes" by re-running against that state, not by replaying chat.
        profile = _build_profile(params)
        # Report-only. set_report_chapters scopes M5 to the ordered chapters and
        # set_grounded_backfill swaps M2's backfill for a real literature search;
        # a full thesis needs neither scope nor that substitution.
        if not _is_full_thesis(params):
            # Scope the deep agent's M5 writing to the chapters this partner
            # ordered (the interactive flow leaves this unset → full thesis).
            # Cuts the wasted composition of unordered/fabricated chapters.
            # Best-effort: if the ContextVar doesn't propagate, M5 falls back
            # to composing everything.
            from agent.run_context import set_grounded_backfill, set_report_chapters  # noqa: PLC0415
            from app.partner_run import resolve_chapters  # noqa: PLC0415
            set_report_chapters(resolve_chapters(
                params.get("depth") or "analysis_report", params.get("chapters")))
            # Report path only: ground M2 with a real literature search (real
            # DOIs + domain-specialized sources) instead of the backfill's LLM
            # recall.
            set_grounded_backfill()

        timer = _PhaseTimer()
        progress_hook = _make_progress_hook(appender, store)
        # Billing: buffers `usage` events per model and flushes into a
        # `token_usage` event on every turn boundary (see _UsageMeter). Without
        # this, the deep agent run never reaches token_ledger and the
        # billing sweep in job_runner._charge_auto_run finds nothing to charge.
        meter = _UsageMeter(project_id, appender)

        def _on_event(ev: dict) -> None:
            meter.observe(ev)
            # Phase timing keys off the module FOCUS at each turn boundary — the
            # same signal the progress hook emits (phase_progress events are written
            # to the appender, they don't come back through on_event, so observing
            # the raw stream here would record nothing).
            if ev.get("type") == "done":
                # One turn's worth of usage per flush; a crash mid-turn loses at
                # most that turn's metering, never a committed slice.
                meter.flush()
                try:
                    timer.mark((store.load() or {}).get("focus") or "M1")
                except Exception:  # noqa: BLE001
                    pass
            progress_hook(ev)

        # Internal auto-retry: a run that stalls / exhausts turns re-runs against
        # the state commit_slice already persisted — a FRESH agent re-reads the
        # committed store (the intended "resume"). Credit-safe: only the final
        # job_done charges, and an intermediate failure emits NO error event.
        # BUDGET-CAPPED: a retry only starts if enough of THIS run's time window
        # remains (_retry_budget_s scales the cap with the mode), so on the report
        # path retries never push total wall time past fillform's 30-min axios
        # timeout (which turns a clean failure into a confusing "timeout").
        _RETRYABLE = {"max_stalls", "max_turns"}
        max_attempts = int(os.getenv("DOTHESIS_HEADLESS_RETRIES", "1")) + 1
        retry_budget_s = _retry_budget_s(profile)

        # Headless/B2B → strict gates: an unrunnable verification gate refuses the
        # commit (fail-closed at the fabrication boundary, gap 2). BUT distinguish
        # "gate not deployed" (thesis_stats submodule missing → the import can NEVER
        # succeed → strict would refuse EVERY M4 commit forever, deadlocking the run)
        # from "gate crashed at runtime on real data". If the validator can't even
        # import, degrade to advisory LOUDLY (attested in provenance) — the same
        # fail-open behavior that let reports complete before strict gates existed.
        strict = params.get("strict_gates", True)
        if strict:
            try:
                from thesis_stats.validation import validate_claims  # noqa: F401,PLC0415
            except Exception:
                logger.error("thesis_stats not importable — strict gates degraded to advisory")
                appender.write({"type": "activity", "agent": "headless",
                                "text": "stats gate unavailable (validator not installed) — "
                                        "running advisory; numbers marked unverified"})
                strict = False
        result = None
        attempt = 0
        for attempt in range(1, max_attempts + 1):
            agent = build_agent(workspace, checkpointer=InMemorySaver(), store=store,
                                strict_gates=strict)
            result = asyncio.run(run_headless(
                agent, store, profile,
                thread_id=f"headless:{args.job_id}:{attempt}",
                initial_prompt=KICKOFF_PROMPT,
                on_event=_on_event,
            ))
            if (result.status == "done" or result.reason not in _RETRYABLE
                    or attempt == max_attempts):
                break
            if time.monotonic() - timer.t0 >= retry_budget_s:
                appender.write({"type": "activity", "agent": "headless",
                                "text": f"attempt {attempt} ended: {result.reason} — "
                                        f"retry budget exhausted, stopping"})
                break
            appender.write({"type": "activity", "agent": "headless",
                            "text": f"attempt {attempt} ended: {result.reason} — retrying"})

        agent_end = time.monotonic()  # freeze phase timing before export

        if result is None or result.status != "done":
            # Budget exhaustion / stalls = a FAILED run with partial state
            # preserved — never a silent success (spec §1). The store keeps
            # everything committed; the partner gets a clean error, not a
            # hollow report.
            appender.write({"type": "phase_timings",
                            **timer.summary({"attempts": attempt,
                                             "final": result.reason if result else "no_result"},
                                            end=agent_end)})
            appender.write({"type": "error",
                            "text": f"headless run failed: "
                                    f"{result.reason if result else 'no_result'} after "
                                    f"{result.turns if result else 0} turns "
                                    f"({attempt} attempt(s))"})
            return 1

        out: dict = {}
        _export_t0 = time.monotonic()
        # PARTNER-PATH WORK ONLY. run_partner_export re-composes the chapter
        # SUBSET a partner ordered and gates it on assess_export_readiness.
        # Consumer auto-draft orders no chapters, so with no `depth` in params it
        # fell through to resolve_chapters("analysis_report", None) and raised
        # ReportError("needs_data") whenever M4.analysis_results was empty — a
        # thesis the agent had just finished emitted {"type": "error"}, _monitor
        # marked the Job `failed`, and _charge_auto_run (job_runner.py:207-222,
        # reached only on job_done) never ran. A completed thesis, given away
        # free. On the runs that did clear the gate it still wrote a spurious
        # second 4-chapter export tagged scope="partner".
        #
        # The consumer thesis is already exported: DbProjectStateStore's M5
        # done-hook (_auto_export_m5, agent_state.py:378) fires inside the
        # commit_slice that flips M5 to done and persists the full-thesis
        # artifacts with scope="full". Nothing here has to export it again.
        if not _is_full_thesis(params):
            from app.partner_run import ReportError, run_partner_export  # noqa: PLC0415
            try:
                out = run_partner_export(store, project_id, params)
            except ReportError as e:
                # A REFUSAL is not a crash. Carry the stable code out over the
                # events pipe (it lands in JobEvent.meta_json) so the endpoint can
                # answer with the specific contract — `needs_data` tells the
                # partner what to send next, where a generic report_failed tells
                # them to retry the same doomed payload.
                appender.write({"type": "phase_timings",
                                **timer.summary({"attempts": attempt}, end=agent_end)})
                appender.write({"type": "error", "code": e.code, "text": e.message})
                return 1
        export_s = round(time.monotonic() - _export_t0, 1)
        # Per-run phase durations — informative: M1-M3 backfill vs M5 compose vs
        # export, plus how many attempts it took.
        appender.write({"type": "phase_timings",
                        **timer.summary({"attempts": attempt, "export_s": export_s,
                                         "report_total_s": round(time.monotonic() - timer.t0, 1)},
                                        end=agent_end)})
        appender.write({"type": "job_done", **out})
        return 0
    except Exception:
        logger.exception("headless run crashed")
        appender.write({"type": "error", "text": "headless run crashed",
                        "traceback": traceback.format_exc()})
        return 1
    finally:
        appender.close()


if __name__ == "__main__":
    sys.exit(main())
