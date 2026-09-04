"""The auto-export hook renders whatever chapters are written so far.

Pivot (continuous per-module writing): the thesis is composed chapter by chapter
as each module M1→M5 completes, so a PARTIAL docx (e.g. Chapters 1–4 while
Chapter 5's Conclusion is still to come) is a first-class, expected state — the
hook renders it rather than waiting for all five chapters. `_missing_chapters`
is retained for logging/UX ("still to draft: …"), not as an export gate. The
only skip left is when there is no drafted prose at all (nothing to render).
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
    # Five-chapter collapse: "discussion" is retired as a canonical name, its
    # content lives inside "conclusion", so it no longer appears as missing.
    assert missing == ["intro", "lit_review", "methodology"]


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


def test_auto_export_emits_five_chapters_and_no_chapter_six():
    # This path never called the merge, so before the collapse it shipped a
    # Chapter 6 while the interactive export shipped five.
    from orchestrator.tools.m5_writing import sections_from_m5_slice
    slice_ = {"chapters": {n: {"prose": f"{n} prose"} for n in
                           ("intro", "lit_review", "methodology", "results", "conclusion")}}
    sections = sections_from_m5_slice(slice_)
    assert len(sections) == 5
    assert sections[-1]["title"] == "Chapter 5 — Conclusions and Recommendations"
    assert not any("Chapter 6" in s["title"] for s in sections)


def test_malformed_sections_fail_towards_skipping():
    """Garbage reports everything missing, so the hook skips rather than
    exporting nonsense. Skipping is always the recoverable direction here."""
    assert Store._missing_chapters([None, "x", 42]) == list(M5_CHAPTER_ORDER)


def test_hook_renders_a_partial_thesis(monkeypatch):
    """Pivot: a partial draft (only results + conclusion) IS now rendered —
    continuous per-module writing means the docx reflects whatever exists."""
    import app.agent_state as A
    import orchestrator.tools.m5_writing as M

    called = {}
    monkeypatch.setattr(M, "run_export",
                        lambda *a, **kw: called.setdefault("ran", True) or ["docx", "pdf"])
    monkeypatch.setattr(M, "sections_from_m5_slice",
                        lambda slice_: [_sec("results"), _sec("conclusion")])
    monkeypatch.setattr(M, "m2_references", lambda *_a, **_k: [])
    monkeypatch.setattr(Store, "persist_export_artifacts", lambda self, arts: None)

    class _CS:
        m5_writing = {"final_sections": [1, 2]}
        m2_literature = {}
        m1_topic = {"language": "en"}

    class _Sess:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, model, pid): return _CS()

    monkeypatch.setattr(A, "Session", _Sess, raising=False)
    monkeypatch.setattr("sqlalchemy.orm.Session", _Sess)

    store = Store.__new__(Store)
    store.engine = object()
    store.project_id = "p1"
    store._auto_export_m5()

    assert called.get("ran"), "a partial thesis should now be rendered and exported"


def test_hook_skips_when_no_prose_at_all(monkeypatch):
    """The only remaining skip: nothing drafted anywhere → no empty document."""
    import app.agent_state as A
    import orchestrator.tools.m5_writing as M

    called = {}
    monkeypatch.setattr(M, "run_export",
                        lambda *a, **kw: called.setdefault("ran", True) or [])
    monkeypatch.setattr(M, "sections_from_m5_slice", lambda slice_: [])
    monkeypatch.setattr(M, "m2_references", lambda *_a, **_k: [])

    class _CS:
        m5_writing = {}
        m2_literature = {}
        m1_topic = {"language": "en"}

    class _Sess:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, model, pid): return _CS()

    monkeypatch.setattr(A, "Session", _Sess, raising=False)
    monkeypatch.setattr("sqlalchemy.orm.Session", _Sess)

    store = Store.__new__(Store)
    store.engine = object()
    store.project_id = "p1"
    store._auto_export_m5()

    assert "ran" not in called, "nothing to render → must skip"


def test_auto_compose_module_merges_only_its_chapters(monkeypatch):
    """_auto_compose_module writes the completed module's chapter(s) into
    m5_writing.chapters WITHOUT clobbering chapters owned by other modules."""
    import app.agent_state as A
    import orchestrator.tools.m5_writing as M

    # M3 owns methodology; stub its composition.
    monkeypatch.setattr(
        M, "compose_module_chapters",
        lambda nested, module: {"methodology": {"name": "methodology", "prose": "Method prose."}},
    )

    committed = {}

    class _CS:
        def __init__(self):
            # An intro chapter already written by M1 must survive the M3 compose.
            self.m5_writing = {"chapters": {"intro": {"name": "intro", "prose": "Intro."}}}
            self.m1_topic = {}
            self.m2_literature = {}
            self.m3_design = {}
            self.m4_analysis = {}

    cs = _CS()

    class _Sess:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def get(self, model, pid): return cs
        def commit(self): committed["done"] = True

    monkeypatch.setattr(A, "Session", _Sess, raising=False)
    monkeypatch.setattr("sqlalchemy.orm.Session", _Sess)
    monkeypatch.setattr("sqlalchemy.orm.attributes.flag_modified", lambda *a, **k: None)

    store = Store.__new__(Store)
    store.engine = object()
    store.project_id = "p1"
    store._auto_compose_module("M3")

    chapters = cs.m5_writing["chapters"]
    assert chapters["intro"]["prose"] == "Intro.", "M1's chapter must be preserved"
    assert chapters["methodology"]["prose"] == "Method prose.", "M3's chapter must be written"
    assert committed.get("done")
