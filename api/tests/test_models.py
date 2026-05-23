from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.models import Job, JobEvent, Paper, Session as UserSession, User


def test_can_persist_full_object_graph():
    with OrmSession(get_engine()) as s:
        user = User(email="a@b.com", password_hash="x")
        s.add(user)
        s.flush()

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
