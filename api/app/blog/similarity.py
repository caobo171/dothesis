"""Are these two posts chasing the same ranking?

Port of WELE's `services/blog/similarity.ts`, with the finding that produced
it kept intact: token overlap ALONE is not cannibalisation. WELE's first audit
run reported 48 pairs on overlap alone, which is more than anyone acts on, so
they were ignored. Classifying the search intent first cuts the list to the
pairs that actually compete for one SERP.

What changed for this market is only the intent table. WELE's buckets were
built for "which dictation app should I use"; a quantitative-methods blog is
mostly `X là gì`, `cách chạy X trong SPSS` and `X bị lỗi, phải làm sao`, so
`definition` and `troubleshooting` are first-class here and `announcement` is
gone.

There is exactly one implementation, and both the save-time guard and the SEO
audit call it — a second one would have to relearn the 48-pairs lesson, and
would relearn it in production. `plan` joined them on 2026-09-08 through
`same_page`, after a load in which 342 of 979 written pages were refused
because plan's `cluster_key` and this module disagreed about what one page is.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Literal

# Function words that carry no topic. Both the accented and unaccented spelling
# of each, because keywords arrive typed either way and `tokens` deliberately
# does NOT strip diacritics (doing so would collide "đo" with "do").
STOP: frozenset[str] = frozenset({
    "la", "là", "gi", "gì", "cach", "cách", "cho", "va", "và", "nao", "nào",
    "cua", "của", "mot", "một", "nhung", "những", "ban", "bạn", "khi", "de",
    "để", "trong", "voi", "với", "co", "có", "khong", "không", "bao", "nhieu",
    "nhiêu", "nhu", "như", "nay", "này", "bang", "bằng", "tren", "trên",
    "duoc", "được", "thi", "thì", "se", "sẽ", "da", "đã", "tot", "tốt",
    "nhat", "nhất",
    "with", "the", "for", "and", "how", "to", "of", "in", "on", "is", "what",
    "best",
})

Intent = Literal["comparison", "troubleshooting", "definition", "tool",
                 "how-to", "informational"]

# Order is the decision procedure: the FIRST pattern that matches wins.
#
# `comparison` leads because "so sánh A và B" is a comparison page whatever
# else it says. `troubleshooting` outranks `how-to` because "cách khắc phục ma
# trận xoay lộn xộn" is a rescue page, not a procedure page. `definition`
# outranks `tool` so "phần mềm SPSS là gì" is a definition, not a download.
#
# Deliberately absent: `đánh giá` (an evaluation, e.g. "đánh giá mô hình đo
# lường", is a SmartPLS procedure here, not a product review) and `tải` (the
# noun in "hệ số tải" is a factor loading, not a download).
INTENT_MARKERS: tuple[tuple[Intent, re.Pattern[str]], ...] = tuple(
    (intent, re.compile(pattern, re.IGNORECASE))
    for intent, pattern in (
        ("comparison", r"(so sánh|so sanh|khác nhau|khac nhau|\bvs\b|\btop\b|"
                       r"tốt nhất|tot nhat|nên chọn|nen chon|nên dùng|nen dung|\bbest\b)"),
        ("troubleshooting", r"(lỗi|\bloi\b|không hội tụ|khong hoi tu|lộn xộn|lon xon|"
                            r"phải làm sao|phai lam sao|khắc phục|khac phuc|bị loại|bi loai|"
                            r"không chạy|khong chay|\berror\b|\bfix\b)"),
        ("definition", r"(là gì|la gi|nghĩa là|nghia la|khái niệm|khai niem|"
                       r"định nghĩa|dinh nghia|ý nghĩa|y nghia|\bwhat is\b|definition)"),
        ("tool", r"(phần mềm|phan mem|download|crack|miễn phí|mien phi|\bfree\b|"
                 r"online|\bapp\b|website|trang web|công cụ|cong cu)"),
        # "X trong SPSS" is a procedure page even without a verb; the same X
        # without the software is the definition page, and the two do not
        # compete for one SERP (calibration finding, 2026-09-08).
        ("how-to", r"(cách|\bcach\b|hướng dẫn|huong dan|làm sao|lam sao|các bước|cac buoc|"
                   r"chạy|\bchay\b|thực hiện|thuc hien|\bhow to\b|kiểm định|kiem dinh|"
                   r"phân tích|phan tich|viết|\bviet\b|tính|\btinh\b|"
                   r"trong spss|trong smartpls|trong amos|trong stata)"),
    )
)

# Two posts on one intent split their own ranking. WELE's calibrated value;
# see guard.py for why the fix for false positives was a narrower key rather
# than a higher number.
CLASH_THRESHOLD = 0.6

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)

# Page-family phrases: they say what KIND of page this is, not what it is
# about. Calibrated on the 2026-09-08 load, where 156 of 421 seeds were refused
# and 49 of those were pairs like "mô hình tam" vs "mô hình swot" (2 of 3
# syllables shared, so 0.67 on the overlap coefficient) and "ave trong spss" vs
# "spss". Removed as PHRASES, not syllables: dropping "định" alone would gut
# "định tính" and "định lượng", which are topics.
#
# Six phrases were added on the 979-seed load, where 342 seeds were refused and
# every refusal was read. "lý thuyết" is the pair of "mô hình" ("lý thuyết TAM"
# and "mô hình TAM" are one page), "biểu đồ" the pair of "thang đo", "kiểm tra"
# the pair of "kiểm định", and "hệ số" is what made "hệ số ICC là gì" collide
# with "hệ số chặn là gì" — two different coefficients sharing a family noun.
# "trong luận văn" is "trong spss" for the other half of the bank: it names
# where the thing sits, so "mục lục trong luận văn" and "kết luận trong luận
# văn" are a table of contents and a conclusion, not one page. That one phrase
# accounts for 30 of the 89 refusals this calibration lifted.
FAMILY_PHRASES: tuple[str, ...] = (
    "mô hình", "mo hinh", "lý thuyết", "ly thuyet", "thang đo", "thang do",
    "biểu đồ", "bieu do", "hệ số", "he so", "kiểm định", "kiem dinh",
    "kiểm tra", "kiem tra",
    "phân tích", "phan tich", "công thức", "cong thuc", "bài tập", "bai tap",
    "có lời giải", "co loi giai", "các loại", "cac loai", "cách tính", "cach tinh",
    "cách chạy", "cach chay", "trong spss", "trong smartpls", "trong amos",
    "trong stata", "trong luận văn", "trong luan van", "hướng dẫn", "huong dan",
)
_FAMILY_RE = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(p) for p in FAMILY_PHRASES) + r")(?!\w)",
    re.IGNORECASE)


def tokens(text: str) -> set[str]:
    cleaned = _FAMILY_RE.sub(" ", (text or "").lower())
    cleaned = _NON_WORD.sub(" ", cleaned)
    return {t for t in cleaned.split() if len(t) > 1 and t not in STOP}


def classify(text: str) -> Intent:
    for intent, pattern in INTENT_MARKERS:
        if pattern.search(text or ""):
            return intent
    return "informational"


def overlap(a: set[str], b: set[str]) -> float:
    """Overlap coefficient: shared / smaller set, NOT Jaccard.

    A three-word keyword fully contained in a seven-word one is the same topic
    at a different length; Jaccard would score that 0.43 and let it through.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


# How many content tokens may sit in FRONT of the shared span before the longer
# keyword counts as naming a different thing. One is a qualifier ("gg" in "gg
# form khảo sát", "cb" in "cb sem là gì"); two is a Vietnamese noun ("đề cương",
# "phương pháp", "đề tài") that takes the rest of the phrase as its complement.
MAX_QUALIFIER_TOKENS = 1


def _sequence(text: str) -> list[tuple[str, bool]]:
    """`(token, is_family)` in reading order — `tokens()` with the order kept.

    `tokens()` throws the family phrases away and returns a set, which is what
    the overlap coefficient wants. `same_page` needs to know WHERE the words
    that survived sat, so this keeps every content token and flags the ones a
    family phrase contributed.
    """
    lowered = (text or "").lower()

    def content(chunk: str) -> list[str]:
        return [t for t in _NON_WORD.sub(" ", chunk).split()
                if len(t) > 1 and t not in STOP]

    out: list[tuple[str, bool]] = []
    pos = 0
    for match in _FAMILY_RE.finditer(lowered):
        out += [(t, False) for t in content(lowered[pos:match.start()])]
        out += [(t, True) for t in content(match.group(0))]
        pos = match.end()
    out += [(t, False) for t in content(lowered[pos:])]
    return out


def _narrows(broad: str, narrow: str) -> bool:
    """Is `narrow` the same page as `broad`, only more specific?

    Called only when `broad`'s topic tokens are a strict subset of `narrow`'s,
    which is where the overlap coefficient reports 100% and is sometimes wrong.
    Vietnamese is head-initial, so the position of the extra words decides:

      `thang đo likert`  ->  `thang đo likert 5 mức độ`   appends a specifier to
      the same head, one page — while

      `nghiên cứu khoa học`  ->  `đề cương nghiên cứu khoa học`  puts a NEW head
      ("đề cương", a proposal) in front and makes the old head its complement.
      A research proposal is not research; these are two pages.

    Two conditions, and the first one is the reason the fix could not just be a
    higher threshold. `tokens()` strips page-family phrases, so a keyword whose
    head IS a family phrase can shrink into a subset of an unrelated one:
    `mô hình nghiên cứu` becomes `{nghiên, cứu}` and disappears inside
    `nghiên cứu khoa học`. Stripping may EQUATE two keywords (`mô hình servqual`
    and `servqual` are one page); it may not silently make one a subset of the
    other. So every word of the broader keyword — family words included — has to
    still be there in the narrower one.
    """
    narrow_seq = _sequence(narrow)
    narrow_words = {t for t, _ in narrow_seq}
    broad_words = {t for t, _ in _sequence(broad)}
    if not broad_words or not broad_words <= narrow_words:
        return False
    lead = 0
    for token, is_family in narrow_seq:
        if token in broad_words:
            break
        # A family phrase in front names the KIND of page, not a new head:
        # "công thức tính phương sai" is still the "cách tính phương sai" page.
        lead += not is_family
    return lead <= MAX_QUALIFIER_TOKENS


def page_overlap(a: str, b: str) -> float:
    """How much of one page's topic the other one covers, 0.0 when they differ.

    The overlap coefficient with the head rule applied. `overlap()` alone
    reports 100% for every containment, and containment is the one case it
    cannot judge on its own — see `_narrows`. A partial overlap (neither set
    inside the other) is two phrasings of one topic and the coefficient is
    right about it, so it is passed straight through.
    """
    ta, tb = tokens(a), tokens(b)
    score = overlap(ta, tb)
    if score <= 0.0 or ta == tb:
        return score
    if ta < tb:
        return score if _narrows(a, b) else 0.0
    if tb < ta:
        return score if _narrows(b, a) else 0.0
    # Partial overlap, where each keyword holds a word the other lacks, is not
    # something this coefficient can judge. Measured over the 125 partial pairs
    # the loader refused on 2026-09-08: what separates "cách trích dẫn tài liệu
    # tham khảo" from "cách ghi tài liệu tham khảo" (one page) is that the
    # differing words are synonyms, and what separates "khoảng tin cậy" from
    # "độ tin cậy" (two pages) is that they are not. The coefficient sees the
    # same number either way, and raising the bar does not help: at 75% and
    # above the split was still roughly six one-page pairs against twenty-two
    # genuinely different ones, including "độ tin cậy tổng hợp" against "độ tin
    # cậy 95" and "nghiện mạng xã hội" against "quảng cáo trên mạng xã hội".
    #
    # So partial overlap is not a block. The costs are not symmetric: a false
    # refusal deletes a real page for good, because `plan` absorbs its keyword
    # into the winner and never commissions it, while a false pass ships two
    # pages a human can merge later without rewriting either. `audit.py`
    # deliberately keeps using the raw coefficient so these pairs still surface
    # for review; they are simply no longer refused at the door.
    return 0.0


def same_page(a: str, b: str, threshold: float = CLASH_THRESHOLD) -> bool:
    """THE test for "these two keywords are one page".

    `plan` calls it over the rows it is about to emit and the loader's guard
    calls it (through `find_clashes`) over the rows it is about to insert, so a
    backlog row that plan kept cannot be refused at load time. Two answers to
    this question is what cost 342 written pages on the 2026-09-08 load.
    """
    return classify(a) == classify(b) and page_overlap(a, b) >= threshold


@dataclass(frozen=True)
class Candidate:
    slug: str
    locale: str
    title: str
    focus: str
    id: object | None = None


@dataclass(frozen=True)
class Clash:
    slug: str
    title: str
    focus: str
    score: float
    intent: str


def find_clashes(
    subject: Candidate,
    others: Iterable[Candidate],
    threshold: float = CLASH_THRESHOLD,
) -> list[Clash]:
    """The posts in `others` that compete with `subject`.

    The fingerprint is the focus keyword, falling back to the title: a post
    with no focus keyword still occupies a topic. `guard.py` closes that
    fallback off for the save-time block — see its header for why.
    """
    subject_text = subject.focus or subject.title or ""
    subject_tokens = tokens(subject_text)
    subject_intent = classify(subject_text)
    if not subject_tokens:
        return []

    out: list[Clash] = []
    for other in others:
        if subject.id is not None and other.id is not None and subject.id == other.id:
            continue
        if other.locale != subject.locale:
            continue
        other_text = other.focus or other.title or ""
        if classify(other_text) != subject_intent:
            continue
        score = page_overlap(subject_text, other_text)
        if score >= threshold:
            out.append(Clash(slug=other.slug, title=other.title, focus=other.focus,
                             score=score, intent=subject_intent))
    out.sort(key=lambda c: c.score, reverse=True)
    return out
