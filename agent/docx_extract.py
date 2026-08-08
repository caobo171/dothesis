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

So walk the body XML instead of the convenience lists.
"""
from __future__ import annotations

import io
import logging

logger = logging.getLogger(__name__)


def extract_docx_text(data: bytes) -> str:
    """Paragraphs and table rows as text, in document order.

    Table rows are flattened to `a | b | c` so the numbers inside them survive
    as text. Best-effort: returns "" rather than raising, because the callers
    are an upload path and a chat turn, and neither should die on one odd file.
    """
    try:
        from docx import Document  # noqa: PLC0415 — heavy, and only needed here
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        doc = Document(io.BytesIO(data))
        parts: list[str] = []
        for child in doc.element.body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "p":
                text = Paragraph(child, doc).text
                if text and text.strip():
                    parts.append(text)
            elif tag == "tbl":
                for row in Table(child, doc).rows:
                    cells = [c.text.strip() for c in row.cells
                             if c.text and c.text.strip()]
                    if cells:
                        parts.append(" | ".join(cells))
        return "\n".join(parts)
    except Exception:
        logger.exception("docx text extraction failed")
        return ""
