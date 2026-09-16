"""Citation enrichment review and atomic acceptance on a disposable database."""
import copy
import json
import threading
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import ContextStore, Project, User, VersionHistory
from app.routers import claim_reviews as cr
from app.routers import m5_editor as editor
from app.agent_state import DbProjectStateStore

TEXT = ('Influencer expertise can increase trust in travel recommendations. '
        'Perceived authenticity can influence tourist intentions. ' + 'Background context. ' * 20)
SOURCE = {'id':'doi:10.1234/test', 'title':'Influencer expertise and travel trust', 'authors':['Hill','Qesja'],
          'year':2022, 'doi':'10.1234/test', 'verified':True, 'abstract':'Expertise increases trust. Authenticity influences intentions.'}


def test_batch_cache_rejects_missing_claims_and_nonliteral_evidence():
    prompt = 'instructions\nCLAIMS: ' + json.dumps([
        {'claim_id': '0', 'candidates': [{'candidate_id': 's1', 'passage': 'Real evidence.'}]},
        {'claim_id': '1', 'candidates': []},
    ])
    rows = [{'claim_id': '0', 'candidate_id': 's1', 'status': 'supported', 'supporting_quote': 'Real evidence.'},
            {'claim_id': '1', 'status': 'unverifiable'}]
    assert cr._valid_claim_llm_result({'judgments': rows}, prompt)
    assert not cr._valid_claim_llm_result({'judgments': rows[:1]}, prompt)
    assert not cr._valid_claim_llm_result({'judgments': [rows[0], rows[0]]}, prompt)
    rows[0]['supporting_quote'] = 'Invented evidence.'
    assert not cr._valid_claim_llm_result({'judgments': rows}, prompt)


def test_claim_cache_hit_never_enters_billing_invoke(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.tools import m5_writing
    monkeypatch.setattr(m5_writing, '_get_llm', lambda: object())

    class Billing:
        calls = 0

        def invoke(self, llm, prompt, **kwargs):
            self.calls += 1
            return SimpleNamespace(content='[{"text":"A claim.","query":"claim evidence"}]')

    billing = Billing()
    first = cr._claim_llm('extract this unique claim', billing=billing)
    assert cr._claim_llm('extract this unique claim', billing=billing) == first
    assert billing.calls == 1


@pytest.fixture
def review(project_id, tmp_path, monkeypatch):
    monkeypatch.setattr(cr, 'workspace_dir', lambda pid: tmp_path / str(pid))
    with Session(get_engine()) as db:
        project = db.get(Project, project_id)
        uid = project.user_id
        db.add(ContextStore(project_id=project_id, m5_writing={'chapters':{'intro':{'prose':TEXT}}},
                            m2_literature={'literature_sources':[]}))
        db.commit()
    return project_id, uid


@pytest.fixture(autouse=True)
def _isolated_research_cache(monkeypatch, tmp_path):
    # Cache behavior is tested locally; never let another test or a developer's
    # persisted search result suppress this test's mocked provider call.
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "research-cache"))


def _suggestion(text, start, sid):
    return {'id':sid, 'chapter':'intro', 'anchor':{'from_offset':start,'to_offset':start+len(text),
            'old_text':text,'document_fingerprint':cr._chapter_fingerprint(TEXT)},
            'classification':'unsupported','rationale_vi':'Nguồn hỗ trợ nhận định.',
            'proposed_text':text.rstrip('.')+' (Hill & Qesja, 2022).', 'source':copy.deepcopy(SOURCE),
            'evidence':{'kind':'abstract','text':'Expertise increases trust.','relation':'supports'},
            'status':'pending','actionable':True}


def _started(review, monkeypatch):
    pid, uid = review
    import quality.claim_confidence as engine
    first, second = TEXT.split('. ')[:2]
    a, b = first+'.', second+'.'
    suggestions = [_suggestion(a,0,'a'),_suggestion(b,TEXT.index(b),'b')]
    monkeypatch.setattr(engine, 'review_chunk', lambda *a,**kw: {'suggestions':copy.deepcopy(suggestions),
        'metrics':{'claims_total':2,'claims_assessed':2,'claims_unresolved':0},'warnings':[]})
    with Session(get_engine()) as db:
        user=db.get(User,uid)
        data=cr.start(pid,cr.StartBody(),user,db)
        assert data['suggestions']==[]
        return cr.next_chunk(pid,uuid.UUID(data['review_id']),user,db)


def test_review_is_read_only_and_reopens(review,monkeypatch):
    pid,uid=review
    data=_started(review,monkeypatch)
    assert data['status']=='completed' and len(data['suggestions'])==2
    assert data['coverage']['claims_assessed']==2
    with Session(get_engine()) as db:
        cs=db.get(ContextStore,pid)
        assert cs.m5_writing['chapters']['intro']['prose']==TEXT
        assert cs.m2_literature['literature_sources']==[]
        assert db.query(VersionHistory).filter_by(project_id=pid).count()==0
        assert cr.latest(pid,db.get(User,uid),db)['review']['review_id']==data['review_id']


def test_two_acceptances_rebase_and_dedupe_source(review,monkeypatch):
    pid,uid=review;data=_started(review,monkeypatch);rid=uuid.UUID(data['review_id'])
    with Session(get_engine()) as db:
        first=cr.accept(pid,rid,'a',db.get(User,uid),db)
        second=cr.accept(pid,rid,'b',db.get(User,uid),db)
    with Session(get_engine()) as db:
        cs=db.get(ContextStore,pid)
        assert cs.m5_writing['chapters']['intro']['prose'].count('(Hill & Qesja, 2022)')==2
        assert len(cs.m2_literature['literature_sources'])==1
        assert second['review']['suggestions'][1]['status']=='accepted'
        assert db.query(VersionHistory).filter_by(project_id=pid,slice_field='m2_literature').count()==2


def test_rejected_m5_rolls_back_new_source_and_history(review,monkeypatch):
    pid,uid=review;data=_started(review,monkeypatch);rid=uuid.UUID(data['review_id'])
    original=DbProjectStateStore.commit_slice
    def reject(self,module,*args,**kwargs):
        if module=='M5':raise ValueError('blocked writing')
        return original(self,module,*args,**kwargs)
    monkeypatch.setattr(DbProjectStateStore,'commit_slice',reject)
    with Session(get_engine()) as db:
        with pytest.raises(ValueError,match='blocked writing'):
            cr.accept(pid,rid,'a',db.get(User,uid),db)
    with Session(get_engine()) as db:
        cs=db.get(ContextStore,pid)
        assert cs.m2_literature['literature_sources']==[]
        assert cs.m5_writing['chapters']['intro']['prose']==TEXT
        assert db.query(VersionHistory).filter_by(project_id=pid).count()==0
    assert cr._read(pid,uid,rid)['suggestions'][0]['status']=='pending'


def test_external_edit_rejected_without_adding_source(review,monkeypatch):
    pid,uid=review;data=_started(review,monkeypatch);rid=uuid.UUID(data['review_id'])
    with Session(get_engine()) as db:
        cs=db.get(ContextStore,pid)
        cs.m5_writing={'chapters':{'intro':{'prose':'New edit. '+TEXT}}};db.commit()
        with pytest.raises(HTTPException) as exc:cr.accept(pid,rid,'a',db.get(User,uid),db)
        assert exc.value.status_code==409
    with Session(get_engine()) as db:
        assert db.get(ContextStore,pid).m2_literature['literature_sources']==[]


def test_reject_has_no_thesis_mutation(review,monkeypatch):
    pid,uid=review;data=_started(review,monkeypatch);rid=uuid.UUID(data['review_id'])
    with Session(get_engine()) as db:
        result=cr.reject(pid,rid,'a',db.get(User,uid),db)
        assert result['review']['suggestions'][0]['status']=='rejected'
        assert db.get(ContextStore,pid).m5_writing['chapters']['intro']['prose']==TEXT


def test_failed_scan_keeps_cursor_and_partial_results(review,monkeypatch):
    pid,uid=review
    import quality.claim_confidence as engine
    def fail(*args,**kwargs):raise TimeoutError('model timed out')
    monkeypatch.setattr(engine,'review_chunk',fail)
    with Session(get_engine()) as db:
        user=db.get(User,uid);data=cr.start(pid,cr.StartBody(),user,db)
        with pytest.raises(HTTPException) as exc:cr.next_chunk(pid,uuid.UUID(data['review_id']),user,db)
        assert exc.value.status_code==503
    assert cr._read(pid,uid,data['review_id'])['chunks_completed']==0


def test_other_user_cannot_read_review(review,monkeypatch):
    pid,uid=review;data=_started(review,monkeypatch)
    stranger=User(id=uuid.uuid4(),email='stranger@example.com',username='stranger',password_hash='x')
    with Session(get_engine()) as db:
        with pytest.raises(HTTPException) as exc:cr.latest(pid,stranger,db)
        assert exc.value.status_code==404


def test_verified_candidate_caches_identity_but_keeps_fresh_query_provenance(monkeypatch, tmp_path):
    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "research-cache"))
    calls = {"openalex": 0}
    canonical = {
        "title": "Canonical title", "authors": ["Canonical Author"], "year": 2023,
        "doi": "10.1234/cache", "journal": "Canonical Journal", "abstract": "Canonical abstract.",
    }

    def resolve(self, doi):
        calls["openalex"] += 1
        return canonical

    monkeypatch.setattr("engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi", resolve)
    first = cr._verified_candidate({
        "title": "Incorrect display title", "authors": ["Wrong"], "year": 2020,
        "doi": "10.1234/cache", "provider": "OpenAlex", "abstract": "First query abstract.",
    })
    second = cr._verified_candidate({
        "title": "Another stale display title", "authors": ["Also wrong"], "year": 2021,
        "doi": "10.1234/cache", "provider": "Semantic Scholar", "abstract": "Fresh query abstract.",
    })

    assert calls == {"openalex": 1}
    assert first["title"] == second["title"] == "Canonical title"
    assert second["authors"] == ["Canonical Author"] and second["year"] == 2023
    assert second["provider"] == "Semantic Scholar"
    assert second["abstract"] == "Fresh query abstract."


def test_complete_trusted_index_marker_skips_resolver_but_keeps_richer_abstract(monkeypatch):
    base = {"title": "Trust and travel", "authors": ["Nguyen"], "year": 2024,
            "doi": "10.1234/trust.travel", "url": "https://doi.org/10.1234/trust.travel",
            "abstract": "Short abstract."}
    monkeypatch.setattr("engine.utils.api_citations.openalex.OpenAlexClient.search_papers", lambda *_args, **_kwargs: [base])
    monkeypatch.setattr("engine.utils.api_citations.semantic_scholar.SemanticScholarClient.search_papers",
                        lambda *_args, **_kwargs: [{**base, "abstract": "Longer retrieved abstract for the same paper."}])
    monkeypatch.setattr(editor, "_crossref_paper_search", lambda *_args: [base])
    row = editor.search_scholarly_references("trust travel", 5)["results"][0]
    assert row["provider"] == "Semantic Scholar"
    assert row["_identity_from_index"]["conflict"] is False

    calls = {"resolver": 0}
    monkeypatch.setattr("engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi",
                        lambda *_args, **_kwargs: calls.__setitem__("resolver", calls["resolver"] + 1))
    verified = cr._verified_candidate(row, trusted_search=True)
    assert calls["resolver"] == 0
    assert verified["verified"] is True
    assert verified["abstract"] == "Longer retrieved abstract for the same paper."


def test_incomplete_conflicting_and_spoofed_index_rows_still_use_exact_resolver(monkeypatch):
    calls = []

    def resolve(_self, doi):
        calls.append(doi)
        return {"title": "Canonical", "authors": ["Resolver"], "year": 2024,
                "doi": doi, "abstract": "Resolved abstract."}

    monkeypatch.setattr("engine.utils.api_citations.openalex.OpenAlexClient.get_paper_by_doi", resolve)
    incomplete = {"provider": "OpenAlex", "title": "Incomplete", "authors": [], "year": 2024,
                  "doi": "10.1234/incomplete", "verified": True}
    marker = editor._trusted_index_marker([
        {"provider": "OpenAlex", "title": "Canonical", "authors": ["Resolver"], "year": 2024, "doi": "10.1234/conflict"},
        {"provider": "Crossref", "title": "Conflicting", "authors": ["Wrong"], "year": 2024, "doi": "10.1234/conflict"},
    ])
    assert marker and marker["conflict"] is True
    conflict = {"provider": "Crossref", "title": "Conflicting", "authors": ["Wrong"], "year": 2024,
                "doi": "10.1234/conflict", "_identity_from_index": marker}
    spoofed = {"provider": "Crossref", "title": "Spoofed", "authors": ["Any"], "year": 2024,
               "doi": "10.1234/spoofed", "verified": True}
    assert cr._verified_candidate(incomplete, trusted_search=True)["title"] == "Canonical"
    assert cr._verified_candidate(conflict, trusted_search=True)["title"] == "Canonical"
    # Provider/verified fields from a caller are never sufficient without the
    # private marker emitted by search_scholarly_references.
    assert cr._verified_candidate(spoofed, trusted_search=True)["title"] == "Canonical"
    assert calls == ["10.1234/incomplete", "10.1234/conflict", "10.1234/spoofed"]
    # Even a complete copied marker cannot bypass verification at the default
    # entry point used for untrusted callers.
    forged = {**spoofed, "doi": "10.1234/forged", "_identity_from_index": {
        "identity": {"doi": "10.1234/forged", "title": "Forged", "authors": ["Any"], "year": 2024},
        "conflict": False,
    }}
    assert cr._verified_candidate(forged)["title"] == "Canonical"
    assert calls[-1] == "10.1234/forged"


def test_claim_llm_caches_only_valid_review_shapes(monkeypatch, tmp_path):
    from types import SimpleNamespace

    monkeypatch.setenv("DOTHESIS_RESEARCH_CACHE_DIR", str(tmp_path / "research-cache"))
    calls = {"llm": 0}
    responses = iter(['{"wrong": true}', '{"claims": [{"text": "A claim.", "query": "claim evidence"}]}'])
    monkeypatch.setattr("orchestrator.tools.m5_writing._get_llm", lambda: object())

    def invoke(*_args, **_kwargs):
        calls["llm"] += 1
        return SimpleNamespace(content=next(responses))

    monkeypatch.setattr("orchestrator.agents.base.bounded_invoke", invoke)
    assert cr._claim_llm("extract these claims") == {"wrong": True}
    assert cr._claim_llm("extract these claims") == {"claims": [{"text": "A claim.", "query": "claim evidence"}]}
    assert calls == {"llm": 2}


def test_progress_is_visible_while_next_chunk_holds_review_lock(review, monkeypatch):
    pid, uid = review
    import quality.claim_confidence as engine
    entered, release = threading.Event(), threading.Event()

    def delayed(chunk, library, search_fn, llm_fn=None, progress_fn=None, search_many_fn=None):
        assert progress_fn is not None
        progress_fn({"stage": "analyzing"})
        entered.set()
        assert release.wait(3)
        return {"suggestions": [], "metrics": {"claims_total": 0, "claims_assessed": 0, "claims_unresolved": 0}, "warnings": []}

    monkeypatch.setattr(engine, "review_chunk", delayed)
    with Session(get_engine()) as db:
        user = db.get(User, uid)
        data = cr.start(pid, cr.StartBody(), user, db)
        rid = uuid.UUID(data["review_id"])

    def run_next():
        with Session(get_engine()) as db:
            cr.next_chunk(pid, rid, db.get(User, uid), db)

    worker = threading.Thread(target=run_next)
    worker.start()
    assert entered.wait(3)
    with Session(get_engine()) as db:
        live = cr.progress(pid, rid, db.get(User, uid), db)
    assert live["status"] == "running"
    assert live["activities"][-1]["stage"] == "analyzing"
    release.set(); worker.join(3)
    assert not worker.is_alive()
    with Session(get_engine()) as db:
        finished = cr.progress(pid, rid, db.get(User, uid), db)
    assert finished["activities"][-1]["stage"] == "chunk_done"


def test_next_chunk_parallelizes_fetch_and_identity_without_caching_partial_failures(review, monkeypatch):
    pid, uid = review
    import quality.claim_confidence as engine
    query_barrier = threading.Barrier(2)
    identity_barrier = threading.Barrier(2)
    queries, identities, seen_payload = [], [], {}

    def provider_search(query, limit):
        queries.append(query)
        if query == "failed query":
            raise TimeoutError("provider unavailable")
        query_barrier.wait(timeout=2)
        suffix = "a" if query == "trust travel" else "b"
        return {"results": [
                    {"title": f"Study {suffix} A", "authors": ["Lee"], "year": 2024,
                     "doi": "10.1/a", "abstract": f"Evidence {suffix} A.", "provider": "Mock"},
                    {"title": f"Study {suffix} B", "authors": ["Lee"], "year": 2024,
                     "doi": "10.1/b", "abstract": f"Evidence {suffix} B.", "provider": "Mock"},
                ],
                "providers": ["Mock"], "responded_providers": ["Mock"]}

    def verify(candidate, **kwargs):
        assert kwargs == {"trusted_search": True}
        identities.append(candidate["doi"])
        identity_barrier.wait(timeout=2)
        return {**candidate, "title": "Canonical study", "authors": ["Canonical"], "year": 2024,
                "verified": True}

    def invoke_parallel(_chunk, _library, search_fn, llm_fn=None, progress_fn=None, search_many_fn=None):
        seen_payload.update(search_many_fn(["trust travel", "expertise tourism", "failed query", "trust travel"]))
        return {"suggestions": [], "metrics": {"claims_total": 0, "claims_assessed": 0, "claims_unresolved": 0}, "warnings": []}

    monkeypatch.setattr(cr, "search_scholarly_references", provider_search)
    monkeypatch.setattr(cr, "_verified_candidate", verify)
    monkeypatch.setattr(engine, "review_chunk", invoke_parallel)
    with Session(get_engine()) as db:
        user = db.get(User, uid)
        data = cr.start(pid, cr.StartBody(), user, db)
        rid = uuid.UUID(data["review_id"])
        cr.next_chunk(pid, rid, user, db)

    assert set(queries) == {"trust travel", "expertise tourism", "failed query"}
    # Four returned rows reduce to two shared DOI checks, which overlap at the
    # identity barrier instead of serially waiting one at a time.
    assert set(identities) == {"10.1/a", "10.1/b"} and len(identities) == 2
    assert set(seen_payload) == {"trust travel", "expertise tourism", "failed query"}
    assert all(payload["results"][0]["title"] == "Canonical study"
               for key, payload in seen_payload.items() if key != "failed query")
    assert seen_payload["failed query"]["results"] == []
    persisted = cr._read(pid, uid, rid)
    assert "failed query" not in persisted["_queries"]
    assert {"trust travel", "expertise tourism"} <= set(persisted["_queries"])


def test_progress_enforces_review_owner(review, monkeypatch):
    pid, uid = review
    with Session(get_engine()) as db:
        data = cr.start(pid, cr.StartBody(), db.get(User, uid), db)
        stranger = User(id=uuid.uuid4(), email="progress-stranger@example.com", username="progress-stranger", password_hash="x")
        with pytest.raises(HTTPException) as exc:
            cr.progress(pid, uuid.UUID(data["review_id"]), stranger, db)
    assert exc.value.status_code == 404


def test_budget_can_change_without_restarting_review(review):
    pid, uid = review
    with Session(get_engine()) as db:
        user = db.get(User, uid)
        data = cr.start(pid, cr.StartBody(credit_limit=2), user, db)
        changed = cr.update_budget(pid, uuid.UUID(data['review_id']), cr.BudgetBody(credit_limit=30), user, db)
        assert changed['review_id'] == data['review_id']
        assert changed['chunks_completed'] == 0
        assert changed['billing']['credits_limit'] == 30
        assert changed['billing']['credits_charged'] == 0
