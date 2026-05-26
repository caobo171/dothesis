"""Tests for the outer-state ↔ sub-graph-state translation layer."""
import uuid

import pytest
from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import PaperUpload, Project, User
from orchestrator.agents.m2.translation import (
    _flatten_to_m2_output, _seed_from_outer,
)
from orchestrator.state import ContextStore


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
