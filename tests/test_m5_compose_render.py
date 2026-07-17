"""Phase 4: compose_chapter weaves verified-state blocks (mocked LLM)."""
import pytest

from tests.fixtures.renderer_blocks import PLS_BLOCK, SCREENING_BLOCK

m5 = pytest.importorskip("orchestrator.tools.m5_writing")


def _mock_llm(monkeypatch, text):
    class _R:
        content = text
    monkeypatch.setattr(m5, "_get_llm", lambda: type("L", (), {"invoke": lambda self, p: _R()})())


def _slice(**extra):
    s = {"results": PLS_BLOCK, "conceptual_model": {"nodes": [], "edges": []},
         "language": "en"}
    s.update(extra)
    return s


def test_results_weaves_at_token(monkeypatch):
    _mock_llm(monkeypatch, "The model explains variance.\n\n[[DT:structural_paths]]\n\nInterpretation.")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "dt-rendered:begin kind=structural_paths" in out["prose"]
    assert "0.34" in out["prose"]  # verbatim from fixture


def test_results_appends_when_token_omitted(monkeypatch):
    _mock_llm(monkeypatch, "No tables here, just prose about the findings.")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    # tables appended even though the LLM emitted no token
    assert "dt-rendered:begin kind=measurement_model" in out["prose"]


def test_results_drops_llm_numeric_table(monkeypatch):
    _mock_llm(monkeypatch, "| H | path | beta | p |\n|---|---|---|---|\n| H1 | X | 0.99 | 0.5 |\n\n[[DT:structural_paths]]")
    out = m5.compose_chapter.func("results", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "0.99" not in out["prose"] and "0.34" in out["prose"]


def test_methodology_weaves_cleaning(monkeypatch):
    _mock_llm(monkeypatch, "We screened the data.\n\n[[DT:data_cleaning]]")
    out = m5.compose_chapter.func("methodology", "quantitative",
                             _slice(results=SCREENING_BLOCK), references=[], citation_style="apa7", language="en")
    assert SCREENING_BLOCK["data_screening"]["narrative"] in out["prose"]


def test_intro_unaffected(monkeypatch):
    _mock_llm(monkeypatch, "Background prose with no tables.")
    out = m5.compose_chapter.func("intro", "quantitative", _slice(), references=[], citation_style="apa7", language="en")
    assert "dt-rendered" not in out["prose"]


def test_empty_results_no_weave(monkeypatch):
    _mock_llm(monkeypatch, "Prose only.")
    out = m5.compose_chapter.func("results", "quantitative",
                             _slice(results=None), references=[], citation_style="apa7", language="en")
    assert "dt-rendered" not in out["prose"]
