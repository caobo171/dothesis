from quality.claim_confidence import MAX_CHUNK_CHARS, build_chunks, review_chunk


def test_numeric_zero_batch_ids_still_match_the_supplied_string_ids():
    source = {'title': 'Study', 'doi': '10.1234/test', 'abstract': 'Evidence.'}
    chunk = {'chapter': 'intro', 'text': 'A claim.', 'start': 0, 'anchor': 'zero'}

    def llm(prompt):
        if 'Identify every' in prompt:
            return [{'text': 'A claim.', 'query': 'claim evidence'}]
        return {'judgments': [{'claim_id': 0, 'candidate_id': 0, 'status': 'supported',
                               'supporting_quote': 'Evidence.'}]}

    result = review_chunk(chunk, [], lambda _: [source], llm)
    assert result['suggestions'][0]['evidence']['text'] == 'Evidence.'


def test_live_progress_precedes_expensive_operations_and_reports_actual_counts():
    events = []
    source = {"id": "s1", "title": "Study", "abstract": "Trust predicts adoption."}
    chunk = {"chapter": "intro", "text": "Trust increases adoption.", "start": 0, "anchor": "progress"}

    def llm(prompt):
        if "Identify every" in prompt:
            assert events[-1]["stage"] == "analyzing"
            return [{"text": chunk["text"], "query": "trust adoption"}]
        assert events[-1]["stage"] == "evaluating"
        return {"judgments": [{"claim_id": "0", "candidate_id": "s1", "status": "supported", "supporting_quote": source["abstract"], "rationale_vi": "Có hỗ trợ."}]}

    def search(query):
        assert events[-1] == {"stage": "searching", "query": query}
        return {"results": [source]}

    result = review_chunk(chunk, [], search, llm, progress_fn=events.append)
    assert {"stage": "search_results", "query": "trust adoption", "count": 1} in events
    assert result["metrics"]["claims_assessed"] == 1


def test_failed_progress_reporting_does_not_fail_review():
    chunk = {"chapter": "intro", "text": "Some claim.", "start": 0, "anchor": "progress"}

    def unavailable(_):
        raise OSError("progress storage unavailable")

    result = review_chunk(chunk, [], lambda _: [], lambda _: [], progress_fn=unavailable)
    assert result["metrics"]["claims_total"] == 0


def test_build_chunks_covers_all_canonical_chapters(monkeypatch):
    monkeypatch.setattr("quality.claim_confidence._canonical_chapters",
                        lambda _: {"intro": "a" * 6_100, "results": "b" * 10})
    chunks = build_chunks({})
    assert {c["chapter"] for c in chunks} == {"intro", "results"}
    assert sum(len(c["text"]) for c in chunks if c["chapter"] == "intro") == 6_100
    assert all(len(c["text"]) <= MAX_CHUNK_CHARS for c in chunks)
    assert len({c["anchor"] for c in chunks}) == len(chunks)


def test_review_batch_size_avoids_hundreds_of_tiny_sequential_calls(monkeypatch):
    monkeypatch.setattr("quality.claim_confidence._canonical_chapters",
                        lambda _: {"intro": "a" * 166_000})
    chunks = build_chunks({})
    assert 70 <= len(chunks) <= 80
    assert "".join(chunk["text"] for chunk in chunks) == "a" * 166_000


def test_review_suggests_only_exactly_quoted_retrieved_evidence():
    calls = []
    def llm(prompt):
        calls.append(prompt)
        if "Identify every" in prompt:
            return {"claims": [{"text": "Trust increases adoption.", "query": "trust technology adoption"}]}
        return {"judgments": [{"claim_id": "0", "candidate_id": "0", "status": "supported", "supporting_quote": "Trust predicts adoption intentions.", "rationale_vi": "Có hỗ trợ."}]}
    chunk = {"chapter": "lit_review", "text": "Trust increases adoption.", "start": 0, "end": 27, "anchor": "abc"}
    source = {"title": "Trust study", "doi": "10.1/x", "abstract": "Trust predicts adoption intentions."}
    result = review_chunk(chunk, [source], lambda q: [source], llm)
    assert result["metrics"]["queries"] == 1
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["evidence"]["text"] in source["abstract"]
    assert result["suggestions"][0]["status"] == "pending"


def test_title_only_or_invented_quote_never_becomes_suggestion():
    def llm(prompt):
        if "Identify every" in prompt:
            return [{"text": "Trust increases adoption.", "query": "trust adoption"}]
        return {"candidate_id": "0", "status": "supported", "supporting_quote": "invented support"}
    chunk = {"chapter": "intro", "text": "Trust increases adoption.", "start": 0, "end": 27, "anchor": "abc"}
    result = review_chunk(chunk, [{"title": "Title only"}], lambda q: [], llm)
    assert result["suggestions"][0]["classification"] == "unverifiable"
    assert result["suggestions"][0]["actionable"] is False


def test_no_llm_does_not_guess_claims_or_search():
    chunk = {"chapter": "intro", "text": "A substantive statement.", "start": 0, "end": 24, "anchor": "abc"}
    assert review_chunk(chunk, [], lambda q: (_ for _ in ()).throw(AssertionError()), None)["metrics"]["claims_total"] == 0


def test_own_hypothesis_or_measured_result_is_excluded_before_search():
    def llm(_):
        return [{"text": "Hypothesis H1 has β = 0.42.", "query": "should not run"}]
    chunk = {"chapter": "results", "text": "Hypothesis H1 has β = 0.42.", "start": 0, "end": 28, "anchor": "abc"}
    result = review_chunk(chunk, [], lambda q: (_ for _ in ()).throw(AssertionError()), llm)
    assert result["metrics"]["claims_total"] == 0


def test_duplicate_query_is_cached_but_each_claim_is_reviewed_and_verified_support_is_actionable():
    calls = []
    def llm(prompt):
        if "Identify every" in prompt:
            return {"claims": [{"text": "A claim.", "query": "same query"}, {"text": "B claim.", "query": "same query"}]}
        return {"judgments": [
            {"claim_id": "0", "candidate_id": "s1", "status": "supported", "supporting_quote": "Evidence supports it.", "rationale_vi": "Có hỗ trợ."},
            {"claim_id": "1", "candidate_id": "s1", "status": "supported", "supporting_quote": "Evidence supports it.", "rationale_vi": "Có hỗ trợ."},
        ]}
    source = {"id": "s1", "title": "Study", "authors": ["Nguyen"], "year": 2024,
              "abstract": "Evidence supports it.", "verified": True}
    chunk = {"chapter": "intro", "text": "A claim. B claim.", "start": 0, "end": 17, "anchor": "abc", "document_fingerprint": "fp"}
    result = review_chunk(chunk, [], lambda q: calls.append(q) or {"results": [source]}, llm)
    assert calls == ["same query"]
    assert len(result["suggestions"]) == 2
    assert all(item["actionable"] and item["proposed_text"] for item in result["suggestions"])


def test_prefetches_unique_anchorable_queries_before_ordered_evidence_judgment():
    first, second = "Trust supports adoption.", "Expertise supports trust."
    chunk = {"chapter": "intro", "text": f"{first} {second}", "start": 0, "anchor": "parallel"}
    first_source = {"id": "s1", "title": "Trust", "abstract": "Trust supports adoption."}
    second_source = {"id": "s2", "title": "Expertise", "abstract": "Expertise supports trust."}
    events, batches = [], []

    def llm(prompt):
        if "Identify every" in prompt:
            return [{"text": first, "query": "trust adoption"}, {"text": second, "query": "expertise trust"}]
        batches.append(prompt)
        return {"judgments": [
            {"claim_id": "0", "candidate_id": "s1", "status": "supported", "supporting_quote": first_source["abstract"], "rationale_vi": "Có hỗ trợ."},
            {"claim_id": "1", "candidate_id": "s2", "status": "supported", "supporting_quote": second_source["abstract"], "rationale_vi": "Có hỗ trợ."},
        ]}

    def search_many(queries):
        assert queries == ["trust adoption", "expertise trust"]
        return {"trust adoption": {"results": [first_source]}, "expertise trust": {"results": [second_source]}}

    result = review_chunk(chunk, [], lambda _: (_ for _ in ()).throw(AssertionError("serial search")), llm,
                          progress_fn=events.append, search_many_fn=search_many)
    assert result["metrics"]["queries"] == 2 and len(batches) == 1
    assert {"stage": "parallel_searching", "count": 2} in events
    assert {"stage": "search_queued", "query": "trust adoption"} in events


def test_raw_editor_offsets_survive_whitespace_and_multiple_chunks():
    import hashlib
    raw = ' \n' + ('A complete paragraph about travel evidence.\n\n' * 230) + '  \n'
    chunks = build_chunks({'m5_writing':{'chapters':{'intro':{'prose':raw}}}})
    assert ''.join(c['text'] for c in chunks)==raw
    for c in chunks:
        assert raw[c['start']:c['end']]==c['text']
        assert c['document_fingerprint']==hashlib.sha256(raw.encode()).hexdigest()


def test_library_does_not_starve_new_papers_and_quote_requires_candidate_id():
    old=[{'id':f'old{i}','title':f'Other topic {i}','abstract':'Unrelated evidence.'} for i in range(10)]
    fresh={'id':'new','title':'Trust in travel','authors':['Lee'],'year':2023,'verified':True,'abstract':'Trust influences travel decisions.'}
    seen=[]
    def llm(prompt):
        if 'Identify every' in prompt:return [{'text':'Trust affects travel.','query':'travel trust'}]
        seen.append(prompt)
        return {'judgments':[{'claim_id':'0','candidate_id':'new','status':'supported','supporting_quote':fresh['abstract'],'rationale_vi':'Có hỗ trợ.'}]}
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':'Trust affects travel.'}}}})[0]
    result=review_chunk(chunk,old,lambda q:[fresh],llm)
    assert result['suggestions'][0]['source']['id']=='new'
    assert result['suggestions'][0]['actionable']
    assert 'new' in seen[0]
    def no_id(prompt):
        if 'Identify every' in prompt:return [{'text':'Trust affects travel.','query':'travel trust'}]
        return {'judgments':[{'claim_id':'0','status':'supported','supporting_quote':fresh['abstract'],'rationale_vi':'Thiếu ID.'}]}
    failed = review_chunk(chunk, [], lambda q: [fresh], no_id)
    assert failed['suggestions'][0]['classification'] == 'assessment_failed'
    assert failed['metrics']['claims_failed'] == 1


def test_all_extracted_claims_are_judged_in_bounded_batches_without_sampling():
    statements=[f"Claim number {i} concerns tourism." for i in range(9)]
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':' '.join(statements)}}}})[0]
    source={'id':'s1','title':'Tourism study','abstract':'Tourism evidence supports the claims.'}
    judge_calls=[]
    def llm(prompt):
        if 'Identify every' in prompt:
            return [{'text':text,'query':'tourism claim'} for text in statements]
        judge_calls.append(prompt)
        rows=__import__('json').loads(prompt.split('CLAIMS: ', 1)[1])
        return {'judgments':[
            {'claim_id':row['claim_id'],'candidate_id':'s1','status':'supported',
             'supporting_quote':source['abstract'],'rationale_vi':'Có hỗ trợ.'}
            for row in rows
        ]}
    result=review_chunk(chunk,[],lambda q:[source],llm)
    assert result['metrics']['claims_total']==9
    assert result['metrics']['claims_assessed']==9
    assert len(result['suggestions'])==9
    assert len(judge_calls)==2  # six + three, never one model call per claim


def test_invalid_batch_rows_are_isolated_without_losing_valid_evidence():
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':'A claim. B claim.'}}}})[0]
    source={'id':'s1','title':'Study','authors':['Nguyen'],'year':2024,'verified':True,'abstract':'Evidence.'}
    def missing(prompt):
        if 'Identify every' in prompt:
            return [{'text':'A claim.','query':'claim evidence'},{'text':'B claim.','query':'claim evidence'}]
        return {'judgments':[{'claim_id':'0','candidate_id':'s1','status':'supported','supporting_quote':'Evidence.','rationale_vi':'Có hỗ trợ.'}]}
    missing_result = review_chunk(chunk, [], lambda _: [source], missing)
    assert missing_result['metrics'] == {
        'claims_total': 2, 'claims_assessed': 1, 'claims_unresolved': 1,
        'claims_failed': 1, 'queries': 1, 'candidates': 2, 'supported': 1,
    }
    assert [item['classification'] for item in missing_result['suggestions']] == ['citation_opportunity', 'assessment_failed']
    assert missing_result['suggestions'][0]['evidence']['text'] == 'Evidence.'
    def duplicate(prompt):
        if 'Identify every' in prompt:
            return [{'text':'A claim.','query':'claim evidence'},{'text':'B claim.','query':'claim evidence'}]
        return {'judgments':[
            {'claim_id':'0','candidate_id':'s1','status':'supported','supporting_quote':'Evidence.','rationale_vi':'Có hỗ trợ.'},
            {'claim_id':'0','candidate_id':'s1','status':'supported','supporting_quote':'Evidence.','rationale_vi':'Có hỗ trợ.'},
        ]}
    duplicate_result = review_chunk(chunk, [], lambda _: [source], duplicate)
    assert duplicate_result['metrics']['claims_assessed'] == 0
    assert duplicate_result['metrics']['claims_failed'] == 2
    assert [item['classification'] for item in duplicate_result['suggestions']] == ['assessment_failed', 'assessment_failed']


def test_malformed_extraction_is_retryable_not_empty_success():
    import pytest
    from quality.claim_confidence import ClaimConfidenceLLMError
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':'A claim.'}}}})[0]
    with pytest.raises(ClaimConfidenceLLMError):review_chunk(chunk,[],lambda q:[],lambda p:{'wrong':'shape'})


def test_existing_citation_with_partial_evidence_is_not_marked_supported():
    sentence='Trust always determines every travel decision (Lee, 2023).'
    source={'id':'lee','title':'Trust','authors':['Lee'],'year':2023,'verified':True,'abstract':'Trust sometimes influences travel choices.'}
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':sentence}}}})[0]
    def llm(prompt):
        if 'Identify every' in prompt:return [{'text':sentence,'query':'trust travel decisions'}]
        return {'judgments':[{'claim_id':'0','candidate_id':'lee','status':'weakly_supported','supporting_quote':source['abstract'],'rationale_vi':'Hỗ trợ một phần.'}]}
    item=review_chunk(chunk,[source],lambda q:[],llm)['suggestions'][0]
    assert item['classification']=='partial_support'
    assert not item['actionable']


def test_missing_editor_chapter_uses_legacy_fallback_without_stripping_raw(monkeypatch):
    monkeypatch.setattr('orchestrator.tools.m5_writing.chapter_prose',lambda m5:{'intro':'trimmed','conclusion':'Legacy conclusion.'})
    chunks=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':'  Raw introduction.\n'}}}})
    assert {c['chapter']:c['text'] for c in chunks}=={'intro':'  Raw introduction.\n','conclusion':'Legacy conclusion.'}


def test_batch_invented_quote_is_an_explicit_nonactionable_failure():
    chunk=build_chunks({'m5_writing':{'chapters':{'intro':{'prose':'A claim.'}}}})[0]
    source={'id':'s1','title':'Study','abstract':'Retrieved evidence only.'}
    def llm(prompt):
        if 'Identify every' in prompt:
            return [{'text':'A claim.','query':'claim evidence'}]
        return {'judgments':[{'claim_id':'0','candidate_id':'s1','status':'supported',
                              'supporting_quote':'invented text','rationale_vi':'Sai.'}]}
    result = review_chunk(chunk, [], lambda _: [source], llm)
    assert result['metrics']['claims_assessed'] == 0
    assert result['metrics']['claims_failed'] == 1
    assert result['metrics']['claims_unresolved'] == 1
    assert result['suggestions'][0]['classification'] == 'assessment_failed'
    assert not result['suggestions'][0]['actionable']


def test_malformed_evidence_batch_marks_only_its_claims_unassessed_without_retrying():
    import json
    chunk = build_chunks({'m5_writing': {'chapters': {'intro': {'prose': 'A claim. B claim.'}}}})[0]
    source = {'id': 's1', 'title': 'Study', 'abstract': 'Evidence.'}
    calls = 0

    def llm(prompt):
        nonlocal calls
        if 'Identify every' in prompt:
            return [{'text': 'A claim.', 'query': 'claim evidence'}, {'text': 'B claim.', 'query': 'claim evidence'}]
        calls += 1
        raise json.JSONDecodeError('bad JSON', '}', 0)

    result = review_chunk(chunk, [], lambda _: [source], llm)
    assert calls == 1
    assert result['metrics']['claims_assessed'] == 0
    assert result['metrics']['claims_failed'] == result['metrics']['claims_unresolved'] == 2
    assert all(item['classification'] == 'assessment_failed' and not item['actionable'] for item in result['suggestions'])


def test_timeout_during_evidence_judgment_keeps_the_chunk_retryable():
    import pytest
    chunk = build_chunks({'m5_writing': {'chapters': {'intro': {'prose': 'A claim.'}}}})[0]
    source = {'id': 's1', 'title': 'Study', 'abstract': 'Evidence.'}

    def llm(prompt):
        if 'Identify every' in prompt:
            return [{'text': 'A claim.', 'query': 'claim evidence'}]
        raise TimeoutError('provider timeout')

    with pytest.raises(TimeoutError):
        review_chunk(chunk, [], lambda _: [source], llm)
