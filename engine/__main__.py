"""Subprocess entrypoint invoked by the API.

    python -m engine \
        --job-id <uuid> --paper-id <uuid> --user-id <uuid> \
        --workdir <path> --brief-json <path>
"""
import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path

# Make `engine.draft_generator` importable when run with `-m engine`
sys.path.insert(0, str(Path(__file__).resolve().parent))

from engine.job_io import JobStreamer, JobTracker, JsonlAppender, upload_artifacts
from engine.s3_for_jobs import s3_from_env

log = logging.getLogger("engine.__main__")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Silence chatty fallback-not-configured warnings. DataForSEO is an OPTIONAL paid
# fallback for Gemini grounded search. When the credentials aren't set, the engine
# logs a warning every time it would have called the fallback (potentially dozens
# per job). The engine handles the missing fallback gracefully — we don't need the noise.
logging.getLogger("utils.api_citations.gemini_grounded").setLevel(logging.ERROR)


class TrackerLoggingBridge(logging.Handler):
    """Forward selected log records from the engine internals into the tracker's activity feed.

    Most engine progress (citation API hits, rate-limit warnings, retries) goes through
    Python logging rather than ctx.tracker — without this bridge the UI feed is nearly empty.

    Only forwards loggers matching a small allow-list to avoid spamming the SSE stream.
    """

    PHASE_BY_LOGGER_PREFIX = {
        "utils.api_citations": "research",
        "utils.deep_research": "research",
        "utils.gemini_client": "research",  # Model-switch messages
        "phases.research": "research",
        "phases.structure": "structure",
        "phases.compose": "compose",
        "phases.validate": "qa",
        "phases.citations": "compile",
        "phases.compile": "compile",
        "utils.citation_compiler": "compile",
        "utils.abstract_generator": "compile",
        "utils.export_professional": "export",
    }

    def __init__(self, tracker: "JobTracker") -> None:
        super().__init__(level=logging.INFO)
        self._tracker = tracker

    def _phase_for(self, logger_name: str) -> str | None:
        for prefix, phase in self.PHASE_BY_LOGGER_PREFIX.items():
            if logger_name.startswith(prefix):
                return phase
        return None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            phase = self._phase_for(record.name)
            if phase is None:
                return
            msg = record.getMessage()
            # Skip very noisy lines that don't carry user-visible signal.
            if "429 signaled" in msg or "DataForSEO fallback" in msg:
                return
            agent = record.name.split(".")[-1].replace("_", " ").title()
            self._tracker.log_activity(
                msg[:500],
                phase=phase,
                agent=agent,
                event_type=("error" if record.levelno >= logging.ERROR
                            else "warn" if record.levelno >= logging.WARNING
                            else "info"),
            )
        except Exception:
            # Never let logging crash the job.
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--paper-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--workdir", required=True)
    parser.add_argument("--brief-json", required=True)
    parser.add_argument("--resume-from", default=None,
                        help="Path to a checkpoint.json to resume from")
    args = parser.parse_args()

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    events_path = workdir / "events.jsonl"
    appender = JsonlAppender(events_path)
    tracker = JobTracker(appender)
    streamer = JobStreamer(appender)

    # Bridge engine-internal Python logging into the tracker so the UI sees real activity.
    bridge = TrackerLoggingBridge(tracker)
    logging.getLogger().addHandler(bridge)

    try:
        brief = json.loads(Path(args.brief_json).read_text(encoding="utf-8"))

        # Lazy import — heavy
        from draft_generator import generate_draft

        # Light up the Research phase chip immediately so the UI doesn't look frozen.
        tracker.update_phase("research", progress_percent=1,
                              details={"active_agents": ["Scout"], "stage": "starting"})
        appender.write({"type": "activity", "phase": "research", "agent": "Scout",
                        "text": "Job starting"})

        resume_path = Path(args.resume_from) if args.resume_from else None
        if resume_path:
            appender.write({"type": "activity", "phase": "research", "agent": "System",
                            "text": f"Resuming from checkpoint at {resume_path.name}"})

        generate_draft(
            topic=brief["topic"],
            language=brief.get("language", "en"),
            academic_level=brief["academic_level"],
            output_dir=workdir,
            citation_style=brief.get("citation_style", "apa"),
            tracker=tracker,
            streamer=streamer,
            verbose=False,
            resume_from=resume_path,
        )

        s3 = s3_from_env()
        key_root = f"users/{args.user_id}/papers/{args.paper_id}/jobs/{args.job_id}"
        exports = upload_artifacts(s3, workdir, key_root)

        appender.write({"type": "job_done", "exports": exports})
        return 0
    except Exception as e:
        log.exception("job failed")
        appender.write({"type": "error", "text": str(e), "traceback": traceback.format_exc()})
        return 1
    finally:
        appender.close()


if __name__ == "__main__":
    sys.exit(main())
