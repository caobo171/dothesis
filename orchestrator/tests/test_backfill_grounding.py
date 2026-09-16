"""Initial and late backfill share discovery without losing existing sources."""
from unittest.mock import MagicMock
import copy

import orchestrator.backfill as B
import orchestrator.tools.literature_discovery as discovery
from orchestrator.state import ContextStore


def paper(i):
    return {'title':f'Paper {i}','doi':f'10.1234/{i}','authors':['Nguyen'],'year':2023,
            'verified':True,'abstract':f'Retrieved evidence {i}.'}


def state(existing=None, topic=True):
    return ContextStore(m1_topic={'research_title':'Influencer credibility and travel intention','research_questions':['How does trust affect intentions?']} if topic else {},
                        m2_literature=existing or {}, m4_analysis={'analysis_results':'PLS-SEM findings. '*150})


def mock_model():
    llm=MagicMock()
    llm.invoke.return_value.content='{"research_title":"Influencer credibility and travel intention","citation_list":[{"title":"Invented recalled paper","verified":true}],"research_gaps":[{"description":"A gap"}]}'
    return llm


def patch_search(monkeypatch, sources=None, raises=False):
    calls=[]
    def discover(topic,**kw):
        calls.append({'topic':topic,**kw})
        if raises: raise RuntimeError('provider failure')
        rows=copy.deepcopy(sources or [])
        return {'sources':rows,'count':len(rows),'target':24,'shortfall':max(0,24-len(rows)),
                'complete':len(rows)>=24,'warnings':[],'coverage':{'queries_completed':4}}
    monkeypatch.setattr(discovery,'discover_literature',discover)
    return calls


def entry(out):return next(e for e in out if e['module']=='M2')


def test_backfill_uses_shared_discovery_and_preserves_evidence(monkeypatch):
    calls=patch_search(monkeypatch,[paper(1)])
    e=entry(B.reconstruct_upstream(state(),targets=['M2'],llm=mock_model()))
    assert len(calls)==1 and calls[0]['min_sources']==24
    assert calls[0]['research_questions']==['How does trust affect intentions?']
    assert e['candidate']['literature_sources']==[paper(1)]
    assert e['candidate']['citation_list']==[paper(1)]
    assert e['source_discovery']['shortfall']==23


def test_six_existing_sources_are_enriched_not_overwritten(monkeypatch):
    old=[paper(i) for i in range(6)]
    old[0]['abstract']=''; old[0]['curated_note']='Keep my note'
    calls=patch_search(monkeypatch,[paper(i) for i in range(30)])
    cs=state({'literature_sources':old,'citation_list':old,'research_gaps':[{'description':'Existing gap'}]})
    e=entry(B.reconstruct_upstream(cs,targets=['M2'],llm=mock_model()))
    sources=e['candidate']['literature_sources']
    assert len(sources)==30 and sources[0]['curated_note']=='Keep my note'
    assert sources[0]['abstract']=='Retrieved evidence 0.'
    assert {p['doi'] for p in old} <= {p['doi'] for p in sources}
    assert e['candidate']['research_gaps']==[{'description':'Existing gap'}]
    assert cs.m2_literature['literature_sources'][0]['abstract']==''  # pure read
    assert len(calls[0]['existing_sources'])==6


def test_failure_preserves_existing_but_never_promotes_recall(monkeypatch):
    patch_search(monkeypatch,raises=True)
    e=entry(B.reconstruct_upstream(state({'literature_sources':[paper(1)]}),targets=['M2'],llm=mock_model()))
    assert e['candidate']['citation_list']==[paper(1)]
    assert e['source_discovery']['complete'] is False


def test_empty_search_does_not_publish_model_references(monkeypatch):
    patch_search(monkeypatch)
    e=entry(B.reconstruct_upstream(state(),targets=['M2'],llm=mock_model()))
    assert e['candidate']['literature_sources']==[] and e['candidate']['citation_list']==[]
    assert not e['ready_to_confirm']


def test_unverified_discovered_candidates_do_not_become_grounded(monkeypatch):
    p=paper(1);p['verified']=False
    patch_search(monkeypatch,[p])
    assert B._m2_real_sources(state())==[]


def test_no_topic_makes_no_provider_calls(monkeypatch):
    calls=patch_search(monkeypatch,[paper(1)])
    assert B._m2_real_sources(state(topic=False))==[] and not calls


def test_late_grounding_is_saved_again_and_never_keeps_recall(monkeypatch):
    calls=patch_search(monkeypatch,[paper(1)])
    handed=[]
    out=B.reconstruct_upstream(state(topic=False),llm=mock_model(),on_module=lambda e:handed.append(copy.deepcopy(e)))
    m2=[e for e in handed if e['module']=='M2']
    assert len(calls)==1 and len(m2)==2
    assert m2[0]['candidate']['literature_sources']==[]
    assert m2[1]['candidate']['literature_sources']==[paper(1)]
    assert entry(out)['candidate']['citation_list']==[paper(1)]


def test_existing_topic_not_searched_twice(monkeypatch):
    calls=patch_search(monkeypatch,[paper(1)])
    B.reconstruct_upstream(state(),targets=['M2'],llm=mock_model())
    assert len(calls)==1
