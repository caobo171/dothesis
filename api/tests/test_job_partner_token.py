"""jobs.partner_token maps the partner's opaque progress_token to the Job row —
the durable, multi-process replacement for the in-memory _PROGRESS dict."""
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Job


def test_partner_token_round_trips():
    with Session(get_engine()) as s:
        j = Job(paper_id=None, project_id=uuid.uuid4(), mode="partner",
                status="queued", partner_token="tok-123")
        s.add(j)
        s.commit()
        got = s.scalar(select(Job).where(Job.partner_token == "tok-123"))
        assert got is not None and got.id == j.id


def test_partner_token_is_optional():
    # Every pre-existing Job row (and every non-partner run) has no token, so the
    # column must stay nullable — a NOT NULL here would break the whole jobs table.
    with Session(get_engine()) as s:
        j = Job(paper_id=None, project_id=uuid.uuid4(), mode="auto", status="queued")
        s.add(j)
        s.commit()
        assert j.partner_token is None


def test_duplicate_partner_token_is_rejected():
    # The token is caller-supplied and partner auth is one global shared secret
    # with no partner-id claim, so two partners CAN send the same token. Without
    # the unique index the progress poll would silently resolve to whichever row
    # Postgres returned — one partner reading another's progress. This pins the
    # collision as a loud IntegrityError the write path is forced to handle.
    with Session(get_engine()) as s:
        s.add(Job(paper_id=None, project_id=uuid.uuid4(), mode="partner",
                  status="queued", partner_token="tok-collide"))
        s.commit()
    with Session(get_engine()) as s:
        s.add(Job(paper_id=None, project_id=uuid.uuid4(), mode="partner",
                  status="queued", partner_token="tok-collide"))
        with pytest.raises(IntegrityError):
            s.commit()


def test_many_null_partner_tokens_coexist():
    # The property that makes unique + nullable safe: Postgres treats each NULL
    # as distinct, so the unique index does NOT collapse the (many) non-partner
    # jobs that carry no token. Pinned so nobody "fixes" the uniqueness away
    # believing it conflicts with the column being optional.
    with Session(get_engine()) as s:
        jobs = [Job(paper_id=None, project_id=uuid.uuid4(), mode="auto", status="queued")
                for _ in range(3)]
        s.add_all(jobs)
        s.commit()
        assert all(j.partner_token is None for j in jobs)
        assert len({j.id for j in jobs}) == 3
