"""The writer's prompt, built from the skill files on disk.

The skills are the source of truth for structure, voice and citations, so the
preamble is read from them at run time rather than copied here. Editing
`references/voice.md` changes the next batch, which is the whole point of
keeping a human-readable skill next to a scripted writer.

The prompt is one JSON-mode call: preamble (rules) plus brief (this row).
"""
from __future__ import annotations

import json
import os
import re

from . import skills_dir as default_skills_dir

# The one definition of "this row has no measured search volume", shared with
# the gate. A prompt that asked for a different bar than the gate enforces would
# spend a repair call on every unmeasured row in the batch.
from .qa import MIN_INTERNAL_LINKS, UNMEASURED_STATUSES

BLOG_SKILL = "dothesis-blog-content"
WORD_TARGET_MIN = 1800
WORD_TARGET_MAX = 2400

CATEGORY_NAMES = {
    "spss": "SPSS",
    "thong-ke": "Thống kê",
    "khao-sat": "Khảo sát",
    "nghien-cuu-khoa-hoc": "Nghiên cứu khoa học",
    "khoa-luan-tot-nghiep": "Khóa luận tốt nghiệp",
    "smartpls": "SmartPLS",
    "phan-tich-du-lieu": "Phân tích dữ liệu",
    "luan-van-thac-si": "Luận văn thạc sĩ",
    "mo-hinh-nghien-cuu": "Mô hình nghiên cứu",
}

PRODUCT_BLOCK = """\
## DoThesis, the product this blog belongs to

DoThesis is a commercial chat-first workspace that takes a Vietnamese student
from a blank topic to a finished quantitative thesis. Five modules:

- **M1** chọn đề tài và câu hỏi nghiên cứu
- **M2** tổng quan tài liệu với nguồn được xác minh thật (CrossRef, OpenAlex,
  Semantic Scholar, arXiv)
- **M3** mô hình nghiên cứu, giả thuyết, phương pháp, thang đo và bảng hỏi
- **M4** phân tích dữ liệu thật của sinh viên bằng SPSS và SmartPLS, không bao
  giờ bịa số
- **M5** viết chương và xuất file DOCX cùng PDF

**DoThesis is quantitative only.** SPSS, SmartPLS, AMOS, bảng hỏi, dữ liệu
`.sav` và `.csv`. Never tell the reader to run interviews, focus groups,
thematic coding or any qualitative step.

**The CTA.** Exactly one link, in the closing paragraph, to `/landing`, naming
the module that does the step this article is about: M3 for thang đo and bảng
hỏi, M4 for chạy phân tích, M5 for viết chương. No second sales sentence
anywhere in the body.

**fillform.info.** For posts about surveys and data collection, fillform.info
is our own Vietnamese form product for collecting questionnaire responses.
Name it plainly as ours when the article reaches the "thu thập dữ liệu" step,
never as a neutral third-party recommendation, and name Google Forms honestly
as the alternative. Do not mention it in posts that are not about collecting
responses."""

_CONTRACT_TEMPLATE = """\
## Output

Return exactly one json object, no prose around it, with these keys:

```
{
  "title": "the H1, Vietnamese, no brand suffix",
  "meta_title": "max 70 characters, may end with ' | DoThesis'",
  "meta_description": "110 to 170 characters, says what the reader gets",
  "excerpt": "one sentence for the listing card, not the meta description again",
  "tags": ["3 to 6 Vietnamese or English terms"],
  "body": "the full article in markdown"
}
```

Hard requirements on `body`, all of them checked mechanically before the post
is accepted:

- %(word_min)d to %(word_max)d words of Vietnamese.
- The H2 spine of the archetype below, as `## ` headings. No `# ` H1, no manual
  heading ids, no raw HTML of any kind.
%(elements)s
- A `## Câu hỏi thường gặp` section with 4 to 6 `### ` questions, each answered
  in one to three paragraphs.
- At least %(link_floor)d distinct internal links, taken only from the list in the brief.
  Every internal link whose target is not on that list is deleted mechanically
  before this is counted: the anchor text stays, the link is thrown away. So an
  invented sibling slug cannot get you to four, and a plausible-looking guess
  costs you a link instead of adding one. The four come from the list or they
  do not exist. Link every entry on the list at least once where it fits the
  sentence you were writing anyway.
- Exactly one link to `/landing`, in the closing paragraph.
- Citations only from the allowlist above, copied character for character, as
  plain text inside the sentence, never inside backticks or a code span. If a
  claim needs a source that is not on the list, drop the number instead.
- No em dash, no exclamation mark, no blacklisted phrase, no `## Kết luận`
  heading, no motivational close.
"""

# The three proprietary elements from `structure.md`, written twice: once for a
# page whose query is measured, once for a page whose is not. The two variants
# are substituted into the contract rather than appended to it, because a
# contract that stated both floors would leave the model to pick one, and it
# picks the cheaper one.
_ELEMENTS_ONE = """\
- At least one GFM table. At least one of: a threshold table where every row
  names its source, a worked output table labelled `số liệu minh họa`, or a
  `cách viết vào luận văn` paragraph with an adaptable sentence."""

_ELEMENTS_TWO = """\
- At least two GFM tables, and at least TWO of these three, not one:
  a threshold table where every row names its source; a worked output table
  labelled `số liệu minh họa`; a `cách viết vào luận văn` paragraph, led by its
  own heading or a bold lead, with the placeholders visible. Two of the three,
  because this page has no measured query behind it: it earns its place by
  being the most useful page on the topic, and the elements are what a student
  cannot get from a competitor's rewrite."""


def output_contract(unmeasured: bool = False) -> str:
    """The `## Output` block, at the bar this row is actually held to."""
    return _CONTRACT_TEMPLATE % {
        "word_min": WORD_TARGET_MIN, "word_max": WORD_TARGET_MAX,
        "elements": _ELEMENTS_TWO if unmeasured else _ELEMENTS_ONE,
        "link_floor": MIN_INTERNAL_LINKS + (1 if unmeasured else 0),
    }


OUTPUT_CONTRACT = output_contract()


def row_is_unmeasured(row) -> bool:
    return getattr(row, "gate_status", "") in UNMEASURED_STATUSES


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def load_skill_files(skills_dir: str | None = None) -> dict[str, str]:
    """structure.md, voice.md and canonical-sources.md, verbatim from disk."""
    base = os.path.join(skills_dir or default_skills_dir(), BLOG_SKILL, "references")
    out = {}
    for name in ("structure", "voice", "canonical-sources"):
        path = os.path.join(base, f"{name}.md")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"the writer's rules come from the skill, and {path} is missing")
        out[name] = _read(path)
    return out


def archetype_skeleton(archetype: str, structure_text: str) -> str:
    """The one `### \\`archetype\\`` block from structure.md, for the brief."""
    pattern = re.compile(r"^### `" + re.escape(archetype) + r"`.*?(?=^### `|\Z)",
                         re.M | re.S)
    match = pattern.search(structure_text)
    return match.group(0).strip() if match else ""


def build_preamble(skills_dir: str | None = None) -> str:
    files = load_skill_files(skills_dir)
    return "\n\n".join([
        "You are writing one article for the DoThesis blog. The reader is a "
        "Vietnamese student writing a quantitative thesis, with their data file "
        "open and a deadline. Write in Vietnamese.",
        "# Structure\n\n" + files["structure"],
        "# Voice\n\n" + files["voice"],
        "# Citation allowlist\n\n" + files["canonical-sources"],
        "# Product\n\n" + PRODUCT_BLOCK,
    ])


def _competitor_hints(urls: list[str], limit: int = 4) -> list[str]:
    """Competitor URL slugs, as question hints only.

    The slug says what question their page answers. Their text is never fetched
    and never paraphrased: take the question, not the answer.
    """
    hints = []
    for ref in urls[:limit]:
        path = ref.split(":", 1)[-1]
        stem = path.rstrip("/").rsplit("/", 1)[-1]
        stem = re.sub(r"\.(html?|php)$", "", stem)
        stem = stem.replace("-", " ").replace("_", " ").strip()
        if stem and not stem.isdigit():
            hints.append(stem)
    return hints


def internal_link_lines(row, sibling_titles: dict[str, str] | None = None,
                        link_slugs: list[str] | None = None) -> list[str]:
    """The brief's link list, one markdown bullet per allowed target.

    `link_slugs` overrides the row's own siblings so the writer can top a thin
    list up from the rest of the backlog. Shared with the repair prompt: the
    retry has to see the same list, character for character, or it will invent
    a target again.
    """
    sibling_titles = sibling_titles or {}
    slugs = row.sibling_slugs if link_slugs is None else link_slugs
    category_route = f"/blog/vi/chu-de/{row.category}"
    links = [f"- `{category_route}` (chủ đề {CATEGORY_NAMES.get(row.category, row.category)})"]
    for slug in slugs:
        title = sibling_titles.get(slug)
        label = f" — {title}" if title else ""
        links.append(f"- `/blog/vi/{slug}`{label}")
    links.append("- `/landing` (the single CTA, closing paragraph only)")
    return links


def build_brief(row, sibling_titles: dict[str, str] | None = None,
                structure_text: str | None = None,
                link_slugs: list[str] | None = None) -> str:
    links = internal_link_lines(row, sibling_titles, link_slugs)
    unmeasured = row_is_unmeasured(row)

    # A row with no measured volume used to read as `0 searches a month`, which
    # says the topic is worthless rather than that nobody measured it. Say what
    # is actually true, and say what it costs.
    volume = ("no measured search volume, this query was never sampled"
              if unmeasured else f"{row.search_volume:,} searches a month, Vietnam")

    parts = [
        "# This article",
        f"- **focus keyword**: `{row.focus_keyword}` ({volume})",
        f"- **slug** (already decided, use it): `{row.slug}`",
        f"- **category**: `{row.category}` ({CATEGORY_NAMES.get(row.category, row.category)})",
        f"- **archetype**: `{row.archetype}`",
        f"- **word target**: {WORD_TARGET_MIN} to {WORD_TARGET_MAX}",
    ]
    if unmeasured:
        parts.append(
            "\n## This page has no measured query, so the bar is doubled\n\n"
            "Nobody measured a search volume for this keyword. That is not a "
            "reason to write less: it is the reason this page has to be the most "
            "useful page on the topic, because usefulness is the whole of its "
            "claim to a URL. Concretely, and all of it is checked mechanically:\n"
            f"- at least {MIN_INTERNAL_LINKS + 1} distinct internal links, not "
            f"{MIN_INTERNAL_LINKS}, from the list below.\n"
            "- at least two tables, not one.\n"
            "- at least TWO of the three proprietary elements, not one. The "
            "pair that fits almost every topic is the two tables, so write those "
            "unless the topic truly has no numbers:\n"
            "  1. a threshold table stating the cut-offs, with the source named "
            "either in a column or in the sentence that introduces the table, "
            "copied from the allowlist character for character;\n"
            "  2. a worked output table labelled `số liệu minh họa`, shaped like "
            "the real SPSS or SmartPLS output for this procedure;\n"
            "  3. a `cách viết vào luận văn` paragraph under its own heading or "
            "bold lead, with the placeholders visible.\n"
            "  A page carrying only the third element is rejected, which is the "
            "single most common way these pages fail.\n"
            "- nothing lifted from a sibling post. The whole bank is compared "
            "sentence by sentence after the batch, and a page sharing a fifth of "
            "its text with another is deleted, not repaired.")
    if row.secondary_keywords:
        parts.append("- **secondary keywords** (work them into H2s and prose, they do not "
                     "get their own pages): " +
                     ", ".join(f"`{k}`" for k in row.secondary_keywords))
    hints = _competitor_hints(row.competitor_urls)
    if hints:
        parts.append("- **questions competitors answer for this query** (hints only, their "
                     "text is never source material): " + "; ".join(hints))

    parts.append("\n## Internal links available to you\n\nUse at least four, and no link "
                 "outside this list. Every one of them resolves, and anything else is "
                 "deleted from your draft before it is checked.\n" + "\n".join(links))

    skeleton = archetype_skeleton(row.archetype, structure_text or "")
    if skeleton:
        parts.append("\n## The skeleton for this archetype\n\n" + skeleton)
    return "\n".join(parts)


def build_prompt(row, sibling_titles: dict[str, str] | None = None,
                 skills_dir: str | None = None,
                 link_slugs: list[str] | None = None) -> str:
    files = load_skill_files(skills_dir)
    return "\n\n".join([
        build_preamble(skills_dir),
        build_brief(row, sibling_titles, files["structure"], link_slugs),
        output_contract(row_is_unmeasured(row)),
    ])


def build_repair_prompt(row, previous: dict, failures: list[str],
                        sibling_titles: dict[str, str] | None = None,
                        skills_dir: str | None = None,
                        link_slugs: list[str] | None = None) -> str:
    """The one retry: same rules, the draft, and the exact list of what failed.

    The link list is repeated here rather than left to the brief above. The
    measured failure mode is a model that invents `/blog/vi/efa`, is told the
    link count is short, and invents two more: it has to read, in the same
    breath as the failure, that unknown targets were already stripped out of the
    draft it is looking at and that adding another cannot raise the count.
    """
    return "\n\n".join([
        build_prompt(row, sibling_titles, skills_dir, link_slugs),
        "# Your previous draft failed the checker\n\n"
        "Fix every item below and return the corrected json object. Keep "
        "everything that was already fine: do not rewrite the article, repair it.\n\n"
        + "\n".join(f"- {f}" for f in failures),
        "## Internal links, again, because this is where drafts fail\n\n"
        "Any internal link that was not on this list has already been stripped "
        "out of the draft below: the anchor text is still there, the link is "
        "gone. Inventing another target does nothing, it is stripped too. If the "
        "link count is short, link more of these:\n"
        + "\n".join(internal_link_lines(row, sibling_titles, link_slugs)),
        "## The draft to repair\n\n```json\n"
        + json.dumps({k: previous.get(k) for k in
                      ("title", "meta_title", "meta_description", "excerpt", "tags", "body")},
                     ensure_ascii=False, indent=2)
        + "\n```",
    ])
