from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.models import Job, Paper
from app import quotas as quotas_module
from tests.conftest import make_user
from app.quotas import (
    MAX_RUNNING_JOBS_PER_USER,
    QuotaError,
    check_can_start_job,
)

# Tests below intentionally enable the daily cap (defaults to 0/off in production).
# Each test that touches it sets quotas_module.MAX_JOBS_PER_DAY explicitly.
DAILY_CAP_FOR_TESTS = 3


def _user(db):
    return make_user(db)


def _paper(db, u):
    p = Paper(user_id=u.id, topic="t", academic_level="master", language="en",
              citation_style="apa", model="gemini-flash", sources_json={})
    db.add(p)
    db.flush()
    return p


def test_passes_when_no_jobs():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        check_can_start_job(db, u.id)  # no raise


def test_blocks_when_already_running():
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        db.add(Job(paper_id=p.id, status="running"))
        db.commit()
        with pytest.raises(QuotaError) as excinfo:
            check_can_start_job(db, u.id)
        assert excinfo.value.code == "already_running"


@pytest.fixture
def daily_cap_enabled(monkeypatch):
    monkeypatch.setattr(quotas_module, "MAX_JOBS_PER_DAY", DAILY_CAP_FOR_TESTS)
    yield DAILY_CAP_FOR_TESTS


def test_daily_cap_off_by_default():
    """When MAX_JOBS_PER_DAY <= 0, the daily check is skipped entirely."""
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        # Many successful runs today — still allowed because cap is disabled by default.
        for _ in range(50):
            db.add(Job(paper_id=p.id, status="done", started_at=now))
        db.commit()
        check_can_start_job(db, u.id)  # no raise


def test_blocks_when_daily_cap_reached(daily_cap_enabled):
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        for _ in range(daily_cap_enabled):
            db.add(Job(paper_id=p.id, status="done", started_at=now))
        db.commit()
        with pytest.raises(QuotaError) as excinfo:
            check_can_start_job(db, u.id)
        assert excinfo.value.code == "daily_quota"


def test_does_not_count_jobs_from_yesterday(daily_cap_enabled):
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        yesterday = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
        for _ in range(daily_cap_enabled):
            db.add(Job(paper_id=p.id, status="done", started_at=yesterday))
        db.commit()
        check_can_start_job(db, u.id)  # no raise


def test_failed_jobs_do_not_count_against_daily_cap(daily_cap_enabled):
    """Failed jobs are usually engine/upstream errors. Users shouldn't be locked out by them."""
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        for _ in range(daily_cap_enabled + 2):
            db.add(Job(paper_id=p.id, status="failed", started_at=now))
        db.commit()
        check_can_start_job(db, u.id)  # no raise — failed jobs are free retries


def test_canceled_jobs_do_not_count_against_daily_cap(daily_cap_enabled):
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        for _ in range(daily_cap_enabled + 2):
            db.add(Job(paper_id=p.id, status="canceled", started_at=now))
        db.commit()
        check_can_start_job(db, u.id)  # no raise


def test_mixed_done_and_failed_counts_only_done(daily_cap_enabled):
    """2 successful + N failed should still allow more (under cap of 3 on successes)."""
    with OrmSession(get_engine()) as db:
        u = _user(db)
        p = _paper(db, u)
        now = datetime.now(timezone.utc)
        db.add(Job(paper_id=p.id, status="failed", started_at=now))
        db.add(Job(paper_id=p.id, status="failed", started_at=now))
        db.add(Job(paper_id=p.id, status="done", started_at=now))
        db.add(Job(paper_id=p.id, status="done", started_at=now))
        db.commit()
        check_can_start_job(db, u.id)  # 2/3 done under cap, no raise
