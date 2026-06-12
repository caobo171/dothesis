"""DbProjectStateStore — the v3 agent's state mapped onto the existing rows.

Verifies the flat agent shape round-trips through context_store slice columns
+ projects.module_status/focus, so the web's module tracker and ContextPanel
read agent-written state with zero changes.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app.agent_state import DbProjectStateStore
from app.db import get_engine
from app.models import ContextStore, Project, User


@pytest.fixture
def project_id():
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
        s.add(p); s.commit()
        return p.id


def _store(project_id, tmp_path):
    return DbProjectStateStore(get_engine(), project_id, tmp_path)


def test_fresh_project_reports_no_state(project_id, tmp_path):
    assert _store(project_id, tmp_path).read_slice("M1")["exists"] is False


def test_commit_lands_in_slice_columns_and_project_row(project_id, tmp_path):
    store = _store(project_id, tmp_path)
    store.commit_slice(
        "M1",
        {"research_title": "T", "research_questions": ["RQ?"]},
        reason="topic locked", confirm_done=True,
    )
    engine = get_engine()
    with Session(engine) as s:
        cs = s.get(ContextStore, project_id)
        p = s.get(Project, project_id)
    assert cs.m1_topic["research_title"] == "T"
    # done → confirmed_at set, so the legacy ContextPanel fallback agrees.
    assert cs.m1_topic["confirmed_at"]
    assert p.focus == "M1"
    assert p.module_status["M1"] == "done"


def test_propagation_flags_visible_to_web(project_id, tmp_path):
    store = _store(project_id, tmp_path)
    store.commit_slice("M1", {"research_title": "T"}, reason="r", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"id": "gap-1"}]}, reason="r", confirm_done=True)
    # Mutating M1 again flags M2 — exactly what module_status drives in the UI.
    store.commit_slice("M1", {"research_title": "T2"}, reason="pivot")
    with Session(get_engine()) as s:
        p = s.get(Project, project_id)
    assert p.module_status["M2"] == "needs_review"
    assert p.focus == "M1"


def test_state_shared_across_store_instances(project_id, tmp_path):
    _store(project_id, tmp_path).commit_slice(
        "M1", {"research_title": "shared"}, reason="r")
    # A second session/thread over the same project sees the commit.
    snap = _store(project_id, tmp_path).read_slice("M1")
    assert snap["slices"]["research_title"] == "shared"


def test_legacy_slice_keys_survive_agent_writes(project_id, tmp_path):
    # A project that graph_v2 touched has extra bookkeeping in the column;
    # agent commits must merge, not clobber.
    with Session(get_engine()) as s:
        s.add(ContextStore(project_id=project_id,
                           m1_topic={"_awaiting_field": "scope", "draft": "x"}))
        s.commit()
    _store(project_id, tmp_path).commit_slice(
        "M1", {"research_title": "T"}, reason="r")
    with Session(get_engine()) as s:
        cs = s.get(ContextStore, project_id)
    assert cs.m1_topic["research_title"] == "T"
    assert cs.m1_topic["_awaiting_field"] == "scope"
