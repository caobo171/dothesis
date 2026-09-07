"""Harvest + gate survivors -> backlog.tsv, one row per page that will exist.

Three jobs, in order:

  1. **Cut.** Harvest rows matching `exclusions.txt` never become pages, and a
     slug already in `docs/blog-index.md` is a post to improve, not to write
     again.
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

from . import topic_bank_dir, repo_root
from .expand import normalise_keyword, read_candidates
from .gate import read_gate_files

BACKLOG_COLUMNS = (
    "priority", "slug", "focus_keyword", "search_volume", "secondary_keywords",
    "category", "archetype", "family", "sibling_slugs", "competitor_urls", "gate_status",
)

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


def is_excluded(keyword: str, url: str, patterns: list[re.Pattern]) -> bool:
    """Keyword and URL are matched separately, never concatenated.

    An anchored rule like `^loc$` has to be able to say "the whole keyword is
    this word"; joining the two fields would break every anchor in the file.
    """
    fields = [f for f in ((keyword or "").strip(), (url or "").strip()) if f]
    return any(p.search(field) for p in patterns for field in fields)


# --------------------------------------------------------- classifying a row

_CATEGORY_RULES = (
    # Order matters: the tool the searcher named wins over the concept, because
    # that is what they typed. `cách chạy EFA trong SPSS` is an SPSS page.
    ("smartpls", ("smartpls", "smart pls", "pls-sem", "pls sem", "partial least squares")),
    ("spss", ("spss",)),
    ("khao-sat", ("khảo sát", "phiếu", "bảng hỏi", "bảng câu hỏi", "form ", "cỡ mẫu",
                  "chọn mẫu", "thang đo likert", "likert", "thu thập dữ liệu")),
    ("luan-van-thac-si", ("luận văn thạc sĩ", "luận án", "cao học", "bảo vệ luận văn")),
    ("khoa-luan-tot-nghiep", ("khóa luận", "khoá luận", "đồ án tốt nghiệp", "tốt nghiệp")),
    ("mo-hinh-nghien-cuu", ("mô hình", "lý thuyết", "thang đo", "servqual", "servperf",
                            "utaut", "tam ", "tpb", "giả thuyết")),
    ("nghien-cuu-khoa-hoc", ("nghiên cứu khoa học", "phương pháp nghiên cứu", "đề tài",
                             "đề cương", "tổng quan tài liệu", "đạo đức nghiên cứu")),
    ("phan-tich-du-lieu", ("phân tích dữ liệu", "xử lý số liệu", "xử lý dữ liệu",
                           "làm sạch dữ liệu", "amos", "stata")),
)

_ARCHETYPE_RULES = (
    ("troubleshoot", ("phải làm sao", "lỗi ", "lộn xộn", "không hội tụ", "bị loại",
                      "không đạt", "quá thấp", "quá cao", "khắc phục", "sửa lỗi")),
    ("topic-list", ("đề tài", "danh sách đề tài", "chọn đề tài")),
    ("thesis-writing", ("cách viết", "luận văn", "khóa luận", "khoá luận", "đề cương",
                        "abstract", "tóm tắt", "hàm ý quản trị", "kết luận")),
    ("smartpls-howto", ("smartpls", "smart pls")),
    ("test", ("kiểm định", "t-test", "t test", "anova", "chi bình phương", "chi-square")),
    ("scale", ("thang đo",)),
    ("model-theory", ("mô hình", "lý thuyết")),
    ("survey", ("khảo sát", "cỡ mẫu", "bảng hỏi", "bảng câu hỏi", "phiếu", "chọn mẫu")),
    ("spss-howto", ("cách chạy", "hướng dẫn", "cách sử dụng", "cách phân tích", "cách làm")),
)


def classify_category(keyword: str) -> str:
    text = (keyword or "").lower()
    for category, needles in _CATEGORY_RULES:
        if any(n in text for n in needles):
            return category
    return "thong-ke"


def classify_archetype(keyword: str) -> str:
    text = (keyword or "").lower()
    for archetype, needles in _ARCHETYPE_RULES:
        if any(n in text for n in needles):
            return archetype
    return "term-la-gi"


def _axis_lookup() -> list[tuple[str, str, str, str]]:
    """(display, family, category, archetype) for every axis unit, longest first.

    A harvest keyword that contains a known unit inherits that unit's family and
    classification, which is better than a keyword regex and keeps the harvest
    rows in the same families as the axis rows, so siblings cross-link between
    the two sources instead of forming two disconnected islands.
    """
    from .expand import load_axes  # noqa: PLC0415 — avoid a cycle at import time

    try:
        rows = load_axes()
    except FileNotFoundError:
        return []
    out = [(r.display, r.family, r.category, r.archetype) for r in rows if r.display]
    out.sort(key=lambda t: -len(t[0]))
    return out


def _classify_from_axes(keyword: str, lookup) -> tuple[str, str, str] | None:
    text = (keyword or "").lower()
    for display, family, category, archetype in lookup:
        if display and display in text:
            return family, category, archetype
    return None


# ------------------------------------------------------------------- sources


def read_harvest(path: str, patterns: list[re.Pattern],
                 lookup=None) -> tuple[list[Phrasing], list[tuple[str, str]]]:
    """Harvest rows as phrasings, plus the rows the exclusions dropped."""
    lookup = _axis_lookup() if lookup is None else lookup
    kept: dict[str, Phrasing] = {}
    dropped: list[tuple[str, str]] = []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="\t"):
            keyword = normalise_keyword(row.get("keyword") or "")
            url = (row.get("url") or "").strip()
            if not keyword:
                continue
            if is_excluded(keyword, url, patterns):
                dropped.append((keyword, url))
                continue
            raw_volume = (row.get("search_volume") or "").strip()
            volume = int(raw_volume) if raw_volume.isdigit() else 0
            if volume <= 0:
                dropped.append((keyword, url))
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
            hit = _classify_from_axes(keyword, lookup)
            family, category, archetype = hit if hit else (
                "harvest-" + classify_category(keyword),
                classify_category(keyword),
                classify_archetype(keyword),
            )
            if hit:
                # The axis supplies the family; the phrasing still decides the
                # shape of the page (a `là gì` unit reached through a
                # `phải làm sao` query is a troubleshooting page).
                archetype = classify_archetype(keyword) if _ARCHETYPE_HINTS.search(
                    keyword) else archetype
            kept[keyword] = Phrasing(keyword=keyword, search_volume=volume, family=family,
                                     category=category, archetype=archetype,
                                     competitor_urls=[ref] if ref else [],
                                     gate_status="measured", axis="harvest")
    return list(kept.values()), dropped


_ARCHETYPE_HINTS = re.compile(
    r"phải làm sao|lỗi |lộn xộn|không hội tụ|đề tài|cách viết|cách chạy|kiểm định",
    re.IGNORECASE)


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


def _round_robin(rows: list[BacklogRow]) -> list[BacklogRow]:
    buckets: dict[str, list[BacklogRow]] = {}
    for row in sorted(rows, key=lambda r: (-r.search_volume, r.slug)):
        buckets.setdefault(row.category, []).append(row)
    order = sorted(buckets, key=lambda c: (-CATEGORY_VOLUMES.get(c, 0), c))

    out: list[BacklogRow] = []
    while any(buckets[c] for c in order):
        for category in order:
            if buckets[category]:
                out.append(buckets[category].pop(0))
    for i, row in enumerate(out, 1):
        row.priority = i
    return out


def build(phrasings: list[Phrasing], exclude_slugs: set[str] | None = None) -> list[BacklogRow]:
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
        index_path: str | None = "__default__") -> dict:
    bank = topic_bank_dir()
    harvest_path = harvest_path or default_harvest_path()
    candidates_path = candidates_path or os.path.join(bank, "candidates.tsv")
    gate_dir = gate_dir or bank
    out_path = out_path or os.path.join(bank, "backlog.tsv")
    if index_path == "__default__":
        index_path = os.path.join(repo_root(), "docs", "blog-index.md")

    patterns = load_exclusions(exclusions_path)
    harvest_rows, dropped = read_harvest(harvest_path, patterns)
    gate_rows = read_gate_survivors(candidates_path, gate_dir)
    covered = read_covered_slugs(index_path)

    all_rows = build(harvest_rows + gate_rows)
    kept = [r for r in all_rows if r.slug not in covered]
    if len(kept) != len(all_rows):
        kept = _round_robin(kept)
        _assign_siblings(kept)
    write_backlog(kept, out_path)

    per_category: dict[str, int] = {}
    for r in kept:
        per_category[r.category] = per_category.get(r.category, 0) + 1
    summary = {
        "rows": len(kept),
        "from_harvest": len(harvest_rows),
        "from_gate": len(gate_rows),
        "excluded": len(dropped),
        "already_covered": len(all_rows) - len(kept),
        "family_inferred": sum(1 for r in kept if r.gate_status == "family-inferred"),
        "volume_total": sum(r.search_volume for r in kept),
        "per_category": per_category,
    }
    print(f"plan: {summary['rows']} backlog rows "
          f"({summary['from_harvest']} harvest phrasings, {summary['from_gate']} gate survivors)")
    print(f"      {summary['excluded']} harvest rows excluded, "
          f"{summary['already_covered']} already covered")
    print(f"      {summary['family_inferred']} family-inferred (insert as draft, never scheduled)")
    print(f"      total volume {summary['volume_total']:,}/month")
    for category in sorted(per_category, key=lambda c: -per_category[c]):
        print(f"        {category:24} {per_category[category]:5d}")
    return summary
