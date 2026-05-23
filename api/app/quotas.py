import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Job, Paper

# A real concurrency constraint (one engine subprocess per user at a time).
# Cannot be raised without changing the subprocess model.
MAX_RUNNING_JOBS_PER_USER = 1

# Daily cap is MVP scaffolding for a future billing system. Off by default so users
# don't hit "429 Too Many Requests" with no warning. Set MAX_JOBS_PER_DAY env var
# to a positive int to re-enable. 0 (default) = unlimited.
MAX_JOBS_PER_DAY = int(os.environ.get("MAX_JOBS_PER_DAY", "0") or 0)


@dataclass
class QuotaError(Exception):
    code: str
    message: str

    def __post_init__(self) -> None:
        super().__init__(self.message)


def check_can_start_job(db: Session, user_id: uuid.UUID) -> None:
    running = db.scalar(
        select(func.count(Job.id))
        .join(Paper, Paper.id == Job.paper_id)
        .where(Paper.user_id == user_id, Job.status.in_(["queued", "running"]))
    )
    if running and running >= MAX_RUNNING_JOBS_PER_USER:
        raise QuotaError("already_running", "you already have a job in progress")

    # Daily cap is opt-in via env. When 0 (default), skip the check entirely.
    if MAX_JOBS_PER_DAY <= 0:
        return

    # Only successful or in-progress jobs count toward the daily cap.
    # Failed and canceled jobs do NOT — otherwise users get locked out by server-side errors.
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    started_today = db.scalar(
        select(func.count(Job.id))
        .join(Paper, Paper.id == Job.paper_id)
        .where(
            Paper.user_id == user_id,
            Job.started_at >= today_start,
            Job.status.in_(["queued", "running", "done"]),
        )
    )
    if started_today and started_today >= MAX_JOBS_PER_DAY:
        raise QuotaError("daily_quota", f"daily limit of {MAX_JOBS_PER_DAY} jobs reached")
