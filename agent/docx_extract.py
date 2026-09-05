"""Read a .docx into plain text, IN DOCUMENT ORDER.

The agent twin of pdf_extract: one place that knows how to turn a Word file
into something a text-only brain can read.

Two properties matter, and both were learned the hard way:

  - Tables must come out AT ALL. A quantitative thesis keeps its results in
    them — Cronbach's alpha, EFA loadings, KMO, path coefficients. Text
    without the tables is a results chapter with no results.
  - Tables must come out WHERE THEY WERE WRITTEN. python-docx exposes
    `doc.paragraphs` and `doc.tables` as two flat lists with no interleaving,
    so the obvious implementation emits every paragraph and then every table,
    which moves a thesis's tables into one block at the very end. Downstream
    that broke the import's chapter split (every table landed on the final
    chapter's side, leaving the analysis module with none) and left the writer
    unable to tell which table belonged to which section.

  - Third, learned the same way: a results table is very often not a table at
    all. Students paste the SmartPLS/SPSS output straight in as a SCREENSHOT,
    so the numbers live in an image and this walk saw nothing. One real upload
    carried eleven result screenshots and extracted as a page of prose holding
    exactly one number; the writer then produced a Results chapter that cited
    tables it had never been given. Images are transcribed with the vision
    model and emitted in place, for the same document-order reason as tables.

So walk the body XML instead of the convenience lists.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)

# Namespaces needed to find an image reference inside a paragraph.
_NS_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_NS_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# Bound the vision spend on one document: a deck of screenshots must not turn a
# single upload into an unbounded run of model calls. Small images are skipped
# outright — logos, bullets and signature scribbles carry no statistics.
_MAX_IMAGES = 25
_MIN_IMAGE_BYTES = 3000

_IMAGE_PROMPT = (
    "This image comes from a thesis (often SmartPLS/SPSS output). "
    "If it shows a TABLE, transcribe it verbatim as a Markdown table — keep every "
    "row label, column header and number EXACTLY as shown. "
    "If it is a path/model diagram, describe the constructs and the arrows between "
    "them, including any numbers on the paths. "
    "If it carries no data, reply with the single word NONE. "
    "Never invent, round or guess a number; mark unreadable cells [unreadable]."
)


def _image_rids(paragraph_el) -> list[str]:
    """Relationship ids of every image embedded in one paragraph element."""
    return [
        rid
        for blip in paragraph_el.iter(f"{_NS_A}blip")
        if (rid := blip.get(f"{_NS_R}embed"))
    ]


def _transcribe(doc, rid: str, index: int) -> str | None:
    """Vision-transcribe one embedded image, or None to skip it.

    Never raises: a missing key, an unreachable model or an odd part degrades to
    the text-only extraction this module did before.
    """
    try:
        part = doc.part.related_parts[rid]
        data = part.blob
    except Exception:
        return None
    if not data or len(data) < _MIN_IMAGE_BYTES:
        return None
    try:
        from agent.multimodal import Attachment, _transcribe_via_vision  # noqa: PLC0415 — heavy/lazy

        name = str(getattr(part, "partname", f"image{index}")).rsplit("/", 1)[-1]
        att = Attachment(
            filename=name,
            bytes=data,
            mime_type=getattr(part, "content_type", None) or "image/png",
        )
        text = (_transcribe_via_vision(att, prompt=_IMAGE_PROMPT) or "").strip()
    except Exception:
        logger.exception("docx image transcription failed (rid=%s)", rid)
        return None
    if not text or text.upper().startswith("NONE"):
        return None
    return f"[Hình {index}]\n{text}"


def extract_docx_text(data: bytes, *, transcribe_images: bool = True) -> str:
    """Paragraphs, table rows and embedded images as text, in document order.

    Table rows are flattened to `a | b | c` so the numbers inside them survive
    as text, and pasted result screenshots are transcribed where they appear.
    Best-effort: returns "" rather than raising, because the callers are an
    upload path and a chat turn, and neither should die on one odd file.

    `transcribe_images=False` skips the vision pass for callers that only need
    the prose and cannot afford the latency.
    """
    try:
        from docx import Document  # noqa: PLC0415 — heavy, and only needed here
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
        parts: list[str] = []
        images_done = 0
        for child in doc.element.body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, doc).text
                if text and text.strip():
                    parts.append(text)
                if not transcribe_images:
                    continue
                for rid in _image_rids(child):
                    if images_done >= _MAX_IMAGES:
                        break
                    block = _transcribe(doc, rid, images_done + 1)
                    if block:
                        images_done += 1
                        parts.append(block)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    cells = [c.text.strip() for c in row.cells
                             if c.text and c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        if images_done:
            logger.info("docx extraction: transcribed %d embedded image(s)", images_done)
        return "\n".join(parts)
    except Exception:
        logger.exception("docx text extraction failed")
        return ""
