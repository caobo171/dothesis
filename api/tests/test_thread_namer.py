"""Thread auto-naming — default detection, Tier-1 (free) from research_title,
and the guards that stop it overwriting hand-set names or re-running."""
import uuid

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore, Project, Thread, User
from app import thread_namer


def test_is_default_name():
    assert thread_namer._is_default_name("Main")
    assert thread_namer._is_default_name("  new thread ")
    assert thread_namer._is_default_name("Start at analysis")
    assert not thread_namer._is_default_name("Gen Z TikTok Study")


def test_shorten_trims_words_and_quotes():
    out = thread_namer._shorten('"A Study of Gen Z TikTok Livestream Buying Behaviour Among Urban Consumers"')
    assert out == "A Study of Gen Z TikTok Livestream Buying"
    assert not out.endswith(".")


def _seed(s: Session, *, thread_name="Main", name_auto=False, research_title=None):
    u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
             password_hash="x", email_verified=True)
    s.add(u); s.flush()
    p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
    s.add(p); s.flush()
    s.add(ContextStore(
        project_id=p.id,
        m1_topic=({"research_title": research_title} if research_title else None),
    ))
    t = Thread(project_id=p.id, name=thread_name, name_auto=name_auto,
               langgraph_thread_id=str(uuid.uuid4()))
    s.add(t); s.commit()
    return t.id


def test_tier1_names_from_research_title():
    eng = get_engine()
    with Session(eng) as s:
        tid = _seed(s, research_title="Parasocial Trust and Impulse Buying on TikTok Live")
    thread_namer.maybe_autoname_thread(eng, tid, "anything")
    with Session(eng) as s:
        t = s.get(Thread, tid)
        assert t.name == "Parasocial Trust and Impulse Buying on TikTok Live"
        assert t.name_auto is True


def test_skips_manual_name(monkeypatch):
    eng = get_engine()
    # Even if Tier-2 would fire, a non-default name must be left untouched.
    monkeypatch.setattr(thread_namer, "_from_llm", lambda *_: "SHOULD NOT APPLY")
    with Session(eng) as s:
        tid = _seed(s, thread_name="My custom thread")
    thread_namer.maybe_autoname_thread(eng, tid, "hello")
    with Session(eng) as s:
        assert s.get(Thread, tid).name == "My custom thread"


def test_skips_when_already_auto(monkeypatch):
    eng = get_engine()
    monkeypatch.setattr(thread_namer, "_from_llm", lambda *_: "NEW")
    with Session(eng) as s:
        tid = _seed(s, thread_name="Main", name_auto=True)
    thread_namer.maybe_autoname_thread(eng, tid, "hello")
    with Session(eng) as s:
        assert s.get(Thread, tid).name == "Main"


def test_tier2_fallback_when_no_research_title(monkeypatch):
    eng = get_engine()
    monkeypatch.setattr(thread_namer, "_from_llm", lambda text: "Cheap Summary Title")
    with Session(eng) as s:
        tid = _seed(s, research_title=None)
    thread_namer.maybe_autoname_thread(eng, tid, "I want to study X")
    with Session(eng) as s:
        t = s.get(Thread, tid)
        assert t.name == "Cheap Summary Title"
        assert t.name_auto is True
