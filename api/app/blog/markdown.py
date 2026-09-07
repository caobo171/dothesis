"""Markdown helpers for blog bodies.

HEADING IDS — the algorithm, because two codebases implement it
===============================================================

The web renderer slugs the H2s it renders, and the contents box is built from
a separate parse. If the two disagree by one character every anchor in the
contents box points at nothing. So the algorithm is written out here in full,
and `api/tests/fixtures/blog/headings.{md,json}` is the executable contract:
`web/app/blog/_lib/markdown.ts` carries a copy of that fixture and must
produce the same ids byte for byte.

Given the heading's rendered text (inline markup already removed):

1. Normalise to NFD and drop every combining mark. `ế` becomes `e`.
2. Replace `đ` and `Đ` with `d`. They carry a stroke, not a combining mark,
   so step 1 leaves them untouched — this is the step every naive Vietnamese
   slugger forgets.
3. Lowercase.
4. Replace every run of characters that is not `a-z` or `0-9` with a single
   hyphen. Apostrophes and colons become hyphens like anything else, so
   `Cronbach's Alpha` is `cronbach-s-alpha`.
5. Trim leading and trailing hyphens.
6. Within one document, the second occurrence of an id gets `-1`, the third
   `-2`, and so on — GitHub-slugger's rule, so a post that repeats a heading
   still has unique anchors.

An empty result (a heading of pure punctuation) stays empty and only the
repeat counter distinguishes it; that is degenerate input and the QA gate
rejects it upstream.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

_COMBINING = dict.fromkeys(range(0x0300, 0x0370))
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
# [text](href) and [text](href "title"); href may not contain whitespace.
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+[\"'][^\"')]*[\"'])?\s*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
# A GFM table delimiter row: only pipes, colons, dashes and spaces.
_TABLE_DELIM_RE = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")

# H2s that open the question block. Matched against the diacritic-stripped,
# lowercased heading text so `Câu hỏi thường gặp` and `Cau hoi thuong gap`
# both hit.
_FAQ_MARKERS = ("cau hoi thuong gap", "hoi dap", "faq")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    id: str
    # Source line, api-side only: `faq()` uses it to slice answers. The web
    # port has no need for it.
    line: int = field(default=-1, compare=False)


@dataclass(frozen=True)
class FaqEntry:
    question: str
    answer: str
    id: str


def _strip_diacritics(text: str) -> str:
    """NFD, drop combining marks, then map the stroked d (step 1 + 2 above)."""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = decomposed.translate(_COMBINING)
    return without_marks.replace("đ", "d").replace("Đ", "d")


def slugify(text: str) -> str:
    """Steps 1-5 of the heading-id algorithm. No repeat handling."""
    ascii_ish = _strip_diacritics(text or "").lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_ish).strip("-")


class Slugger:
    """`slugify` plus the per-document repeat counter (step 6)."""

    def __init__(self) -> None:
        self._seen: dict[str, int] = {}

    def slug(self, text: str) -> str:
        base = slugify(text)
        count = self._seen.get(base, 0)
        self._seen[base] = count + 1
        return base if count == 0 else f"{base}-{count}"


def _inline_text(text: str) -> str:
    """The rendered text of an inline span: markup removed, words kept."""
    out = _IMAGE_RE.sub("", text)
    out = _LINK_RE.sub(r"\1", out)
    out = out.replace("`", "")
    out = re.sub(r"(\*\*\*|\*\*|\*|___|__|_|~~)", "", out)
    out = re.sub(r"<[^>]+>", " ", out)
    return re.sub(r"\s+", " ", out).strip()


def _scan_headings(body: str) -> list[tuple[int, str, int]]:
    """(level, rendered text, line index) for every ATX heading.

    Fenced blocks are skipped: `# comment` inside a python block is not an H1,
    and treating it as one puts nonsense in the contents box.
    """
    found: list[tuple[int, str, int]] = []
    fence: str | None = None
    for i, line in enumerate((body or "").splitlines()):
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
            found.append((len(m.group(1)), _inline_text(m.group(2)), i))
    return found


def headings(body: str) -> list[Heading]:
    slugger = Slugger()
    return [Heading(level=lvl, text=text, id=slugger.slug(text), line=line)
            for lvl, text, line in _scan_headings(body)]


def faq(body: str) -> list[FaqEntry]:
    """The `### ` questions under the FAQ H2, with their answers.

    Ids come from the same single pass as every other heading, so the FAQ
    JSON-LD on the web can point at the anchors the page actually renders.
    """
    all_headings = headings(body)
    lines = (body or "").splitlines()

    start = None
    for idx, h in enumerate(all_headings):
        if h.level == 2 and any(m in _strip_diacritics(h.text).lower() for m in _FAQ_MARKERS):
            start = idx
            break
    if start is None:
        return []

    entries: list[FaqEntry] = []
    for idx in range(start + 1, len(all_headings)):
        h = all_headings[idx]
        if h.level <= 2:
            break  # the FAQ section ended
        if h.level != 3:
            continue
        # The answer runs to the next heading of any level, or the end.
        end = len(lines)
        if idx + 1 < len(all_headings):
            end = all_headings[idx + 1].line
        answer = "\n".join(lines[h.line + 1:end]).strip()
        entries.append(FaqEntry(question=h.text, answer=answer, id=h.id))
    return entries


def links(body: str) -> list[tuple[str, str]]:
    """(text, href) for every markdown link, images excluded.

    Every href, not just the well-formed ones: the link audit exists because
    authors paste `example.com/x` with no scheme, which the browser resolves
    under the post's own directory and turns into a 404.
    """
    out: list[tuple[str, str]] = []
    for m in _LINK_RE.finditer(body or ""):
        if m.group(0).startswith("!"):
            continue  # an image, not a link
        out.append((m.group(1).strip(), m.group(2).strip()))
    return out


def internal_links(body: str) -> list[str]:
    """Distinct root-relative hrefs, in the order they first appear.

    Distinct rather than every occurrence, because both callers — the QA gate
    counting links and the audit resolving them — ask about the set of pages
    this post points at, not how often it points there.
    """
    seen: list[str] = []
    for _, href in links(body):
        if href.startswith("/") and href not in seen:
            seen.append(href)
    return seen


def plain_text(body: str) -> str:
    """Body prose with markup removed, for counting and excerpting.

    Link URLs, table pipes, delimiter rows and fenced code are dropped: none of
    them is prose, and counting them inflates the word count enough to slip a
    thin post past the QA gate's floor.
    """
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


def reading_time(body: str, words_per_minute: int = 200) -> int:
    """Minutes, rounded up, never zero — WELE's 200 wpm."""
    return max(1, math.ceil(word_count(body) / words_per_minute))
