"""The writer's prompt and the translator's, built from the skill files on disk.

The skills are the source of truth for structure, voice and citations, so the
preamble is read from them at run time rather than copied here. Editing
`references/voice.md` changes the next batch, which is the whole point of
keeping a human-readable skill next to a scripted writer.

The prompt is one JSON-mode call: preamble (rules) plus brief (this row).

The translation prompt lives here too, and for the same reason: it reads the
same `voice.md` and the same `canonical-sources.md`, and the three things it
has to get exactly right (the FAQ heading, the worked-table label, the
writing-paragraph lead) are quoted out of `qa.LOCALE_RULES` rather than typed
again, so the prompt and the gate cannot drift apart.
"""
from __future__ import annotations

import json
import os
import re

from . import skills_dir as default_skills_dir

# The one definition of "this row has no measured search volume", shared with
# the gate. A prompt that asked for a different bar than the gate enforces would
# spend a repair call on every unmeasured row in the batch.
from .qa import (BLACKLIST_EN, MIN_INTERNAL_LINKS, MIN_WORDS, META_DESC_MAX,
                 META_DESC_MIN, META_TITLE_MAX, UNMEASURED_STATUSES, rules_for)

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
        # These do not get their own pages — `plan` absorbs a row the loader's
        # duplicate guard would refuse into the row that beat it, and this line
        # is the only place that intent survives. So it has to reach the title
        # and the metas, not just an H2: a page that never names the absorbed
        # query does not rank for it, and nothing else will.
        parts.append("- **secondary keywords** (these queries get no page of their own, so "
                     "this page has to answer them: work the closest one into the title and "
                     "the meta description, and give each of the others an H2 or a named "
                     "paragraph): " +
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


# ---------------------------------------------------------------- translation

# The English edition is a translation of a bank that already passed the gate,
# so the translator is not asked to make editorial choices: the structure, the
# numbers, the tables and the citations are decided, and its whole job is to say
# the same things in English a graduate student would actually write.
TRANSLATE_ROLE = """\
You are producing the English edition of an article that already exists on the
DoThesis blog in Vietnamese. The reader is a graduate student writing a
quantitative thesis in English, with their data file open and a deadline.

This is a translation into idiomatic English, not a gloss. Every sentence has to
read as though it had been written in English by someone who has run the
analysis. Do not translate word by word, do not keep Vietnamese sentence shapes,
and do not leave a Vietnamese word in an English sentence.

What you may not do is change the article. The structure, the numbers, the
tables, the citations, the menu paths and the links are decided and stay put.
You are not rewriting, expanding, shortening, improving or updating anything."""

# Vietnamese is written in syllables, so the gate's whitespace word count reads
# high on the source and low on a faithful translation: the 979 seeds run a
# median of 3,025 Vietnamese tokens, and 27 of them sit under 2,000. Those are
# the ones that can land under the 1,500-word English floor, and the answer is
# never padding, it is that something was dropped.
_TRANSLATE_LENGTH = """\
The English body must be at least %(min_words)d words. A full translation of one
of these articles normally lands between 1,500 and 2,300 English words: the
Vietnamese count looks higher because Vietnamese writes each syllable as a
separate word. If your draft comes out short, the cause is something you left
out, not the language. Translate every paragraph, every table row, every FAQ
answer, every menu path and every caption. Do not add a section, do not pad a
paragraph, and do not repeat a point to make a length."""


def english_rules_block() -> str:
    """The three strings the gate matches on, quoted from the gate itself."""
    rules = rules_for("en")
    return """\
# Three strings the checker matches literally

These are not stylistic suggestions. A mechanical checker looks for them, and a
post missing one is rejected before anyone reads it.

1. The FAQ section is an H2 reading exactly `## %(faq)s`, with its `### `
   questions kept as `### ` questions, one per question, each still answered in
   one to three paragraphs. Translate the question text; keep the count.
2. The worked output table, the one showing what the software prints, is
   labelled `%(worked)s` in its caption, in the sentence right before the table
   or the one right after it. The Vietnamese label `số liệu minh họa` is where
   it is now; the English label replaces it.
3. The writing paragraph opens with a heading or a bold lead reading
   `%(writing)s`, and keeps its bracketed placeholders visible.""" % {
        "faq": rules.faq_heading,
        "worked": rules.worked_label,
        "writing": rules.writing_lead.capitalize(),
    }


def english_voice_block() -> str:
    """What `voice.md` means once the sentence around the term is English."""
    return """\
## The voice rules in English

Everything under Do and Do not in the voice guide above applies unchanged. No em
dash, no exclamation mark, no `Not X. It is Y.` reversal, no motivational close,
no `## Conclusion` heading, no listicle padding, no fake precision, no promise
about the reader's own numbers, no invented source, and never a qualitative
method offered as a step: the English checker rejects `in-depth interview` and
`qualitative coding` the way the Vietnamese one rejects `phỏng vấn sâu`.

The section headed "Vietnamese specifics" is the one thing that changes shape.
Its rule was: keep the English technical vocabulary in English and write the
surrounding sentence in Vietnamese. In English the technical vocabulary is
already English, so keep it exactly as the source has it (`Cronbach's Alpha`,
`outer loading`, `AVE`, `HTMT`, `VIF`, `p-value`, `Rotated Component Matrix`)
and translate the sentence around it. `chạy` becomes `run`. `biến quan sát`
becomes `item`, or `indicator` in a PLS model, never `question`. `thang đo` is
`scale`, `cỡ mẫu` is `sample size`, `bảng hỏi` is `questionnaire`, `luận văn` is
`thesis`, and `hội đồng` is `the committee`. Second person, direct, short
paragraphs of two to four sentences.

Write for a student who will submit in English. Do not explain Vietnamese
academic conventions to them and do not mention Vietnam unless the source
sentence is specifically about it.

## Phrases that fail the English post

The checker rejects a body containing any of these, case-insensitively. They are
the English half of the slop blacklist:

%(blacklist)s""" % {
        "blacklist": "\n".join(f"- `{p}`" for p in BLACKLIST_EN),
    }


TRANSLATE_CONTRACT = """\
## Output

Return exactly one json object, no prose around it, with these keys:

```
{
  "title": "the H1 in English, no brand suffix",
  "meta_title": "max %(meta_title_max)d characters, may end with ' | DoThesis'",
  "meta_description": "%(desc_min)d to %(desc_max)d characters, says what the reader gets",
  "excerpt": "one sentence for the listing card, not the meta description again",
  "focus_keyword": "the English query a student would type for this page",
  "secondary_keywords": ["2 to 4 English variants of that query"],
  "tags": ["3 to 6 English terms"],
  "body": "the whole article in English markdown"
}
```

`meta_title` and `meta_description` are written to fit, not translated to
length: the character limits are checked, and a literal translation of the
Vietnamese one usually misses them. `focus_keyword` is what the page should rank
for in English, and it is also what the slug is built from, so give the plain
search phrase and not a sentence.

Carried over untouched, character for character, and you do not get to change
any of them:

- **Every number.** Thresholds, coefficients, p-values, sample sizes, years,
  version numbers, the cells of every table. Do not convert, round, reformat or
  re-derive one. `0.7` stays `0.7`, `5,000` stays `5,000`.
- **Every table.** Same tables, same number of rows, same order, same cells.
  Translate the header labels and the wording inside a text cell; a cell that is
  a number or a citation is copied.
- **Every code identifier and menu path.** `Analyze > Scale > Reliability
  Analysis`, `Transform > Recode into Different Variables`, `.sav`, `.csv`,
  variable names like `SAT1`, and anything inside backticks or a fenced block.
- **Every citation.** The surname and the year are copied exactly. The only
  thing that changes is the connector: `và cộng sự` becomes `et al.`, and `và`
  between two surnames becomes `and`. `(Hair và cộng sự, 2010)` becomes
  `(Hair et al., 2010)`. Never add a citation, never drop one, never move one to
  a different sentence, and never cite a source that is not already in the
  Vietnamese body.
- **Every markdown link target.** Copy the part inside the parentheses exactly
  as it is, including `/blog/vi/...` targets. A later pass rewrites those to
  their English equivalents, and a target you edited is a target that pass
  cannot find. Translate the anchor text, never the href. There is exactly one
  `/landing` link and it stays in the closing paragraph.
- **Every `{{img:...}}` token**, spelled exactly as it appears.

%(length)s

No em dash and no exclamation mark anywhere in the output.
""" % {"meta_title_max": META_TITLE_MAX, "desc_min": META_DESC_MIN,
       "desc_max": META_DESC_MAX,
       "length": _TRANSLATE_LENGTH % {"min_words": MIN_WORDS}}

_SOURCE_FIELDS = ("title", "meta_title", "meta_description", "excerpt",
                  "focus_keyword", "secondary_keywords", "tags")


def build_translate_preamble(skills_dir: str | None = None) -> str:
    files = load_skill_files(skills_dir)
    return "\n\n".join([
        TRANSLATE_ROLE,
        "# Voice\n\n" + files["voice"],
        english_voice_block(),
        "# Citation allowlist\n\n" + files["canonical-sources"],
        "# Product\n\n" + PRODUCT_BLOCK,
        english_rules_block(),
    ])


def build_translate_brief(seed: dict) -> str:
    """The source article, whole, as the thing to translate."""
    head = {k: seed.get(k) for k in _SOURCE_FIELDS}
    return "\n\n".join([
        "# The Vietnamese article to translate",
        "Its metadata, for context. Produce the English counterpart of each, "
        "written to the limits in the contract rather than translated to "
        "length:\n\n```json\n"
        + json.dumps(head, ensure_ascii=False, indent=2) + "\n```",
        "Its body. Translate all of it:\n\n<article>\n"
        + (seed.get("body") or "") + "\n</article>",
    ])


def build_translate_prompt(seed: dict, skills_dir: str | None = None) -> str:
    return "\n\n".join([
        build_translate_preamble(skills_dir),
        build_translate_brief(seed),
        TRANSLATE_CONTRACT,
    ])


def build_translate_repair_prompt(seed: dict, previous: dict, failures: list[str],
                                  skills_dir: str | None = None) -> str:
    """The one retry: the same rules, the draft, and what the checker rejected."""
    return "\n\n".join([
        build_translate_prompt(seed, skills_dir),
        "# Your previous translation failed the checker\n\n"
        "Fix every item below and return the corrected json object. Keep "
        "everything that was already fine: do not translate the article again, "
        "repair the draft. A word-count failure means you dropped something, so "
        "find the paragraph you skipped rather than writing a new one.\n\n"
        + "\n".join(f"- {f}" for f in failures),
        "## The draft to repair\n\n```json\n"
        + json.dumps({k: previous.get(k) for k in
                      ("title", "meta_title", "meta_description", "excerpt",
                       "focus_keyword", "secondary_keywords", "tags", "body")},
                     ensure_ascii=False, indent=2)
        + "\n```",
    ])
