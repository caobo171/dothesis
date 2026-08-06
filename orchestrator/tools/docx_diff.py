"""Paragraph-by-paragraph diff between a tool run's input and its output.

Exists because "80 đoạn đã viết lại" is a number, not evidence. A student
handing a rewritten chapter to a supervisor — and an admin answering "what did
your tool do to my document" — both need to see the actual words that moved,
next to the words that did not.

Word-level, not line-level: a humanize pass rewrites inside sentences, so a
line diff would mark every touched paragraph as one big delete followed by one
big insert and show nothing useful. Splitting on whitespace-with-punctuation
keeps the changed spans small enough to read.

Positional pairing is safe here and only here: humanize_docx writes each rewrite
back into the paragraph it came from and refuses any batch whose paragraph count
changed, so input paragraph N and output paragraph N are the same paragraph by
construction. If that ever stops holding, `aligned` goes False and the caller
must not present the pairs as a diff.
"""
from __future__ import annotations

import difflib
import io
import re
from dataclasses import dataclass, field

# Keep punctuation attached to its word but split on whitespace, so "0,412."
# stays one token and a moved comma does not shred the diff.
_TOKEN_RE = re.compile(r"\S+|\s+")


@dataclass
class Segment:
    op: str          # "equal" | "del" | "ins"
    text: str


@dataclass
class ParagraphDiff:
    index: int
    before: str
    after: str
    segments: list[Segment] = field(default_factory=list)


@dataclass
class RunDiff:
    aligned: bool
    total: int = 0
    changed: int = 0
    unchanged: int = 0
    items: list[ParagraphDiff] = field(default_factory=list)
    truncated: bool = False


def _paragraphs(body: bytes) -> list[str]:
    from docx import Document  # noqa: PLC0415 — heavy, and only needed here

    return [(p.text or "").strip() for p in Document(io.BytesIO(body)).paragraphs]


def word_segments(before: str, after: str) -> list[Segment]:
    """The two strings as a run of equal / deleted / inserted spans."""
    a = _TOKEN_RE.findall(before or "")
    b = _TOKEN_RE.findall(after or "")
    ops = difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes()

    # The tokenizer emits whitespace as its own token, so a rewritten clause
    # comes back as del/ins/equal(" ")/del/ins/… — a stutter of one-word
    # highlights with unhighlighted gaps between them. An `equal` span that is
    # ONLY whitespace and has a change on both sides is a bridge: it belongs to
    # the changed region rather than separating two of them.
    bridge = [
        op == "equal"
        and not "".join(a[i1:i2]).strip()
        and 0 < k < len(ops) - 1
        and ops[k - 1][0] != "equal" and ops[k + 1][0] != "equal"
        for k, (op, i1, i2, j1, j2) in enumerate(ops)
    ]

    out: list[Segment] = []
    k = 0
    while k < len(ops):
        op, i1, i2, j1, j2 = ops[k]
        if op == "equal" and not bridge[k]:
            out.append(Segment("equal", "".join(a[i1:i2])))
            k += 1
            continue
        # One changed region: everything up to the next real `equal`, emitted
        # as a single deletion followed by a single insertion.
        removed, added = [], []
        while k < len(ops) and (ops[k][0] != "equal" or bridge[k]):
            _, x1, x2, y1, y2 = ops[k]
            removed.append("".join(a[x1:x2]))
            added.append("".join(b[y1:y2]))
            k += 1
        out.append(Segment("del", "".join(removed)))
        out.append(Segment("ins", "".join(added)))
    # Merge neighbours of the same kind so the client renders fewer spans.
    merged: list[Segment] = []
    for seg in out:
        if merged and merged[-1].op == seg.op:
            merged[-1].text += seg.text
        else:
            merged.append(Segment(seg.op, seg.text))

    return [s for s in merged if s.text]


def diff_docx(before_bytes: bytes, after_bytes: bytes, *,
              limit: int = 200, changed_only: bool = True) -> RunDiff:
    """Compare two .docx files paragraph by paragraph."""
    before = _paragraphs(before_bytes)
    after = _paragraphs(after_bytes)

    if len(before) != len(after):
        # Not a rewrite of the same document, or the walk's alignment broke.
        # Reporting pairs anyway would attribute one paragraph's text to
        # another, which is worse than reporting nothing.
        return RunDiff(aligned=False, total=max(len(before), len(after)))

    result = RunDiff(aligned=True, total=len(before))
    for i, (b, a) in enumerate(zip(before, after)):
        if b == a:
            result.unchanged += 1
            if changed_only or len(result.items) >= limit:
                continue
            result.items.append(ParagraphDiff(i, b, a, [Segment("equal", b)]))
            continue
        result.changed += 1
        if len(result.items) >= limit:
            result.truncated = True
            continue
        result.items.append(ParagraphDiff(i, b, a, word_segments(b, a)))
    return result
