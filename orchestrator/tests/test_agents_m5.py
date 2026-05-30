"""Auto-mode roundtrip test for M5 agent — validates schema-driven auto-fill
against the SP6 chapter-based schema."""
import json
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_m5_normalize_chapters_coerces_autofill_list_to_dict():
    """Regression: auto-fill sometimes returns `chapters` as a LIST of chapter
    dicts (with 'title') instead of the schema's name-keyed dict — which crashed
    _build_sections_for_export with 'list object has no attribute get'."""
    agent = M5Agent()
    chapters_list = [
        {"title": "Chapter 1: Introduction", "prose": "intro text"},
        {"title": "Chapter 2: Literature Review", "prose": "lit text"},
        {"title": "Chapter 3: Methodology", "prose": "method text"},
        {"title": "Chapter 4: Results", "prose": "results text"},
        {"title": "Chapter 5: Discussion", "prose": "disc text"},
        {"title": "Chapter 6: Conclusion", "prose": "concl text"},
    ]
    out = agent._normalize_chapters(chapters_list)
    assert isinstance(out, dict)
    assert out["intro"]["prose"] == "intro text"
    assert out["lit_review"]["prose"] == "lit text"
    assert out["methodology"]["prose"] == "method text"
    assert out["conclusion"]["prose"] == "concl text"


def test_m5_normalize_chapters_passthrough_dict():
    agent = M5Agent()
    d = {"intro": {"prose": "x"}}
    assert agent._normalize_chapters(d) == d


def test_m5_build_sections_survives_list_chapters():
    agent = M5Agent()
    sections = agent._build_sections_for_export(
        {"chapters": [{"title": "Chapter 1: Introduction", "prose": "hi"}]})
    intro = next(s for s in sections if s["name"] == "intro")
    assert intro["text"] == "hi"


def test_m5_auto_composes_each_chapter_separately_and_exports(monkeypatch):
    """Auto mode composes each chapter in its OWN compose_chapter call (6 calls)
    rather than one monolithic _auto_fill request — which hit Gemini 504
    DEADLINE_EXCEEDED for a full 6-chapter generation — then exports to S3."""
    from orchestrator.agents import m5_writing as m5_mod

    fake_compose = MagicMock()
    fake_compose.invoke.side_effect = lambda p: {
        "name": p["chapter_name"], "prose": f"# {p['chapter_name']}\nContent"}
    monkeypatch.setattr(m5_mod, "compose_chapter", fake_compose)

    fake_bib = MagicMock()
    fake_bib.invoke.return_value = "Bass, A. (1990)."
    monkeypatch.setattr(m5_mod, "compile_bibliography", fake_bib)

    fake_docx = MagicMock()
    fake_docx.invoke.return_value = {"s3_key": "projects/p/exports/thesis-real.docx", "size_bytes": 512}
    monkeypatch.setattr(m5_mod, "export_docx", fake_docx)

    fake_pdf = MagicMock()
    fake_pdf.invoke.return_value = {"s3_key": "projects/p/exports/thesis-real.pdf", "size_bytes": 1024}
    monkeypatch.setattr(m5_mod, "compile_pdf", fake_pdf)

    state = {
        "messages": [HumanMessage(content="export")],
        "current_module": "M5",
        "project_id": "p",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    res = M5Agent().step(state)
    assert res.transition is True
    # Composed per-chapter: one compose_chapter call per chapter, no monolith.
    assert fake_compose.invoke.call_count == 6
    assert set(res.context_patch["chapters"].keys()) == {
        "intro", "lit_review", "methodology", "results", "discussion", "conclusion",
    }
    assert "confirmed_at" in res.context_patch
    # export_artifacts populated with real upload results.
    keys = {a["s3_key"] for a in res.context_patch["export_artifacts"]}
    assert "projects/p/exports/thesis-real.docx" in keys
    assert "projects/p/exports/thesis-real.pdf" in keys
    assert fake_docx.invoke.called and fake_pdf.invoke.called
