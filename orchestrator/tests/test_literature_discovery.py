from orchestrator.tools.literature_discovery import discover_literature
import time
import pytest


@pytest.fixture(autouse=True)
def isolated_research_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "cache"))


def test_discovers_across_facets_providers_and_dedupes_without_verifying():
    calls=[]
    def a(q): calls.append(("a",q)); return [{"title":"trust adoption One","doi":"10.1/X","abstract":"trust adoption"}]
    def b(q): calls.append(("b",q)); return [{"title":"trust adoption Duplicate","doi":"10.1/x"},{"title":"trust adoption Two","year":2024}]
    out=discover_literature("topic",min_sources=3,llm_fn=lambda _: {"queries":[{"query":"trust adoption","facet":"construct"}]},providers={"a":a,"b":b})
    assert out["count"]==0 and len(out["unverified_candidates"])==2 and out["shortfall"]==3 and not out["complete"]
    assert {q for _,q in calls} == {"trust adoption"}


def test_existing_identity_and_provider_failure_leave_honest_partial_result():
    def bad(_): raise RuntimeError()
    out=discover_literature("topic",min_sources=2,existing_sources=[{"doi":"10.1/x","verified":False}],providers={"bad":bad})
    assert out["count"]==1 and out["verified_count"]==0 and out["shortfall"]==2 and out["warnings"]


def test_identity_resolver_controls_verified_not_doi_presence():
    provider={"p": lambda q: [{"title":"topic exact paper","doi":"10.1/exact","abstract":"topic exact"},{"title":"topic wrong paper","doi":"10.1/wrong","abstract":"topic wrong"}]}
    out=discover_literature("topic",llm_fn=lambda _: {"queries":["topic paper"]},providers=provider,identity_resolver=lambda source, _: source["doi"] == "10.1/exact")
    assert [source["verified"] for source in out["sources"]] == [True]
    assert len(out["unverified_candidates"]) == 1


def test_structured_planner_facets_drive_coverage_and_preserve_provider_metadata():
    def llm(_):
        return {"queries": [{"query": "trust adoption model", "facet": "mechanism"},
                             {"query": "trust adoption context", "facet": "context"},
                             {"query": "trust adoption method", "facet": "method"},
                             {"query": "trust adoption gap", "facet": "gap"}]}
    def provider(query):
        return [{"title": query, "doi": "10.1/" + query[-3:], "abstract": "Trust adoption evidence.",
                 "provider": "mock", "venue": "Journal"}]
    out = discover_literature("Vietnamese topic", llm_fn=llm, providers={"mock": provider},
                              identity_resolver=lambda *_: True)
    assert len(out["queries"]) >= 4
    assert all(source["verified"] for source in out["sources"])
    assert all(source["abstract"] and source["provider"] == "mock" and source["venue"] == "Journal"
               for source in out["sources"])
    assert all(out["coverage"].get(facet) for facet in ("mechanism", "context", "method", "gap"))


def test_deadline_keeps_fast_provider_partial_without_waiting_for_slow_provider():
    def slow(_):
        time.sleep(.3); return [{"title": "topic slow", "doi": "10.1/slow"}]
    def fast(_):
        return [{"title": "topic fast", "doi": "10.1/fast", "abstract": "topic evidence"}]
    started = time.monotonic()
    out = discover_literature("topic", budget_s=.05, providers={"slow": slow, "fast": fast},
                              identity_resolver=lambda *_: True)
    assert time.monotonic() - started < .15
    assert any(source["title"] == "topic fast" for source in out["sources"])
    assert out["warnings"]


def test_conflicting_dois_survive_and_duplicate_merge_keeps_richer_abstract():
    def provider(_):
        return [{"title": "topic same", "doi": "10.1/a", "abstract": "short"},
                {"title": "topic same", "doi": "10.1/b", "abstract": "different work"},
                {"title": "topic same", "doi": "10.1/a", "abstract": "a much richer abstract"}]
    out = discover_literature("topic", providers={"p": provider}, identity_resolver=lambda *_: False)
    assert {source["doi"] for source in out["unverified_candidates"]} == {"10.1/a", "10.1/b"}
    assert next(source for source in out["unverified_candidates"] if source["doi"] == "10.1/a")["abstract"]


def test_unverified_candidates_do_not_satisfy_target_and_malformed_planner_warns():
    out = discover_literature("topic", min_sources=2, llm_fn=lambda _: "not json",
                              providers={"p": lambda _: [{"title": "topic paper", "doi": "10.1/x"}]},
                              identity_resolver=lambda *_: False)
    assert out["count"] == 0 and out["shortfall"] == 2
    assert any("planner" in warning.casefold() or "truy vấn" in warning.casefold() for warning in out["warnings"])


def test_production_adaptive_refill_keeps_first_verified_source_and_fills_shortfall(monkeypatch):
    import orchestrator.tools.literature_discovery as discovery

    def provider(query):
        if "complementary" in query:
            return [{"title": "new trust adoption paper", "doi": "10.1/new", "abstract": "new trust adoption evidence"}]
        return [{"title": "travel trust adoption paper", "doi": "10.1/first", "abstract": "travel trust adoption evidence"}]
    monkeypatch.setattr(discovery, "_openalex", provider)
    monkeypatch.setattr(discovery, "_crossref", provider)
    monkeypatch.setattr(discovery, "_semantic", provider)

    def llm(prompt):
        if "Screen literature" in prompt:
            return {"keep": [0]}
        if "complementary" in prompt:
            return {"queries": [{"query": "complementary new trust adoption", "facet": "context"}]}
        return {"queries": [{"query": "travel trust adoption", "facet": "construct"}]}

    started = time.monotonic()
    out = discovery.discover_literature("travel trust", min_sources=2, budget_s=25,
                                        llm_fn=llm, identity_resolver=lambda *_: True)
    assert time.monotonic() - started < 2
    assert {source["doi"] for source in out["sources"]} == {"10.1/first", "10.1/new"}
    assert out["count"] == 2 and out["shortfall"] == 0
    assert any("travel trust adoption" in query for query in out["queries"])
    assert any("complementary new" in query for query in out["queries"])


def test_legacy_scout_mapping_preserves_abstract_and_distinguishes_venue(monkeypatch):
    from types import SimpleNamespace
    import orchestrator.tools.m2_literature as m2
    paper=SimpleNamespace(title='Travel trust',authors=['Lee'],year=2023,
                          journal='Tourism Journal',api_source='OpenAlex',doi='10.1234/trust',
                          url='https://doi.org/10.1234/trust',abstract='Observed evidence.',citation_count=12)
    monkeypatch.setattr(m2,'_engine_model',lambda:object())
    monkeypatch.setattr(m2,'research_citations_via_api',lambda **kwargs:{'citations':[paper]})
    monkeypatch.setattr(m2,'_filter_relevant_citations',lambda rows,topic:rows)
    row=m2.scout_citations.func('travel trust',deep=False)[0]
    assert row['abstract']=='Observed evidence.' and row['citation_count']==12
    assert row['venue']=='Tourism Journal' and row['provider']=='OpenAlex'
    assert row['verified'] is False  # identity cannot be inferred from a DOI string


def test_repeat_research_reuses_provider_identity_and_model_results(monkeypatch):
    from types import SimpleNamespace
    import orchestrator.tools.literature_discovery as discovery
    import orchestrator.tools.m5_writing as writing
    calls={'search':0,'model':0,'identity':0}
    def provider(query):
        calls['search']+=1
        return [{'title':'Travel trust adoption','doi':'10.1234/cache','authors':['Lee'],
                 'year':2023,'abstract':'Travel trust predicts adoption.'}]
    for name in ('_openalex_uncached','_crossref_uncached','_semantic_uncached'):
        monkeypatch.setattr(discovery,name,provider)
    def invoke(prompt):
        calls['model']+=1
        return {'keep':[0]} if 'Screen literature' in prompt else {'queries':[{'query':'travel trust adoption','facet':'constructs'}]}
    monkeypatch.setattr(writing,'_get_llm',lambda:SimpleNamespace(invoke=invoke))
    def identity(*args):calls['identity']+=1;return True
    monkeypatch.setattr(discovery,'_resolve_identity_uncached',identity)
    first=discovery.discover_literature('Travel trust',min_sources=1,_refill=False)
    counts=dict(calls)
    second=discovery.discover_literature('Travel trust',min_sources=1,_refill=False)
    assert counts=={'search':3,'model':2,'identity':1}
    assert calls==counts and first['sources']==second['sources']
    discovery.discover_literature('Travel trust',research_questions=['Different population?'],min_sources=1,_refill=False)
    assert calls=={'search':3,'model':4,'identity':1}  # new judgment, same provider query/identity
