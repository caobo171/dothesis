"""Report-only grounding of the M2 backfill with a REAL literature search.

The headless report populates M2 via reconstruct_upstream (pure LLM recall) — no
DOIs. With the report opt-in (ground_m2 / env DOTHESIS_BACKFILL_GROUND_M2) the M2
candidate is grounded with a real deep scout + domain supplement. Chat/import
backfill (no opt-in) stays LLM-fast. No network/LLM — everything is faked.
"""
from unittest.mock import MagicMock

import orchestrator.backfill as B
import orchestrator.tools.domain_sources as DS
import orchestrator.tools.m2_literature as M2mod
from orchestrator.state import ContextStore

# A valid-enough M2 candidate JSON so reconstruct_artifact returns non-empty.
_M2_LLM_JSON = ('{"citation_list": [{"title": "LLM recalled", "authors": ["X"], '
                '"year": 2019}], "research_gaps": [{"description": "a gap"}]}')


def _fake_llm(content=_M2_LLM_JSON) -> MagicMock:
    llm = MagicMock()
    llm.invoke.return_value.content = content
    return llm


class _CountingScout:
    def __init__(self, rows=None, raises=False):
        self.calls = 0
        self.rows = rows or []
        self.raises = raises

    def func(self, topic, min_n=10, **kwargs):
        self.calls += 1
        self.kwargs = kwargs          # what the caller asked the planner for
        if self.raises:
            raise RuntimeError("scout blew up")
        return self.rows


class _FakeERIC:
    def search_papers(self, q, limit=10):
        return [{"title": "ERIC edu row", "authors": ["Tran"], "year": 2020,
                 "doi": "", "url": "https://eric.ed.gov/?id=EJ9"}]


def _edu_cs():
    return ContextStore(
        m1_topic={"research_title": "Language learning via Duolingo in education",
                  "field": "Education", "research_questions": ["RQ1 teaching methods"]},
        m4_analysis={"data_type_detected": "Quantitative", "results": {"n": 1}},
    )


def _m2_entry(out):
    return next(e for e in out if e["module"] == "M2")


def _patch_search(monkeypatch, scout, eric=True):
    monkeypatch.setattr(M2mod, "scout_citations", scout)
    monkeypatch.setattr(DS, "search_query_en", lambda t, rq: "duolingo language learning")
    if eric:
        monkeypatch.setattr(DS, "EricClient", _FakeERIC)


def test_report_optin_grounds_m2_with_real_dois(monkeypatch):
    scout = _CountingScout([{"title": "Real edtech", "authors": ["Ng"], "year": 2021,
                             "source": "OpenAlex", "doi": "10.1/real", "url": "u"}])
    _patch_search(monkeypatch, scout)
    out = B.reconstruct_upstream(_edu_cs(), targets=["M2"], llm=_fake_llm(), ground_m2=True)
    cand = _m2_entry(out)["candidate"]
    dois = {s.get("doi") for s in cand["literature_sources"]}
    assert scout.calls == 1
    assert "10.1/real" in dois                       # real base DOI
    assert any(s["title"] == "ERIC edu row" for s in cand["literature_sources"])  # domain supp
    assert cand["citation_list"] == cand["literature_sources"]  # both keys carry the real list


def test_chat_backfill_is_grounded_too(monkeypatch):
    """Was `test_chat_backfill_stays_llm_only` — grounding is now the default.

    The old behaviour traded correctness for latency: an ungrounded backfill
    ships whatever sources the MODEL recalled, and those entries become the
    citation_list, i.e. the bibliography of a document the student submits under
    their own name. A model's recollection of citations is not citations, and a
    thesis is the last place to guess. The search is bounded and degrades to the
    LLM candidate on failure (see test_search_failure_degrades_to_llm), so the
    cost of being wrong here is a slower import, not a broken one."""
    scout = _CountingScout([{"title": "Real", "doi": "10.1/x", "source": "OpenAlex"}])
    _patch_search(monkeypatch, scout)
    monkeypatch.delenv("DOTHESIS_BACKFILL_GROUND_M2", raising=False)
    out = B.reconstruct_upstream(_edu_cs(), targets=["M2"], llm=_fake_llm())  # ground_m2 unset
    cand = _m2_entry(out)["candidate"]
    assert scout.calls == 1                           # scouted without being asked
    assert any(s.get("doi") == "10.1/x" for s in cand["literature_sources"])
    assert cand["citation_list"] == cand["literature_sources"]


def test_env_var_triggers_grounding(monkeypatch):
    scout = _CountingScout([{"title": "Real", "doi": "10.1/x", "source": "OpenAlex"}])
    _patch_search(monkeypatch, scout)
    monkeypatch.setenv("DOTHESIS_BACKFILL_GROUND_M2", "1")
    B.reconstruct_upstream(_edu_cs(), targets=["M2"], llm=_fake_llm())
    assert scout.calls == 1


def test_search_failure_degrades_to_llm(monkeypatch):
    # general-domain topic (no supplement) + scout raises → keep the LLM candidate
    cs = ContextStore(
        m1_topic={"research_title": "Brand loyalty in e-commerce", "field": "Marketing",
                  "research_questions": ["RQ1"]},
        m4_analysis={"data_type_detected": "Quantitative", "results": {"n": 1}})
    scout = _CountingScout(raises=True)
    monkeypatch.setattr(M2mod, "scout_citations", scout)
    monkeypatch.setattr(DS, "search_query_en", lambda t, rq: "brand loyalty")
    out = B.reconstruct_upstream(cs, targets=["M2"], llm=_fake_llm(), ground_m2=True)
    cand = _m2_entry(out)["candidate"]
    assert scout.calls == 1
    assert "literature_sources" not in cand           # empty real search → untouched
    assert cand["citation_list"][0]["title"] == "LLM recalled"


def test_no_topic_skips_search(monkeypatch):
    scout = _CountingScout([{"title": "Real", "doi": "10.1/x"}])
    monkeypatch.setattr(M2mod, "scout_citations", scout)
    cs = ContextStore(m4_analysis={"data_type_detected": "Quantitative", "results": {"n": 1}})
    assert B._m2_real_sources(cs) == []               # no research_title
    assert scout.calls == 0


def test_the_backfill_asks_for_a_plan_that_can_finish(monkeypatch):
    """The grounded search must not use the deep planner from inside a request.

    At the engine's defaults the deep planner emitted 249 queries for one
    thesis title, each allowed 90s. It could never finish inside
    _m2_real_sources' deadline, so the future timed out, the except swallowed
    it, and every real DOI already found was discarded — grounding was on by
    default, cost two minutes of the student's import, and always returned [].
    """
    scout = _CountingScout([{"title": "Real", "doi": "10.1/x", "source": "OpenAlex"}])
    _patch_search(monkeypatch, scout)
    B.reconstruct_upstream(_edu_cs(), targets=["M2"], llm=_fake_llm(), ground_m2=True)
    assert scout.calls == 1
    assert scout.kwargs.get("deep") is False
