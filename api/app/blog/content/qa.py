#!/usr/bin/env python3
"""The mechanical QA gate over DoThesis blog seed JSON.

Every rule the skills declare, checked so a batch cannot ship on vibes. Exit
code 1 if any file FAILs.

`--corpus` adds the one check a single seed cannot make: is this page a refill
of a page the bank already has. Measured on the 421 real seeds in
`api/data/blog-seeds/vi/posts` on 2026-09-08, word 5-gram Jaccard over a
1-in-16 sketch:

- every one of the 88,410 possible pairs scores under **0.081**. p99 is 0.033,
  p95 0.018, median 0.005. That ceiling is the shared skeleton, not shared
  prose: the FAQ heading, the `Đọc thêm` line, the CTA sentence and the rows of
  a threshold table that two posts legitimately quote from the same source.
- a swapped-noun refill of a real post (`SPSS` -> `SmartPLS` throughout) scores
  **0.88**. Rewriting a third of its blocks still scores 0.38, and half an
  article pasted into another scores 0.48. The score tracks the fraction of the
  body reused almost linearly, so a threshold reads as "how much of this page
  may be someone else's sentences".
- so the band from 0.081 to 0.38 is empty on real content, and the thresholds
  below sit inside it with a factor of two of headroom on either side.

The finding that matters more than the numbers: the top real pairs
(`cronbach-alpha-trong-spss` / `phan-tich-cronbach-alpha-spss`, `ly-thuyet-tpb`
/ `tpb-la-gi`) score 0.07 and 0.08 while sharing all eight H2 headings and the
same subject. Independently written prose about one topic is invisible to a
shingle gate. This check refuses *reused text*; two pages competing for one
query is a different failure with a different tool, `app/blog/similarity.py`,
which classifies intent first. Neither substitutes for the other.

**Two languages, one set of numbers.** The bank ships Vietnamese and English
editions of the same posts, so every rule that reads the prose is stated per
locale in `LOCALE_RULES` and picked with the seed's own `locale` field: the FAQ
heading, the worked-table label, the writing-paragraph lead, the slop blacklist
and the qualitative-method refusal. An English post has to pass on English
terms and cannot buy a check with a Vietnamese string. Not one threshold moves
between the two, and citations are shared: `(Hair et al., 2010)` and
`(Hair và cộng sự, 2010)` are the same surname and the same year.

**Stdlib only, and no import of `app.blog.markdown`.** This module is also
reached from `.claude/skills/dothesis-content-pipeline/scripts/qa_seeds.py`,
which runs under a bare `python3` with no virtualenv, on a seed directory
someone is inspecting before publishing. So the heading-id, word-count and
link helpers are vendored below rather than imported. They implement the same
algorithm as `app/blog/markdown.py` and `web/app/blog/_lib/markdown.ts`, and a
test pins all three to `api/tests/fixtures/blog/headings.json`: a single
character of drift breaks every in-page anchor.
"""
from __future__ import annotations

import collections
import csv
import itertools
import json
import os
import re
import sys
import unicodedata
import zlib

# --------------------------------------------------------------------- rules

MIN_WORDS = 1500
WARN_WORDS = 3000
WARN_PARAGRAPH_WORDS = 120
MIN_H2 = 5
MIN_FAQ_QUESTIONS = 4
MIN_INTERNAL_LINKS = 4
MIN_TABLES = 1
MIN_PROPRIETARY = 1
META_TITLE_MAX = 70
META_DESC_MIN = 110
META_DESC_MAX = 170
SLUG_MAX = 120

# A page with no measured search volume is allowed to exist, but volume is then
# doing none of the work of justifying it: quality is the only thing between
# this bank and Google's scaled-content-abuse policy, which covers human-written
# pages too. So every "is this page worth its URL" bar is doubled for one.
# `family-inferred` is the legacy spelling of the same state.
UNMEASURED_STATUSES = frozenset({"unmeasured", "family-inferred"})

SCHEMA = "dothesis-blog-seed/1"

REQUIRED_FIELDS = ("schema", "title", "slug", "locale", "meta_title", "meta_description",
                   "focus_keyword", "excerpt", "category", "archetype", "body")

ALLOWED_CATEGORIES = {
    "spss", "thong-ke", "khao-sat", "nghien-cuu-khoa-hoc", "khoa-luan-tot-nghiep",
    "smartpls", "phan-tich-du-lieu", "luan-van-thac-si", "mo-hinh-nghien-cuu",
}

ALLOWED_ARCHETYPES = {
    "term-la-gi", "spss-howto", "smartpls-howto", "test", "model-theory",
    "scale", "thesis-writing", "survey", "topic-list", "troubleshoot",
}

# Routes that are not blog posts but are valid link targets.
ALLOWED_ROUTES = {"/landing", "/signup", "/login", "/blog/vi", "/blog/en"}
CTA_ROUTE = "/landing"

# The middle segment of a category route, `/blog/<locale>/<segment>/<category>`.
# A constant with one reader here and one in `translate.py`, because the English
# edition may end up on an English segment and the web route is owned elsewhere:
# when it changes, this line moves and nothing else does.
CATEGORY_SEGMENT = "chu-de"

# Kept verbatim in sync with
# .claude/skills/dothesis-blog-content/references/voice.md.
BLACKLIST = (
    "Trong bài viết này, chúng ta sẽ cùng tìm hiểu",
    "Bài viết dưới đây sẽ giúp bạn",
    "Hy vọng bài viết trên đã giúp bạn",
    "Hy vọng bài viết này sẽ giúp ích cho bạn",
    "Trên đây là toàn bộ",
    "Không thể phủ nhận rằng",
    "đóng vai trò vô cùng quan trọng",
    "một trong những phương pháp hiệu quả nhất hiện nay",
    "Hãy cùng khám phá ngay sau đây",
    "Cùng tìm hiểu ngay nhé",
    "Như các bạn đã biết",
    "Chắc hẳn bạn đã từng",
    "vô cùng đơn giản và dễ dàng",
    "nhanh chóng và chính xác nhất",
    "uy tín và chất lượng",
    "Liên hệ ngay với chúng tôi",
    "Chúc bạn thành công",
    "Trong thời đại công nghệ 4.0",
)

# DoThesis is quantitative only. These are not "mention with care" phrases, they
# are instructions the product cannot support, so the gate refuses the post.
QUALITATIVE_PHRASES = ("phỏng vấn sâu", "mã hóa định tính")

# ------------------------------------------------------------------- locales
#
# The bank ships in two languages, so every rule that reads the prose has to be
# stated in the language it reads. An English post passes on its own terms: it
# may not satisfy the FAQ rule, the worked-table rule or the writing-paragraph
# rule by carrying a Vietnamese string, and a Vietnamese post may not satisfy
# them with an English one. Which set applies is read off the seed's `locale`
# field and never guessed from the text, because these posts mix languages by
# design (`Cronbach's Alpha`, `Rotated Component Matrix`) and a guess would pick
# the wrong rules for exactly the posts that follow the voice guide best.
#
# Nothing below is a threshold. The word floor, the H2 count, the FAQ minimum,
# the table and link minimums and the doubled bar for a page with no measured
# search volume are the same numbers in both languages.

DEFAULT_LOCALE = "vi"
ALLOWED_LOCALES = ("vi", "en")

# The English half of the slop blacklist: same failure mode as the Vietnamese
# list in `voice.md`, in the language the English edition is written in. A
# phrase earns its place by being one no editor would leave in and one that a
# model reaches for unprompted, so each is either a stock opener, a stock close,
# or an intensifier that says nothing. It lives here rather than in the skill
# file because a test pins that file's list to `BLACKLIST` word for word; the
# translation prompt reads this tuple and quotes it.
BLACKLIST_EN = (
    "In this article, we will",
    "This article will help you",
    "We hope this article",
    "Hopefully this article",
    "It cannot be denied that",
    "plays an extremely important role",
    "one of the most effective methods available today",
    "Let's dive right in",
    "Let's dive in",
    "As you may already know",
    "you have probably wondered",
    "incredibly simple and easy",
    "quickly and accurately",
    "reputable and professional",
    "Contact us now",
    "Good luck with your thesis",
    "we wish you every success",
    "In the era of Industry 4.0",
    "In today's digital age",
    "delve into",
    "In conclusion,",
    "a testament to",
    "ever-evolving world of",
)

# The direct English equivalents of `QUALITATIVE_PHRASES`, and only those, so a
# body fails on the same instruction in either language. `voice.md` also names
# focus groups and saturation checks; the Vietnamese gate does not catch those
# either, and widening one locale but not the other is how the two editions
# start disagreeing about what a post may say.
QUALITATIVE_PHRASES_EN = ("in-depth interview", "qualitative coding")


def _writing_lead_re(phrase: str) -> "re.Pattern":
    """The writing paragraph announces itself: a heading, or a bolded lead."""
    return re.compile(r"^(?:\s{0,3}#{1,6}\s+|\s{0,3}\*\*)[^\n]*" + re.escape(phrase),
                      re.IGNORECASE | re.MULTILINE)


_Rules = collections.namedtuple(
    "_Rules",
    "locale faq_heading faq_markers worked_label writing_lead writing_lead_re "
    "blacklist qualitative hedge")

LOCALE_RULES = {
    "vi": _Rules(
        locale="vi",
        faq_heading="Câu hỏi thường gặp",
        faq_markers=("cau hoi thuong gap", "hoi dap", "faq"),
        worked_label="số liệu minh họa",
        writing_lead="cách viết vào luận văn",
        writing_lead_re=_writing_lead_re("cách viết vào luận văn"),
        blacklist=BLACKLIST,
        qualitative=QUALITATIVE_PHRASES,
        hedge="nghiên cứu cho thấy",
    ),
    "en": _Rules(
        locale="en",
        faq_heading="Frequently asked questions",
        faq_markers=("frequently asked questions", "faq"),
        # Both labels name a table of numbers the writer made up to show the
        # shape of real output. `illustrative output` is the English wording the
        # translation prompt requires verbatim, for the same reason the
        # Vietnamese one is required verbatim: a label that varies is a label
        # nothing can check.
        worked_label="illustrative output",
        writing_lead="how to write this in your thesis",
        writing_lead_re=_writing_lead_re("how to write this in your thesis"),
        blacklist=BLACKLIST_EN,
        qualitative=QUALITATIVE_PHRASES_EN,
        hedge="research shows",
    ),
}


def rules_for(locale: str | None) -> "_Rules":
    """The rule set for a seed's locale, Vietnamese when it is not one of the two.

    Falling back rather than raising: an unrecognised locale already FAILs on
    its own line in `check_post`, and a run that reported only that would hide
    every other thing wrong with the file.
    """
    return LOCALE_RULES.get(locale or "", LOCALE_RULES[DEFAULT_LOCALE])

# (first surname token, year) for every entry in
# .claude/skills/dothesis-blog-content/references/canonical-sources.md.
# A test parses that file and asserts the two sets are equal, so adding a source
# to the skill without adding it here fails the suite rather than a post.
ALLOWED_CITATIONS = frozenset({
    ("cronbach", 1951), ("nunnally", 1978), ("nunnally", 1994),
    ("kaiser", 1960), ("kaiser", 1974),
    ("hair", 1998), ("hair", 2010), ("hair", 2011), ("hair", 2019), ("hair", 2022),
    ("fornell", 1981), ("henseler", 2009), ("henseler", 2015), ("chin", 1998),
    ("dijkstra", 2015), ("stone", 1974), ("bagozzi", 1988), ("anderson", 1988),
    ("hu", 1999), ("bollen", 1989), ("kline", 2015), ("byrne", 2010),
    ("podsakoff", 2003), ("baron", 1986), ("preacher", 2008), ("hayes", 2018),
    ("cohen", 1988), ("tabachnick", 2013), ("field", 2013), ("comrey", 1992),
    ("cochran", 1977), ("yamane", 1967), ("likert", 1932), ("davis", 1989),
    ("ajzen", 1991), ("venkatesh", 2003), ("venkatesh", 2012),
    ("parasuraman", 1988), ("nguyen", 2011), ("hoang", 2008),
    # Econometrics, added 2026-09-08 when the axes gained panel and time-series
    # units (Hausman, Tobit, cointegration, unit root). Four classics only, each
    # one the paper the method is named after; a citation nobody can check is
    # worse than a dropped number, so the bar for adding here is certainty.
    ("engle", 1987), ("granger", 1969), ("dickey", 1979), ("hausman", 1978),
})

# ------------------------------------------------------- vendored markdown bits

_COMBINING = dict.fromkeys(range(0x0300, 0x0370))
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+[\"'][^\"')]*[\"'])?\s*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_TABLE_DELIM_RE = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>")


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text or "")
    return decomposed.translate(_COMBINING).replace("đ", "d").replace("Đ", "d")


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _ascii(text).lower()).strip("-")


class Slugger:
    """slugify plus the per-document repeat counter: base, base-1, base-2."""

    def __init__(self):
        self._seen = {}

    def slug(self, text):
        base = slugify(text)
        count = self._seen.get(base, 0)
        self._seen[base] = count + 1
        return base if count == 0 else f"{base}-{count}"


def _inline_text(text: str) -> str:
    out = _IMAGE_RE.sub("", text)
    out = _LINK_RE.sub(r"\1", out)
    out = out.replace("`", "")
    out = re.sub(r"(\*\*\*|\*\*|\*|___|__|_|~~)", "", out)
    out = re.sub(r"<[^>]+>", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def headings(body: str) -> list[tuple[int, str, str]]:
    """(level, text, id) for every ATX heading outside a fenced block."""
    slugger = Slugger()
    out = []
    fence = None
    for line in (body or "").splitlines():
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue
        m = _ATX_RE.match(line)
        if m:
            text = _inline_text(m.group(2))
            out.append((len(m.group(1)), text, slugger.slug(text)))
    return out


def faq_questions(body: str, locale: str = DEFAULT_LOCALE) -> list[str]:
    """The `### ` questions under the FAQ H2, in this locale's wording."""
    markers = rules_for(locale).faq_markers
    all_headings = headings(body)
    start = None
    for idx, (level, text, _) in enumerate(all_headings):
        if level == 2 and any(m in _ascii(text).lower() for m in markers):
            start = idx
            break
    if start is None:
        return []
    questions = []
    for level, text, _ in all_headings[start + 1:]:
        if level <= 2:
            break
        if level == 3:
            questions.append(text)
    return questions


def plain_text(body: str) -> str:
    text = body or ""
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    text = re.sub(r"^\s{0,3}(```|~~~).*?^\s{0,3}\1.*?$", " ", text, flags=re.S | re.M)
    text = _IMAGE_RE.sub(" ", text)
    text = _LINK_RE.sub(r"\1", text)
    text = re.sub(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$", " ", text, flags=re.M)
    text = text.replace("|", " ")
    text = re.sub(r"^ {0,3}#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^ {0,3}>\s?", "", text, flags=re.M)
    text = re.sub(r"^ {0,3}([-*+]|\d+\.)\s+", "", text, flags=re.M)
    text = re.sub(r"^ {0,3}([-*_])\s*(\1\s*){2,}$", " ", text, flags=re.M)
    text = text.replace("`", "")
    text = re.sub(r"(\*\*\*|\*\*|\*|___|__|_|~~)", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def word_count(body: str) -> int:
    text = plain_text(body)
    return len(text.split()) if text else 0


def internal_links(body: str) -> list[str]:
    seen = []
    for m in _LINK_RE.finditer(body or ""):
        if m.group(0).startswith("!"):
            continue
        href = m.group(2).strip()
        if href.startswith("/") and href not in seen:
            seen.append(href)
    return seen


def table_rows(body: str) -> tuple[int, int]:
    """(tables, data rows). A table is a delimiter row with a header above it."""
    lines = (body or "").splitlines()
    tables = rows = 0
    in_table = False
    for i, line in enumerate(lines):
        if _TABLE_DELIM_RE.match(line) and "|" in line and i > 0 and "|" in lines[i - 1]:
            tables += 1
            in_table = True
            continue
        if in_table:
            if "|" in line and line.strip():
                rows += 1
            else:
                in_table = False
    return tables, rows


# ------------------------------------------------------------------ citations

_CITE_PAREN = re.compile(r"\(([^()]{2,80}?),\s*(\d{4})[a-z]?\)")
_CITE_NARRATIVE = re.compile(
    r"\b([^\W\d_][^\W\d_]*)"
    r"(?:\s+(?:và|and)\s+[^\W\d_]+|\s+và cộng sự|\s+et\s+al\.?)?"
    r"\s*\((\d{4})[a-z]?\)")


def citations(body: str) -> list[tuple[str, int, str]]:
    """(surname key, year, raw match) for every citation-shaped span in the body."""
    found = []
    for m in _CITE_PAREN.finditer(body or ""):
        name = m.group(1).strip()
        if not name or not name[0].isalpha():
            continue
        key = _ascii(name).lower().split()[0]
        found.append((key, int(m.group(2)), m.group(0)))
    for m in _CITE_NARRATIVE.finditer(body or ""):
        name = m.group(1)
        if not name[:1].isupper():
            continue  # `SmartPLS 4 (2024)` and `bảng 3 (2020)` are not citations
        found.append((_ascii(name).lower(), int(m.group(2)), m.group(0)))
    return found


# ------------------------------------------------------- proprietary elements

# `structure.md`, "the three rules that apply to every archetype": a post that
# carries none of these is a rewrite of a competitor page. The rule has been in
# the skill from the start and was never mechanical, so it was aspirational;
# these detectors make it checkable. Each one looks for the cheapest signal that
# cannot be produced by accident, not for the whole element:
#
# - a threshold table is a table with a canonical citation *inside a row*, which
#   is the "every row names its source" column and nothing else looks like it;
# - a worked table is one carrying the locale's worked label (`số liệu minh
#   họa`, `illustrative output`), which the skill and the translation prompt
#   both require verbatim, in the table or in the line either side of it;
# - a writing paragraph (`cách viết vào luận văn`, `how to write this in your
#   thesis`) announces itself as a heading or a bolded lead, because a bare
#   mention inside prose is a cross-reference to another post's section, not the
#   section itself.
#
# The label and the lead are per locale, in `LOCALE_RULES`. A citation is not:
# `(Hair et al., 2010)` and `(Hair và cộng sự, 2010)` carry the same surname and
# the same year, which is all `citations()` reads.
PROPRIETARY_ELEMENTS = ("threshold-table", "worked-table", "writing-paragraph")


def table_blocks(body: str) -> list[tuple[list[str], list[str]]]:
    """Every GFM table as (its own lines, the lines around it).

    The context is the up-to-three non-blank lines before the header and the
    first after the table, because a caption sits on either side depending on
    who wrote the post.
    """
    lines = (body or "").splitlines()
    out: list[tuple[list[str], list[str]]] = []
    i = 0
    while i < len(lines):
        if (_TABLE_DELIM_RE.match(lines[i]) and "|" in lines[i]
                and i > 0 and "|" in lines[i - 1]):
            end = i + 1
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                end += 1
            before = [ln for ln in lines[max(0, i - 4):i - 1] if ln.strip()][-3:]
            after = [ln for ln in lines[end:end + 3] if ln.strip()][:1]
            out.append((lines[i - 1:end], before + after))
            i = end
            continue
        i += 1
    return out


# A threshold table states a cut-off: its header names one, or its cells carry a
# decimal, a ratio or a percentage. A procedure table ("Bước | Thao tác") does
# neither, which is what keeps a citation beside one from counting as a source.
# Both languages in one list, because the header of an English table on this
# blog often keeps a Vietnamese-bank term and vice versa; a table only has to
# look like a threshold table in one of them.
_THRESHOLD_WORDS = ("ngưỡng", "tối thiểu", "tối đa", "tiêu chuẩn", "chấp nhận",
                    "khuyến nghị", "mức", "giới hạn", "đạt", "threshold", "cut-off",
                    "cutoff", "minimum", "maximum", "acceptable", "recommended",
                    "criterion", "rule of thumb")
_THRESHOLD_NUMBER_RE = re.compile(r"\d+[.,]\d+|\d+\s*:\s*\d+|\d+\s*%")


def _looks_like_thresholds(rows: list[str]) -> bool:
    blob = "\n".join(rows).lower()
    return (any(word in blob for word in _THRESHOLD_WORDS)
            or bool(_THRESHOLD_NUMBER_RE.search(blob)))


def proprietary_elements(body: str, locale: str = DEFAULT_LOCALE) -> list[str]:
    """Which of the three the post actually carries, in `PROPRIETARY_ELEMENTS` order."""
    rules = rules_for(locale)
    found: set[str] = set()
    for rows, context in table_blocks(body):
        blob = "\n".join(rows + context).lower()
        if rules.worked_label in blob:
            found.add("worked-table")
        if "threshold-table" not in found:
            # A citation inside the rows is a source column and always counts.
            # A citation in the sentence that introduces the table counts too,
            # but only when the table is actually a threshold table: measured on
            # the first bank, 20 posts carried a real threshold table sourced in
            # the paragraph above it, which is how the sentence is normally
            # written ("theo Hair và cộng sự (2010), tỷ lệ 5:1"). Demanding a
            # citation in every row pushes a writer to pad rows instead of
            # sourcing the claim. The table test is what stops a citation next
            # to an unrelated procedure table from buying the element.
            sourced_rows = any(
                (key, year) in ALLOWED_CITATIONS
                for line in rows for key, year, _raw in citations(line))
            sourced_context = any(
                (key, year) in ALLOWED_CITATIONS
                for line in context for key, year, _raw in citations(line))
            if sourced_rows or (sourced_context and _looks_like_thresholds(rows)):
                found.add("threshold-table")
    if rules.writing_lead_re.search(body or ""):
        found.add("writing-paragraph")
    return [name for name in PROPRIETARY_ELEMENTS if name in found]


def is_unmeasured(post: dict) -> bool:
    """Does this seed carry no measured search volume?

    Read off `gate_status`, which the writer copies from the backlog row, so the
    gate and the planner cannot disagree about which pages are on the hard bar.
    """
    return (post.get("gate_status") or "") in UNMEASURED_STATUSES


# --------------------------------------------------- corpus near-duplication

SHINGLE_WORDS = 5
SKETCH_MODULUS = 16     # keep 1 shingle in 16; a 2,000-word post keeps ~180
SKETCH_FLOOR = 64       # under this many, keep every shingle instead
# A shingle this common is boilerplate (the FAQ heading, the CTA sentence). It
# is still counted in the score; it is only skipped when *finding* candidates,
# where one such posting list would cost 200*199/2 pair increments and name
# every pair in the corpus anyway.
_MAX_POSTING = 200

# See the module docstring for the measurement. 0.35 of a body is roughly a
# third of its sentences taken from a sibling; the real corpus never exceeds
# 0.081, and a swapped-noun refill scores 0.88.
NEAR_DUPLICATE = 0.35
# Literally half, because the product rule is "twice as heavy for a page with no
# measured search volume" and a reader of this file should be able to see that
# rather than take two unrelated constants on trust.
NEAR_DUPLICATE_UNMEASURED = NEAR_DUPLICATE / 2

_SHINGLE_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)


def shingle_hashes(body: str, n: int = SHINGLE_WORDS) -> set[int]:
    """Hashed word n-grams over the plain text, lowercased, punctuation stripped.

    `zlib.crc32` rather than the builtin `hash`: PYTHONHASHSEED salts str hashing
    per process, so a sketch built in one run would not compare against one built
    in the next. crc32 is stdlib (this module imports nothing else), and its 32
    bits collide often enough to be worth a sentence: across a 3M-shingle corpus
    a few hundred pairs of distinct 5-grams share a hash, which moves a pair
    score by well under a thousandth. That is noise beneath every threshold here.
    """
    words = _SHINGLE_PUNCT_RE.sub(" ", plain_text(body).lower()).split()
    if len(words) < n:
        return set()
    return {zlib.crc32(" ".join(words[i:i + n]).encode("utf-8"))
            for i in range(len(words) - n + 1)}


class Sketch:
    """A sampled fingerprint of one document.

    Sampling is on the hash value, never on the document, so any two sketches
    are comparable. `dense` is the exception: a document with too few shingles
    to sample keeps all of them, and is put back on the sampled plane before it
    is compared with a sampled one. Down-sampling recovers exactly what the
    sampled side kept, because a dense sketch is a superset of its own sample.
    """

    __slots__ = ("values", "dense", "shingles")

    def __init__(self, values: frozenset[int], dense: bool, shingles: int):
        self.values = values
        self.dense = dense
        self.shingles = shingles

    def __len__(self) -> int:
        return len(self.values)


def _sample(values) -> frozenset[int]:
    return frozenset(h for h in values if h % SKETCH_MODULUS == 0)


def sketch(body: str) -> Sketch:
    shingles = shingle_hashes(body)
    sampled = _sample(shingles)
    if len(sampled) < SKETCH_FLOOR:
        return Sketch(frozenset(shingles), True, len(shingles))
    return Sketch(sampled, False, len(shingles))


def sketch_jaccard(a: Sketch, b: Sketch) -> float:
    left, right = a.values, b.values
    if a.dense != b.dense:
        left = _sample(left) if a.dense else left
        right = _sample(right) if b.dense else right
    union = len(left | right)
    return (len(left & right) / union) if union else 0.0


def pair_threshold(unmeasured_a: bool, unmeasured_b: bool) -> float:
    return NEAR_DUPLICATE_UNMEASURED if (unmeasured_a or unmeasured_b) else NEAR_DUPLICATE


def near_duplicates(docs: list[dict]) -> list[dict]:
    """Every pair scoring at or above its threshold, worst first.

    `docs` are `{"key", "unmeasured", "sketch"}`. Pairs are found through an
    inverted index from sketch value to document, so the full O(n^2) cross
    product is never built; only pairs sharing at least one sampled shingle are
    scored, and those are scored exactly from the stored sketches rather than
    from the index's approximate share count.
    """
    index: dict[int, list[int]] = collections.defaultdict(list)
    for i, doc in enumerate(docs):
        # A dense sketch goes in whole rather than down-sampled: its sampled
        # plane can be empty, and a document in no posting list can never become
        # a candidate. Indexing a value the other side never samples only costs
        # a candidate pair, which is then scored properly.
        for value in doc["sketch"].values:
            index[value].append(i)

    candidates: set[tuple[int, int]] = set()
    for ids in index.values():
        if len(ids) < 2 or len(ids) > _MAX_POSTING:
            continue
        candidates.update(itertools.combinations(ids, 2))

    hits = []
    for i, j in candidates:
        a, b = docs[i], docs[j]
        limit = pair_threshold(a["unmeasured"], b["unmeasured"])
        score = sketch_jaccard(a["sketch"], b["sketch"])
        if score >= limit:
            hits.append({"a": a["key"], "b": b["key"], "score": score, "limit": limit,
                         "unmeasured": a["unmeasured"] or b["unmeasured"]})
    hits.sort(key=lambda h: (-h["score"], h["a"], h["b"]))
    return hits


# ---------------------------------------------------------------- known links


def known_slugs(seed_dir: str, extra: set[str] | None = None) -> set[str]:
    """Slugs a link may resolve to: the batch itself, plus the planned backlog."""
    slugs = set(extra or ())
    if seed_dir and os.path.isdir(seed_dir):
        for name in os.listdir(seed_dir):
            if not name.endswith(".json") or name == "categories.json":
                continue
            try:
                with open(os.path.join(seed_dir, name), encoding="utf-8") as fh:
                    slugs.add((json.load(fh) or {}).get("slug") or "")
            except Exception:  # a broken seed is the JSON check's problem, not this one
                continue
    backlog = _default_backlog_path()
    if backlog and os.path.isfile(backlog):
        with open(backlog, encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                if row.get("slug"):
                    slugs.add(row["slug"])
    slugs.discard("")
    return slugs


def _default_backlog_path() -> str | None:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    path = os.path.join(root, "docs", "seo", "topic-bank", "backlog.tsv")
    return path if os.path.isfile(path) else None


def link_is_known(href: str, slugs: set[str]) -> bool:
    """Does this internal href resolve to a page that exists or is planned?

    Public because the writer strips the links this returns False for before it
    runs the gate. One predicate, so what the writer removes is exactly what the
    gate would have failed.
    """
    target = href.split("#")[0].split("?")[0].rstrip("/") or "/"
    if target in ALLOWED_ROUTES:
        return True
    m = re.match(r"^/blog/[a-z]{2}/" + re.escape(CATEGORY_SEGMENT) + r"/([a-z0-9-]+)$",
                 target)
    if m:
        return m.group(1) in ALLOWED_CATEGORIES
    m = re.match(r"^/blog/[a-z]{2}/([a-z0-9-]+)$", target)
    if m:
        return m.group(1) in slugs
    return False


_link_is_known = link_is_known  # the old private name, kept for existing callers


# ----------------------------------------------------------------- the checks


def check_post(post: dict, slugs: set[str] | None = None) -> tuple[list[str], list[str], dict]:
    """(fails, warns, stats) for one already-parsed seed."""
    slugs = slugs if slugs is not None else set()
    fails: list[str] = []
    warns: list[str] = []

    missing = [f for f in REQUIRED_FIELDS if not (post.get(f) or "")]
    for field in missing:
        fails.append(f"missing required field `{field}`")
    if "body" in missing or "title" in missing:
        return fails, warns, {}

    body = post["body"]
    # Which language's rules apply is decided here, once, off the seed's own
    # `locale`. Everything below that reads the prose goes through `rules`.
    locale = post.get("locale")
    rules = rules_for(locale)

    # Volume no longer decides whether a page may exist, it only orders the
    # queue. What it still decides is how hard this page has to work: with no
    # measured query behind it, being the most useful page on the topic is the
    # whole of its claim to a URL, so every bar below that measures usefulness
    # is doubled. See `UNMEASURED_STATUSES`.
    unmeasured = is_unmeasured(post)
    min_links = MIN_INTERNAL_LINKS + (1 if unmeasured else 0)
    min_tables = MIN_TABLES + (1 if unmeasured else 0)
    min_elements = MIN_PROPRIETARY * (2 if unmeasured else 1)

    if post.get("schema") != SCHEMA:
        fails.append(f"schema is {post.get('schema')!r}, must be {SCHEMA!r}")
    if locale not in ALLOWED_LOCALES:
        fails.append(f"locale is {locale!r}, must be one of "
                     + " or ".join(repr(x) for x in ALLOWED_LOCALES))
    category = post.get("category")
    if category and category not in ALLOWED_CATEGORIES:
        fails.append(f"category {category!r} is not one of the nine")
    archetype = post.get("archetype")
    if archetype and archetype not in ALLOWED_ARCHETYPES:
        fails.append(f"archetype {archetype!r} is not one of the ten")

    slug = post.get("slug") or ""
    if slug and (slug != slugify(slug) or len(slug) > SLUG_MAX):
        fails.append(f"slug {slug!r} is not normalised (lowercase ascii, hyphens, "
                     f"{SLUG_MAX} chars max)")

    meta_title = post.get("meta_title") or ""
    if len(meta_title) > META_TITLE_MAX:
        fails.append(f"meta_title is {len(meta_title)} chars, max {META_TITLE_MAX}")
    meta_desc = post.get("meta_description") or ""
    if meta_desc and not (META_DESC_MIN <= len(meta_desc) <= META_DESC_MAX):
        fails.append(f"meta_description is {len(meta_desc)} chars, "
                     f"must be {META_DESC_MIN} to {META_DESC_MAX}")

    words = word_count(body)
    if words < MIN_WORDS:
        fails.append(f"body is {words} words, floor is {MIN_WORDS}")
    if words > WARN_WORDS:
        warns.append(f"body is {words} words, over the {WARN_WORDS} soft ceiling")

    all_headings = headings(body)
    h2s = [h for h in all_headings if h[0] == 2]
    if len(h2s) < MIN_H2:
        fails.append(f"{len(h2s)} H2 sections, need at least {MIN_H2}")
    seen_h2: set[str] = set()
    for _, text, _id in h2s:
        key = text.strip().lower()
        if key in seen_h2:
            warns.append(f"duplicate H2 text {text!r}, its anchor will collide")
        seen_h2.add(key)
    if any(h[0] == 1 for h in all_headings):
        warns.append("body contains an H1, the page renders `title` as the H1")

    questions = faq_questions(body, rules.locale)
    if not questions:
        fails.append(f"no `## {rules.faq_heading}` section with `###` questions")
    elif len(questions) < MIN_FAQ_QUESTIONS:
        fails.append(f"FAQ has {len(questions)} questions, need at least "
                     f"{MIN_FAQ_QUESTIONS}")

    tables, rows = table_rows(body)
    if tables < min_tables:
        if min_tables == 1:
            fails.append("no table, every post needs a threshold or worked-output table")
        else:
            fails.append(f"{tables} table(s), a page with no measured search volume "
                         f"needs at least {min_tables}")

    elements = proprietary_elements(body, rules.locale)
    if len(elements) < min_elements:
        have = ", ".join(elements) if elements else "none"
        fails.append(f"{len(elements)} of the three proprietary elements ({have}), "
                     f"needs at least {min_elements}"
                     + (" because it has no measured search volume" if unmeasured else ""))

    if "—" in body or "—" in (post.get("title") or ""):
        fails.append("contains an em dash")
    prose = _IMAGE_RE.sub("", body)
    if "!" in prose:
        fails.append("contains an exclamation mark")
    lowered = body.lower()
    for phrase in rules.blacklist:
        if phrase.lower() in lowered:
            fails.append(f"blacklisted phrase: {phrase!r}")
    for phrase in rules.qualitative:
        if phrase in lowered:
            fails.append(f"tells the reader to do qualitative work: {phrase!r}. "
                         f"DoThesis is quantitative only")

    for key, year, raw in citations(body):
        if (key, year) not in ALLOWED_CITATIONS:
            fails.append(f"citation {raw!r} is not in canonical-sources.md")

    if _HTML_TAG_RE.search(body):
        fails.append(f"raw HTML tag {_HTML_TAG_RE.search(body).group(0)!r}, body is markdown")

    image_ids = {(i or {}).get("id") for i in (post.get("images") or [])}
    for ref in set(re.findall(r"\{\{img:([^}]+)\}\}", body)):
        if ref not in image_ids:
            fails.append(f"body references {{{{img:{ref}}}}} with no images[] entry")

    links = internal_links(body)
    if len(links) < min_links:
        fails.append(f"{len(links)} distinct internal links, need at least "
                     f"{min_links}"
                     + (" because it has no measured search volume" if unmeasured else ""))
    unknown = [href for href in links if not link_is_known(href, slugs)]
    if unknown:
        fails.append(f"internal link(s) resolve to nothing known: {', '.join(unknown[:4])}")

    cta_count = sum(1 for m in _LINK_RE.finditer(body)
                    if not m.group(0).startswith("!")
                    and m.group(2).split("#")[0].rstrip("/") == CTA_ROUTE)
    if cta_count > 1:
        warns.append(f"{cta_count} CTA links to {CTA_ROUTE}, the close carries exactly one")

    for para in _paragraphs(body):
        if len(para.split()) > WARN_PARAGRAPH_WORDS:
            warns.append(f"a paragraph runs {len(para.split())} words: "
                         f"{para[:48]!r}...")
            break
        if re.search(r"\d+([.,]\d+)?\s*%", para) and "|" not in para:
            warns.append(f"a percentage outside a table: {para[:60]!r}")
            break
    for para in _paragraphs(body):
        if rules.hedge in para.lower() and not citations(para):
            warns.append(f"`{rules.hedge}` with no citation in the same paragraph")
            break

    stats = {"words": words, "h2": len(h2s), "tables": tables, "rows": rows,
             "links": len(links), "faq": len(questions), "locale": rules.locale,
             "elements": len(elements), "unmeasured": unmeasured}
    return fails, warns, stats


def _paragraphs(body: str) -> list[str]:
    out = []
    for block in re.split(r"\n\s*\n", body or ""):
        block = block.strip()
        if not block or block.startswith("#") or block.startswith("|"):
            continue
        out.append(plain_text(block))
    return [p for p in out if p]


def check_file(path: str, slugs: set[str] | None = None):
    name = os.path.basename(path)
    try:
        with open(path, encoding="utf-8") as fh:
            post = json.load(fh)
    except Exception as exc:
        return name, [f"JSON does not parse: {exc}"], [], {}
    if not isinstance(post, dict):
        return name, ["JSON is not an object"], [], {}
    fails, warns, stats = check_post(post, slugs)
    return name, fails, warns, stats


# ------------------------------------------------------------------ reporting


def read_slug_file(path: str) -> set[str]:
    """One slug per line, `#` comments and blanks ignored.

    A bare `/blog/vi/<slug>` line is accepted too, because the list someone
    pastes in is usually copied out of a post's links.
    """
    slugs = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            slugs.add(line.rstrip("/").rsplit("/", 1)[-1])
    slugs.discard("")
    return slugs


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Link resolution defaults to the batch on disk plus `backlog.tsv`. Outside
    # a checkout there is no backlog, so every internal link would read as
    # broken; `--known-slugs FILE` says what else resolves. Optional on purpose:
    # without it this behaves exactly as it did.
    extra: set[str] = set()
    positional: list[str] = []
    corpus = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--corpus":
            corpus = True
            i += 1
            continue
        if arg == "--known-slugs":
            if i + 1 >= len(argv):
                print("--known-slugs needs a file path")
                return 1
            extra |= read_slug_file(argv[i + 1])
            i += 2
            continue
        if arg.startswith("--known-slugs="):
            extra |= read_slug_file(arg.split("=", 1)[1])
        else:
            positional.append(arg)
        i += 1

    seed_dir = positional[0] if positional else os.path.join("data", "blog-seeds", "vi", "posts")
    if not os.path.isdir(seed_dir):
        print(f"no seed dir at {seed_dir}")
        return 1
    files = sorted(f for f in os.listdir(seed_dir)
                   if f.endswith(".json") and f != "categories.json")
    if not files:
        print(f"no seed files in {seed_dir}")
        return 1

    slugs = known_slugs(seed_dir, extra)
    total_fail = 0
    detail = []
    print(f"{'file':<46} {'words':>6} {'h2':>3} {'faq':>4} {'tbl':>4} {'rows':>5} "
          f"{'lnk':>4}  status")
    print("-" * 96)
    for name in files:
        name, fails, warns, st = check_file(os.path.join(seed_dir, name), slugs)
        status = "OK" if not fails else f"FAIL({len(fails)})"
        if fails:
            total_fail += 1
        if st:
            print(f"{name:<46} {st['words']:>6} {st['h2']:>3} {st['faq']:>4} "
                  f"{st['tables']:>4} {st['rows']:>5} {st['links']:>4}  {status}")
        else:
            print(f"{name:<46} {'-':>6} {'-':>3} {'-':>4} {'-':>4} {'-':>5} "
                  f"{'-':>4}  {status}")
        if fails or warns:
            detail.append((name, fails, warns))

    if detail:
        print("\nDetail")
        for name, fails, warns in detail:
            print(f"\n  {name}")
            for x in fails:
                print(f"    FAIL {x}")
            for x in warns:
                print(f"    warn {x}")

    duplicate_pairs = 0
    if corpus:
        duplicate_pairs = _report_corpus(seed_dir, files)

    print(f"\n{len(files)} file(s), {total_fail} failing"
          + (f", {duplicate_pairs} near-duplicate pair(s)" if corpus else ""))
    return 1 if (total_fail or duplicate_pairs) else 0


def build_corpus(seed_dir: str, files: list[str]) -> list[dict]:
    """One `near_duplicates` entry per readable seed in the directory."""
    docs = []
    for name in files:
        try:
            with open(os.path.join(seed_dir, name), encoding="utf-8") as fh:
                post = json.load(fh)
        except Exception:  # a broken seed already FAILed on its own line
            continue
        if not isinstance(post, dict) or not (post.get("body") or ""):
            continue
        docs.append({"key": post.get("slug") or name,
                     "unmeasured": is_unmeasured(post),
                     "sketch": sketch(post["body"])})
    return docs


def _report_corpus(seed_dir: str, files: list[str]) -> int:
    docs = build_corpus(seed_dir, files)
    hits = near_duplicates(docs)
    print(f"\nCorpus: {len(docs)} bodies, word {SHINGLE_WORDS}-gram Jaccard over a "
          f"1-in-{SKETCH_MODULUS} sketch")
    print(f"        limit {NEAR_DUPLICATE:.3f} between two measured pages, "
          f"{NEAR_DUPLICATE_UNMEASURED:.3f} when either has no measured volume")
    if not hits:
        print("        no pair is a near duplicate of another")
        return 0
    for hit in hits:
        why = "unmeasured" if hit["unmeasured"] else "measured"
        print(f"  FAIL {hit['score']:.3f} >= {hit['limit']:.3f} ({why})  "
              f"{hit['a']}  <->  {hit['b']}")
    return len(hits)


if __name__ == "__main__":
    sys.exit(main())
