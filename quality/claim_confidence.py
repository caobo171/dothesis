"""Bounded, evidence-first claim-confidence review for canonical thesis prose.

The module is deliberately pure: callers supply scholarly search and LLM
callbacks.  It can therefore never insert a citation or manufacture metadata;
it returns review suggestions only when a retrieved source contains a passage
whose quoted support is verified verbatim.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable

# Each extracted claim needs retrieval and a judge call; short chunks keep
# stop/resume responsive without silently dropping claims from dense prose.
MAX_CHUNK_CHARS = 1_000


class ClaimConfidenceLLMError(ValueError):
    """Retryable invalid structured output from the injected classifier."""


def _canonical_chapters(context: dict) -> dict[str, str]:
    try:
        from orchestrator.tools.m5_writing import canonical_chapter, chapter_prose  # noqa: PLC0415
        m5 = (context or {}).get("m5_writing") or {}
        chapters, direct = m5.get("chapters"), {}
        if isinstance(chapters, dict):
            for name, value in chapters.items():
                canonical = canonical_chapter(name)
                prose = value.get("prose") if isinstance(value, dict) else value
                if canonical and isinstance(prose, str):
                    direct[canonical] = prose
        # Legacy final_sections can carry chapters missing from the editor map;
        # preserve those while keeping raw editor bytes for existing anchors.
        return {**chapter_prose(m5), **direct}
    except Exception:
        return {}


def build_chunks(context: dict) -> list[dict]:
    """Return every canonical chapter as contiguous, boundary-aware chunks."""
    chunks: list[dict] = []
    for chapter, prose in _canonical_chapters(context).items():
        text = str(prose or "")
        fingerprint = hashlib.sha256(text.encode()).hexdigest()
        # Slice the raw canonical string directly: reviews must anchor exactly
        # the bytes the editor/exporter sees, including whitespace.
        start = 0
        while start < len(text):
            end = min(start + MAX_CHUNK_CHARS, len(text))
            if end < len(text):
                boundary = text.rfind("\n", start, end)
                if boundary > start:
                    end = boundary + 1
                else:
                    sentence = list(re.finditer(r"[.!?]\s+", text[start:end]))
                    if sentence:
                        end = start + sentence[-1].end()
            chunks.append(_chunk(chapter, text[start:end], start, fingerprint))
            start = end
    return chunks


def _chunk(chapter: str, text: str, start: int, fingerprint: str) -> dict:
    return {"chapter": chapter, "text": text, "start": start, "end": start + len(text),
            "document_fingerprint": fingerprint,
            "anchor": hashlib.sha256(f"{chapter}\0{start}\0{text}".encode()).hexdigest()[:16]}


def _call(fn: Callable | None, prompt: str) -> Any:
    if fn is None:
        return None
    value = fn(prompt)
    if hasattr(value, "content"):
        value = value.content
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return value


def _claims(chunk: dict, llm_fn: Callable | None) -> tuple[list[dict], list[str]]:
    prompt = ("Identify every substantive general claim that would benefit from scholarly evidence in this thesis excerpt. "
              "Include UNCITED claims as well as already-cited claims; do not limit the list to sentences with author-year citations. "
              "Do not sample a few examples or impose a claim count limit. Exclude the "
              "author's methods, sample, results, hypotheses, and recommendations. Return JSON list of "
              "{text,query}; text must copy a complete original sentence verbatim including any inline citation. "
              "Do not paraphrase or repeat sentences. General methodological knowledge may need citations, "
              "but the author's actual measured statistics must never be sourced from other papers. "
              "query must be a focused English scholarly search query inferred from the original text.\n\n"
              + chunk["text"])
    value = _call(llm_fn, prompt)
    warnings = []
    if llm_fn is None:
        return [], ["Không thể phân loại tuyên bố vì mô hình chưa sẵn sàng."]
    rows = value.get("claims") if isinstance(value, dict) else value
    if not isinstance(rows, list):
        raise ClaimConfidenceLLMError("Mô hình không trả về JSON danh sách tuyên bố hợp lệ.")
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text, query = str(row.get("text") or "").strip(), str(row.get("query") or "").strip()
        lower = text.casefold()
        own_result = ("β" in text or re.search(r"\b(?:p|t|r²|r2)\s*[<=>]", lower)
                      or any(marker in lower for marker in ("giả thuyết", "hypothesis", "mẫu nghiên cứu", "our results")))
        if text and query and text in chunk["text"] and not own_result:
            if not any(item["text"] == text for item in out):
                out.append({"text": text, "query": query})
        elif text and not own_result:
            warnings.append("Một nhận định do mô hình trả về không khớp nguyên văn; không tạo đề xuất cho nhận định đó.")
    return out, warnings


def _identity(source: dict) -> str:
    doi = str(source.get("doi") or "").strip().lower()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi)
    title = re.sub(r"\W+", "", str(source.get("title") or "").casefold())
    return f"doi:{doi}" if doi else f"title:{title}" if title else ""


def _passage(source: dict) -> str:
    for key in ("passage", "abstract", "abstract_preview", "evidence"):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _best_support(claim: str, candidates: list[dict], llm_fn: Callable | None):
    """One bounded judge call chooses among retrieved passages for one claim."""
    rows = []
    for index, source in enumerate(candidates):
        passage = _passage(source)
        if passage:
            rows.append({"candidate_id": str(source.get("id") or index), "source": source, "passage": passage})
    if not rows:
        return None
    prompt_rows = [{"candidate_id": row["candidate_id"], "passage": row["passage"]} for row in rows]
    value = _call(llm_fn, "Choose at most one passage that supports the claim. Return JSON "
                  "{candidate_id,status:supported|weakly_supported|unverifiable,supporting_quote,rationale_vi}; "
                  "rationale_vi must explain in Vietnamese what the passage establishes and any limits. "
                  "Use supported only when the evidence supports the WHOLE claim at its stated strength; "
                  "mere topical similarity is insufficient. quote must be copied exactly.\nCLAIM: " + claim + "\nCANDIDATES: " + json.dumps(prompt_rows, ensure_ascii=False))
    if not isinstance(value, dict) or value.get("status") not in {"supported", "weakly_supported", "unverifiable"}:
        raise ClaimConfidenceLLMError("Mô hình không trả về đánh giá bằng chứng hợp lệ.")
    quote, status = str(value.get("supporting_quote") or "").strip(), str(value.get("status") or "unverifiable")
    wanted = str(value.get("candidate_id") or "")
    for row in rows:
        if wanted == row["candidate_id"] and status in ("supported", "weakly_supported") and quote and quote in row["passage"]:
            return row["source"], {"status": status, "quote": quote, "rationale_vi": str(value.get("rationale_vi") or "")}
    return None


MAX_JUDGMENTS_PER_CALL = 6


def _batch_judgments(records: list[dict], llm_fn: Callable | None,
                     progress_fn: Callable[[dict], None] | None) -> dict[str, tuple[dict, dict] | None]:
    """Judge up to six claims at once, validating every returned association.

    A batch is an all-or-retry contract.  Accepting a partial response would
    make an expensive model omission look like an honest unsupported finding.
    """
    assessed: dict[str, tuple[dict, dict] | None] = {}
    for offset in range(0, len(records), MAX_JUDGMENTS_PER_CALL):
        group = records[offset:offset + MAX_JUDGMENTS_PER_CALL]
        _emit_progress(progress_fn, "evaluating", count=len(group))
        prompt_records = []
        candidate_maps: dict[str, dict[str, tuple[dict, str]]] = {}
        for record in group:
            candidate_map: dict[str, tuple[dict, str]] = {}
            rows = []
            for index, source in enumerate(record["candidates"]):
                passage = _passage(source)
                if not passage:
                    continue
                candidate_id = str(source.get("id") or index)
                if candidate_id in candidate_map:
                    raise ClaimConfidenceLLMError("Nguồn trùng ID trong một nhận định; không thể đối chiếu an toàn.")
                candidate_map[candidate_id] = (source, passage)
                rows.append({"candidate_id": candidate_id, "passage": passage})
            candidate_maps[record["claim_id"]] = candidate_map
            prompt_records.append({"claim_id": record["claim_id"], "claim": record["claim"]["text"], "candidates": rows})

        value = _call(llm_fn, "Assess every listed claim against only its own candidates. Return JSON "
                      "{judgments:[{claim_id,candidate_id,status:supported|weakly_supported|unverifiable,"
                      "supporting_quote,rationale_vi}]}. Return exactly one judgment for every claim_id; "
                      "never omit, duplicate, or invent an ID. For supported or weakly_supported, candidate_id "
                      "must be one of that claim's candidates and supporting_quote must copy its passage exactly. "
                      "Use supported only when the evidence supports the WHOLE claim at its stated strength; "
                      "mere topical similarity is insufficient. Explain the support and its limitations "
                      "in Vietnamese in rationale_vi.\nCLAIMS: " + json.dumps(prompt_records, ensure_ascii=False))
        rows = value.get("judgments") if isinstance(value, dict) else None
        expected = {record["claim_id"] for record in group}
        if not isinstance(rows, list) or len(rows) != len(group):
            raise ClaimConfidenceLLMError("Mô hình không trả về đủ đánh giá bằng chứng theo lô.")
        seen: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ClaimConfidenceLLMError("Mô hình trả về một đánh giá bằng chứng không hợp lệ.")
            claim_id = str(row.get("claim_id") or "")
            if claim_id not in expected or claim_id in seen:
                raise ClaimConfidenceLLMError("Mô hình trả về ID nhận định bị thiếu, lạ hoặc trùng lặp.")
            seen.add(claim_id)
            status = str(row.get("status") or "")
            if status not in {"supported", "weakly_supported", "unverifiable"}:
                raise ClaimConfidenceLLMError("Mô hình trả về trạng thái bằng chứng không hợp lệ.")
            if status == "unverifiable":
                assessed[claim_id] = None
                continue
            candidate_id = str(row.get("candidate_id") or "")
            quote = str(row.get("supporting_quote") or "").strip()
            candidate = candidate_maps[claim_id].get(candidate_id)
            if not candidate or not quote or quote not in candidate[1]:
                raise ClaimConfidenceLLMError("Trích dẫn bằng chứng không khớp nguyên văn nguồn đã truy xuất.")
            source, _ = candidate
            assessed[claim_id] = (source, {
                "status": status, "quote": quote,
                "rationale_vi": str(row.get("rationale_vi") or ""),
            })
        if seen != expected:
            raise ClaimConfidenceLLMError("Mô hình bỏ sót một nhận định trong đánh giá theo lô.")
    return assessed


def _emit_progress(progress_fn: Callable[[dict], None] | None, stage: str, **details: Any) -> None:
    """Progress is advisory: it must never alter a review if its sidecar fails."""
    if progress_fn is None:
        return
    try:
        progress_fn({"stage": stage, **details})
    except Exception:
        pass


def _suggestion_for(record: dict, result: tuple[dict, dict] | None) -> dict:
    """Build one explicit proposal after batch validation has completed."""
    claim, candidates, start = record["claim"], record["candidates"], record["start"]
    if result is None:
        classification = "needs_source" if not candidates else "unverifiable"
        return {"id": hashlib.sha256((record["chunk"]["anchor"] + claim["text"]).encode()).hexdigest()[:16],
                "chapter": record["chunk"]["chapter"],
                "anchor": {"from_offset": record["chunk"]["start"] + max(start, 0), "to_offset": record["chunk"]["start"] + max(start, 0) + len(claim["text"]), "old_text": claim["text"], "document_fingerprint": record["chunk"].get("document_fingerprint")},
                "classification": classification, "rationale_vi": "Không có bằng chứng truy xuất đã kiểm chứng cho nhận định này.",
                "proposed_text": None, "source": None, "evidence": None, "status": "pending", "actionable": False}

    source, assessed = result
    source_view = {key: source.get(key) for key in ("id", "title", "authors", "year", "doi", "url", "provider", "venue")
                   if source.get(key) is not None}
    source_view["verified"] = bool(source.get("verified"))
    anchor = {"from_offset": record["chunk"]["start"] + max(start, 0),
              "to_offset": record["chunk"]["start"] + max(start, 0) + len(claim["text"]),
              "old_text": claim["text"], "document_fingerprint": record["chunk"].get("document_fingerprint")}
    evidence = {"kind": "full_text" if source.get("passage") and source.get("evidence_kind") == "full_text" else "abstract", "text": assessed["quote"],
                "source_url": source.get("url") or ("https://doi.org/" + str(source.get("doi")) if source.get("doi") else None),
                "relation": "supports" if assessed["status"] == "supported" else "partial"}
    suggestion_id = hashlib.sha256((record["chunk"]["anchor"] + claim["text"] + _identity(source)).encode()).hexdigest()[:16]
    try:
        from orchestrator.tools.m5_inline import build_citation_text  # noqa: PLC0415
        citation = build_citation_text(source)
    except Exception:
        citation = ""
    following = record["chunk"]["text"][start + len(claim["text"]):].lstrip()
    already_cited = bool(citation and (citation in claim["text"] or following.startswith(citation)))
    actionable = assessed["status"] == "supported" and source_view["verified"] and bool(citation) and not already_cited
    ending = claim["text"][-1:] if claim["text"][-1:] in ".!?" else ""
    proposed = (claim["text"].rstrip(".!?") + " " + citation + ending) if actionable else None
    return {"id": suggestion_id, "chapter": record["chunk"]["chapter"], "anchor": anchor,
            "classification": ("supported" if already_cited and assessed["status"] == "supported" else "citation_opportunity" if actionable else "partial_support"),
            "rationale_vi": assessed["rationale_vi"] or ("Nguồn cung cấp bằng chứng phù hợp cho nhận định này; bạn có thể bổ sung trích dẫn."
                if actionable else "Bằng chứng chỉ hỗ trợ một phần hoặc chưa đủ điều kiện để chèn trích dẫn tự động."),
            "proposed_text": proposed, "source": source_view, "evidence": evidence,
            "status": "pending", "actionable": actionable, "query": claim["query"]}


def review_chunk(chunk: dict, library: list[dict], search_fn: Callable[[str], Any],
                 llm_fn: Callable | None = None, progress_fn: Callable[[dict], None] | None = None,
                 search_many_fn: Callable[[list[str]], dict[str, Any]] | None = None) -> dict:
    """Review every extracted claim, prefetching independent searches safely.

    Retrieval can overlap because it has no credit side effect. Claim extraction
    and the later batch judge deliberately remain ordered, single-call work so
    a billing checkpoint still controls every model invocation.
    """
    suggestions, warnings = [], []
    metrics = {"claims_total": 0, "claims_assessed": 0, "claims_unresolved": 0,
               "queries": 0, "candidates": 0, "supported": 0}
    _emit_progress(progress_fn, "analyzing")
    claims, claim_warnings = _claims(chunk, llm_fn)
    warnings.extend(claim_warnings)
    metrics["claims_total"] = len(claims)
    _emit_progress(progress_fn, "claims_identified", count=len(claims))

    # Establish all edit anchors before issuing a request. A duplicated sentence
    # cannot be applied safely, so it must not spend a provider lookup either.
    anchored_claims: list[dict] = []
    queries: list[tuple[str, str]] = []
    query_keys: set[str] = set()
    for index, claim in enumerate(claims):
        starts = [match.start() for match in re.finditer(re.escape(claim["text"]), chunk["text"])]
        if len(starts) != 1:
            warnings.append("Bỏ qua tuyên bố trùng lặp trong đoạn vì không thể tạo neo chỉnh sửa duy nhất.")
            metrics["claims_unresolved"] += 1
            continue
        query_key = re.sub(r"\s+", " ", claim["query"].casefold()).strip()
        anchored_claims.append({"claim_id": str(index), "claim": claim, "start": starts[0], "query_key": query_key})
        if query_key not in query_keys:
            query_keys.add(query_key)
            queries.append((query_key, claim["query"]))

    query_cache: dict[str, list[dict]] = {}
    metrics["queries"] = len(queries)
    if search_many_fn is not None and queries:
        # The callback owns the bounded worker pool. Progress is recorded before
        # dispatch and results are replayed in this stable order, not completion
        # order, so the later model prompt and cache key remain deterministic.
        _emit_progress(progress_fn, "parallel_searching", count=min(3, len(queries)))
        for _, query in queries:
            _emit_progress(progress_fn, "search_queued", query=query)
        try:
            prefetched = search_many_fn([query for _, query in queries])
        except Exception:
            prefetched = {}
            warnings.append("Không thể tra cứu song song một số nguồn; các nhận định tương ứng chưa được xác minh.")
        if not isinstance(prefetched, dict):
            prefetched = {}
            warnings.append("Kết quả tra cứu nguồn không hợp lệ; không dùng để tạo đề xuất.")
        for query_key, query in queries:
            searched = prefetched.get(query_key)
            if searched is None:
                # Do not silently repeat an uncertain parallel request in the
                # serial fallback: that can duplicate provider work on retry.
                query_cache[query_key] = []
                warnings.append("Không nhận được kết quả cho một truy vấn nguồn; nhận định tương ứng chưa được xác minh.")
                _emit_progress(progress_fn, "search_results", query=query, count=0)
                continue
            rows = searched.get("results", []) if isinstance(searched, dict) else searched
            if isinstance(searched, dict):
                warnings.extend(str(warning) for warning in (searched.get("warnings", []) or []))
            query_cache[query_key] = list(rows or [])
            _emit_progress(progress_fn, "search_results", query=query, count=len(query_cache[query_key]))

    records: list[dict] = []
    for item in anchored_claims:
        claim, query_key = item["claim"], item["query_key"]
        if query_key not in query_cache:
            # Existing callers and unit tests use the one-query seam. The API
            # passes search_many_fn, so production does not serialize queries.
            _emit_progress(progress_fn, "searching", query=claim["query"])
            searched = search_fn(claim["query"]) or {}
            search_rows = searched.get("results", []) if isinstance(searched, dict) else searched
            if isinstance(searched, dict):
                warnings.extend(str(warning) for warning in (searched.get("warnings", []) or []))
            query_cache[query_key] = list(search_rows or [])
            _emit_progress(progress_fn, "search_results", query=claim["query"], count=len(query_cache[query_key]))
        words = set(re.findall(r"\w{3,}", claim["query"].casefold()))

        def rank(paper):
            haystack = (str(paper.get("title") or "") + " " + _passage(paper)).casefold()
            return (bool(_passage(paper)), sum(word in haystack for word in words))

        old = sorted((paper for paper in library if isinstance(paper, dict)), key=rank, reverse=True)
        fresh = sorted((paper for paper in query_cache[query_key] if isinstance(paper, dict)), key=rank, reverse=True)
        candidates, identities = [], set()
        for source in old[:1] + fresh[:3] + old[1:4] + fresh[3:4]:
            identity = _identity(source)
            if not identity or identity in identities:
                continue
            identities.add(identity)
            candidates.append(source)
        candidates = candidates[:4]
        metrics["candidates"] += len(candidates)
        metrics["claims_assessed"] += 1
        records.append({"claim_id": item["claim_id"], "claim": claim, "candidates": candidates,
                        "start": item["start"], "chunk": chunk})

    judgeable = [record for record in records if any(_passage(source) for source in record["candidates"])]
    judged = _batch_judgments(judgeable, llm_fn, progress_fn) if judgeable else {}
    for record in records:
        result = judged.get(record["claim_id"])
        if result is None:
            metrics["claims_unresolved"] += 1
        else:
            metrics["supported"] += result[1]["status"] == "supported"
        suggestion = _suggestion_for(record, result)
        if result is not None and not suggestion["actionable"] and suggestion["classification"] != "supported":
            metrics["claims_unresolved"] += 1
        suggestions.append(suggestion)
    return {"suggestions": suggestions, "metrics": metrics, "warnings": warnings}
