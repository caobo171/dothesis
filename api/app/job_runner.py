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
from .models import Job, JobEvent, Paper, TokenLedger
from .pubsub import pubsub
from .settings import get_settings

log = logging.getLogger(__name__)

_monitors: dict[uuid.UUID, asyncio.Task] = {}

# The app's main event loop, captured at startup (main.lifespan). start_monitor
# needs it to schedule the monitor task when called from a sync endpoint, which
# FastAPI runs in a threadpool worker thread where get_running_loop() raises.
_app_loop: asyncio.AbstractEventLoop | None = None


def set_app_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _app_loop
    _app_loop = loop


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
    # Async endpoints run on the loop (get_running_loop works); sync endpoints
    # run in a threadpool worker with no running loop, so fall back to the
    # loop captured at startup. create_task / dict assignment must happen ON
    # the loop thread, so when we're off it we hop over via call_soon_threadsafe.
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    loop = running or _app_loop
    if loop is None:
        log.warning("start_monitor: no event loop available — progress streaming "
                    "disabled for %s", job_id)
        return

    def _create() -> None:
        if job_id in _monitors and not _monitors[job_id].done():
            return
        _monitors[job_id] = loop.create_task(_monitor(job_id))

    if running is loop:
        _create()
    else:
        loop.call_soon_threadsafe(_create)


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


def _sync_context_store_from_checkpoint(db: Session, job: Job) -> None:
    """Copy an auto-run's LangGraph checkpoint into the context_store table.

    The orchestrator subprocess keeps module state only in its PostgresSaver
    checkpoint (keyed by thread_id == run.id) and never writes the DB itself
    (orchestrator/__main__.py). Without this, the context_store table — which
    feeds the right-panel UI, the project module_status pills, and the handoff
    into interactive editing (orchestrator/loader.py reads it) — stays empty for
    auto runs, so a failed run looks like it lost all its progress. The API is
    the single DB writer, so we read the checkpoint here and upsert the table at
    every module boundary and on the terminal event.
    """
    if not job.project_id:
        return
    try:
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        from orchestrator.graph import get_auto_graph
        from orchestrator.state import compute_status_map

        from .models import ContextStore as DbContextStore
        from .models import Project

        graph = get_auto_graph()
        snap = graph.get_state({"configurable": {"thread_id": str(job.id)}})
        cs = (snap.values or {}).get("context_store") if snap else None
        if cs is None:
            return

        slices = dict(
            m1_topic=cs.m1_topic, m2_literature=cs.m2_literature,
            m3_design=cs.m3_design, m4_analysis=cs.m4_analysis,
            m5_writing=cs.m5_writing,
        )
        stmt = (
            pg_insert(DbContextStore.__table__)
            .values(project_id=job.project_id, **slices)
            .on_conflict_do_update(
                index_elements=[DbContextStore.__table__.c.project_id], set_=slices
            )
        )
        db.execute(stmt)

        proj = db.get(Project, job.project_id)
        if proj is not None:
            proj.module_status = compute_status_map(cs).model_dump()
    except Exception:  # noqa: BLE001 — a sync failure must never break the monitor
        log.exception("context_store sync from checkpoint failed for run %s", job.id)


async def _ingest_event(job_id: uuid.UUID, payload: dict) -> bool:
    """Persist one event, update job state, publish to subscribers. Returns True when terminal."""
    type_ = payload.get("type", "activity")
    session_factory = get_session_factory()

    if type_ == "token_usage":
        # Billing telemetry from the orchestrator subprocess, not user-facing
        # activity — it becomes a token_ledger row, NOT a JobEvent, so the run's
        # activity feed stays readable. `events_processed` is still incremented
        # because _monitor uses it to skip already-consumed lines on resume;
        # dropping that would replay every prior line and double-bill the run.
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job:
                job.events_processed += 1
            pid = payload.get("project_id")
            db.add(TokenLedger(
                project_id=uuid.UUID(pid) if pid else None,
                action_kind=payload.get("action_kind", "unknown"),
                model=payload.get("model", "unknown"),
                prompt_tokens=int(payload.get("prompt_tokens") or 0),
                completion_tokens=int(payload.get("completion_tokens") or 0),
                reserved=int(payload.get("reserved") or 0),
                duration_ms=int(payload.get("duration_ms") or 0),
            ))
            db.commit()
        return False

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

            # Auto runs only persist state in the LangGraph checkpoint. Mirror it
            # into the context_store table at each module boundary (supervisor
            # routing to the next module) and on every terminal event, so the UI
            # panel, module_status, resume, and interactive handoff all see the
            # progress — even when the run failed mid-way.
            if job.mode == "auto" and (
                type_ in {"job_done", "error", "paused"}
                or (type_ == "activity"
                    and (payload.get("text") or "").startswith("Supervisor routed to"))
            ):
                _sync_context_store_from_checkpoint(db, job)

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

    # Bill each ledger row at ITS OWN model's rate, grouped by the model the
    # ledger recorded. token_meter writes the model that actually served the call
    # (orchestrator/token_meter.py), so the truth is already in these rows.
    #
    # This previously summed tokens and scaled by credit_multiplier(getenv(
    # "ORCHESTRATOR_LLM_MODEL", "gemini-3.5-flash")) — re-deriving from env what
    # the ledger had already recorded. That default was correct when written, then
    # orchestrator/llm.py landed defaulting to gemini-2.5-flash and the two drifted:
    # with the env var unset (as .env.example ships it), auto runs EXECUTED on
    # 2.5-flash and were BILLED at the 3.5-flash rate — a 4x overcharge, which
    # test_auto_run_charges_actual_tokens_and_is_idempotent had been failing on.
    # An env guess can only ever be right by luck; a run may also legitimately span
    # several models (e.g. a Gemini citation planner alongside the main brain), and
    # one scalar multiplier cannot price that at all.
    rows = db.execute(
        select(
            TokenLedger.model,
            func.coalesce(
                func.sum(TokenLedger.prompt_tokens + TokenLedger.completion_tokens), 0
            ),
        )
        .where(
            TokenLedger.project_id == run.project_id,
            TokenLedger.created_at >= run.started_at,
        )
        .group_by(TokenLedger.model)
    ).all()
    total_tokens = sum(int(t or 0) for _, t in rows)
    if total_tokens <= 0:
        return
    from .pricing import credit_multiplier
    cost = max(1, round(sum(int(t or 0) / 1000 * credit_multiplier(m) for m, t in rows)))
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


def spawn_citation_search(project_id, run_id: int | None) -> bool:
    """Detach the M2 deep literature search from the request that triggered it.

    Deliberately lighter than the spawners below: no Job row, no events.jsonl,
    no monitor task. This job streams nothing — it searches for several minutes
    and writes one slice at the end — so the events plumbing would be machinery
    with no reader. Progress rides the ToolRun row the caller already opened,
    which is what /runs/active and the screen already poll.

    A separate PROCESS rather than a thread so it outlives the request, the
    worker, and an API restart — the whole point is that it takes longer than
    anything in the request lifecycle is allowed to.

    Returns whether it started. Never raises: the import that triggers this has
    already committed the student's modules, and failing to launch a background
    improvement must not turn a successful import into an error.
    """
    settings = get_settings()
    env = os.environ.copy()
    env["DATABASE_URL"] = os.environ.get("DATABASE_URL", "")
    # The scout resolves its planner and API keys from the environment
    # (m2_literature._engine_model reads OPENAI_API_KEY directly), and a
    # subprocess does not inherit what pydantic-settings loaded from .env.
    if settings.openai_api_key:
        env["OPENAI_API_KEY"] = settings.openai_api_key
    if settings.gemini_api_key:
        env["GEMINI_API_KEY"] = settings.gemini_api_key
        env["GOOGLE_API_KEY"] = settings.gemini_api_key

    cmd = [sys.executable, "-m", "app.citation_job", "--project-id", str(project_id)]
    if run_id:
        cmd.extend(["--run-id", str(run_id)])
    try:
        subprocess.Popen(
            cmd,
            cwd=str(Path(__file__).resolve().parents[1]),   # api/, so `app` imports
            env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,     # survives the API process going away
        )
        return True
    except Exception:  # noqa: BLE001
        log.exception("could not spawn the citation search for %s", project_id)
        return False


def spawn_headless_run(db: Session, run: Job, params: dict) -> None:
    """Spawn `python -m app.headless_entry` — the deep-agent twin of
    spawn_orchestrator_run. Reuses the events.jsonl contract so the existing
    _monitor works unchanged, which is exactly what makes C (auto-mode
    migration) a swap later: point THIS spawner at auto briefs instead of
    `python -m orchestrator --auto-draft`.
    """
    from .partner_run import mint_partner_token

    settings = get_settings()
    workdir = settings.job_workdir_root / str(run.id)
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "params.json").write_text(json.dumps(params), encoding="utf-8")
    (workdir / "events.jsonl").touch()

    # Mint the progress token HERE rather than trusting a caller-supplied one.
    # jobs.partner_token is UNIQUE and partner auth is a single shared secret,
    # so two callers echoing the same value would collide at INSERT. Assigning
    # at the spawner means every headless run gets a unique, unguessable token
    # no matter which router calls it. `or` (not a plain set) so a caller that
    # already minted one keeps it — this is a floor, not an override.
    run.partner_token = run.partner_token or mint_partner_token()

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
    if settings.anthropic_api_key:
        env["ANTHROPIC_API_KEY"] = settings.anthropic_api_key

    cmd = [sys.executable, "-m", "app.headless_entry",
           "--project-id", str(run.project_id),
           "--job-id", str(run.id),
           "--workdir", str(workdir),
           "--params-json", str(workdir / "params.json")]
    proc = subprocess.Popen(
        cmd,
        # repo root: `app`/`agent`/`orchestrator` resolve via editable installs,
        # `engine` via python -m's cwd-on-sys.path (same as the orchestrator spawn).
        cwd=str(Path(__file__).resolve().parents[2]),
        env=env,
    )
    run.pid = proc.pid
    run.workdir = str(workdir)
    run.status = "running"
    run.started_at = datetime.now(timezone.utc)
    db.commit()

    start_monitor(run.id)
