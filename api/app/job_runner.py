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
                # Orchestrator runs (mode="auto") have no paper_id — skip paper update.
                if job.paper_id:
                    paper = db.get(Paper, job.paper_id)
                    if paper:
                        paper.status = "done"
                else:
                    # Auto-approve run finished: charge the LLM tokens it used.
                    # Only successful runs reach job_done, so failures cost nothing.
                    try:
                        _charge_auto_run(db, job)
                    except Exception:  # noqa: BLE001 — never break the monitor on billing
                        log.exception("auto-run credit charge failed for job %s", job_id)
            if type_ == "error":
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
                job.error_text = payload.get("text") or "unknown error"
                # Orchestrator runs (mode="auto") have no paper_id — skip paper/credit cleanup.
                if job.paper_id:
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
            # Orchestrator emits a "paused" event when the graph halts gracefully
            # (e.g., after receiving SIGTERM). Mark the run paused so it can be resumed.
            if type_ == "paused":
                job.status = "paused"
                job.finished_at = datetime.now(timezone.utc)

        db.commit()
        ev_id = event.id

    await pubsub.publish(job_id, {"id": ev_id, **payload})
    # "paused" is terminal for the monitor loop — the run will be resumed via a new spawn.
    return type_ in {"job_done", "error", "paused"}


def cancel_job(db: Session, job: Job) -> None:
    if job.pid:
        try:
            os.kill(job.pid, signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass
    job.status = "canceled"
    job.finished_at = datetime.now(timezone.utc)
    # Orchestrator runs (mode="auto") have no paper_id — skip paper/credit cleanup.
    if job.paper_id:
        paper = db.get(Paper, job.paper_id)
        if paper:
            paper.status = "failed"
            from .credit_ledger import refund_if_unrefunded
            from .models import User
            paper_user = db.get(User, paper.user_id)
            if paper_user:
                refund_if_unrefunded(db, paper_user, paper_id=paper.id)
    db.commit()


def _charge_auto_run(db: Session, run: Job) -> None:
    """Charge an auto-approve run for the LLM tokens it actually consumed.

    The orchestrator records every metered call in `token_ledger` (per project).
    Sum the tokens recorded since this run started, convert at the chat rate
    (~1 credit / 1k tokens), and debit the project owner — writing a ledger row
    that shows up on the Transactions page. Idempotent (skips if this run was
    already charged) and capped at the available balance so a finished run never
    errors the monitor.
    """
    if run.paper_id or not run.project_id or not run.started_at:
        return
    from sqlalchemy import func, select

    from .credit_ledger import debit
    from .models import CreditTransaction, Project, TokenLedger, User

    already = db.scalar(
        select(CreditTransaction.id).where(
            CreditTransaction.ref_type == "run",
            CreditTransaction.ref_id == run.id,
            CreditTransaction.reason == "auto_run",
        )
    )
    if already:
        return

    proj = db.get(Project, run.project_id)
    owner = db.get(User, proj.user_id) if proj else None
    if owner is None:
        return

    total_tokens = int(
        db.scalar(
            select(
                func.coalesce(
                    func.sum(TokenLedger.prompt_tokens + TokenLedger.completion_tokens), 0
                )
            ).where(
                TokenLedger.project_id == run.project_id,
                TokenLedger.created_at >= run.started_at,
            )
        )
        or 0
    )
    if total_tokens <= 0:
        return
    cost = max(1, round(total_tokens / 1000))
    charge = min(cost, owner.credit or 0)
    if charge > 0:
        debit(db, owner, delta=charge, reason="auto_run", ref_type="run", ref_id=run.id)


def spawn_orchestrator_run(db: Session, run: Job, brief: dict,
                           resume_from: str | None = None) -> None:
    """Spawn `python -m orchestrator` as a subprocess for an auto-mode run.

    Mirrors `spawn_job` but uses the orchestrator entrypoint. Reuses events.jsonl
    contract so existing `_monitor` works unchanged.
    """
    settings = get_settings()
    workdir = settings.job_workdir_root / str(run.id)
    workdir.mkdir(parents=True, exist_ok=True)
    if not resume_from:
        (workdir / "brief.json").write_text(json.dumps(brief), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    env = os.environ.copy()
    env["RUN_ID"] = str(run.id)
    if run.project_id:
        env["PROJECT_ID"] = str(run.project_id)
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
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

    user_id = None
    if run.project_id:
        from .models import Project
        proj = db.get(Project, run.project_id)
        user_id = str(proj.user_id) if proj else None

    cmd = [sys.executable, "-m", "orchestrator",
           "--workdir", str(workdir),
           "--run-id", str(run.id)]
    if resume_from:
        cmd.extend(["--resume-run-id", resume_from])
    else:
        cmd.extend([
            "--auto-draft",
            "--brief-json", str(workdir / "brief.json"),
            "--project-id", str(run.project_id) if run.project_id else "",
            "--user-id", user_id or "",
        ])

    proc = subprocess.Popen(
        cmd,
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    run.pid = proc.pid
    run.workdir = str(workdir)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(run.id)
