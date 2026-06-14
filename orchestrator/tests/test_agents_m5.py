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


def test_m5_collect_references_falls_back_to_citation_list():
    """When gaps carry no supporting_papers (common in auto mode), references
    fall back to the M2 citation_list so chapters still cite the scout's finds."""
    agent = M5Agent()
    refs = agent._collect_references({
        "research_gaps": [],
        "citation_list": [
            {"authors": "Carolin et al.", "year": 2025, "title": "X"},
            {"author": "Bass", "year": 1985},
        ],
    })
    pairs = {(r.get("author"), str(r.get("year"))) for r in refs}
    assert ("Carolin et al.", "2025") in pairs
    assert ("Bass", "1985") in pairs


def test_m5_collect_references_handles_authors_as_list():
    """The engine scout emits citation_list entries with `authors: list[str]`
    (see engine/prompts/01_research/scout.md spec). Without normalizing, the
    dedupe key was (list, str) — tuple with an unhashable list — and `key
    not in seen` crashed with TypeError. Regression for the M5 compose-all
    crash on thread ab4198a1.
    """
    agent = M5Agent()
    refs = agent._collect_references({
        "research_gaps": [],
        "citation_list": [
            {"authors": ["John Smith", "Mary Johnson"], "year": 2024,
             "title": "Y"},
        ],
    })
    assert len(refs) == 1
    assert refs[0]["year"] == 2024
    assert isinstance(refs[0]["author"], str)
    # Joined author string keeps both names recognisable for downstream
    # citation rendering.
    assert "Smith" in refs[0]["author"]
    assert "Johnson" in refs[0]["author"]


def test_m5_collect_references_prefers_gap_papers_and_adds_citation_list():
    agent = M5Agent()
    refs = agent._collect_references({
        "research_gaps": [{"supporting_papers": [
            {"author": "Wang", "year": 2011, "page": 5, "title": "Leadership styles"}]}],
        "citation_list": [{"author": "Bass", "year": 1985, "title": "Leadership"}],
    })
    pairs = {(r.get("author"), str(r.get("year"))) for r in refs}
    assert ("Wang", "2011") in pairs    # titled gap paper preserved
    assert ("Bass", "1985") in pairs    # citation_list merged in


def test_m5_collect_references_drops_titleless_gap_papers():
    """Gap papers with no title (the common find_research_gaps shape) render as
    blank bibliography lines, so they're excluded from the reference pool."""
    agent = M5Agent()
    refs = agent._collect_references({
        "research_gaps": [{"supporting_papers": [{"author": "Wang", "year": 2011}]}],
        "citation_list": [{"author": "Bass", "year": 1985, "title": "Leadership"}],
    })
    pairs = {(r.get("author"), str(r.get("year"))) for r in refs}
    assert ("Wang", "2011") not in pairs   # title-less gap paper dropped
    assert ("Bass", "1985") in pairs       # titled citation_list entry kept


def test_m5_normalize_chapters_passthrough_dict():
    agent = M5Agent()
    d = {"intro": {"prose": "x"}}
    assert agent._normalize_chapters(d) == d


def test_m5_build_sections_survives_list_chapters():
    agent = M5Agent()
    sections = agent._build_sections_for_export(
        {"chapters": [{"title": "Chapter 1: Introduction", "prose": "hi"}]})
    # Sections use the renderer's {title, prose} contract — the old {name, text}
    # shape produced a blank docx because _sections_to_markdown reads title/prose.
    intro = next(s for s in sections if s["prose"] == "hi")
    assert intro["prose"] == "hi"
    assert intro["title"]  # localized chapter heading present, not the raw key


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

    # Auto export now goes through the shared citeproc path (run_export) so
    # citations/bibliography/tables render correctly — mock it at that level.
    fake_run_export = MagicMock(return_value=[
        {"kind": "docx", "s3_key": "projects/p/exports/thesis-real.docx",
         "size_bytes": 512, "download_url": "/api/v1/projects/p/exports/thesis-real.docx"},
        {"kind": "pdf", "s3_key": "projects/p/exports/thesis-real.pdf",
         "size_bytes": 1024, "download_url": "/api/v1/projects/p/exports/thesis-real.pdf"},
    ])
    monkeypatch.setattr(m5_mod, "run_export", fake_run_export)

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
    assert fake_run_export.called
