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
    page_overlap,
    same_page,
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
    # "trong spss" is a page-family phrase (see FAMILY_PHRASES): the software
    # names the kind of page, the topic is the regression.
    assert tokens("cách chạy hồi quy trong spss") == {"hồi", "quy"}
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


# ---- calibration on the 2026-09-08 load (156 refusals reviewed by hand) ----


def test_family_phrases_do_not_count_as_shared_topic():
    from app.blog.similarity import tokens, overlap

    assert tokens("mô hình tam") == {"tam"}
    assert overlap(tokens("mô hình tam"), tokens("mô hình swot")) == 0.0
    assert overlap(tokens("ave trong spss"), tokens("spss")) == 0.0
    # a longer phrasing of the same page still clashes
    assert overlap(tokens("thang đo likert 5 mức độ"), tokens("thang đo likert")) == 1.0
    # syllables inside a topic survive: "kiểm định" goes, "định tính" stays
    assert tokens("định tính là gì") == {"định", "tính"}


def test_a_procedure_page_and_its_definition_page_are_different_intents():
    from app.blog.similarity import classify

    assert classify("biến điều tiết trong smartpls") == "how-to"
    assert classify("biến điều tiết") == "informational"
    assert classify("cronbach alpha trong spss") == "how-to"


# ---- the head rule, calibrated on the 979-seed load (342 refusals read) ----
#
# `tokens()` strips page-family phrases, and stripping can leave one keyword a
# token subset of another. The overlap coefficient is `shared / min`, so every
# such subset scored 100% and 342 written pages were refused. Vietnamese is
# head-initial: extra words AFTER the shared span narrow the same head (one
# page), extra words IN FRONT name a new head that takes the rest as its
# complement (two pages). These are the real pairs the rule was calibrated on.


def test_a_specifier_appended_to_the_same_head_is_still_one_page():
    # The refusals this rule must NOT lift: they were all genuine.
    assert same_page("thang đo likert 5 mức độ", "thang đo likert")
    assert same_page("thang đo likert 7 mức độ", "thang đo likert")
    # Family stripping may EQUATE two keywords — that is what it is for.
    assert same_page("mô hình servqual", "servqual")
    assert same_page("lý thuyết tam", "mô hình tam")
    assert same_page("công thức phương sai", "phương sai")


def test_one_qualifier_in_front_is_a_qualifier_not_a_new_head():
    # A single token in front is a brand or an acronym prefix, not a noun that
    # takes the phrase as its complement. "gg" is Google; a Google Form page
    # and a form page are one SERP.
    assert same_page("gg form khảo sát", "form khảo sát")
    assert same_page("cb sem là gì", "sem là gì")


def test_a_different_head_in_front_is_a_different_page():
    # A research PROPOSAL is not research, a research METHOD is not research,
    # and a research MODEL is not research. All three were refused against
    # "nghiên cứu khoa học" on the 979-seed load; all three are real pages.
    assert not same_page("đề cương nghiên cứu khoa học", "nghiên cứu khoa học")
    assert not same_page("phương pháp nghiên cứu khoa học", "nghiên cứu khoa học")
    assert not same_page("mô hình nghiên cứu", "nghiên cứu khoa học")
    # ... and the same shape elsewhere in the bank.
    assert not same_page("đề tài luận văn kinh tế", "luận văn")
    assert not same_page("cấu trúc vốn là gì", "mô hình cấu trúc là gì")
    assert not same_page("split half reliability là gì", "reliability là gì")


def test_stripping_may_equate_two_keywords_but_not_nest_one_inside_the_other():
    # "mô hình nghiên cứu" only fits inside "nghiên cứu khoa học" because its
    # own head was stripped as a page family. Every word of the BROADER keyword
    # has to survive in the narrower one, family words included, or the
    # containment is an artefact of the stripper rather than a shared topic.
    assert tokens("mô hình nghiên cứu") < tokens("nghiên cứu khoa học")
    assert overlap(tokens("mô hình nghiên cứu"), tokens("nghiên cứu khoa học")) == 1.0
    assert page_overlap("mô hình nghiên cứu", "nghiên cứu khoa học") == 0.0
    # A family phrase in FRONT of the shared span is transparent, though: it
    # names the kind of page, so it cannot be the new head.
    assert same_page("công thức tính phương sai", "cách tính phương sai")


def test_a_partial_overlap_never_blocks():
    """Measured on the 125 partial pairs the loader refused on 2026-09-08.

    Each side holds a word the other lacks, and whether that makes one page or
    two turns on synonymy, which this coefficient cannot see. Raising the bar
    did not separate them: at 75% and above the split was still about six
    one-page pairs against twenty-two genuinely different ones. Refusing costs
    more than passing, because plan absorbs a refused keyword and the page is
    never commissioned, so partial overlap is reported by the audit and blocked
    by nobody.
    """
    # Two pages that would have been merged, and are not close to the same page.
    for a, b in (("khoảng tin cậy", "độ tin cậy"),
                 ("ordinary least squares là gì", "partial least squares là gì"),
                 ("phần mềm spss", "phần mềm stata"),
                 ("lỗi ave nhỏ hơn 0 5 spss", "lỗi kmo nhỏ hơn 0 5 spss")):
        assert not (tokens(a) < tokens(b) or tokens(b) < tokens(a)), "partial, not containment"
        assert overlap(tokens(a), tokens(b)) >= CLASH_THRESHOLD, "the raw coefficient still fires"
        assert page_overlap(a, b) == 0.0
        assert not same_page(a, b)

    # The price of the rule, stated rather than hidden: a synonym pair now ships
    # as two pages and is left to the audit and a human to consolidate.
    assert not same_page("lời nói đầu", "lời mở đầu")


def test_same_page_needs_the_intent_to_agree_as_well():
    # `page_overlap` scores the topic; `same_page` is the whole test, and the
    # intent split is the older half of it.
    assert page_overlap("cronbach alpha trong spss", "cronbach alpha là gì") == 1.0
    assert not same_page("cronbach alpha trong spss", "cronbach alpha là gì")


def test_find_clashes_uses_the_head_rule():
    subject = _c("new", "đề cương nghiên cứu khoa học")
    assert find_clashes(subject, [_c("old", "nghiên cứu khoa học")]) == []
