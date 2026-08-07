"""The background M2 literature search.

Pins the properties that make it safe to run unattended, minutes after the
request that started it has returned.
"""
import uuid

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore as DbContextStore, Project, User


def _project_with_topic(sources=None):
    """A project mid-import: M1 reconstructed, M2 holding the fast shallow set."""
    from app.agent_state import DbProjectStateStore
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M2", status="draft")
        s.add(p); s.commit()
        pid = p.id
    store = DbProjectStateStore(engine, pid, f"/tmp/ws-{pid}")
    store.commit_slice("M1", {"research_title": "KOL credibility and purchase intent",
                              "research_questions": ["RQ1"]},
                       reason="seed", confirm_done=True)
    store.commit_slice("M2", {"research_gaps": [{"description": "a gap"}],
                              "literature_sources": sources or []},
                       reason="seed")
    store.commit_slice("M3", {"conceptual_model": {"constructs": ["A"]}},
                       reason="seed", confirm_done=True)
    return pid


def _patch_search(monkeypatch, rows):
    import orchestrator.tools.domain_sources as DS
    import orchestrator.tools.m2_literature as M2

    class _Scout:
        def func(self, topic, min_n=10, **kw):
            self.kwargs = kw
            return rows
    scout = _Scout()
    monkeypatch.setattr(M2, "scout_citations", scout)
    monkeypatch.setattr(DS, "search_query_en", lambda t, rq: "kol credibility purchase")
    return scout


def _m2_of(pid):
    with Session(get_engine()) as s:
        return (s.get(DbContextStore, pid).m2_literature) or {}


def test_the_deep_sources_land_without_losing_the_rest_of_m2(monkeypatch):
    """It writes citations only — the gaps M2 already had must survive."""
    from app import citation_job
    pid = _project_with_topic()
    scout = _patch_search(monkeypatch, [
        {"title": "Real A", "doi": "10.1/a", "source": "Crossref"},
        {"title": "Real B", "doi": "10.1/b", "source": "OpenAlex"},
    ])
    assert citation_job.run(str(pid)) == 2

    m2 = _m2_of(pid)
    assert {s["doi"] for s in m2["literature_sources"]} == {"10.1/a", "10.1/b"}
    assert m2["citation_list"] == m2["literature_sources"]
    assert m2["research_gaps"]                       # not clobbered
    # This is the whole reason it runs out of band.
    assert scout.kwargs.get("deep") is True


def test_a_thin_deep_run_never_costs_the_student_citations(monkeypatch):
    """The import already committed real, on-topic sources. A deep run that
    comes back thin (provider trouble, an odd topic) must ADD to them, never
    replace them with less."""
    from app import citation_job
    pid = _project_with_topic(sources=[{"title": "From import", "doi": "10.9/import"}])
    _patch_search(monkeypatch, [{"title": "Real A", "doi": "10.1/a"}])
    citation_job.run(str(pid))

    dois = {s["doi"] for s in _m2_of(pid)["literature_sources"]}
    assert dois == {"10.9/import", "10.1/a"}


def test_filling_citations_does_not_flag_the_modules_below(monkeypatch):
    """Grounding M2 improves it; it does not invalidate the design built on it.
    Telling a student their finished M3 needs re-review because their
    bibliography got better is the bug we fixed for `language`."""
    from app import citation_job
    from app.agent_state import DbProjectStateStore
    pid = _project_with_topic()
    _patch_search(monkeypatch, [{"title": "Real A", "doi": "10.1/a"}])
    citation_job.run(str(pid))

    status = DbProjectStateStore(get_engine(), pid, f"/tmp/ws-{pid}").load()["status"]
    assert status["M3"] == "done"


def test_no_topic_is_not_a_failure(monkeypatch):
    """The import may not have reconstructed a title. Searching on nothing —
    or inventing a topic to search on — would both be worse than stopping."""
    from app import citation_job
    from app.agent_state import DbProjectStateStore
    engine = get_engine()
    with Session(engine) as s:
        u = User(email=f"t-{uuid.uuid4().hex[:8]}@x.com", username=uuid.uuid4().hex[:8],
                 password_hash="x", email_verified=True)
        s.add(u); s.flush()
        p = Project(user_id=u.id, name="T", current_module="M1", status="draft")
        s.add(p); s.commit()
        pid = p.id
    DbProjectStateStore(engine, pid, f"/tmp/ws-{pid}").commit_slice(
        "M4", {"analysis_results": "x" * 200}, reason="seed")
    scout = _patch_search(monkeypatch, [{"title": "Real A", "doi": "10.1/a"}])

    assert citation_job.run(str(pid)) == 0
    assert not hasattr(scout, "kwargs")              # never even searched


def test_a_search_that_explodes_leaves_m2_alone(monkeypatch):
    """It runs unattended with nobody to see a traceback, so a provider outage
    must cost the improvement and nothing else."""
    from app import citation_job
    import orchestrator.tools.m2_literature as M2
    pid = _project_with_topic(sources=[{"title": "From import", "doi": "10.9/import"}])

    class _Boom:
        def func(self, *a, **kw):
            raise RuntimeError("provider down")
    monkeypatch.setattr(M2, "scout_citations", _Boom())

    assert citation_job.run(str(pid)) == 0
    assert _m2_of(pid)["literature_sources"][0]["doi"] == "10.9/import"
