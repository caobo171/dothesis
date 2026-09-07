"""Harvest + gate survivors -> backlog.tsv, one row per page that will exist.

Three jobs, in order:

  1. **Cut.** A harvest row becomes a page only if it is on topic: it must
     survive `exclusions.txt` (the blacklist) *and* name something this product
     teaches (`vocabulary.txt`, the whitelist). A slug already in
     `docs/blog-index.md` is a post to improve, not to write again.
  2. **Cluster.** Several phrasings of one intent are one page. The biggest
     becomes `focus_keyword` and the rest ride along as `secondary_keywords`,
     because two URLs chasing one query is the failure that multiplies fastest
     at a thousand posts.
  3. **Order and link.** Category round-robin by volume, so the first tranche is
     the best page of every category rather than 40 SPSS pages; 3 to 5 siblings
     per row so no post ships as a dead end.
"""
from __future__ import annotations

import csv
import os
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from . import topic_bank_dir, repo_root
from .expand import normalise_keyword, read_candidates
from .gate import read_gate_files

BACKLOG_COLUMNS = (
    "priority", "slug", "focus_keyword", "search_volume", "secondary_keywords",
    "category", "archetype", "family", "sibling_slugs", "competitor_urls", "gate_status",
)

REJECTED_COLUMNS = ("keyword", "volume", "reason")

MAX_SLUG_LENGTH = 120
MIN_SIBLINGS = 3
MAX_SIBLINGS = 5
MAX_SECONDARY = 8

# Category order for the round robin, by the measured volume of the category's
# own name (measured-heads-2026-09-07.tsv). A category with no measured name
# would not exist, so a missing key here is a bug, not a default.
CATEGORY_VOLUMES = {
    "spss": 14800,
    "thong-ke": 14800,
    "khao-sat": 6600,
    "nghien-cuu-khoa-hoc": 6600,
    "khoa-luan-tot-nghiep": 2900,
    "smartpls": 2400,
    "phan-tich-du-lieu": 1600,
    "luan-van-thac-si": 1000,
    "mo-hinh-nghien-cuu": 720,
}

# Function words and generic modifiers that do not change what a page is about.
# Deliberately conservative: over-stripping merges two intents into one page,
# which is worse than leaving two near-duplicate rows for the human review of
# the top 30 to catch. `du` and `phan` are absent on purpose (they collide with
# `dữ liệu` and `phần dư`).
_STOPWORDS = {
    "la", "gi", "cach", "chay", "trong", "cua", "va", "cho", "nhu", "the", "nao",
    "bao", "nhieu", "tot", "lam", "sao", "huong", "dan", "tiet", "moi", "nhat",
    "he", "so", "cac", "nhung", "ve", "duoc", "thi", "hay", "phai", "khi", "ban",
    "don", "gian", "chi",
}

_COMBINING = dict.fromkeys(range(0x0300, 0x0370))


def _ascii(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").lower())
    return decomposed.translate(_COMBINING).replace("đ", "d")


def slugify(text: str) -> str:
    """The shared heading-id/slug algorithm, minus the repeat counter."""
    return re.sub(r"[^a-z0-9]+", "-", _ascii(text)).strip("-")


def cluster_key(keyword: str) -> str:
    """A phrasing-independent identity for one intent.

    Sorted unique content tokens: `cronbach alpha là gì`, `hệ số cronbach alpha`
    and `cronbach alpha bao nhiêu là tốt` all reduce to `alpha cronbach`, which
    is one page. `cách chạy hồi quy trong spss` keeps `spss` and so stays its own.
    """
    tokens = [t for t in re.split(r"[^a-z0-9]+", _ascii(keyword)) if t]
    content = sorted({t for t in tokens if t not in _STOPWORDS})
    return " ".join(content) or " ".join(sorted(set(tokens)))


@dataclass
class Phrasing:
    keyword: str
    search_volume: int
    family: str
    category: str
    archetype: str
    competitor_urls: list[str] = field(default_factory=list)
    gate_status: str = "measured"
    axis: str = ""


@dataclass
class BacklogRow:
    priority: int
    slug: str
    focus_keyword: str
    search_volume: int
    secondary_keywords: list[str]
    category: str
    archetype: str
    family: str
    sibling_slugs: list[str]
    competitor_urls: list[str]
    gate_status: str


# ------------------------------------------------------------------ exclusions


def load_exclusions(path: str | None = None) -> list[re.Pattern]:
    path = path or os.path.join(topic_bank_dir(), "exclusions.txt")
    patterns: list[re.Pattern] = []
    if not os.path.isfile(path):
        return patterns
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            rule = line.strip()
            if not rule or rule.startswith("#"):
                continue
            try:
                patterns.append(re.compile(rule, re.IGNORECASE))
            except re.error as exc:
                raise ValueError(f"{path}:{lineno}: bad regex {rule!r}: {exc}") from exc
    return patterns


def excluded_by(keyword: str, url: str, patterns: list[re.Pattern]) -> re.Pattern | None:
    """The first exclusion rule that matches, or None.

    Keyword and URL are matched separately, never concatenated. An anchored rule
    like `^loc$` has to be able to say "the whole keyword is this word"; joining
    the two fields would break every anchor in the file.
    """
    fields = [f for f in ((keyword or "").strip(), (url or "").strip()) if f]
    for pattern in patterns:
        if any(pattern.search(field) for field in fields):
            return pattern
    return None


def is_excluded(keyword: str, url: str, patterns: list[re.Pattern]) -> bool:
    return excluded_by(keyword, url, patterns) is not None


# ----------------------------------------------------------------- vocabulary

# A whole word or a whole phrase, never a substring. `\b` would do for ASCII,
# but these lookarounds also behave for an entry that starts or ends with a
# non-word character (`t-test`, `pls-sem`, `p-value`). Vietnamese is written
# syllable-by-syllable with spaces, so `\w` boundaries land where a reader would
# put them: `tra` (the TRA model) matches `mô hình tra` and not `straight`, and
# `ave` matches `ave là gì` and not `average`.
def compile_terms(entries) -> re.Pattern | None:
    parts = sorted({(e or "").strip().lower() for e in entries if (e or "").strip()},
                   key=len, reverse=True)
    if not parts:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(p) for p in parts) + r")(?!\w)")


def load_vocabulary(path: str | None = None) -> list[str]:
    """The whitelist entries from `vocabulary.txt`, comments and blanks dropped."""
    path = path or os.path.join(topic_bank_dir(), "vocabulary.txt")
    entries: list[str] = []
    if not os.path.isfile(path):
        return entries
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            entry = line.strip()
            if entry and not entry.startswith("#"):
                entries.append(entry.lower())
    return entries


def vocabulary_matcher(path: str | None = None, lookup=None) -> re.Pattern | None:
    """`vocabulary.txt` plus every axis unit display, as one whole-word matcher.

    The axis displays are folded in at load time rather than copied into the
    file: 600 copied lines would go stale the first time an axis TSV changed,
    and the axis files are already the committed answer to what a unit is called.
    """
    lookup = _axis_lookup() if lookup is None else lookup
    return compile_terms(load_vocabulary(path) + [display for display, *_ in lookup])


def matches_vocabulary(keyword: str, matcher: re.Pattern | None) -> bool:
    """No vocabulary file means no whitelist, so nothing is rejected by it."""
    if matcher is None:
        return True
    return bool(matcher.search((keyword or "").lower()))


# --------------------------------------------------------- classifying a row

def _rule(*alternatives: str) -> re.Pattern:
    """One ordered rule: any alternative, matched as a whole word or phrase.

    Alternatives are regex source, not literals, so a rule can say `chương \\d+`.
    The boundary lookarounds are what keep the short acronyms usable: `tam`,
    `tra`, `ave` and `sem` are all real units here and all live inside ordinary
    words, so a substring rule mis-files `straight` as the TRA model — which is
    exactly what it did before.
    """
    return re.compile(r"(?<!\w)(?:" + "|".join(alternatives) + r")(?!\w)", re.IGNORECASE)


# First match wins, top to bottom. The order is the editorial decision: the tool
# the searcher named beats the concept (`cách chạy EFA trong SPSS` is an SPSS
# page), the degree beats the generic thesis word (`luận văn thạc sĩ` is not a
# khóa luận page), and the leftovers are statistics.
_CATEGORY_RULES = (
    ("smartpls", _rule("smartpls", "smart pls", "pls-sem", "pls sem", "partial least squares",
                       "bootstrapping", "blindfolding", "htmt", "outer loading",
                       "hệ số tải ngoài", "ave", "composite")),
    ("luan-van-thac-si", _rule("luận văn thạc sĩ", "thạc sĩ", "luận án", "cao học",
                               "nghiên cứu sinh")),
    # The citation tools sit next to `trích dẫn` because that is the same job:
    # a student asking about Mendeley or Turnitin is writing the document, not
    # analysing the data, and thong-ke would be the wrong shelf for them.
    ("khoa-luan-tot-nghiep", _rule("khóa luận", "khoá luận", "luận văn",
                                   "tài liệu tham khảo", "trích dẫn", "đề tài", "đề cương",
                                   "tóm tắt luận", "chương \\d+", "lý do chọn đề tài",
                                   "mục tiêu nghiên cứu", "đồ án tốt nghiệp", "đạo văn",
                                   "turnitin", "mendeley", "endnote", "lời nói đầu",
                                   "đặt vấn đề", "hàm ý quản trị")),
    ("khao-sat", _rule("khảo sát", "bảng hỏi", "bảng câu hỏi", "phiếu", "google form",
                       "cỡ mẫu", "chọn mẫu", "tỷ lệ phản hồi", "likert")),
    ("mo-hinh-nghien-cuu", _rule("mô hình", "lý thuyết", "thuyết", "tháp nhu cầu", "maslow",
                                 "herzberg", "tam", "tpb", "tra", "utaut", "servqual",
                                 "servperf", "swot", "aida", "porter")),
    # `đối tượng / phạm vi / khách thể nghiên cứu` are the same shelf as
    # `câu hỏi nghiên cứu`: the front matter of a study, not a statistic.
    ("nghien-cuu-khoa-hoc", _rule("nghiên cứu khoa học", "nckh", "phương pháp nghiên cứu",
                                  "quy trình nghiên cứu", "câu hỏi nghiên cứu",
                                  "giả thuyết nghiên cứu", "dữ liệu sơ cấp",
                                  "dữ liệu thứ cấp", "định tính", "định lượng",
                                  "tổng quan tài liệu", "khoảng trống",
                                  "đối tượng nghiên cứu", "phạm vi nghiên cứu",
                                  "khách thể nghiên cứu", "lĩnh vực nghiên cứu",
                                  "phương pháp luận", "cơ sở lý luận")),
    # `^spss$` is here so the category's own head term (14,800/month) lands in
    # its own category. Without it every other head term files itself correctly
    # and `spss` alone falls through to thong-ke, which is the one row nobody
    # can afford to have in the wrong place.
    ("spss", _rule("^spss$", "cách chạy", "trong spss", "kiểm định .* spss", "chạy spss",
                   "spss là gì", "tải spss", "cách dùng spss", "phải làm sao", "lỗi",
                   "ma trận xoay", "không hội tụ")),
    ("phan-tich-du-lieu", _rule("phân tích dữ liệu", "xử lý số liệu", "xử lý dữ liệu",
                                "làm sạch dữ liệu", "dữ liệu bị thiếu", "missing", "stata",
                                "rstudio", "r studio", "jasp", "eviews", "amos")),
)

# Archetype is mostly a function of the category — a survey page is a survey
# page — with two overrides that beat it, because they describe the *shape* of
# the answer rather than its subject. A reader asking `HTMT vượt ngưỡng phải làm
# sao` wants a troubleshooting page, not a SmartPLS walkthrough.
_TROUBLESHOOT = _rule("phải làm sao", "lỗi", "lộn xộn", "không hội tụ", "bị loại",
                      "không đạt", "quá thấp", "quá cao", "khắc phục", "sửa lỗi",
                      "vượt ngưỡng")
_TOPIC_LIST = _rule("đề tài")
_SMARTPLS_HOWTO = _rule("trong smartpls", "cách chạy", "cách vẽ", "cách phân tích")
_HOWTO = _rule("cách viết", "cách làm", "cách trình bày", "hướng dẫn", "quy trình",
               "các bước")
_TEST = _rule("kiểm định", "t-test", "t test", "anova", "ancova", "manova",
              "chi bình phương", "chi-square", "mann whitney", "kruskal", "wilcoxon")
_SCALE = _rule("thang đo")

_CATEGORY_ARCHETYPES = {
    "khao-sat": "survey",
    "mo-hinh-nghien-cuu": "model-theory",
    "khoa-luan-tot-nghiep": "thesis-writing",
    "luan-van-thac-si": "thesis-writing",
    "spss": "spss-howto",
}


def classify_category(keyword: str) -> str:
    text = (keyword or "").lower()
    for category, rule in _CATEGORY_RULES:
        if rule.search(text):
            return category
    return "thong-ke"


def classify_archetype(keyword: str, category: str | None = None) -> str:
    """The page shape. `category` is passed in when it is already known.

    An axis hit supplies the category, so re-deriving it here would be both
    wasted work and a chance for the two to disagree on the same row.
    """
    text = (keyword or "").lower()
    if _TROUBLESHOOT.search(text):
        return "troubleshoot"
    if _TOPIC_LIST.search(text):
        return "topic-list"
    category = category or classify_category(text)
    if category == "smartpls":
        return "smartpls-howto" if _SMARTPLS_HOWTO.search(text) else "term-la-gi"
    if category == "nghien-cuu-khoa-hoc":
        return "thesis-writing" if _HOWTO.search(text) else "term-la-gi"
    if category == "phan-tich-du-lieu":
        return "spss-howto" if _HOWTO.search(text) else "term-la-gi"
    if category in _CATEGORY_ARCHETYPES:
        return _CATEGORY_ARCHETYPES[category]
    # thong-ke and anything unmapped: a statistical term page unless the
    # phrasing names a test or a scale.
    if _TEST.search(text):
        return "test"
    if _SCALE.search(text):
        return "scale"
    return "term-la-gi"


def _axis_lookup() -> list[tuple[str, str, str, str]]:
    """(display, family, category, archetype) for every axis unit, longest first.

    A harvest keyword that names a known unit inherits that unit's family and
    classification, which is better than a keyword regex and keeps the harvest
    rows in the same families as the axis rows, so siblings cross-link between
    the two sources instead of forming two disconnected islands.
    """
    from .expand import load_axes  # noqa: PLC0415 — avoid a cycle at import time

    try:
        rows = load_axes()
    except FileNotFoundError:
        return []
    out = [(r.display.lower(), r.family, r.category, r.archetype) for r in rows if r.display]
    out.sort(key=lambda t: -len(t[0]))
    return out


def _classify_from_axes(keyword: str, lookup) -> tuple[str, str, str] | None:
    """Longest display first, matched as a whole word or phrase.

    Substring matching filed `straight` (5,400/month, an English dictionary
    query) under the TRA model, because `s-TRA-ight` contains the display. A
    display has to be *named*, not merely spelled out inside another word.
    """
    text = (keyword or "").lower()
    for display, family, category, archetype in lookup:
        if display and _display_pattern(display).search(text):
            return family, category, archetype
    return None


@lru_cache(maxsize=4096)
def _display_pattern(display: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(display) + r"(?!\w)")


# ------------------------------------------------------------------- sources


def read_harvest(path: str, patterns: list[re.Pattern], lookup=None,
                 vocabulary="__default__", allow: set[str] | None = None,
                 ) -> tuple[list[Phrasing], list[tuple[str, int, str]]]:
    """Harvest rows as phrasings, plus `(keyword, volume, reason)` for each drop.

    Two filters, and the second one is the point of this function. The blacklist
    (`exclusions.txt`) knows the junk somebody already met; the whitelist
    (`vocabulary.txt` plus the axis displays) is what stops the *next* competitor
    with a generic Q&A section from donating `cách làm tài liệu` at 368,000 a
    month to the backlog. A row earns a page by naming a unit we teach, not by
    failing to look like anything we have banned so far.

    `allow` is the candidate list: a keyword `expand` produced from an axis is on
    topic by construction, and the only reason to look for it in the harvest is
    to upgrade its gate status to measured. The whitelist must not veto that.

    `vocabulary` is a compiled matcher; the `"__default__"` sentinel builds one
    from the committed files and an explicit `None` turns the whitelist off.
    """
    lookup = _axis_lookup() if lookup is None else lookup
    allow = allow or set()
    if vocabulary == "__default__":
        vocabulary = vocabulary_matcher(lookup=lookup)
    kept: dict[str, Phrasing] = {}
    dropped: list[tuple[str, int, str]] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            keyword = normalise_keyword(row.get("keyword") or "")
            url = (row.get("url") or "").strip()
            if not keyword:
                continue
            raw_volume = (row.get("search_volume") or "").strip()
            volume = int(raw_volume) if raw_volume.isdigit() else 0
            rule = excluded_by(keyword, url, patterns)
            if rule is not None:
                dropped.append((keyword, volume, f"exclusion: {rule.pattern}"))
                continue
            if volume <= 0:
                dropped.append((keyword, volume, "no measured volume"))
                continue
            hit = _classify_from_axes(keyword, lookup)
            if (hit is None and keyword not in allow
                    and not matches_vocabulary(keyword, vocabulary)):
                dropped.append((keyword, volume, "off-vocabulary"))
                continue
            competitor = (row.get("competitor") or "").strip()
            ref = f"{competitor}:{url}" if competitor and url else (url or competitor)
            existing = kept.get(keyword)
            if existing:
                # Same query, several competitor pages. One page, all the URLs.
                if ref and ref not in existing.competitor_urls:
                    existing.competitor_urls.append(ref)
                existing.search_volume = max(existing.search_volume, volume)
                continue
            if hit:
                family, category, archetype = hit
                # The axis supplies the family; the phrasing still decides the
                # shape of the page (a `là gì` unit reached through a
                # `phải làm sao` query is a troubleshooting page).
                if _ARCHETYPE_HINTS.search(keyword):
                    archetype = classify_archetype(keyword, category)
            else:
                category = classify_category(keyword)
                family = "harvest-" + category
                archetype = classify_archetype(keyword, category)
            kept[keyword] = Phrasing(keyword=keyword, search_volume=volume, family=family,
                                     category=category, archetype=archetype,
                                     competitor_urls=[ref] if ref else [],
                                     gate_status="measured", axis="harvest")
    return list(kept.values()), dropped


_ARCHETYPE_HINTS = _rule("phải làm sao", "lỗi", "lộn xộn", "không hội tụ", "đề tài",
                         "cách viết", "cách chạy", "kiểm định")


def write_rejected(dropped: list[tuple[str, int, str]], path: str) -> None:
    """Every harvest row that did not become a page, biggest first.

    A whitelist can be wrong in the expensive direction — silently dropping a
    query worth writing — so the drops are committed to a file a human can skim
    in a minute rather than left as a count in a log line.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    seen: set[str] = set()
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(REJECTED_COLUMNS)
        for keyword, volume, reason in sorted(dropped, key=lambda d: (-d[1], d[0])):
            if keyword in seen:
                continue  # one line per query, not one per competitor page
            seen.add(keyword)
            writer.writerow([keyword, volume, reason])


def read_gate_survivors(candidates_path: str, gate_dir: str) -> list[Phrasing]:
    verdicts = read_gate_files(gate_dir)
    out: list[Phrasing] = []
    if not os.path.isfile(candidates_path):
        return out
    for candidate in read_candidates(candidates_path):
        verdict = verdicts.get(candidate.keyword)
        if not verdict or verdict.verdict != "pass":
            continue
        out.append(Phrasing(keyword=candidate.keyword,
                            search_volume=verdict.search_volume or 0,
                            family=candidate.family, category=candidate.category,
                            archetype=candidate.archetype,
                            gate_status=verdict.gate_status or "measured",
                            axis=candidate.axis))
    return out


def read_covered_slugs(index_path: str | None) -> set[str]:
    """Slugs already published, read from the committed blog index snapshot."""
    if not index_path or not os.path.isfile(index_path):
        return set()
    with open(index_path, encoding="utf-8") as fh:
        text = fh.read()
    return set(re.findall(r"/blog/[a-z]{2}/([a-z0-9][a-z0-9-]*)", text))


# ------------------------------------------------------------------ the build


def _merge_clusters(clusters: dict[str, list[Phrasing]]) -> dict[str, list[Phrasing]]:
    """WELE's morphological merge: identical volume plus a shared head token.

    Google reports close variants under one number, so two phrasings with the
    exact same volume and the same first word are one query wearing two hats.
    Two pages for that pair cannibalise each other.
    """
    leads = {key: max(group, key=lambda p: (p.search_volume, -len(p.keyword)))
             for key, group in clusters.items()}
    by_signature: dict[tuple[int, str, str], list[str]] = {}
    for key, lead in leads.items():
        head = _ascii(lead.keyword).split()[0] if lead.keyword.strip() else ""
        by_signature.setdefault((lead.search_volume, head, lead.family), []).append(key)

    merged = dict(clusters)
    for keys in by_signature.values():
        if len(keys) < 2:
            continue
        target = min(keys, key=lambda k: (len(leads[k].keyword), k))
        for key in keys:
            if key == target:
                continue
            merged[target] = merged[target] + merged[key]
            merged.pop(key, None)
    return merged


def _assign_siblings(rows: list[BacklogRow]) -> None:
    by_family: dict[str, list[BacklogRow]] = {}
    by_category: dict[str, list[BacklogRow]] = {}
    for row in sorted(rows, key=lambda r: -r.search_volume):
        by_family.setdefault(row.family, []).append(row)
        by_category.setdefault(row.category, []).append(row)

    for row in rows:
        picked: list[str] = []
        for pool in (by_family.get(row.family, []), by_category.get(row.category, []), rows):
            for other in pool:
                if other.slug == row.slug or other.slug in picked:
                    continue
                picked.append(other.slug)
                if len(picked) >= MAX_SIBLINGS:
                    break
            if len(picked) >= MIN_SIBLINGS:
                break
        row.sibling_slugs = picked[:MAX_SIBLINGS]


def _round_robin_tier(rows: list[BacklogRow]) -> list[BacklogRow]:
    buckets: dict[str, list[BacklogRow]] = {}
    for row in sorted(rows, key=lambda r: (-r.search_volume, r.slug)):
        buckets.setdefault(row.category, []).append(row)
    order = sorted(buckets, key=lambda c: (-CATEGORY_VOLUMES.get(c, 0), c))

    out: list[BacklogRow] = []
    while any(buckets[c] for c in order):
        for category in order:
            if buckets[category]:
                out.append(buckets[category].pop(0))
    return out


def _round_robin(rows: list[BacklogRow]) -> list[BacklogRow]:
    """Two tiers, measured first, each one a category round robin.

    `create` schedules in priority order, and a family-inferred row is inserted
    as a DRAFT that is never scheduled until it is measured on its own. Ordering
    both kinds together would let a draft take priority 3 while a measured page
    waits at 40, i.e. spend a publishing slot on a page that cannot publish. So
    the tier split comes first and the round robin runs inside each tier.
    """
    measured = [r for r in rows if r.gate_status != "family-inferred"]
    inferred = [r for r in rows if r.gate_status == "family-inferred"]
    out = _round_robin_tier(measured) + _round_robin_tier(inferred)
    for i, row in enumerate(out, 1):
        row.priority = i
    return out


FOLDS_COLUMNS = ("from_category", "to_category", "keyword_regex")


def load_folds(path: str | None = None) -> list[tuple[str, str, re.Pattern | None]]:
    """Category folds: (from, to, optional keyword regex), first match wins.

    WELE's taxonomy rule: a category that cannot clear ten posts is folded into
    a broader one rather than shipped thin. The fold lives in a TSV beside the
    backlog so a re-run reproduces it instead of a hand edit that the next
    `plan` silently undoes.
    """
    path = path or os.path.join(topic_bank_dir(), "category-folds.tsv")
    if not os.path.isfile(path):
        return []
    out: list[tuple[str, str, re.Pattern | None]] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            src = (row.get("from_category") or "").strip()
            dst = (row.get("to_category") or "").strip()
            if not src or not dst or src.startswith("#"):
                continue
            raw = (row.get("keyword_regex") or "").strip()
            out.append((src, dst, re.compile(raw, re.IGNORECASE) if raw else None))
    return out


def apply_folds(rows: list[BacklogRow], folds) -> int:
    """Rewrite row.category in place; returns how many rows moved."""
    moved = 0
    for row in rows:
        for src, dst, pattern in folds:
            if row.category != src:
                continue
            if pattern is not None and not pattern.search(row.focus_keyword):
                continue
            row.category = dst
            moved += 1
            break
    return moved


def build(phrasings: list[Phrasing], exclude_slugs: set[str] | None = None,
          folds=None) -> list[BacklogRow]:
    exclude_slugs = exclude_slugs or set()
    clusters: dict[str, list[Phrasing]] = {}
    for p in phrasings:
        clusters.setdefault(cluster_key(p.keyword), []).append(p)
    clusters = _merge_clusters(clusters)

    rows: list[BacklogRow] = []
    used_slugs: set[str] = set()
    for key in sorted(clusters, key=lambda k: -max(p.search_volume for p in clusters[k])):
        group = clusters[key]
        # Shortest of the highest-volume phrasings: the head term rather than a
        # long-tail restatement of it.
        lead = max(group, key=lambda p: (p.search_volume, -len(p.keyword)))
        slug = slugify(lead.keyword)[:MAX_SLUG_LENGTH].strip("-")
        if not slug or slug in exclude_slugs:
            continue
        base, n = slug, 2
        while slug in used_slugs:
            slug = f"{base}-{n}"
            n += 1
        used_slugs.add(slug)

        secondary = [p.keyword for p in sorted(group, key=lambda p: -p.search_volume)
                     if p.keyword != lead.keyword][:MAX_SECONDARY]
        urls: list[str] = []
        for p in group:
            for u in p.competitor_urls:
                if u not in urls:
                    urls.append(u)
        # A cluster is family-inferred only when nothing in it was measured on
        # its own; one measured phrasing is enough to schedule the page.
        status = "measured" if any(p.gate_status == "measured" for p in group) \
            else "family-inferred"
        rows.append(BacklogRow(priority=0, slug=slug, focus_keyword=lead.keyword,
                               search_volume=lead.search_volume, secondary_keywords=secondary,
                               category=lead.category, archetype=lead.archetype,
                               family=lead.family, sibling_slugs=[], competitor_urls=urls,
                               gate_status=status))

    if folds:
        apply_folds(rows, folds)  # before ordering: round-robin is per category
    ordered = _round_robin(rows)
    _assign_siblings(ordered)
    return ordered


def write_backlog(rows: list[BacklogRow], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(BACKLOG_COLUMNS)
        for r in rows:
            writer.writerow([r.priority, r.slug, r.focus_keyword, r.search_volume,
                             "; ".join(r.secondary_keywords), r.category, r.archetype,
                             r.family, "; ".join(r.sibling_slugs),
                             "; ".join(r.competitor_urls), r.gate_status])


def read_backlog(path: str) -> list[BacklogRow]:
    rows: list[BacklogRow] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh, delimiter="\t"):
            def split(value):
                return [v.strip() for v in (value or "").split(";") if v.strip()]

            rows.append(BacklogRow(
                priority=int(raw.get("priority") or 0),
                slug=raw["slug"],
                focus_keyword=raw["focus_keyword"],
                search_volume=int(raw.get("search_volume") or 0),
                secondary_keywords=split(raw.get("secondary_keywords")),
                category=raw.get("category") or "",
                archetype=raw.get("archetype") or "",
                family=raw.get("family") or "",
                sibling_slugs=split(raw.get("sibling_slugs")),
                competitor_urls=split(raw.get("competitor_urls")),
                gate_status=raw.get("gate_status") or "measured",
            ))
    return rows


def default_harvest_path() -> str:
    return os.path.join(topic_bank_dir(), "harvest-2026-09-07.tsv")


def run(harvest_path: str | None = None, candidates_path: str | None = None,
        gate_dir: str | None = None, exclusions_path: str | None = None,
        out_path: str | None = None,
        index_path: str | None = "__default__",
        vocabulary_path: str | None = None,
        rejected_path: str | None = None,
        folds_path: str | None = None) -> dict:
    bank = topic_bank_dir()
    harvest_path = harvest_path or default_harvest_path()
    candidates_path = candidates_path or os.path.join(bank, "candidates.tsv")
    gate_dir = gate_dir or bank
    out_path = out_path or os.path.join(bank, "backlog.tsv")
    # The rejects file belongs beside the backlog it explains, so a run pointed
    # at a temp directory keeps both artefacts there instead of half in the repo.
    rejected_path = rejected_path or os.path.join(
        os.path.dirname(os.path.abspath(out_path)), "plan-rejected.tsv")
    if index_path == "__default__":
        index_path = os.path.join(repo_root(), "docs", "blog-index.md")

    patterns = load_exclusions(exclusions_path)
    lookup = _axis_lookup()
    candidate_keywords = {c.keyword for c in read_candidates(candidates_path)} \
        if os.path.isfile(candidates_path) else set()
    harvest_rows, dropped = read_harvest(
        harvest_path, patterns, lookup=lookup,
        vocabulary=vocabulary_matcher(vocabulary_path, lookup=lookup),
        allow=candidate_keywords)
    write_rejected(dropped, rejected_path)
    gate_rows = read_gate_survivors(candidates_path, gate_dir)
    covered = read_covered_slugs(index_path)

    folds = load_folds(folds_path)
    all_rows = build(harvest_rows + gate_rows, folds=folds)
    kept = [r for r in all_rows if r.slug not in covered]
    if len(kept) != len(all_rows):
        kept = _round_robin(kept)
        _assign_siblings(kept)
    write_backlog(kept, out_path)

    per_category: dict[str, int] = {}
    for r in kept:
        per_category[r.category] = per_category.get(r.category, 0) + 1
    off_vocabulary = sum(1 for _, _, reason in dropped if reason == "off-vocabulary")
    summary = {
        "rows": len(kept),
        "from_harvest": len(harvest_rows),
        "from_gate": len(gate_rows),
        "excluded": len(dropped),
        "off_vocabulary": off_vocabulary,
        "blacklisted": sum(1 for _, _, r in dropped if r.startswith("exclusion:")),
        "rejected_path": rejected_path,
        "already_covered": len(all_rows) - len(kept),
        "family_inferred": sum(1 for r in kept if r.gate_status == "family-inferred"),
        "volume_total": sum(r.search_volume for r in kept),
        "per_category": per_category,
    }
    print(f"plan: {summary['rows']} backlog rows "
          f"({summary['from_harvest']} harvest phrasings, {summary['from_gate']} gate survivors)")
    print(f"      {summary['excluded']} harvest rows dropped "
          f"({summary['blacklisted']} by exclusions.txt, "
          f"{off_vocabulary} off-vocabulary) -> {rejected_path}")
    print(f"      {summary['already_covered']} already covered")
    print(f"      {summary['family_inferred']} family-inferred (insert as draft, never scheduled)")
    print(f"      total volume {summary['volume_total']:,}/month")
    for category in sorted(per_category, key=lambda c: -per_category[c]):
        print(f"        {category:24} {per_category[category]:5d}")
    return summary
