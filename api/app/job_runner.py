import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from .db import get_session_factory
from .models import Job, JobEvent, Paper
from .pubsub import pubsub
from .settings import get_settings

log = logging.getLogger(__name__)

_monitors: dict[uuid.UUID, asyncio.Task] = {}


def spawn_job(db: Session, job: Job, brief: dict, resume_from: str | None = None) -> None:
    settings = get_settings()
    workdir = settings.job_workdir_root / str(job.id)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    env = os.environ.copy()
    env["JOB_ID"] = str(job.id)
    env["PAPER_ID"] = str(job.paper_id)
    env["AWS_REGION"] = settings.aws_region
    env["S3_BUCKET"] = settings.s3_bucket
    env["S3_PREFIX"] = settings.s3_prefix
    env["AWS_ACCESS_KEY"] = settings.aws_access_key
    env["AWS_SECRET_KEY"] = settings.aws_secret_key
    if settings.gemini_api_key:
        env["GEMINI_API_KEY"] = settings.gemini_api_key
        env["GOOGLE_API_KEY"] = settings.gemini_api_key
    if settings.openai_api_key:
        env["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    cmd = [
        sys.executable, "-m", "engine",
        "--job-id", str(job.id),
        "--paper-id", str(job.paper_id),
        "--workdir", str(workdir),
        "--brief-json", str(workdir / "brief.json"),
        "--user-id", str(db.get(Paper, job.paper_id).user_id),
    ]
    if resume_from:
        cmd.extend(["--resume-from", resume_from])

    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    job.pid = proc.pid
    job.workdir = str(workdir)
    job.status = "running"
    job.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(job.id)


def start_monitor(job_id: uuid.UUID) -> None:
    if job_id in _monitors and not _monitors[job_id].done():
        return
    loop = asyncio.get_running_loop()
    _monitors[job_id] = loop.create_task(_monitor(job_id))


async def _monitor(job_id: uuid.UUID) -> None:
    session_factory = get_session_factory()
    with session_factory() as db:
        job = db.get(Job, job_id)
        if not job or not job.workdir:
            return
        path = Path(job.workdir) / "events.jsonl"

    last_pos = 0
    last_line_count = 0
    try:
        while True:
            if not path.exists():
                await asyncio.sleep(0.5)
                continue

            with session_factory() as db:
                job = db.get(Job, job_id)
                if not job:
                    return
                skip_lines = job.events_processed

            with path.open("r", encoding="utf-8") as f:
                f.seek(last_pos)
                lines = f.readlines()
                last_pos = f.tell()

            new_lines = lines[max(0, skip_lines - last_line_count):]
            last_line_count = last_line_count + len(lines)

            done = False
            for raw in new_lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("malformed event line: %r", raw[:200])
                    continue
                done = await _ingest_event(job_id, payload) or done

            if done:
                return

            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        return


async def _ingest_event(job_id: uuid.UUID, payload: dict) -> bool:
    """Persist one event, update job state, publish to subscribers. Returns True when terminal."""
    type_ = payload.get("type", "activity")
    session_factory = get_session_factory()
    with session_factory() as db:
        event = JobEvent(
            job_id=job_id,
            type=type_,
            phase=payload.get("phase"),
            agent=payload.get("agent"),
            text=payload.get("text"),
            meta_json={k: v for k, v in payload.items() if k not in {"type", "phase", "agent", "text"}},
        )
        db.add(event)

        job = db.get(Job, job_id)
        if job:
            job.events_processed += 1
            if type_ == "phase_progress":
                if "phase" in payload:
                    job.phase = payload["phase"]
                if "progress" in payload:
                    job.progress = float(payload["progress"])
            if type_ == "job_done":
                job.status = "done"
                job.finished_at = datetime.now(timezone.utc)
                job.progress = 1.0
                paper = db.get(Paper, job.paper_id)
                if paper:
                    paper.status = "done"
            if type_ == "error":
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.error_text = payload.get("text") or "unknown error"
                paper = db.get(Paper, job.paper_id)
                if paper:
                    paper.status = "failed"
                    from .credit_ledger import refund_if_unrefunded
                    from .models import User
                    paper_user = db.get(User, paper.user_id)
                    if paper_user:
                        refund_if_unrefunded(db, paper_user, paper_id=paper.id)
            if type_ == "checkpoint" and job.workdir:
                # Engine wrote a fresh {workdir}/checkpoint.json after a phase boundary.
                # Persist the entire JSON blob to the DB so we can resume even if the
                # workdir later disappears.
                cp_path = Path(job.workdir) / "checkpoint.json"
                if cp_path.exists():
                    try:
                        job.checkpoint_json = json.loads(cp_path.read_text(encoding="utf-8"))
                        job.completed_phase = payload.get("phase") or job.checkpoint_json.get("completed_phase")
                    except Exception as e:
                        log.warning("could not load checkpoint for job %s: %s", job_id, e)

        db.commit()
        ev_id = event.id

    await pubsub.publish(job_id, {"id": ev_id, **payload})
    return type_ in {"job_done", "error"}


def cancel_job(db: Session, job: Job) -> None:
    if job.pid:
        try:
            os.kill(job.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    job.status = "canceled"
    job.finished_at = datetime.now(timezone.utc)
    paper = db.get(Paper, job.paper_id)
    if paper:
        paper.status = "failed"
        from .credit_ledger import refund_if_unrefunded
        from .models import User
        paper_user = db.get(User, paper.user_id)
        if paper_user:
            refund_if_unrefunded(db, paper_user, paper_id=paper.id)
    db.commit()
