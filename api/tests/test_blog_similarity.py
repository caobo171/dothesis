"""Topic overlap, and the intent classifier that makes it usable.

Ported from WELE's `tests/blog.similarity.ts`, with the intent buckets
retargeted at this market: a thesis-methods blog asks "what is X", "how do I
run X in SPSS" and "X is broken, now what" far more than it asks "which app".
"""
from __future__ import annotations

from app.blog.similarity import (
    CLASH_THRESHOLD,
    Candidate,
    classify,
    find_clashes,
    overlap,
    tokens,
)


def test_tokens_drop_stopwords_and_punctuation():
    t = tokens("Cronbach's Alpha là gì?")
    assert "là" not in t and "gì" not in t
    assert {"cronbach", "alpha"} <= t


def test_tokens_drop_single_characters_and_empty_input():
    assert tokens("") == set()
    # "t-test" splits to "t" and "test"; a one-character token carries no topic.
    assert tokens("kiểm định t-test") >= {"test"}
    assert "t" not in tokens("kiểm định t-test")


def test_tokens_keep_the_words_that_carry_the_topic():
    assert tokens("cách chạy hồi quy trong spss") >= {"hồi", "quy", "spss"}
    assert "trong" not in tokens("cách chạy hồi quy trong spss")


def test_classify_definition():
    assert classify("cronbach alpha là gì") == "definition"
    assert classify("khái niệm biến trung gian") == "definition"


def test_classify_how_to():
    assert classify("cách chạy hồi quy trong spss") == "how-to"
    assert classify("kiểm định anova spss") == "how-to"


def test_classify_troubleshooting():
    assert classify("ma trận xoay lộn xộn phải làm sao") == "troubleshooting"
    assert classify("lỗi khi chạy efa") == "troubleshooting"


def test_classify_tool():
    assert classify("phần mềm spss miễn phí") == "tool"


def test_classify_comparison():
    assert classify("so sánh pls-sem và cb-sem") == "comparison"


def test_classify_falls_back_to_informational():
    assert classify("mô hình nghiên cứu") == "informational"
    assert classify("") == "informational"


def test_classify_prefers_definition_over_the_software_noun():
    # "phần mềm spss là gì" is a definition page, not a download page. The
    # order of the marker table is what decides this, so it is pinned.
    assert classify("phần mềm spss là gì") == "definition"


def test_overlap_is_the_overlap_coefficient_not_jaccard():
    assert overlap({"a", "b"}, {"a", "b", "c", "d"}) == 1
    assert overlap(set(), {"a"}) == 0


def _c(slug, focus, locale="vi", id=None):
    return Candidate(id=id, slug=slug, locale=locale, title="", focus=focus)


def test_find_clashes_needs_the_same_locale_and_the_same_intent():
    subject = _c("new", "cronbach alpha là gì")
    others = [
        _c("same-intent", "hệ số cronbach alpha là gì"),
        _c("other-intent", "cách chạy cronbach alpha trong spss"),
        _c("other-locale", "cronbach alpha là gì", locale="en"),
    ]
    clashes = find_clashes(subject, others)
    assert [c.slug for c in clashes] == ["same-intent"]
    assert clashes[0].score >= CLASH_THRESHOLD
    assert clashes[0].intent == "definition"


def test_find_clashes_never_reports_a_post_against_itself():
    subject = _c("x", "cronbach alpha là gì", id=7)
    assert find_clashes(subject, [_c("x", "cronbach alpha là gì", id=7)]) == []


def test_find_clashes_is_sorted_by_score_descending():
    subject = _c("new", "phân tích efa là gì")
    others = [
        _c("weaker", "phân tích efa và cfa khác biệt ở đâu là gì"),
        _c("stronger", "phân tích efa là gì"),
    ]
    scores = [c.score for c in find_clashes(subject, others, threshold=0.0)]
    assert scores == sorted(scores, reverse=True)


def test_find_clashes_ignores_a_subject_with_no_usable_tokens():
    assert find_clashes(_c("new", "là gì"), [_c("other", "là gì")]) == []
