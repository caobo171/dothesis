"""Unit tests for the mid-journey import classifier/inferrer (F12 Task 1).

The inference helpers (_classify / _infer_topic / _infer_model) hit an LLM, so
these stub them and assert only the routing: each classified kind lands in the
right module slice, with the source filename recorded as evidence, and unreadable
files are surfaced rather than silently dropped."""
from app import import_work as iw


def test_classifies_and_infers(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output" if "AVE" in text else "proposal")
    monkeypatch.setattr(iw, "_infer_topic", lambda text, language: {"research_title": "T", "research_questions": ["Q"]})
    monkeypatch.setattr(iw, "_infer_model", lambda text, language: {"constructs": [{"id": "a"}]})
    files = [{"filename": "proposal.pdf", "text": "This study examines..."},
             {"filename": "results.pdf", "text": "AVE=0.62 HTMT ok"}]
    out = iw.import_existing_work(files, language="en")
    assert out["slices"]["M1"]["research_title"] == "T"
    assert out["slices"]["M4"]["analysis_results"]
    assert out["evidence"]["M4"] == "results.pdf"


def test_unreadable_file_skipped(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "unknown")
    out = iw.import_existing_work([{"filename": "x.bin", "text": ""}], language="en")
    assert "x.bin" in out["unreadable"]
