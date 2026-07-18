"""Tests for the outer-state ↔ sub-graph-state translation layer."""
import uuid

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import PaperUpload, Project, User
from orchestrator.agents.m2.translation import (
    _flatten_to_m2_output, _seed_from_outer,
)
from orchestrator.state import ContextStore


@pytest.fixture(autouse=True)
def _real_db(pg_url, monkeypatch):
    """Unlike its mock-only siblings, this module actually hits the DB via
    get_engine(). The agents-subtree conftest no-ops the parent's _bind_db, so
    without this the tests would connect to whatever stale local Postgres is
    configured — and fail on schema drift (e.g. a `projects` predating
    `last_nudge_at`). Bind a fresh testcontainer schema built from current models.
    """
    monkeypatch.setenv("DATABASE_URL", pg_url)
    from app.db import Base, get_engine as _ge, reset_engine_for_tests
    reset_engine_for_tests(pg_url)
    with _ge().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    Base.metadata.create_all(_ge())
    yield


def _make_user_project(db: Session) -> Project:
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
             username=f"u{uuid.uuid4().hex[:6]}", password_hash="x")
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
    db.add(p); db.flush()
    return p


def test_seed_from_outer_reads_m1_topic():
    with Session(get_engine()) as db:
        p = _make_user_project(db); db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [HumanMessage("hi")],
            "current_module": "M2",
            "context_store": ContextStore(
                m1_topic={
                    "research_title": "TL→EE",
                    "research_type": "quantitative",
                    "language": "vi",
                    "confirmed_at": "2026-05-26T00:00:00",
                },
            ),
            "mode": "interactive",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sub["research_title"] == "TL→EE"
        assert sub["research_type"] == "quantitative"
        assert sub["language"] == "vi"
        assert sub["paper_uris"] == []
        assert sub["current_phase"] == "familiarize"


def test_seed_from_outer_populates_paper_uris_from_uploads():
    with Session(get_engine()) as db:
        p = _make_user_project(db)
        for fn, uri in [("a.pdf", "s3://b/a.pdf"), ("b.pdf", "s3://b/b.pdf")]:
            db.add(PaperUpload(
                project_id=p.id, filename=fn, s3_uri=uri,
                size_bytes=100, mime_type="application/pdf",
            ))
        db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [], "current_module": "M2",
            "context_store": ContextStore(
                m1_topic={"research_title": "X", "research_type": "qualitative",
                          "language": "en", "confirmed_at": "2026-05-26"},
            ),
            "mode": "auto",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sorted(sub["paper_uris"]) == ["s3://b/a.pdf", "s3://b/b.pdf"]


def test_seed_restores_partial_work_from_context_store():
    with Session(get_engine()) as db:
        p = _make_user_project(db); db.commit()
        outer_state = {
            "project_id": p.id, "thread_id": uuid.uuid4(),
            "messages": [],
            "context_store": ContextStore(
                m1_topic={"research_title": "X", "research_type": "qualitative",
                          "language": "en", "confirmed_at": "2026-05-26"},
                m2_literature={
                    "research_state_summary": "draft so far...",
                    "research_gaps": [{"description": "g1"}],
                    "theoretical_framework": "F",
                    "literature_review_doc": "",
                    "citation_list": [],
                },
            ),
            "mode": "interactive",
        }
        sub = _seed_from_outer(outer_state, db)
        assert sub["research_state_draft"] == "draft so far..."


def test_flatten_complete_state_emits_full_m2_output():
    sub_state = {
        "current_phase": "DONE",
        "research_state_draft": "synthesis",
        "candidate_gaps": [{"description": "g1", "supporting_papers": [],
                            "relevance": "High", "confirmed": True}],
        "selected_gap_ids": ["0"],
        "verified_refs": [],
        "ch2_draft": "Chapter 2 draft",
        "citation_list": [{"author": "A", "year": 2024, "title": "T"}],
        "research_type": "quantitative",
    }
    out = _flatten_to_m2_output(sub_state)
    assert out["research_state_summary"] == "synthesis"
    assert out["literature_review_doc"] == "Chapter 2 draft"
    assert out["hypotheses"] == []
    assert out["citation_list"][0]["author"] == "A"
    assert "confirmed_at" in out


def test_flatten_partial_state_omits_confirmed_at():
    sub_state = {
        "current_phase": "gap_analysis",
        "research_state_draft": "partial",
        "candidate_gaps": [],
        "verified_refs": [],
        "ch2_draft": None,
        "citation_list": [],
        "research_type": "qualitative",
    }
    out = _flatten_to_m2_output(sub_state)
    assert out.get("confirmed_at") is None


def test_flatten_excludes_progress_emitter_from_phase_state():
    """Regression: M2Agent.step stashes engine.utils.progress's per-request
    emitter (a Python callable) into sub_state['_progress_emitter']. The
    catch-all `_phase_state` writer used to include it, and the callable
    rode into context_store.m2_literature → outer postgres checkpoint →
    msgpack crash ('Type is not msgpack serializable: ContextStore').

    The emitter is re-attached fresh from the registry on every M2 entry,
    so dropping it from the persisted snapshot loses nothing. Pinning this
    contract here so a future refactor can't silently re-introduce the leak.
    """
    sub_state = {
        "current_phase": "research_state",   # mid-M2 → triggers _phase_state path
        "research_state_draft": "partial",
        "candidate_gaps": [],
        "_progress_emitter": lambda payload: None,
        "research_type": "quantitative",
    }
    out = _flatten_to_m2_output(sub_state)
    assert "_phase_state" in out, "mid-M2 must persist the working sub-state"
    assert "_progress_emitter" not in out["_phase_state"], (
        "_progress_emitter must be filtered out — it's an unserializable "
        "callable that would crash the postgres checkpointer."
    )

    # Belt-and-braces: round-trip through the actual LangGraph serializer
    # so a future change to _SEEDED_INPUT_KEYS that re-allows a callable
    # fails here even if the field name changes.
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    cs = ContextStore(m2_literature=out)
    # Should not raise.
    JsonPlusSerializer().dumps_typed(cs)
