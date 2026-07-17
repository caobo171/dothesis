"""Similarity & quote-hygiene self-check (roadmap #11) — offline."""
import subprocess
import sys

import pytest

from quality.similarity import (
    K, W, check_similarity, matched_spans, normalize_tokens, shingle_hashes,
    similarity_findings, similarity_report, source_label, source_texts, winnow,
)

SRC_TEXT = ("Perceived organisational support consistently predicts affective commitment across "
            "sectors and cultures, and this relationship is mediated by felt obligation among "
            "employees in emerging markets today")


def _store(chapters, sources=(), hypotheses=()):
    return {"m5_writing": {"chapters": {k: {"prose": v} for k, v in chapters.items()}},
            "m2_literature": {"literature_sources": list(sources)},
            "m3_design": {"hypotheses": list(hypotheses)}}


# --- core -------------------------------------------------------------------

def test_tokens_offsets_roundtrip():
    text = "Hello, World! Xin chào."
    toks = normalize_tokens(text)
    for tok, s, e in toks:
        assert text[s:e].lower() == tok


def test_nfc_composed_and_decomposed_agree():
    import unicodedata
    a = "tác động tích cực"
    b = unicodedata.normalize("NFD", a)
    assert [t[0] for t in normalize_tokens(a)] == [t[0] for t in normalize_tokens(b)]


def test_hash_is_deterministic_across_processes():
    code = ("import sys; sys.path.insert(0,'.');"
            "from quality.similarity import shingle_hashes;"
            "print(shingle_hashes(['a','b','c','d','e','f','g'])[0])")
    outs = []
    for seed in ("1", "2"):
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                           env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"})
        outs.append(r.stdout.strip())
    assert outs[0] == outs[1] and outs[0]  # blake2b, not builtin hash()


def test_winnow_rightmost_min_and_dedup():
    fp = winnow([5, 3, 3, 9, 7, 1], w=3)
    assert fp and all(isinstance(x, tuple) for x in fp)


def test_detection_floor_property():
    common = [f"w{i}" for i in range(W + K - 1)]  # exactly 10 tokens
    a = [f"a{i}" for i in range(30)] + common + [f"a{i}" for i in range(30, 60)]
    b = [f"b{i}" for i in range(30)] + common + [f"b{i}" for i in range(30, 60)]
    fa = {h for h, _ in winnow(shingle_hashes(a))}
    fb = {h for h, _ in winnow(shingle_hashes(b))}
    assert fa & fb  # a 10-token run is always detected


def test_short_common_run_not_detected():
    common = [f"w{i}" for i in range(K - 1)]  # 6 tokens
    a = [f"a{i}" for i in range(40)] + common
    b = [f"b{i}" for i in range(40)] + common
    assert not ({h for h, _ in winnow(shingle_hashes(a))} & {h for h, _ in winnow(shingle_hashes(b))})


def test_matched_spans_exact_boundaries():
    src = normalize_tokens(SRC_TEXT)
    draft = normalize_tokens("In this study we argue that " + SRC_TEXT + " which motivates our model")
    spans = matched_spans(draft, src, 12)
    assert len(spans) == 1 and spans[0]["tokens"] >= 20


def test_min_span_filter():
    assert matched_spans(normalize_tokens("one two three four five six seven eight nine ten"),
                         normalize_tokens("one two three four five six seven eight nine ten"),
                         12) == []


# --- corpus -----------------------------------------------------------------

def test_source_texts_prefers_abstract_falls_back_to_title():
    assert source_texts({"abstract": "A long abstract"})[0][0] == "abstract"
    assert source_texts({"title": "Only a title"})[0][0] == "title"
    assert source_texts("not a dict") == []


def test_source_label():
    assert source_label({"authors": ["Nguyen, T."], "year": 2023}) == "Nguyen 2023"


def test_known_plant_source_overlap():
    store = _store({"lit_review": "Prior work shows that " + SRC_TEXT + " and this matters a lot here."},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    raw = check_similarity(store)
    assert len(raw["source_overlaps"]) == 1
    assert raw["source_overlaps"][0]["source"] == "Nguyen 2023"


def test_paraphrase_no_match():
    store = _store({"lit_review": "Support from the organisation tends to raise how attached staff feel, "
                                  "an effect that seems to run through a sense of reciprocal duty."},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    assert check_similarity(store)["source_overlaps"] == []


def test_intra_duplication_detected():
    dup = ("The structural model was estimated with the partial least squares algorithm using five "
           "thousand bootstrap subsamples and the resulting path coefficients were then interpreted "
           "against the hypothesised relationships in the model")
    store = _store({"results": "We report the findings. " + dup, "discussion": dup + " Furthermore we note."})
    assert check_similarity(store)["intra_duplication"]


def test_hypothesis_restatement_exempt():
    h = ("H1: perceived organisational support has a significant positive effect on affective "
         "commitment among employees working in emerging market firms today")
    store = _store({"results": "We tested it. " + h, "discussion": h + " This was confirmed."},
                   hypotheses=[h])
    assert check_similarity(store)["intra_duplication"] == []


def test_cite_pill_and_bibliography_immunity():
    pill = "{{cite: A | " + SRC_TEXT + " | http://x}}"
    store = _store({"lit_review": "Background text here is fine. " + pill,
                    "results": "References\n" + SRC_TEXT},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    assert check_similarity(store)["source_overlaps"] == []


def test_never_raises_on_garbage():
    assert check_similarity({})["source_overlaps"] == []
    assert check_similarity({"m5_writing": None, "m2_literature": {"literature_sources": ["x"]}})["source_overlaps"] == []


# --- hygiene ----------------------------------------------------------------

def _hyg(prose):
    return similarity_findings(_store({"lit_review": prose},
                                      [{"title": "T", "abstract": SRC_TEXT,
                                        "authors": ["Nguyen, T."], "year": 2023}]))


def test_quoted_and_cited_is_clean():
    assert _hyg(f'As argued, "{SRC_TEXT}" (Nguyen, 2023). We build on that claim here.') == []


def test_unquoted_uncited_finding_copy():
    f = _hyg("Prior work shows that " + SRC_TEXT + " and this matters here.")
    assert len(f) == 1 and "quote it with a page number, or paraphrase" in f[0]["fix"].lower()


def test_unquoted_but_cited():
    f = _hyg("Prior work shows that " + SRC_TEXT + " (Nguyen, 2023).")
    assert f and "quotation marks" in f[0]["fix"]


def test_all_findings_soft():
    dup = "The structural model was estimated with partial least squares using five thousand bootstrap " \
          "subsamples and the path coefficients were interpreted against the hypothesised relationships"
    store = _store({"lit_review": "Prior work shows that " + SRC_TEXT + " indeed.",
                    "results": dup, "discussion": dup},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    fs = similarity_findings(store)
    assert fs and all(f["severity"] == "soft" for f in fs)
    assert all(set(f) == {"issue", "fix", "chapter", "severity"} for f in fs)


# --- report -----------------------------------------------------------------

def test_report_schema_and_no_headline():
    store = _store({"lit_review": "Prior work shows that " + SRC_TEXT + " indeed."},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    r = similarity_report(store)
    assert r["headline"] is None  # never a percentage
    assert set(r) == {"headline", "counts", "top_spans", "per_source", "truncated", "coverage_note"}
    assert len(r["top_spans"]) <= 10
    assert "NOT a Turnitin scan" in r["coverage_note"]
    assert similarity_report(store) == r  # deterministic


def test_report_never_raises():
    assert similarity_report({})["headline"] is None


# --- both store shapes + rubric dimension -----------------------------------

def test_flat_store_shape_works():
    """store.load()'s FLAT contextStore (what export_docx passes) must work too."""
    flat = {"chapters": {"lit_review": {"prose": "Prior work shows that " + SRC_TEXT + " indeed."}},
            "literature_sources": [{"title": "T", "abstract": SRC_TEXT,
                                    "authors": ["Nguyen, T."], "year": 2023}]}
    assert len(check_similarity(flat)["source_overlaps"]) == 1


def test_rubric_dimension():
    from quality.rubric import similarity_dimension
    store = _store({"lit_review": "Prior work shows that " + SRC_TEXT + " indeed."},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    d = similarity_dimension(store)
    assert d["name"] == "similarity" and d["weight"] == 0.10
    assert d["findings"] and all(f["severity"] == "soft" for f in d["findings"])
    assert d["score"] < 1.0
    assert similarity_dimension({})["score"] == 1.0


def test_rubric_dimension_never_blocks(monkeypatch):
    from quality import rubric
    monkeypatch.setattr(rubric, "judge_dimension",
                        lambda name, weight, prompt, cs: {"name": name, "weight": weight,
                                                          "score": 0.6, "findings": []})
    store = _store({"lit_review": "Prior work shows that " + SRC_TEXT + " indeed."},
                   [{"title": "T", "abstract": SRC_TEXT, "authors": ["Nguyen, T."], "year": 2023}])
    out = rubric.score_thesis(store)
    assert "similarity" in {d["name"] for d in out["dimensions"]}
    sim = next(d for d in out["dimensions"] if d["name"] == "similarity")
    assert sim["findings"] and not any(f["issue"] in out["blocking"] for f in sim["findings"])
