"""F5 Task 3: the agent-layer analytics hook fires quality/advisor events.

Stubs agent.analytics.emit directly (F0: no live model, no app import) — the hook
defaults to a no-op, so instrumentation is inert until the app wires it. The
LLM-judge is stubbed too so review_thesis stays a pure-function assertion.
"""
import pytest

import agent.analytics as aa
from agent.tools.writing import make_writing_tools


@pytest.fixture(autouse=True)
def _stub_judge_llm(monkeypatch):
    # review_thesis -> score_thesis fires LLM-judge dims; stub _get_llm so no test
    # hits a live model (F0). Benign valid-JSON response.
    import orchestrator.tools.m5_writing as _m5

    class _Resp:
        content = '{"score": 0.7, "findings": []}'

    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())


class _Store:
    """Test double: the nested context store + the coaching typed getters
    review_thesis reads (matches the real store interface, F0)."""

    def load_full_context_store(self):
        return {"m1_topic": {"research_title": "T", "research_questions": ["Q"]},
                "m3_design": {"methodology": "PLS-SEM"},
                "m4_analysis": {"analysis_results": "AVE=0.6"}}

    def get_institution_profile(self):
        return {}

    def get_advisor_feedback(self):
        return []


def test_review_thesis_emits_quality_reviewed(monkeypatch):
    events = []
    monkeypatch.setattr(aa, "emit", lambda e, uid, props=None: events.append((e, props)))
    tools = {t.name: t for t in make_writing_tools(_Store())}
    tools["review_thesis"].func()
    assert any(e == "quality_reviewed" for e, _ in events)


def test_citation_rejected_emitted_for_uncited(monkeypatch):
    # F0 citation_rejected decision: emit from F3's citation dimension in
    # quality.rubric (quality already imports agent, so agent.analytics.emit is a
    # clean call with no new layering edge). An uncited (Author, Year) is the
    # hallucination catch.
    from quality.rubric import deterministic_dimensions

    events = []
    monkeypatch.setattr(aa, "emit", lambda e, uid, props=None: events.append((e, props)))
    cs = {"m5_writing": {"final_sections": [
        {"title": "Intro", "prose": "As shown (Ghost, 2099) this matters."}]}}
    deterministic_dimensions(cs)
    assert any(e == "citation_rejected" for e, _ in events)


def test_ingest_advisor_feedback_emits_event(monkeypatch, tmp_path):
    from agent.state import ProjectStateStore
    from agent.tools.state_tools import make_state_tools
    import agent.feedback as feedback

    # Stub the directive extractor (LLM) so this is a pure assertion.
    monkeypatch.setattr(feedback, "extract_directives",
                        lambda text: [{"issue": "Report effect sizes", "chapter": "results",
                                       "required_change": "add f2", "status": "open"}])
    events = []
    monkeypatch.setattr(aa, "emit", lambda e, uid, props=None: events.append((e, props)))
    tools = {t.name: t for t in make_state_tools(ProjectStateStore(tmp_path))}
    tools["ingest_advisor_feedback"].func("prof: add effect sizes")
    assert any(e == "advisor_feedback_ingested" for e, _ in events)


def test_mark_feedback_addressed_emits_event(monkeypatch, tmp_path):
    from agent.state import ProjectStateStore
    from agent.tools.state_tools import make_state_tools

    events = []
    monkeypatch.setattr(aa, "emit", lambda e, uid, props=None: events.append(e))
    store = ProjectStateStore(tmp_path)
    d = store.upsert_advisor_feedback({"issue": "x", "status": "open"})
    tools = {t.name: t for t in make_state_tools(store)}
    tools["mark_feedback_addressed"].func(d["id"])
    assert "advisor_feedback_addressed" in events
