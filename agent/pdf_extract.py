"""PDF text extraction — sync, no OCR.

Lives in agent/ (moved from api/app/pdf_extract.py) because the multimodal
capability path (agent/multimodal.py) extracts PDFs for text-only brains, and
agent/ importing api.app.* is the recurring layering defect this repo bans.
Used by the uploads router (via the api shim) to cache extracted text
alongside the binary in S3, and by M2 Phase 4 to verify page-reference claims.
"""
from __future__ import annotations

import io
import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def extract_pdf_text(pdf_bytes: bytes) -> Tuple[str, int]:
    """Extract plain text and page count from a PDF byte string.

    Returns ('', 0) for empty input, invalid PDFs, or extraction failure
    (e.g., image-only scans). Callers should treat both empty results as
    "no usable text" and surface a warning rather than treating it as an
    error — image-only PDFs are valid input but yield no text.
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
        return (text or "", page_count)
    except Exception as e:
        logger.warning("pdfminer extract failed: %s", e)
        return ("", 0)
