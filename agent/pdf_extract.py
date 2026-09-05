"""PDF text extraction — sync, with an opt-in vision fallback for scans.

Lives in agent/ (moved from api/app/pdf_extract.py) because the multimodal
capability path (agent/multimodal.py) extracts PDFs for text-only brains, and
agent/ importing api.app.* is the recurring layering defect this repo bans.
Used by the uploads router (via the api shim) to cache extracted text
alongside the binary in S3, and by M2 Phase 4 to verify page-reference claims.

pdfminer reads a text layer; a PDF that is page images — a scan, or a results
section exported as pictures — has none, so extraction came back empty and the
caller was handed a document with no numbers in it. `ocr_if_hollow=True` sends
those through the vision model instead. It is OPT-IN because the callers differ:
the ingest paths want the text at any cost, while M2's page-reference check only
needs the text layer and should not pay for a model call, and multimodal already
runs its own hollow-check fallback (double-OCR would be pure waste).
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# "Hollow" = a text layer thin enough that the real content must be pictures.
# Both bars matter: a wholly scanned file trips the absolute one, while a 40-page
# thesis whose every result page is a screenshot trips the per-page one even
# though its prose pages push the total past 200.
_MIN_TEXT_CHARS = 200
_MIN_CHARS_PER_PAGE = 100

# Guards on the fallback: one oversized file must not become one enormous model
# call. Beyond these the hollow text is returned as-is and the reason logged.
_MAX_OCR_BYTES = 20 * 1024 * 1024
_MAX_OCR_PAGES = 60

_OCR_PROMPT = (
    "Transcribe this document faithfully as plain text/Markdown, in reading "
    "order. Render every table as a Markdown table, keeping row labels, column "
    "headers and numbers EXACTLY as shown. Never invent, round or guess a "
    "value; mark anything unreadable as [unreadable]."
)


def _looks_hollow(text: str, pages: int) -> bool:
    """True when the text layer is too thin to be the document's real content."""
    n = len((text or "").strip())
    if n < _MIN_TEXT_CHARS:
        return True
    return pages > 0 and (n / pages) < _MIN_CHARS_PER_PAGE


def _ocr_pdf(pdf_bytes: bytes, pages: int) -> str:
    """Vision-transcribe a PDF whose text layer is hollow. Returns "" on any
    failure so the caller keeps whatever pdfminer managed to find.

    The file goes to the model as a PDF rather than being rasterized here: the
    vision path already accepts PDF attachments (it is how multimodal handles a
    scanned attachment), so this adds no imaging dependency.
    """
    if len(pdf_bytes) > _MAX_OCR_BYTES or pages > _MAX_OCR_PAGES:
        logger.info(
            "pdf ocr skipped: %d bytes / %d pages exceeds the fallback budget",
            len(pdf_bytes), pages,
        )
        return ""
    try:
        from agent.multimodal import Attachment, _transcribe_via_vision  # noqa: PLC0415 — heavy/lazy

        att = Attachment(filename="document.pdf", bytes=pdf_bytes, mime_type="application/pdf")
        return (_transcribe_via_vision(att, prompt=_OCR_PROMPT) or "").strip()
    except Exception:
        logger.exception("pdf ocr fallback failed")
        return ""


def extract_pdf_text(pdf_bytes: bytes, *, ocr_if_hollow: bool = False) -> Tuple[str, int]:
    """Extract plain text and page count from a PDF byte string.

    Returns ('', 0) for empty input, invalid PDFs, or extraction failure.
    With `ocr_if_hollow=True`, a PDF whose text layer is missing or implausibly
    thin (a scan, or results pages exported as images) is transcribed with the
    vision model instead of coming back empty; the page count is preserved and
    the OCR text replaces the hollow layer only when it actually yields more.
    Without the flag the behaviour is exactly as before — callers should treat
    an empty result as "no usable text" rather than an error.
    """
    if not pdf_bytes:
        return ("", 0)
    try:
        from pdfminer.high_level import extract_text
        from pdfminer.pdfpage import PDFPage
    except ImportError:
        logger.exception("pdfminer.six not installed")
        return ("", 0)

    try:
        text = extract_text(io.BytesIO(pdf_bytes))
        page_count = sum(1 for _ in PDFPage.get_pages(io.BytesIO(pdf_bytes)))
    except Exception as e:
        logger.warning("pdfminer extract failed: %s", e)
        text, page_count = "", 0

    text = text or ""
    if ocr_if_hollow and _looks_hollow(text, page_count):
        ocr = _ocr_pdf(pdf_bytes, page_count)
        # Keep whichever is richer: a partial text layer still beats an OCR pass
        # that came back short because the model refused or the file was odd.
        if len(ocr) > len(text.strip()):
            logger.info(
                "pdf ocr fallback used: text layer %d chars over %d page(s) -> %d chars",
                len(text.strip()), page_count, len(ocr),
            )
            return (ocr, page_count)
    return (text, page_count)
