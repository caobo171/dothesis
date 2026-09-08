"""Publishing part of the bank without lying about when it was written."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.blog import STATUS_DRAFT, STATUS_PUBLISHED, STATUS_SCHEDULED, cli
from app.blog.schedule import VN_TZ
from app.db import get_session_factory
from app.models import BlogPost


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


def _waiting(db, n):
    """A queue of posts still waiting their turn, one per day."""
    for i in range(n):
        when = datetime(2026, 11, 1, tzinfo=timezone.utc) + timedelta(days=i)
        db.add(BlogPost(locale="vi", slug=f"post-{i:03d}", title=f"Post {i}",
                        body="x", excerpt="x", status=STATUS_SCHEDULED,
                        scheduled_at=when, published_at=when))
    db.commit()


def test_publishing_marks_them_live_today_newest_first(db):
    _waiting(db, 5)
    assert cli.main(["publish", "--count", "3"]) == 0

    rows = db.scalars(select(BlogPost).order_by(BlogPost.slug)).all()
    live = [p for p in rows if p.status == STATUS_PUBLISHED]
    assert len(live) == 3
    today = datetime.now(timezone.utc).date()
    for p in live:
        assert p.published_at.date() == today, "published today, not backdated"
        assert p.scheduled_at is None

    # Priority order survives as listing order: post-000 is the newest.
    by_slug = {p.slug: p.published_at for p in live}
    assert by_slug["post-000"] > by_slug["post-001"] > by_slug["post-002"]

    waiting = [p for p in rows if p.status == STATUS_SCHEDULED]
    assert len(waiting) == 2, "the rest keep their dates"


def test_a_dry_run_changes_nothing(db):
    _waiting(db, 4)
    assert cli.main(["publish", "--count", "2", "--dry-run"]) == 0
    assert db.scalars(select(BlogPost).where(BlogPost.status == STATUS_PUBLISHED)).all() == []


def test_the_remainder_can_be_respread_in_one_pass(db):
    _waiting(db, 10)
    assert cli.main(["publish", "--count", "4", "--rest-from", "2026-10-01",
                     "--per-week", "2"]) == 0

    rest = db.scalars(select(BlogPost).where(BlogPost.status == STATUS_SCHEDULED)
                      .order_by(BlogPost.scheduled_at)).all()
    assert len(rest) == 6
    # The cadence is read in Vietnam time: the audience and the supervisor
    # deadlines this blog is written for are both there, so a post dated the
    # first of the month should be the first of the month in Hanoi.
    assert rest[0].scheduled_at.astimezone(VN_TZ).date() == datetime(2026, 10, 1).date()
    # Two a week, so the third waiting post starts the second week.
    assert rest[2].scheduled_at.astimezone(VN_TZ).date() == datetime(2026, 10, 8).date()


def test_a_draft_is_never_published_by_count(db):
    _waiting(db, 2)
    db.add(BlogPost(locale="vi", slug="draft-1", title="Draft", body="x",
                    excerpt="x", status=STATUS_DRAFT))
    db.commit()

    cli.main(["publish", "--count", "50"])
    draft = db.scalar(select(BlogPost).where(BlogPost.slug == "draft-1"))
    assert draft.status == STATUS_DRAFT, "a draft is not waiting, it is unfinished"


def test_publishing_an_empty_queue_says_so(db, capsys):
    assert cli.main(["publish", "--count", "5"]) == 0
    assert "Nothing is waiting" in capsys.readouterr().out
