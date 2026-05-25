from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)


def test_scout_citations_calls_engine_with_min_n(monkeypatch):
    fake_result = {"citations": [
        MagicMock(title="Paper A", authors="Wang", year=2011,
                  source="Journal", url="http://x"),
    ], "count": 1}
    captured = {}
    def fake_research(model, research_topics, output_path, target_minimum, **kw):
        captured["target_minimum"] = target_minimum
        captured["topics"] = research_topics
        return fake_result
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research
    )
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock()
    )

    out = scout_citations.invoke({"topic": "Transformational leadership", "min_n": 30})
    assert captured["target_minimum"] == 30
    assert any("Transformational leadership" in t for t in captured["topics"])
    assert out[0]["title"] == "Paper A"


def test_summarize_paper_reads_file_and_calls_llm(tmp_path, monkeypatch):
    pdf = tmp_path / "paper.txt"
    pdf.write_text("This paper studies X. Key findings: A, B, C.")
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "Studies X; finds A, B, C."
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: fake_llm)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._read_paper_text",
        lambda p: pdf.read_text(),
    )
    out = summarize_paper.invoke({"pdf_path": str(pdf)})
    assert out == "Studies X; finds A, B, C."


def test_find_research_gaps_asks_llm_for_json(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = (
        '[{"description":"No SME context","relevance":"High",'
        '"supporting_papers":[{"author":"Wang","year":2011}]}]'
    )
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: fake_llm)
    gaps = find_research_gaps.invoke({
        "citations": [{"title": "X", "author": "Wang", "year": 2011}],
    })
    assert len(gaps) == 1
    assert gaps[0]["description"] == "No SME context"


def test_compile_citations_uses_engine_compiler(monkeypatch):
    fake = MagicMock()
    fake.compile.return_value = "Wang, X. (2011). …"
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.CitationCompiler", lambda style: fake
    )
    out = compile_citations.invoke({
        "items": [{"author": "Wang", "year": 2011, "title": "X"}],
        "style": "apa7",
    })
    assert "Wang" in out


def test_verify_page_numbers_returns_status(monkeypatch):
    out = verify_page_numbers.invoke({
        "claim": {"author": "Wang", "year": 2011, "page": 118, "quote": "leadership inspires"},
    })
    assert out["status"] in {"verified", "unverified", "not_found"}
