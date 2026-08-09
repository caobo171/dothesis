"""Unit tests for the mid-journey import classifier/inferrer (F12 Task 1).

The inference helpers (_classify / _infer_topic / _infer_model /
_infer_analysis_results) hit an LLM, so these stub them and assert only the
routing: each classified kind lands in the right module slice, with the source
filename recorded as evidence, and unreadable files are surfaced rather than
silently dropped."""
import json

import pytest

from app import import_work as iw


def _stub_llm(monkeypatch, reply: str):
    """Point the module's lazily-imported _get_llm at a canned reply."""
    from orchestrator.tools import m5_writing as _m5
    monkeypatch.setattr(
        _m5, "_get_llm",
        lambda: type("L", (), {"invoke": lambda self, p: type("R", (), {"content": reply})()})())


def test_classifies_and_infers(monkeypatch):
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output" if "AVE" in text else "proposal")
    monkeypatch.setattr(iw, "_infer_topic", lambda text, language: {"research_title": "T", "research_questions": ["Q"]})
    monkeypatch.setattr(iw, "_infer_model", lambda text, language: {"constructs": [{"id": "a"}]})
    monkeypatch.setattr(iw, "_infer_analysis_results", lambda text, language: {})
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


# --- analysis_results must arrive STRUCTURED ---------------------------------

def test_analysis_output_is_stored_as_structured_dict(monkeypatch):
    """A parsed result block must be a dict, not the raw paste.

    Everything downstream keys off this. results_render.detect_family and
    render_results_tables return empty on a non-dict, and
    coherence.coverage_findings coerces one to {} and then reports every M3
    hypothesis as having no result — which is how a thesis containing a full
    H1-H3 table still produced "no structured result entries for H1, H2, H3".
    """
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output")
    monkeypatch.setattr(iw, "_infer_analysis_results", lambda text, language: {
        "hypothesis_tests": [
            {"id": "H1", "hypothesis": "H1", "path": "ATT → PB",
             "numbers": {"beta": 0.371, "t": 11.921, "p": "0.000"},
             "decision": "supported"},
        ]})
    out = iw.import_existing_work(
        [{"filename": "thesis.docx", "text": "Bảng 4.17 ... H1 ... 0.371"}], language="vi")
    ar = out["slices"]["M4"]["analysis_results"]
    assert isinstance(ar, dict)
    assert ar["hypothesis_tests"][0]["id"] == "H1"


def test_unparseable_analysis_output_falls_back_to_raw_text(monkeypatch):
    """Extraction failure must leave a STRING, not an empty dict.

    stats_validation raises structure.unstructured ("results are stored as free
    text, so the numbers cannot be verified") only for a str. Storing {} would
    silence that warning while leaving the results exactly as unverified.
    """
    monkeypatch.setattr(iw, "_classify", lambda fn, text: "analysis-output")
    monkeypatch.setattr(iw, "_infer_analysis_results", lambda text, language: {})
    out = iw.import_existing_work(
        [{"filename": "messy.pdf", "text": "some unparseable results"}], language="en")
    assert out["slices"]["M4"]["analysis_results"] == "some unparseable results"


def test_infer_analysis_results_extracts_hypothesis_rows(monkeypatch):
    """The helper returns the parsed block and drops empty containers."""
    _stub_llm(monkeypatch, json.dumps({
        "hypothesis_tests": [{"id": "H2", "path": "TR → PB",
                              "numbers": {"beta": 0.551}, "decision": "supported"}],
        "measurement_model": [],       # empty ⇒ must not survive
    }))
    got = iw._infer_analysis_results("Bảng 4.17 H2 0.551 Chấp nhận", "vi")
    assert got["hypothesis_tests"][0]["id"] == "H2"
    assert "measurement_model" not in got


def test_infer_analysis_results_returns_empty_on_bad_json(monkeypatch):
    """Never raise into the import — an unusable reply is just no extraction."""
    _stub_llm(monkeypatch, "sorry, I could not find any results")
    assert iw._infer_analysis_results("nothing here", "en") == {}


# --- classifier hints are whole words, not substrings ------------------------

@pytest.mark.parametrize("text", [
    "AVE = 0.62 for every construct",
    "Cronbach's alpha exceeded 0.7",
    "Các giá trị VIF nằm trong khoảng 1.000 đến 1.022",
    "HTMT ratios were below 0.85",
])
def test_real_stat_hints_still_classify_as_analysis_output(text):
    assert iw._classify("f.docx", text) == "analysis-output"


@pytest.mark.parametrize("text", [
    "Participants have a strong preference for the brand.",
    "The average respondent gave a positive answer.",
    "A wave of interest followed the campaign.",
])
def test_prose_containing_ave_is_not_analysis_output(monkeypatch, text):
    """'ave' as a bare substring matched have/gave/average/wave, so ordinary
    English prose skipped classification and was filed as analysis output."""
    _stub_llm(monkeypatch, "proposal")
    assert iw._classify("f.docx", text) == "proposal"
