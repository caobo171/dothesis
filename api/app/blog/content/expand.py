"""Axis unit lists -> candidate keywords.

One TSV per axis under `docs/seo/topic-bank/axes/`, each row a real
methodological unit with the phrasings a student actually types. Crossing unit
by template is the whole of the expansion: no audience segmentation, no version
pages, and one cross only (see the depth budget in the pipeline skill).

Nothing here decides whether a page exists. `gate` does that, from measured
volume. This module only enumerates what is worth measuring.
"""
from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass

from . import axes_dir as default_axes_dir
from . import topic_bank_dir

# The nine categories from the design (§6). Kept here rather than imported from
# the API models so that `expand` and `qa` agree without a database import.
CATEGORY_SLUGS = (
    "spss", "thong-ke", "khao-sat", "nghien-cuu-khoa-hoc", "khoa-luan-tot-nghiep",
    "smartpls", "phan-tich-du-lieu", "luan-van-thac-si", "mo-hinh-nghien-cuu",
)

# The ten article skeletons in dothesis-blog-content/references/structure.md.
ARCHETYPES = (
    "term-la-gi", "spss-howto", "smartpls-howto", "test", "model-theory",
    "scale", "thesis-writing", "survey", "topic-list", "troubleshoot",
)

AXIS_COLUMNS = ("unit", "display", "templates", "category", "archetype", "family")
CANDIDATE_COLUMNS = ("keyword", "axis", "unit", "family", "category", "archetype")


@dataclass(frozen=True)
class AxisRow:
    axis: str
    unit: str
    display: str
    templates: list[str]
    category: str
    archetype: str
    family: str


@dataclass(frozen=True)
class Candidate:
    keyword: str
    axis: str
    unit: str
    family: str
    category: str
    archetype: str


def normalise_keyword(text: str) -> str:
    """Lowercase, collapse whitespace. What DataForSEO matches on."""
    return re.sub(r"\s+", " ", (text or "").strip()).lower()


def load_axis_file(path: str) -> list[AxisRow]:
    axis = os.path.splitext(os.path.basename(path))[0]
    rows: list[AxisRow] = []
    with open(path, encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        missing = [c for c in AXIS_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: axis file is missing column(s) {missing}")
        for raw in reader:
            unit = (raw["unit"] or "").strip()
            if not unit:
                continue  # tolerate a trailing blank line
            templates = [t.strip() for t in (raw["templates"] or "").split(";") if t.strip()]
            rows.append(AxisRow(
                axis=axis,
                unit=unit,
                display=(raw["display"] or "").strip(),
                templates=templates,
                category=(raw["category"] or "").strip(),
                archetype=(raw["archetype"] or "").strip(),
                family=(raw["family"] or "").strip(),
            ))
    return rows


def load_axes(directory: str | None = None) -> list[AxisRow]:
    directory = directory or default_axes_dir()
    if not os.path.isdir(directory):
        raise FileNotFoundError(f"no axes directory at {directory}")
    rows: list[AxisRow] = []
    for name in sorted(os.listdir(directory)):
        if name.endswith(".tsv"):
            rows.extend(load_axis_file(os.path.join(directory, name)))
    return rows


def expand_rows(rows: list[AxisRow]) -> list[Candidate]:
    """Cross every unit with its templates, first occurrence wins on a collision.

    Two units can legitimately produce the same phrase (`cronbach alpha` and
    `hệ số cronbach alpha` both reach `cronbach alpha là gì` on some templates).
    One keyword is one measurement and one page, so the duplicate is dropped
    here rather than paid for at the gate and then clustered away in `plan`.
    """
    seen: set[str] = set()
    out: list[Candidate] = []
    for row in rows:
        for template in row.templates:
            keyword = normalise_keyword(
                template.replace("{display}", row.display).replace("{unit}", row.unit))
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            out.append(Candidate(keyword=keyword, axis=row.axis, unit=row.unit,
                                 family=row.family, category=row.category,
                                 archetype=row.archetype))
    return out


def write_candidates(candidates: list[Candidate], path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
        writer.writerow(CANDIDATE_COLUMNS)
        for c in candidates:
            writer.writerow([c.keyword, c.axis, c.unit, c.family, c.category, c.archetype])


def read_candidates(path: str) -> list[Candidate]:
    with open(path, encoding="utf-8", newline="") as fh:
        return [Candidate(keyword=r["keyword"], axis=r["axis"], unit=r["unit"],
                          family=r["family"], category=r["category"],
                          archetype=r["archetype"])
                for r in csv.DictReader(fh, delimiter="\t")]


def default_candidates_path() -> str:
    return os.path.join(topic_bank_dir(), "candidates.tsv")


def run(axes_dir: str | None = None, out_path: str | None = None) -> dict[str, int]:
    """Write candidates.tsv. Returns candidates per axis, for the CLI to print."""
    rows = load_axes(axes_dir)
    candidates = expand_rows(rows)
    write_candidates(candidates, out_path or default_candidates_path())
    counts: dict[str, int] = {}
    for c in candidates:
        counts[c.axis] = counts.get(c.axis, 0) + 1
    return counts
