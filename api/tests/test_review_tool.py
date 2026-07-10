import json

import pytest

from agent.tools.writing import make_writing_tools


@pytest.fixture(autouse=True)
def _stub_judge_llm(monkeypatch):
    # review_thesis -> score_thesis fires the LLM-judge dims; stub _get_llm so no
    # test hits a live model (F0). Benign valid-JSON response.
    import orchestrator.tools.m5_writing as _m5

    class _Resp:
        content = '{"score": 0.7, "findings": []}'

    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: _Resp()})())


class _Store:
    """Test double: exposes the FULL nested context store plus the coaching
    typed getters review_thesis reads (F0: getters, not getattr)."""

    def __init__(self, advisor_feedback=None, institution_profile=None):
        self._advisor = advisor_feedback or []
        self._profile = institution_profile or {}

    def load_full_context_store(self):
        return {"m1_topic": {"research_title": "T", "research_questions": ["Q"]},
                "m3_design": {"methodology": "PLS-SEM"},
                "m4_analysis": {"analysis_results": "AVE=0.6"}}

    def get_advisor_feedback(self):
        return self._advisor

    def get_institution_profile(self):
        return self._profile


def test_review_thesis_returns_rubric():
    tools = {t.name: t for t in make_writing_tools(_Store())}
    assert "review_thesis" in tools
    out = json.loads(tools["review_thesis"].func())
    assert "overall" in out and "dimensions" in out


def test_review_thesis_surfaces_open_advisor_directive():
    # F0 integration test: a written advisor directive (status open) makes
    # review_thesis return a non-empty advisor dimension.
    fb = [{"id": "1", "chapter": "results", "issue": "Report effect sizes",
           "required_change": "add Cohen's f2", "status": "open"}]
    tools = {t.name: t for t in make_writing_tools(_Store(advisor_feedback=fb))}
    out = json.loads(tools["review_thesis"].func())
    adv = next(d for d in out["dimensions"] if d["name"] == "advisor")
    assert adv["findings"], "open advisor directive must produce a finding"
    assert out["advisor"]["open"] == fb
