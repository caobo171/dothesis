#!/usr/bin/env python3
"""The mechanical QA gate over DoThesis blog seed JSON.

Every rule the skills declare, checked so a batch cannot ship on vibes. Exit
code 1 if any file FAILs.

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

import csv
import json
import os
import re
import sys
import unicodedata

# --------------------------------------------------------------------- rules

MIN_WORDS = 1500
WARN_WORDS = 3000
WARN_PARAGRAPH_WORDS = 120
MIN_H2 = 5
MIN_FAQ_QUESTIONS = 4
MIN_INTERNAL_LINKS = 4
META_TITLE_MAX = 70
META_DESC_MIN = 110
META_DESC_MAX = 170
SLUG_MAX = 120

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
ALLOWED_ROUTES = {"/landing", "/signup", "/login", "/blog/vi"}
CTA_ROUTE = "/landing"

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
})

# ------------------------------------------------------- vendored markdown bits

_COMBINING = dict.fromkeys(range(0x0300, 0x0370))
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")
_ATX_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(\s*<?([^)\s>]*)>?(?:\s+[\"'][^\"')]*[\"'])?\s*\)")
_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_TABLE_DELIM_RE = re.compile(r"^\s*\|?[\s:\-|]+\|[\s:\-|]*$")
_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9-]*(\s[^<>]*)?/?>")
_FAQ_MARKERS = ("cau hoi thuong gap", "hoi dap", "faq")


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


def faq_questions(body: str) -> list[str]:
    """The `### ` questions under the FAQ H2."""
    all_headings = headings(body)
    start = None
    for idx, (level, text, _) in enumerate(all_headings):
        if level == 2 and any(m in _ascii(text).lower() for m in _FAQ_MARKERS):
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


def _link_is_known(href: str, slugs: set[str]) -> bool:
    target = href.split("#")[0].split("?")[0].rstrip("/") or "/"
    if target in ALLOWED_ROUTES:
        return True
    m = re.match(r"^/blog/[a-z]{2}/chu-de/([a-z0-9-]+)$", target)
    if m:
        return m.group(1) in ALLOWED_CATEGORIES
    m = re.match(r"^/blog/[a-z]{2}/([a-z0-9-]+)$", target)
    if m:
        return m.group(1) in slugs
    return False


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

    if post.get("schema") != SCHEMA:
        fails.append(f"schema is {post.get('schema')!r}, must be {SCHEMA!r}")
    if post.get("locale") != "vi":
        fails.append(f"locale is {post.get('locale')!r}, must be 'vi'")
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

    questions = faq_questions(body)
    if not questions:
        fails.append("no `## Câu hỏi thường gặp` section with `###` questions")
    elif len(questions) < MIN_FAQ_QUESTIONS:
        fails.append(f"FAQ has {len(questions)} questions, need at least "
                     f"{MIN_FAQ_QUESTIONS}")

    tables, rows = table_rows(body)
    if tables < 1:
        fails.append("no table, every post needs a threshold or worked-output table")

    if "—" in body or "—" in (post.get("title") or ""):
        fails.append("contains an em dash")
    prose = _IMAGE_RE.sub("", body)
    if "!" in prose:
        fails.append("contains an exclamation mark")
    lowered = body.lower()
    for phrase in BLACKLIST:
        if phrase.lower() in lowered:
            fails.append(f"blacklisted phrase: {phrase!r}")
    for phrase in QUALITATIVE_PHRASES:
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
    if len(links) < MIN_INTERNAL_LINKS:
        fails.append(f"{len(links)} distinct internal links, need at least "
                     f"{MIN_INTERNAL_LINKS}")
    unknown = [href for href in links if not _link_is_known(href, slugs)]
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
        if "nghiên cứu cho thấy" in para.lower() and not citations(para):
            warns.append("`nghiên cứu cho thấy` with no citation in the same paragraph")
            break

    stats = {"words": words, "h2": len(h2s), "tables": tables, "rows": rows,
             "links": len(links), "faq": len(questions)}
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


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    seed_dir = argv[0] if argv else os.path.join("data", "blog-seeds", "vi", "posts")
    if not os.path.isdir(seed_dir):
        print(f"no seed dir at {seed_dir}")
        return 1
    files = sorted(f for f in os.listdir(seed_dir)
                   if f.endswith(".json") and f != "categories.json")
    if not files:
        print(f"no seed files in {seed_dir}")
        return 1

    slugs = known_slugs(seed_dir)
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

    print(f"\n{len(files)} file(s), {total_fail} failing")
    return 1 if total_fail else 0


if __name__ == "__main__":
    sys.exit(main())
