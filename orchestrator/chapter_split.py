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
