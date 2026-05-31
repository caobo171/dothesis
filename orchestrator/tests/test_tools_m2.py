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


class _Cite:
    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def test_scout_passes_use_deep_research_and_topic(monkeypatch):
    """B4: enable upstream's deep-research planner (50+ queries from topic+scope)
    instead of our hand-rolled 3 topic variants. Without this, 'gen Z + titok
    affectiveness' searched 3 near-identical typo'd variants → 0 hits."""
    captured = {}
    def fake_research(**kw):
        captured.update(kw)
        return {"citations": []}
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())
    # Both retries should also pass deep_research; isolate first call by
    # raising ValueError-via-mocking only on attempts > 1.
    scout_citations.invoke({"topic": "TikTok engagement Gen Z purchase", "min_n": 20})
    assert captured.get("use_deep_research") is True
    assert captured.get("topic") == "TikTok engagement Gen Z purchase"
    assert captured.get("scope") == "TikTok engagement Gen Z purchase"


def test_scout_reads_api_source_attribute(monkeypatch):
    """B3: engine's Citation class exposes `.api_source` (not `.source`).
    scout_citations was reading `.source` and getting None for every citation,
    so downstream code that filtered on `source` dropped them all. Read
    api_source, with source as a back-compat fallback."""
    cite = _Cite(title="Paper A", authors="Wang", year=2011,
                 api_source="Crossref",  # ← the real attribute name
                 url=None, doi="10.1/x")
    monkeypatch.setattr("orchestrator.tools.m2_literature.research_citations_via_api",
                        lambda **kw: {"citations": [cite]})
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())
    out = scout_citations.invoke({"topic": "X", "min_n": 5})
    assert out[0]["source"] == "Crossref"


def test_scout_topic_count_env_overrides_default(monkeypatch):
    """M2_SCOUT_TOPIC_COUNT lets the sim (or anything else) cut scout to 1
    research-topic for speed, without changing production defaults (3)."""
    captured = {}
    def fake_research(model, research_topics, output_path, target_minimum, **kw):
        captured["topics"] = research_topics
        return {"citations": []}
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())
    monkeypatch.setenv("M2_SCOUT_TOPIC_COUNT", "1")
    scout_citations.invoke({"topic": "X", "min_n": 5})
    assert len(captured["topics"]) == 1


def test_scout_topic_count_defaults_to_three(monkeypatch):
    captured = {}
    def fake_research(model, research_topics, output_path, target_minimum, **kw):
        captured["topics"] = research_topics
        return {"citations": []}
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())
    monkeypatch.delenv("M2_SCOUT_TOPIC_COUNT", raising=False)
    scout_citations.invoke({"topic": "X", "min_n": 5})
    assert len(captured["topics"]) == 3  # production default unchanged


def test_scout_citations_handles_citation_objects_with_falsy_fields(monkeypatch):
    """The engine returns Citation OBJECTS (no .get). A falsy field must not
    trigger a `.get()` fallback that raises AttributeError and crashes the whole
    scout (which then degraded M2 to zero citations)."""
    cite = _Cite(title="Paper A", authors="Wang", year=2011,
                 source=None, url=None, doi=None)
    monkeypatch.setattr("orchestrator.tools.m2_literature.research_citations_via_api",
                        lambda **kw: {"citations": [cite]})
    monkeypatch.setattr("orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())
    out = scout_citations.invoke({"topic": "x", "min_n": 5})
    assert out[0]["title"] == "Paper A"
    assert out[0]["source"] is None  # falsy field handled, no crash


def test_scout_citations_retries_with_low_target_on_quality_gate(monkeypatch):
    """When the engine raises the quality gate (too few citations), scout retries
    with a minimal target so the found citations are kept, not discarded."""
    calls = []
    fake_result = {"citations": [
        MagicMock(title="Paper A", authors="Wang", year=2011, source="J", url="http://x"),
        MagicMock(title="Paper B", authors="Bass", year=1985, source="J", url=None),
    ]}

    def fake_research(model, research_topics, output_path, target_minimum, **kw):
        calls.append(target_minimum)
        if target_minimum > 1:
            raise ValueError("QUALITY GATE FAILED (INSUFFICIENT CITATIONS)")
        return fake_result
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature.research_citations_via_api", fake_research)
    monkeypatch.setattr(
        "orchestrator.tools.m2_literature._get_llm", lambda: MagicMock())

    out = scout_citations.invoke({"topic": "TikTok Gen Z", "min_n": 20})
    assert calls == [20, 1]  # tried 20 (gate), retried with 1
    assert {c["title"] for c in out} == {"Paper A", "Paper B"}


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
