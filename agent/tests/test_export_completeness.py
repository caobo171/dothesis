"""A full export must contain every chapter, not just the ones already stored.

Regression cover for a real export: a project whose import preserved the
student's chapters 4 and 5 into final_sections produced a 35KB .docx containing
ONLY those two — no introduction, no literature review, no methodology — while
the reply claimed the thesis was complete.

Before chapter preservation, final_sections was empty on that path, so
export_docx composed all six. Preserving two chapters is what exposed this:
whatever is already stored must be REUSED, and everything missing still has to
be written.
"""
import json

import pytest

import agent.tools.writing as W
from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER


_PRESERVED = [
    {"chapter_name": "results", "title": "Chapter 4: Research Results",
     "prose": "# Chapter 4\n\nThe imported results chapter.\n\n| A | B |\n|---|---|\n| 1 | 2 |"},
    {"chapter_name": "conclusion", "title": "Chapter 5: Conclusions",
     "prose": "# Chapter 5\n\nThe imported conclusion chapter."},
]


class _Store:
    project_id = "11111111-2222-3333-4444-555555555555"

    def load(self):
        return {"contextStore": {"final_sections": _PRESERVED, "language": "en"}}

    def load_full_context_store(self):
        return {
            "m1_topic": {"research_title": "T", "language": "en",
                         "research_questions": ["Q"], "objectives": ["O"]},
            "m2_literature": {"literature_sources": [], "research_gaps": [{"description": "g"}]},
            "m3_design": {"paradigm": "quantitative", "design": "regression", "tool": "SPSS"},
            "m4_analysis": {"analysis_results": {"hypothesis_tests": [{"id": "H1"}]}},
            "m5_writing": {"final_sections": _PRESERVED},
        }


@pytest.fixture
def captured(monkeypatch):
    """Capture the sections handed to the renderer; skip S3/pandoc entirely."""
    seen = {}

    def _fake_run_export(sections, project_id, **kw):
        seen["sections"] = sections
        return [{"kind": "docx", "url": "https://example/thesis.docx", "filename": "thesis.docx"},
                {"kind": "pdf", "url": "https://example/thesis.pdf", "filename": "thesis.pdf"}]

    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "run_export", _fake_run_export)
    monkeypatch.setattr(M, "compose_chapter",
                        type("C", (), {"invoke": staticmethod(
                            lambda p: {"prose": f"Composed {p['chapter_name']} body."})})())
    monkeypatch.setattr(M, "assess_export_readiness", lambda cs, chapters=None: [])
    return seen


def _export(store=None):
    tools = W.make_writing_tools(store or _Store())
    tool = next(t for t in tools if t.name == "export_docx")
    return json.loads(tool.invoke({"force": True}))


def test_export_includes_chapters_that_were_never_stored(captured):
    """The bug: only the two preserved chapters reached the document."""
    _export()
    titles = [s.get("title", "") for s in captured["sections"]]
    assert len(titles) >= len(M5_CHAPTER_ORDER), (
        f"exported {len(titles)} chapters, expected {len(M5_CHAPTER_ORDER)}: {titles}")


def test_export_reuses_the_preserved_chapters_verbatim(captured):
    """Composing over the student's own chapter is what loses their tables."""
    _export()
    joined = "\n".join(s.get("prose", "") for s in captured["sections"])
    assert "The imported results chapter." in joined
    assert "| A | B |" in joined            # their table survives
    assert "The imported conclusion chapter." in joined


def test_a_partial_full_export_is_refused_and_names_what_is_missing(monkeypatch, captured):
    """The silent failure: composition under-delivers and the file ships anyway.

    Every path into composition is best-effort — an unreadable full_cs, a short
    return — and each one fell through to rendering whatever `sections` held. A
    real export went out as a 35KB file with only the two imported chapters
    while the reply said the thesis was complete.
    """
    import orchestrator.tools.m5_writing as M
    # Composition yields nothing new, so only the preserved two survive.
    monkeypatch.setattr(M, "compose_all_sections",
                        lambda cs: [{"chapter_name": s["chapter_name"],
                                     "title": s["title"], "prose": s["prose"]}
                                    for s in _PRESERVED])
    out = _export_no_force()
    assert out["error"] == "incomplete_export"
    assert set(out["missing_chapters"]) >= {"intro", "lit_review", "methodology"}
    assert "sections" not in captured        # nothing was rendered


def test_force_still_allows_an_intentional_partial_export(monkeypatch, captured):
    import orchestrator.tools.m5_writing as M
    monkeypatch.setattr(M, "compose_all_sections",
                        lambda cs: [{"chapter_name": s["chapter_name"],
                                     "title": s["title"], "prose": s["prose"]}
                                    for s in _PRESERVED])
    out = _export()                          # force=True
    assert out.get("error") is None
    assert len(captured["sections"]) == 2


def _export_no_force(store=None):
    tools = W.make_writing_tools(store or _Store())
    tool = next(t for t in tools if t.name == "export_docx")
    return json.loads(tool.invoke({}))


def test_chapter_scope_exports_only_the_named_committed_chapter(captured):
    tools = W.make_writing_tools(_Store())
    tool = next(t for t in tools if t.name == "export_docx")
    # The compact fixture prose is intentionally below the production
    # anti-placeholder threshold; force isolates scope selection here.
    out = json.loads(tool.invoke({"scope": "chapter:results", "force": True}))

    assert out["ok"] is True
    assert out["scope"] == "chapter:results"
    assert [section["chapter_name"] for section in captured["sections"]] == ["results"]


def test_chapter_scope_refuses_a_chapter_that_was_not_written(captured):
    tools = W.make_writing_tools(_Store())
    tool = next(t for t in tools if t.name == "export_docx")
    # "discussion" stays accepted as user input — it resolves to the
    # canonical "conclusion" key, the chapter that now holds that material.
    out = json.loads(tool.invoke({"scope": "chapter:discussion"}))

    assert out["error"] == "needs_data"
    assert out["missing_chapters"] == ["conclusion"]
    assert "sections" not in captured


def test_chapter_scope_composes_requested_chapter_from_upstream_state(monkeypatch, captured):
    import orchestrator.tools.m5_writing as M
    prose = "A complete grounded discussion paragraph. " * 8
    monkeypatch.setattr(M, "compose_all_sections", lambda cs, chapters=None: [
        {"chapter_name": "conclusion", "title": "Conclusion", "prose": prose}
    ])
    monkeypatch.setattr(M, "assess_export_readiness", lambda cs, chapters=None: [])
    store = _Store()
    store.commit_slice = lambda *args, **kwargs: {"ok": True}
    tools = W.make_writing_tools(store)
    tool = next(t for t in tools if t.name == "export_docx")
    # Student types the legacy word "discussion"; it must still resolve to
    # the one chapter ("conclusion") that carries that content post-collapse.
    out = json.loads(tool.invoke({"scope": "chapter:discussion"}))

    assert out["ok"] is True
    assert out["scope"] == "chapter:conclusion"
    assert [section["chapter_name"] for section in captured["sections"]] == ["conclusion"]


def test_export_backfills_recoverable_legacy_m3_through_commit_slice():
    from agent.tools.writing import _backfill_legacy_m3_for_export

    class Store:
        calls = []

        def commit_slice(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            return {"module": "M3"}

    store = Store()
    prose = "Regression model: Intention = β₀ + β₁·PB + β₂·PD + β₃·PDT + ε."
    updated, report = _backfill_legacy_m3_for_export(
        store, {"m3_design": {"conceptual_model": prose, "methodology": "survey"}}
    )

    assert report == {"module": "M3", "nodes": 4, "edges": 3,
                      "commit": {"module": "M3"}}
    assert len(store.calls) == 1
    writes = store.calls[0][0][1]
    assert writes["conceptual_model"] == updated["m3_design"]["conceptual_model"]
    assert updated["m3_design"]["methodology"] == "survey"


def test_export_does_not_backfill_unstructured_prose_model():
    from agent.tools.writing import _backfill_legacy_m3_for_export

    class Store:
        def commit_slice(self, *args, **kwargs):
            raise AssertionError("unrecoverable prose must not be committed")

    original = {"m3_design": {"conceptual_model": "general discussion"}}
    updated, report = _backfill_legacy_m3_for_export(Store(), original)
    assert updated is original
    assert report is None
