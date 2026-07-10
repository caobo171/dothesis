"""Cross-project user memory (Phase 0) — whitelist, merge, isolation.

The whitelist is the safety boundary that keeps thesis content/citations out of
cross-project memory (anti-fabrication). These tests pin that boundary.
"""
import uuid

import pytest
from sqlalchemy.orm import Session

from app import user_memory as um  # F4: alias for the new keys/distill tests
from app.db import get_engine
from app.models import User
from app.user_memory import (
    ForbiddenMemoryKey,
    load_user_prefs,
    write_user_prefs,
)


def _new_user(s: Session) -> User:
    u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
             password_hash="x", email_verified=True)
    s.add(u); s.flush()
    return u


def test_load_empty_returns_dict():
    with Session(get_engine()) as s:
        u = _new_user(s); s.commit()
        assert load_user_prefs(s, u.id) == {}


def test_write_and_load_roundtrip():
    with Session(get_engine()) as s:
        u = _new_user(s); s.commit()
        write_user_prefs(s, u.id, {
            "field": "Marketing", "language": "vi", "citation_style": "apa",
        })
        s.commit()
        assert load_user_prefs(s, u.id) == {
            "field": "Marketing", "language": "vi", "citation_style": "apa",
        }


def test_forbidden_key_rejected():
    """Writing thesis content (e.g. literature_sources) must RAISE, not persist —
    this is the anti-fabrication guard."""
    with Session(get_engine()) as s:
        u = _new_user(s); s.commit()
        with pytest.raises(ForbiddenMemoryKey):
            write_user_prefs(s, u.id, {"literature_sources": [{"doi": "10.x"}]})
        with pytest.raises(ForbiddenMemoryKey):
            write_user_prefs(s, u.id, {"language": "en", "analysis_results": {"r2": 0.8}})
        # Nothing should have been written.
        assert load_user_prefs(s, u.id) == {}


def test_none_and_blank_values_skipped():
    with Session(get_engine()) as s:
        u = _new_user(s); s.commit()
        write_user_prefs(s, u.id, {"field": None, "language": "  ", "citation_style": "mla"})
        s.commit()
        assert load_user_prefs(s, u.id) == {"citation_style": "mla"}


def test_merge_preserves_other_keys_and_records_provenance():
    with Session(get_engine()) as s:
        u = _new_user(s); s.commit()
        pid = uuid.uuid4()
        write_user_prefs(s, u.id, {"field": "Finance"}, source_project_id=pid)
        s.commit()
        write_user_prefs(s, u.id, {"language": "en"})
        s.commit()
        assert load_user_prefs(s, u.id) == {"field": "Finance", "language": "en"}
        from app.user_memory import load_user_memory_row
        row = load_user_memory_row(s, u.id)
        assert row.prefs["field"]["source_project_id"] == str(pid)
        assert "updated_at" in row.prefs["field"]


def test_isolation_between_users():
    with Session(get_engine()) as s:
        a = _new_user(s); b = _new_user(s); s.commit()
        write_user_prefs(s, a.id, {"field": "Law"})
        s.commit()
        assert load_user_prefs(s, a.id) == {"field": "Law"}
        assert load_user_prefs(s, b.id) == {}


# -- F4: cross-project advisor learning ------------------------------------
def test_new_keys_allowed():
    assert {"institution_default", "recurring_advisor_themes"} <= um.USER_MEMORY_KEYS


def test_distill_writes_themes(monkeypatch):
    calls = {}
    monkeypatch.setattr(um, "write_user_prefs",
                        lambda db, uid, updates, **k: calls.update(updates))
    fb = [{"issue": "report effect sizes", "status": "addressed"},
          {"issue": "report effect sizes", "status": "addressed"}]
    um.distill_advisor_themes(db=None, user_id="u", advisor_feedback=fb, source_project_id=None)
    assert "recurring_advisor_themes" in calls


def test_distill_ignores_single_or_open(monkeypatch):
    # only-once or not-yet-addressed issues are NOT themes (needs recurrence >= 2).
    calls = {}
    monkeypatch.setattr(um, "write_user_prefs",
                        lambda db, uid, updates, **k: calls.update(updates))
    fb = [{"issue": "add effect sizes", "status": "addressed"},
          {"issue": "fix citations", "status": "open"}]
    um.distill_advisor_themes(db=None, user_id="u", advisor_feedback=fb)
    assert calls == {}
