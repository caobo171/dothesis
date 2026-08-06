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


# --- export ---------------------------------------------------------------
#
# Deliberately plain HTML: inline styles, no flexbox, no CSS variables, <ins>
# and <del> rather than styled spans. Two readers have to cope with it — a
# browser, and LibreOffice, which is what turns this into a PDF and supports
# roughly the CSS of 2005. Anything fancier renders in the browser and comes out
# of soffice as unstyled text, which is worse than plain.

_HTML_HEAD = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: Georgia, "Times New Roman", serif; font-size: 11pt;
          line-height: 1.6; color: #1a1a1a; margin: 2.2cm; }}
  h1 {{ font-size: 15pt; margin: 0 0 .2em; }}
  .meta {{ color: #555; font-size: 9.5pt; margin: 0 0 1.4em; }}
  /* Spacing only, no border: LibreOffice renders a div's border-bottom as an
     UNDERLINE under the text, which collides with <ins> meaning "added". */
  .p {{ margin: 0 0 1.3em; padding: 0; }}
  .n {{ color: #999; font-size: 8.5pt; letter-spacing: .06em; }}
  del {{ background: #fbe9e9; color: #8a3a3a; }}
  ins {{ background: #e6f2e8; color: #2f5136; text-decoration: none; }}
  .legend {{ font-size: 9pt; color: #555; margin: 0 0 1.6em; }}
  @media print {{ .p {{ page-break-inside: avoid; }} }}
</style>
</head>
<body>
<h1>{title}</h1>
<p class="meta">{meta}</p>
<p class="legend"><del>removed</del> &nbsp; <ins>added</ins></p>
"""


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def render_diff_html(diff: RunDiff, *, title: str, meta: str = "",
                     lang: str = "vi") -> str:
    """The diff as one self-contained HTML file — no assets, no network."""
    out = [_HTML_HEAD.format(title=_esc(title), meta=_esc(meta), lang=lang)]
    if not diff.aligned:
        out.append("<p><strong>These two files no longer line up paragraph for "
                   "paragraph, so no comparison is shown.</strong></p>")
    for item in diff.items:
        out.append(f'<div class="p"><div class="n">#{item.index + 1}</div><p>')
        for seg in item.segments:
            text = _esc(seg.text)
            # Colour repeated INLINE, not left to the stylesheet: LibreOffice
            # honours an inline style attribute but drops the background from a
            # <style> rule, so the PDF came out shape-only (strikethrough vs
            # underline). Belt and braces keeps both readers in colour.
            if seg.op == "del":
                out.append(f'<del style="background:#fbe9e9;color:#8a3a3a">'
                           f'{text}</del>')
            elif seg.op == "ins":
                out.append(f'<ins style="background:#e6f2e8;color:#2f5136">'
                           f'{text}</ins>')
            else:
                out.append(text)
        out.append("</p></div>")
    if diff.truncated:
        out.append("<p class='meta'>Truncated — download the two files for the rest.</p>")
    out.append("</body></html>")
    return "".join(out)


def html_to_pdf(html: str, *, timeout: int = 120) -> bytes | None:
    """Render the HTML to PDF with LibreOffice. None when it isn't available.

    soffice rather than a Python renderer because it is ALREADY a hard
    dependency of this deployment (scripts/check-export-deps.sh installs it for
    the .docx export path), so this adds a code path rather than a dependency.
    """
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415
    import tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "diff.html"
        src.write_text(html, encoding="utf-8")
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf",
                 "--outdir", tmp, str(src)],
                capture_output=True, timeout=timeout, check=False)
        except Exception:  # noqa: BLE001 — a missing/hung converter is not fatal
            return None
        pdf = Path(tmp) / "diff.pdf"
        return pdf.read_bytes() if pdf.exists() else None
