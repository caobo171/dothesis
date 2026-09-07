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
would relearn it in production.
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
        ("how-to", r"(cách|\bcach\b|hướng dẫn|huong dan|làm sao|lam sao|các bước|cac buoc|"
                   r"chạy|\bchay\b|thực hiện|thuc hien|\bhow to\b|kiểm định|kiem dinh|"
                   r"phân tích|phan tich|viết|\bviet\b|tính|\btinh\b)"),
    )
)

# Two posts on one intent split their own ranking. WELE's calibrated value;
# see guard.py for why the fix for false positives was a narrower key rather
# than a higher number.
CLASH_THRESHOLD = 0.6

_NON_WORD = re.compile(r"[^\w\s]", re.UNICODE)


def tokens(text: str) -> set[str]:
    cleaned = _NON_WORD.sub(" ", (text or "").lower())
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
        score = overlap(subject_tokens, tokens(other_text))
        if score >= threshold:
            out.append(Clash(slug=other.slug, title=other.title, focus=other.focus,
                             score=score, intent=subject_intent))
    out.sort(key=lambda c: c.score, reverse=True)
    return out
