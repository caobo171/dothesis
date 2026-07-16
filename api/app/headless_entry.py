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
import sys
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


def _build_profile(params: dict):
    """The run's budgets + what "done" means for THIS request, as data.

    required_modules is derived from the REQUESTED chapters (partner_run owns the
    single chapter->module map): without it `done` meant all five modules, so a
    4-chapter analysis_report on a seeded project — M2 empty, because payloads
    rarely carry literature — had to drive a full literature review to completion
    or the partner got a hard error for work they never asked for.
    """
    from agent.headless import RunProfile  # noqa: PLC0415
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
        # InMemorySaver: the conversation only needs to outlive THIS run —
        # durable progress is whatever commit_slice wrote, and a failed run
        # "resumes" by re-running against that state, not by replaying chat.
        agent = build_agent(workspace, checkpointer=InMemorySaver(), store=store)
        profile = _build_profile(params)
        result = asyncio.run(run_headless(
            agent, store, profile,
            thread_id=f"headless:{args.job_id}",
            initial_prompt=KICKOFF_PROMPT,
            on_event=_make_progress_hook(appender, store),
        ))
        if result.status != "done":
            # Budget exhaustion / stalls = a FAILED run with partial state
            # preserved — never a silent success (spec §1). The store keeps
            # everything committed; the partner gets a clean error, not a
            # hollow report.
            appender.write({"type": "error",
                            "text": f"headless run failed: {result.reason} "
                                    f"after {result.turns} turns"})
            return 1

        from app.partner_run import run_partner_export
        out = run_partner_export(store, project_id, params)
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
