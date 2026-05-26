"""Tests for PDF text extraction."""
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixtures" / "sample.pdf"


def test_extract_pdf_text_returns_known_string():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(FIXTURE.read_bytes())
    assert "transformational leadership" in text.lower()
    assert page_count == 1


def test_extract_pdf_text_empty_bytes_returns_empty():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(b"")
    assert text == ""
    assert page_count == 0


def test_extract_pdf_text_invalid_bytes_returns_empty():
    from app.pdf_extract import extract_pdf_text
    text, page_count = extract_pdf_text(b"not a pdf")
    assert text == ""
    assert page_count == 0
