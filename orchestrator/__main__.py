"""Auto-mode subprocess entrypoint for the orchestrator.

Invoked by `api/app/job_runner.py` when a run has `mode = "auto"`. Streams
semantic events to `<workdir>/events.jsonl` so the API's existing `_monitor`
task can tail them and update DB rows. Never writes to DB directly.

Usage:
    python -m orchestrator --auto-draft \
        --project-id <uuid> --user-id <uuid> \
        --workdir <path> --brief-json <path>

    python -m orchestrator --resume-run-id <uuid> --workdir <path>
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import traceback
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger("orchestrator")


def _require_aws_s3_bucket():
    """SP6: M5 export uploads to S3; refuse to start without a configured bucket."""
    if not os.environ.get("AWS_S3_BUCKET"):
        raise SystemExit(
            "AWS_S3_BUCKET env var is required for M5 export artifacts. "
            "Set it (e.g. AWS_S3_BUCKET=opendraft-dev) and re-run."
        )


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m orchestrator")
    p.add_argument("--auto-draft", action="store_true",
                   help="Run the full graph end-to-end in auto-mode.")
    p.add_argument("--resume-run-id", default=None,
                   help="Resume a paused run by its uuid (reads checkpoint from DB).")
    p.add_argument("--project-id", default=None)
    p.add_argument("--user-id", default=None)
    p.add_argument("--workdir", required=True)
    p.add_argument("--brief-json", default=None,
                   help="Path to JSON with {topic, language, citation_style, ...}.")
    p.add_argument("--run-id", default=None,
                   help="Run UUID (used as langgraph thread_id).")
    return p


def _install_sigterm_handler(appender: Any, current: dict) -> None:
    """SIGTERM → write a paused event and exit cleanly. LangGraph checkpoint
    is already on disk thanks to per-node auto-checkpointing.
    """
    def _on_term(signum, frame):
        try:
            appender.write({
                "type": "paused",
                "module": current.get("module"),
                "reason": "user_stop",
            })
        except Exception:
            logger.exception("failed to write paused event")
        finally:
            try:
                appender.close()
            except Exception:
                pass
        sys.exit(0)
    signal.signal(signal.SIGTERM, _on_term)


def _emit_event(appender, event: dict, current_module: dict) -> None:
    """Translate a LangGraph stream event into our events.jsonl format."""
    for node_name, payload in event.items():
        if node_name == "supervisor":
            new_mod = payload.get("current_module")
            if new_mod and new_mod != current_module.get("module"):
                current_module["module"] = new_mod
                appender.write({
                    "type": "activity",
                    "module": new_mod,
                    "text": f"Supervisor routed to {new_mod}",
                })
        elif node_name in {"M1", "M2", "M3", "M4", "M5"}:
            current_module["module"] = node_name
            msgs = payload.get("messages") or []
            text = msgs[-1].content if msgs else ""
            appender.write({
                "type": "activity",
                "module": node_name,
                "agent": f"{node_name} Agent",
                "text": text[:500],
            })


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    args = build_arg_parser().parse_args()
    _require_aws_s3_bucket()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    events_path = workdir / "events.jsonl"

    # Reuse the engine's existing JsonlAppender + JobTracker — same SSE bridge.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from engine.job_io import JsonlAppender

    appender = JsonlAppender(events_path)
    current_module: dict[str, str | None] = {"module": None}
    _install_sigterm_handler(appender, current_module)

    try:
        from langchain_core.messages import HumanMessage

        from orchestrator.graph import get_auto_graph
        from orchestrator.state import ContextStore

        graph = get_auto_graph()
        run_id = args.run_id or args.resume_run_id or str(uuid4())
        config = {"configurable": {"thread_id": run_id}}

        if args.resume_run_id:
            appender.write({"type": "activity", "agent": "System",
                            "text": f"Resuming run {args.resume_run_id}"})
            # Empty input = LangGraph picks up at last checkpoint
            for event in graph.stream({}, config=config):
                _emit_event(appender, event, current_module)
        else:
            if not args.brief_json:
                raise SystemExit("--brief-json required for new auto-draft runs")
            brief = json.loads(Path(args.brief_json).read_text("utf-8"))
            initial = {
                "project_id": UUID(args.project_id) if args.project_id else None,
                "thread_id": None,
                "messages": [HumanMessage(content=brief.get("topic", ""))],
                "current_module": "M1",
                "context_store": ContextStore(),
                "mode": "auto",
                "user_intent": None,
                "pending_confirmations": [],
            }
            for event in graph.stream(initial, config=config):
                _emit_event(appender, event, current_module)

        # Final state — look up exports if M5 produced any.
        snapshot = graph.get_state(config)
        cs = snapshot.values.get("context_store")
        exports = {}
        if cs is not None and cs.m5_writing:
            for art in cs.m5_writing.get("export_artifacts", []):
                # SP6: new field is download_url; fall back to uri for back-compat.
                exports[art["kind"]] = art.get("download_url") or art.get("uri", "")

        # SP6: compile_pdf/export_docx already uploaded to S3 with the new
        # mandatory single-code-path. The old optional secondary upload block
        # (engine.s3_for_jobs) is dead; export URIs live in cs.m5_writing
        # already.

        appender.write({"type": "job_done", "exports": exports})
        return 0
    except SystemExit:
        raise
    except Exception:
        logger.exception("auto-draft failed")
        appender.write({
            "type": "error",
            "text": "orchestrator auto-draft failed",
            "traceback": traceback.format_exc(),
        })
        return 1
    finally:
        appender.close()


if __name__ == "__main__":
    sys.exit(main())
