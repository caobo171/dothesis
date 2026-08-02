"""The humanize style anchor is asked for ONCE, then remembered.

Why this matters: skills/dothesis-humanize/references/anchors ships with
`{"anchors": []}` on purpose — an anchor has to be off the LLM training
distribution, so it cannot be generated. Without a stored per-user sample,
humanize_prose returns `no_anchor` on every call forever.
"""
import uuid

from app.agent_state import DbProjectStateStore
from app.db import get_session_factory
from app.models import Project, User
from app.user_memory import USER_MEMORY_KEYS, load_user_prefs

ANCHOR = (
    "Trong quá trình học tập tại trường, tôi nhận thấy rằng việc vận dụng lý "
    "thuyết vào thực tiễn luôn gặp nhiều khó khăn hơn so với những gì sách vở "
    "mô tả. Bài viết này ghi lại một vài quan sát của riêng tôi."
)


def _seed():
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"a{uuid.uuid4().hex[:6]}@x", username=f"a{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.flush()
        p = Project(user_id=u.id, name="T")
        db.add(p); db.commit()
        return u.id, p.id


def test_writing_anchor_is_whitelisted():
    # It is NOT in the whitelist by default — the layer's docstring says it
    # "must never hold thesis content", so this key was added deliberately.
    assert "writing_anchor" in USER_MEMORY_KEYS


def test_store_round_trips_the_anchor_for_the_project_owner(tmp_path):
    uid, pid = _seed()
    sf = get_session_factory()
    store = DbProjectStateStore(sf.kw["bind"], pid, tmp_path)

    # Nothing saved yet -> the tool must fall through to asking.
    assert store.load_writing_anchor() is None

    store.save_writing_anchor(ANCHOR)

    # Readable back through the store...
    assert store.load_writing_anchor() == ANCHOR
    # ...and landed on the USER, not the project — that is what makes it work
    # across a student's second thesis without asking again.
    with sf() as db:
        assert load_user_prefs(db, uid)["writing_anchor"] == ANCHOR


def test_blank_anchor_is_not_saved(tmp_path):
    _uid, pid = _seed()
    sf = get_session_factory()
    store = DbProjectStateStore(sf.kw["bind"], pid, tmp_path)
    store.save_writing_anchor("   ")
    assert store.load_writing_anchor() is None


def test_save_is_best_effort_and_never_raises(tmp_path):
    # A telemetry-ish write must not fail the humanize turn the student asked
    # for: they should still get their rewrite, just get asked again next time.
    sf = get_session_factory()
    store = DbProjectStateStore(sf.kw["bind"], uuid.uuid4(), tmp_path)  # no such project
    store.save_writing_anchor(ANCHOR)          # must not raise
    assert store.load_writing_anchor() is None
