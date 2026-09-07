"""The save-time duplicate block, ported from WELE's `blog.duplicate.guard`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.blog.guard import (
    MIN_OVERRIDE_LENGTH,
    assert_no_duplicate,
    build_candidates,
    build_refusal,
)
from app.blog.similarity import Clash, find_clashes
from app.db import get_session_factory
from app.models import BlogPost

NOW = datetime.now(timezone.utc)


def _post(db, slug, focus, *, status=1, scheduled_at=None, locale="vi"):
    p = BlogPost(
        locale=locale, slug=slug, title=slug.replace("-", " "), body="x",
        focus_keyword=focus, status=status, scheduled_at=scheduled_at,
        published_at=NOW if status == 1 else None,
    )
    db.add(p)
    db.commit()
    return p


@pytest.fixture
def db():
    with get_session_factory()() as s:
        yield s


# --- the refusal message ---------------------------------------------------

def test_refusal_names_slug_overlap_keyword_and_intent():
    msg = build_refusal([Clash(slug="cronbach-alpha-la-gi", title="t",
                               focus="cronbach alpha", score=0.83, intent="definition")])
    assert "cronbach-alpha-la-gi" in msg
    assert "83%" in msg
    assert "cronbach alpha" in msg
    assert "definition" in msg
    assert "duplicate_override_reason" in msg


def test_refusal_names_every_clashing_post():
    clashes = [
        Clash(slug="first", title="t", focus="k", score=0.9, intent="definition"),
        Clash(slug="second", title="t", focus="k", score=0.7, intent="definition"),
    ]
    msg = build_refusal(clashes)
    assert "first" in msg and "second" in msg


# --- candidate construction ------------------------------------------------

def test_only_keyworded_posts_become_candidates():
    class P:
        def __init__(self, slug, focus):
            self.id, self.slug, self.locale, self.focus_keyword = slug, slug, "vi", focus

    cands = build_candidates([P("has", "cronbach alpha"), P("empty", ""),
                              P("null", None), P("blank", "   ")])
    assert [c.slug for c in cands] == ["has"]
    # Never a title: that closes off find_clashes' focus-or-title fallback,
    # which is the mechanism WELE's 2026-09-07 calibration found unusable.
    assert all(c.title == "" for c in cands)


def test_a_keywordless_post_cannot_collide_with_anyone():
    class P:
        def __init__(self, slug, focus):
            self.id, self.slug, self.locale, self.focus_keyword = slug, slug, "vi", focus

    subject_like = build_candidates([P("keyworded", "phân tích efa là gì")])
    assert len(find_clashes(subject_like[0], build_candidates([P("silent", None)]))) == 0


# --- assert_no_duplicate ---------------------------------------------------

def test_a_subject_with_no_focus_keyword_is_never_blocked(db):
    _post(db, "existing", "cronbach alpha là gì")
    for seed in ({"locale": "vi"}, {"locale": "vi", "focus_keyword": "   "}):
        result = assert_no_duplicate(db, seed)
        assert result.blocked is False
        assert result.clashes == []


def test_a_published_post_on_the_same_keyword_blocks(db):
    _post(db, "cronbach-alpha-la-gi", "cronbach alpha là gì")
    result = assert_no_duplicate(db, {"locale": "vi", "focus_keyword": "hệ số cronbach alpha là gì"})
    assert result.blocked is True
    assert "cronbach-alpha-la-gi" in result.message


def test_a_draft_never_blocks(db):
    _post(db, "draft-post", "cronbach alpha là gì", status=0)
    result = assert_no_duplicate(db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì"})
    assert result.blocked is False


def test_a_future_scheduled_post_still_blocks(db):
    # It is not visible yet, but it already owns the keyword and will publish
    # itself. See the guard's header: a `create` run inserts almost everything
    # future-scheduled, so keying candidates on visibility would make the CLI's
    # per-seed guard a no-op against its own batch.
    _post(db, "queued", "cronbach alpha là gì", status=2,
          scheduled_at=NOW + timedelta(days=30))
    result = assert_no_duplicate(db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì"})
    assert result.blocked is True


def test_another_locale_never_blocks(db):
    _post(db, "en-post", "cronbach alpha là gì", locale="en")
    result = assert_no_duplicate(db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì"})
    assert result.blocked is False


def test_a_different_intent_never_blocks(db):
    _post(db, "howto", "cách chạy cronbach alpha trong spss")
    result = assert_no_duplicate(db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì"})
    assert result.blocked is False


def test_a_long_enough_override_lets_it_through_but_still_reports(db):
    _post(db, "cronbach-alpha-la-gi", "cronbach alpha là gì")
    reason = "Bài này nhắm vào ngưỡng cho thang đo hai biến quan sát, khác hẳn bài kia."
    assert len(reason) >= MIN_OVERRIDE_LENGTH
    result = assert_no_duplicate(
        db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì",
             "duplicate_override_reason": reason})
    assert result.blocked is False
    assert [c.slug for c in result.clashes] == ["cronbach-alpha-la-gi"]


def test_a_short_override_does_not(db):
    _post(db, "cronbach-alpha-la-gi", "cronbach alpha là gì")
    result = assert_no_duplicate(
        db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì",
             "duplicate_override_reason": "vì tôi muốn"})
    assert result.blocked is True


def test_a_post_never_blocks_itself_on_update(db):
    existing = _post(db, "cronbach-alpha-la-gi", "cronbach alpha là gì")
    result = assert_no_duplicate(
        db, {"locale": "vi", "focus_keyword": "cronbach alpha là gì"},
        exclude_id=existing.id)
    assert result.blocked is False
