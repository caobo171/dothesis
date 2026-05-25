"""Verify first-confirm-wins semantics with the agent's commit path."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore, Project, Thread, User
from orchestrator.concurrency import ContextCommitConflict, commit_module_output

pytestmark = pytest.mark.integration


def _make_project(db: Session):
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
             username=f"u{uuid.uuid4().hex[:6]}", password_hash="x")
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="X", language="en", citation_style="apa")
    db.add(p); db.flush()
    for n in ("Main", "Alt"):
        db.add(Thread(project_id=p.id, name=n,
                      langgraph_thread_id=f"lg-{uuid.uuid4()}"))
    db.add(ContextStore(project_id=p.id))
    db.commit()
    return p


def test_second_confirm_raises_with_first_thread_name():
    # Read project_id inside the session so it is not detached when used below.
    with Session(get_engine()) as db:
        p = _make_project(db)
        project_id = p.id  # capture while session is open

    payload = {"research_title": "X", "objectives": ["a"], "research_questions": ["q"],
               "field": "Marketing", "research_type": "quantitative",
               "target_population": "p", "scope": "s",
               "confirmed_at": datetime.now(timezone.utc).isoformat()}

    with Session(get_engine()) as db:
        commit_module_output(db, project_id=project_id, module="M1",
                             output=payload, thread_name="Main")
        db.commit()

    with Session(get_engine()) as db, pytest.raises(ContextCommitConflict) as exc:
        commit_module_output(db, project_id=project_id, module="M1",
                             output={**payload, "research_title": "Y"},
                             thread_name="Alt")
        db.commit()
    assert exc.value.existing_thread_name == "Main"
    assert exc.value.module == "M1"
