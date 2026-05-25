"""Verifies first-confirm-wins + alert on second commit to same module."""
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore, Project, User
from orchestrator.concurrency import (
    ContextCommitConflict, commit_module_output,
)


def _make_project(db: Session) -> Project:
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
             password_hash="x")
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
    db.add(p); db.flush()
    db.add(ContextStore(project_id=p.id))
    db.commit()
    # Eagerly load id before the session closes so the caller can access p.id
    # after the session context manager exits (plain Session() expires on commit).
    db.refresh(p)
    return p


def test_first_commit_wins_second_raises_conflict():
    with Session(get_engine()) as db:
        p = _make_project(db)

    blob = {"research_title": "X", "objectives": ["a"], "research_questions": ["q"],
            "field": "Marketing", "research_type": "quantitative",
            "target_population": "x", "scope": "y",
            "confirmed_at": datetime.now(timezone.utc).isoformat()}

    # Thread A commits first
    with Session(get_engine()) as db:
        commit_module_output(db, project_id=p.id, module="M1",
                             output=blob, thread_name="Main")
        db.commit()

    # Thread B tries to commit — must raise ContextCommitConflict
    with Session(get_engine()) as db, pytest.raises(ContextCommitConflict) as exc:
        commit_module_output(db, project_id=p.id, module="M1",
                             output={**blob, "research_title": "Y"},
                             thread_name="Alt")
        db.commit()
    assert "Main" in str(exc.value)


def test_unrelated_module_commit_still_succeeds():
    with Session(get_engine()) as db:
        p = _make_project(db)
    blob_m1 = {"confirmed_at": "2026-05-26T00:00:00+00:00", "research_title": "X"}
    blob_m2 = {"confirmed_at": "2026-05-26T00:00:00+00:00", "research_state_summary": "..."}
    with Session(get_engine()) as db:
        commit_module_output(db, project_id=p.id, module="M1",
                             output=blob_m1, thread_name="Main")
        commit_module_output(db, project_id=p.id, module="M2",
                             output=blob_m2, thread_name="Main")
        db.commit()
    with Session(get_engine()) as db:
        cs = db.get(ContextStore, p.id)
        assert cs.m1_topic["research_title"] == "X"
        assert cs.m2_literature["research_state_summary"] == "..."
