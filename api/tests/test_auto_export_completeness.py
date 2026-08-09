"""The M5 auto-export hook must not ship a partial thesis.

The hook fires from the STORE layer when a commit flips M5 to done, and renders
exactly what final_sections holds — it cannot compose, and must not, because it
runs inside a commit where an LLM call has no business.

That was harmless while final_sections stayed empty until the composer filled
it. Once the import began preserving the student's chapters 4 and 5, the hook
fired holding two chapters and produced a 35KB "full thesis" with no
introduction, literature review or methodology. And because the export came from
here rather than the export_docx tool, no export_artifacts widget was ever
emitted, so the chat had no download card either — one cause, both symptoms.
"""
from app.agent_state import DbProjectStateStore as Store
from orchestrator.tools.m5_writing import (
    M5_CHAPTER_ORDER, M5_CHAPTER_TITLES, M5_CHAPTER_TITLES_VI,
)


def _sec(name, title=None):
    return {"chapter_name": name, "title": title or M5_CHAPTER_TITLES[name], "prose": "body"}


def test_preserved_chapters_alone_are_reported_incomplete():
    """Exactly the shape a fresh import leaves behind."""
    missing = Store._missing_chapters([_sec("results"), _sec("conclusion")])
    assert missing == ["intro", "lit_review", "methodology", "discussion"]


def test_a_whole_thesis_is_reported_complete():
    assert Store._missing_chapters([_sec(n) for n in M5_CHAPTER_ORDER]) == []


def test_sections_carrying_only_titles_still_match():
    """sections_from_m5_slice emits {title, prose} for the `chapters` shape —
    matching on chapter_name alone would call a complete thesis incomplete."""
    assert Store._missing_chapters(
        [{"title": M5_CHAPTER_TITLES[n], "prose": "b"} for n in M5_CHAPTER_ORDER]) == []


def test_vietnamese_titles_match_too():
    assert Store._missing_chapters(
        [{"title": M5_CHAPTER_TITLES_VI[n], "prose": "b"} for n in M5_CHAPTER_ORDER]) == []


def test_malformed_sections_fail_towards_skipping():
    """Garbage reports everything missing, so the hook skips rather than
    exporting nonsense. Skipping is always the recoverable direction here."""
    assert Store._missing_chapters([None, "x", 42]) == list(M5_CHAPTER_ORDER)


def test_hook_skips_the_export_when_chapters_are_missing(monkeypatch):
    """End-to-end through _auto_export_m5: nothing is rendered or persisted."""
    import app.agent_state as A
    import orchestrator.tools.m5_writing as M

    called = {}
    monkeypatch.setattr(M, "run_export",
                        lambda *a, **kw: called.setdefault("ran", True) or [])
    monkeypatch.setattr(M, "sections_from_m5_slice",
                        lambda slice_: [_sec("results"), _sec("conclusion")])

    class _CS:
        m5_writing = {"final_sections": [1, 2]}
        m2_literature = {}
        m1_topic = {"language": "en"}

    class _Sess:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, model, pid): return _CS()

    monkeypatch.setattr(A, "Session", _Sess, raising=False)
    monkeypatch.setattr("sqlalchemy.orm.Session", _Sess)

    store = Store.__new__(Store)
    store.engine = object()
    store.project_id = "p1"
    store._auto_export_m5()

    assert "ran" not in called, "a partial thesis was rendered and exported"
