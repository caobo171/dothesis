"""Find the final chapter inside an imported thesis.

A student who uploads a finished thesis has their whole document written into
`m4_analysis.analysis_results` as one string — chapters 4 and 5 together — so M5
never receives anything and stays locked behind work that is already done.

This finds the boundary so the caller can move the last chapter to where it
belongs. It is deliberately conservative: **misfiling a student's discussion
chapter is worse than leaving the document whole**, so every uncertain case
returns None and the blob stays exactly as it arrived. A split that happens is
one we can defend; a split that does not happen costs the student one manual
paste.
"""
from __future__ import annotations

import re

# A final-chapter heading, at the start of a line: "CHƯƠNG 5", "CHAPTER 5",
# "Chương V". Numbered 5-9 because a thesis's conclusions are its last chapter
# and 5 is the common case, but a six-chapter thesis is not unusual.
#
# The heading must OWN its line (`$` after a short remainder) — "CHƯƠNG 5 sẽ
# trình bày kết luận" is a forward reference in running prose, not a heading,
# and treating it as one would cut the results chapter in half.
_FINAL_CHAPTER_RE = re.compile(
    r"^[ \t]*(?:CH[ƯU]ƠNG|CHAPTER|Chương|Chapter)[ \t]+(?:[5-9]|V|VI{1,3})\b[^\n]{0,80}$",
    re.MULTILINE,
)

# Below this a "chapter" is a heading with nothing under it — a table of
# contents entry, or a heading the student had not written yet.
_MIN_TAIL_CHARS = 400
# Below this the head would not be a results chapter any more; a boundary that
# early means we matched something other than the real heading.
_MIN_HEAD_CHARS = 400


def split_final_chapter(text: str | None) -> tuple[str, str] | None:
    """Split an imported document at its final chapter.

    Returns (head, tail) where `tail` starts at the final-chapter heading, or
    None when the document should be left alone — no heading, an ambiguous one,
    or either side too small to be a real chapter.
    """
    if not isinstance(text, str) or not text.strip():
        return None

    matches = list(_FINAL_CHAPTER_RE.finditer(text))
    if len(matches) != 1:
        # Zero: nothing to move. More than one: we cannot tell which heading is
        # the real chapter start (a contents page, a running header repeated per
        # page, or two genuinely different headings), and picking wrong splits
        # the thesis in the wrong place. Both are "leave it alone".
        return None

    at = matches[0].start()
    head, tail = text[:at].rstrip(), text[at:].strip()
    if len(head) < _MIN_HEAD_CHARS or len(tail) < _MIN_TAIL_CHARS:
        return None
    return head, tail


# --- plain extracted text -> markdown ----------------------------------------
#
# The exporter's contract is markdown: sections go through _sections_to_markdown
# into pandoc, and m5_writing states plainly that "prose is assumed to already be
# markdown (chapter composers emit markdown)". A PRESERVED chapter does not come
# from a composer — it is plain text pulled out of the student's .docx — and
# feeding that straight in produced exactly three defects in one page:
#
#   * single newlines are soft wraps in markdown, so the whole chapter collapsed
#     into one unbroken paragraph;
#   * "Tiêu chí | Phân loại | Tần số" has no leading/trailing pipes and no
#     |---| separator row, so every table rendered inline as running prose;
#   * "4.1. Thống kê mô tả mẫu" is not a heading, so Chapter 4 contributed no
#     entries to the table of contents while every composed chapter did.

# "CHƯƠNG 4: ...", "Chapter 4 - ..." → H1.
_H1_RE = re.compile(r"^(?:CH[ƯU]ƠNG|CHAPTER|Chương|Chapter)\s+[0-9IVX]+\b", re.IGNORECASE)
# "4.1 ...", "4.1. ..." → H2;  "4.1.1 ..." → H3. Requires text after the number
# so a bare "4.1" or a decimal inside prose is not promoted.
_HN_RE = re.compile(r"^(\d+(?:\.\d+)+)\.?\s+(\S.*)$")
# A table row: pipe-separated with at least two separators, i.e. 3+ cells.
_ROW_RE = re.compile(r"^[^|\n]*\|[^|\n]*\|.*$")


def _flush_table(rows: list[list[str]], out: list[str]) -> None:
    """Emit collected rows as ONE GitHub-style markdown table block.

    A single block, not one entry per row: blocks are later joined by blank
    lines, and a blank line between rows terminates the table — which turns it
    straight back into the loose prose this function exists to prevent.
    """
    if not rows:
        return
    if len(rows) == 1:                      # a lone piped line is not a table
        out.append(" ".join(rows[0]))
        return
    width = max(len(r) for r in rows)
    # Pandoc needs every row to have the header's column count; a short or long
    # row silently breaks the whole table rather than just its own line.
    norm = [(r + [""] * (width - len(r)))[:width] for r in rows]
    head, body = norm[0], norm[1:]
    lines = ["| " + " | ".join(head) + " |",
             "|" + "|".join(["---"] * width) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    out.append("\n".join(lines))


def plaintext_to_markdown(text: str) -> str:
    """Reflow extracted document text into markdown the exporter can render.

    Conservative by design: anything not recognised as a heading or a table row
    passes through as its own paragraph. Worst case the output is the same prose
    with proper paragraph breaks — never less than what came in.
    """
    if not isinstance(text, str) or not text.strip():
        return text or ""
    out: list[str] = []
    pending: list[list[str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            _flush_table(pending, out); pending = []
            continue
        if _ROW_RE.match(line):
            pending.append([c.strip() for c in line.split("|")])
            continue
        _flush_table(pending, out); pending = []
        if _H1_RE.match(line):
            out.append(f"# {line}")
            continue
        m = _HN_RE.match(line)
        if m:
            depth = min(m.group(1).count(".") + 1, 5)   # 4.1 → H2, 4.1.1 → H3
            out.append(f"{'#' * depth} {m.group(1)} {m.group(2)}")
            continue
        out.append(line)
    _flush_table(pending, out)
    # Blank line between every block: in markdown a single newline is a soft
    # wrap, which is what merged the chapter into one paragraph.
    return "\n\n".join(out)
