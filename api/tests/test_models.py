import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.models import (
    ContextStore,
    Job,
    JobEvent,
    Message,
    Paper,
    Project,
    Session as UserSession,
    Thread,
    User,
)
from tests.conftest import make_user


def test_can_persist_full_object_graph():
    with OrmSession(get_engine()) as s:
        user = make_user(s, email="a@b.com")

        sess = UserSession(user_id=user.id, expires_at=datetime.now(timezone.utc) + timedelta(days=30))
        s.add(sess)

        paper = Paper(
            user_id=user.id,
            topic="topic",
            academic_level="master",
            language="en",
            citation_style="apa",
            model="gemini-flash",
            sources_json={"crossref": True},
        )
        s.add(paper)
        s.flush()

        job = Job(paper_id=paper.id, status="running", phase="research", progress=0.1)
        s.add(job)
        s.flush()

        s.add(JobEvent(job_id=job.id, type="activity", phase="research", text="hello"))
        s.commit()

        assert s.query(User).count() == 1
        assert s.query(UserSession).count() == 1
        assert s.query(Paper).count() == 1
        assert s.query(Job).count() == 1
        assert s.query(JobEvent).count() == 1




def test_project_thread_message_roundtrip():
    with OrmSession(get_engine()) as db:
        u = make_user(db)
        p = Project(user_id=u.id, name="Test", language="en", citation_style="apa")
        db.add(p)
        db.flush()
        t = Thread(project_id=p.id, name="Main", langgraph_thread_id=f"lg-{uuid.uuid4()}")
        db.add(t)
        db.flush()
        m = Message(thread_id=t.id, role="user", content="hello")
        db.add(m)
        db.commit()

        got = db.scalar(select(Message).where(Message.thread_id == t.id))
        assert got.content == "hello"
        assert got.role == "user"
        assert got.created_at is not None


def test_context_store_jsonb_roundtrip():
    with OrmSession(get_engine()) as db:
        u = make_user(db)
        p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
        db.add(p)
        db.flush()
        cs = ContextStore(project_id=p.id,
                          m1_topic={"research_title": "X", "objectives": ["a", "b"]})
        db.add(cs)
        db.commit()

        got = db.get(ContextStore, p.id)
        assert got.m1_topic == {"research_title": "X", "objectives": ["a", "b"]}
        assert got.m2_literature is None


def test_paper_upload_roundtrip():
    from app.models import PaperUpload
    with OrmSession(get_engine()) as db:
        u = make_user(db)
        p = Project(user_id=u.id, name="X", language="en", citation_style="apa")
        db.add(p); db.flush()
        up = PaperUpload(
            project_id=p.id, filename="paper.pdf",
            s3_uri="s3://bucket/key.pdf",
            size_bytes=12345, mime_type="application/pdf",
        )
        db.add(up); db.commit()

        got = db.scalar(select(PaperUpload).where(PaperUpload.project_id == p.id))
        assert got.filename == "paper.pdf"
        assert got.text_extracted_at is None
        assert got.uploaded_at is not None


def test_threads_can_have_many_per_project():
    with OrmSession(get_engine()) as db:
        u = make_user(db)
        p = Project(user_id=u.id, name="T", language="en", citation_style="apa")
        db.add(p)
        db.flush()
        for n in ("Main", "Alt", "Experiment"):
            db.add(Thread(project_id=p.id, name=n,
                          langgraph_thread_id=f"lg-{uuid.uuid4()}"))
        db.commit()
        rows = db.scalars(select(Thread).where(Thread.project_id == p.id)).all()
        assert {r.name for r in rows} == {"Main", "Alt", "Experiment"}
