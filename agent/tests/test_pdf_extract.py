"""extract_pdf_text moved into agent/ (headless convergence spec §2): the
capability-driven multimodal path needs it, and agent/ importing api.app.*
is the banned agent->app direction. The shim keeps api import paths alive."""
from agent.pdf_extract import extract_pdf_text


def test_empty_bytes_returns_empty():
    assert extract_pdf_text(b"") == ("", 0)


def test_garbage_bytes_fail_soft():
    # Image-only scans / invalid PDFs must yield ("", 0), never raise — callers
    # treat empty as "no usable text" and fall back (spec Risk 3).
    assert extract_pdf_text(b"not a pdf at all") == ("", 0)


def test_api_shim_reexports_same_function():
    from app.pdf_extract import extract_pdf_text as shim
    assert shim is extract_pdf_text
