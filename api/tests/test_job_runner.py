import asyncio
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.orm import Session as OrmSession

from app.db import get_engine
from app.job_runner import _monitor
from app.models import Job, JobEvent, Paper
from app.pubsub import pubsub
from tests.conftest import make_user


def _make_running_job(tmp_path: Path) -> uuid.UUID:
    with OrmSession(get_engine()) as db:
        u = make_user(db)
        p = Paper(user_id=u.id, topic="t", academic_level="master", language="en",
                  citation_style="apa", model="gemini-flash", sources_json={}, status="running")
        db.add(p)
        db.flush()
        wd = tmp_path / str(uuid.uuid4())
        wd.mkdir()
        (wd / "events.jsonl").touch()
        j = Job(paper_id=p.id, status="running", workdir=str(wd))
        db.add(j)
        db.commit()
        return j.id


@pytest.mark.asyncio
async def test_monitor_ingests_lines_and_marks_done(tmp_path):
    job_id = _make_running_job(tmp_path)
    with OrmSession(get_engine()) as db:
        wd = Path(db.get(Job, job_id).workdir)

    sub = pubsub.subscribe(job_id)
    task = asyncio.create_task(_monitor(job_id))

    await asyncio.sleep(0.6)
    with (wd / "events.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "activity", "phase": "research", "agent": "Scout",
                             "text": "found a paper"}) + "\n")
        f.flush()
        f.write(json.dumps({"type": "phase_progress", "phase": "research", "progress": 0.5}) + "\n")
        f.flush()
        f.write(json.dumps({"type": "job_done", "exports": ["pdf"]}) + "\n")
        f.flush()

    await asyncio.wait_for(task, timeout=5)

    msgs = []
    while not sub.empty():
        msgs.append(sub.get_nowait())
    assert any(m["type"] == "activity" for m in msgs)
    assert any(m["type"] == "job_done" for m in msgs)

    with OrmSession(get_engine()) as db:
        j = db.get(Job, job_id)
        assert j.status == "done"
        assert j.progress == 1.0
        assert j.events_processed == 3
        assert db.query(JobEvent).filter(JobEvent.job_id == job_id).count() == 3
    pubsub.unsubscribe(job_id, sub)
