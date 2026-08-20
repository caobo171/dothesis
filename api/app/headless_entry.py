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
    """
    topic = (params.get("topic") or "").strip()
    if not topic:
        return False
    existing = (store.load().get("contextStore") or {}).get("research_title")
    if existing:
        return False
    writes = {"research_title": topic,
              # user_context is the seeding-only key (agent/state.py:30-34):
              # the agent must not be able to rewrite the brief it is steered by.
              "user_context": {k: v for k, v in {
                  "topic": topic,
                  "citation_style": params.get("citation_style"),
              }.items() if v}}
    if params.get("language"):
        writes["language"] = params["language"]
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

        def _on_event(ev: dict) -> None:
            # Phase timing keys off the module FOCUS at each turn boundary — the
            # same signal the progress hook emits (phase_progress events are written
            # to the appender, they don't come back through on_event, so observing
            # the raw stream here would record nothing).
            if ev.get("type") == "done":
                try:
                    timer.mark((store.load() or {}).get("focus") or "M1")
                except Exception:  # noqa: BLE001
                    pass
            progress_hook(ev)

        # Internal auto-retry: a run that stalls / exhausts turns re-runs against
        # the state commit_slice already persisted — a FRESH agent re-reads the
        # committed store (the intended "resume"). Credit-safe: only the final
        # job_done charges, and an intermediate failure emits NO error event.
        # BUDGET-CAPPED: a retry only starts if enough of the report's time window
        # remains, so retries never push total wall time past fillform's 30-min
        # axios timeout (which turns a clean failure into a confusing "timeout").
        _RETRYABLE = {"max_stalls", "max_turns"}
        max_attempts = int(os.getenv("DOTHESIS_HEADLESS_RETRIES", "1")) + 1
        _retry_budget_s = int(os.getenv("DOTHESIS_HEADLESS_RETRY_BUDGET_S", "1200"))

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
            if time.monotonic() - timer.t0 >= _retry_budget_s:
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

        from app.partner_run import ReportError, run_partner_export
        _export_t0 = time.monotonic()
        try:
            out = run_partner_export(store, project_id, params)
        except ReportError as e:
            # A REFUSAL is not a crash. Carry the stable code out over the events
            # pipe (it lands in JobEvent.meta_json) so the endpoint can answer
            # with the specific contract — `needs_data` tells the partner what to
            # send next, where a generic report_failed tells them to retry the
            # same doomed payload.
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
