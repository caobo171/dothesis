"""Per-module chapter ownership + composition.

The pivot: instead of M5 composing the whole thesis, each module owns and
composes its own chapter(s) as it completes, so the docx grows continuously.
No LLM — compose_all_sections is stubbed at its seam.
"""
import orchestrator.tools.m5_writing as M


def test_module_chapters_partition_the_canonical_order_exactly():
    # Every canonical chapter is owned by exactly one module, and no module
    # claims a chapter that isn't in the canonical order.
    owned = [c for names in M.MODULE_CHAPTERS.values() for c in names]
    assert sorted(owned) == sorted(M.M5_CHAPTER_ORDER)
    assert len(owned) == len(set(owned)), "a chapter is owned by two modules"


def test_m5_owns_the_single_conclusion_chapter():
    # Vietnamese quantitative theses end at Chapter 5; the discussion of
    # findings is written INSIDE that chapter, not as a chapter of its own.
    assert M.MODULE_CHAPTERS["M5"] == ["conclusion"]
    assert M.chapters_for_module("M1") == ["intro"]
    assert M.chapters_for_module("m4") == ["results"]  # case-insensitive
    assert M.chapters_for_module("nope") == []


def test_canonical_order_has_five_chapters_ending_at_conclusion():
    assert M.M5_CHAPTER_ORDER == [
        "intro", "lit_review", "methodology", "results", "conclusion"]
    assert "discussion" not in M.M5_CHAPTER_ORDER


def test_chapter_five_titles_say_conclusions_and_recommendations():
    assert M.M5_CHAPTER_TITLES["conclusion"] == "Chapter 5 — Conclusions and Recommendations"
    assert M.M5_CHAPTER_TITLES_VI["conclusion"] == "Chương 5 — Kết luận và Kiến nghị"
    # No title anywhere may still say "6".
    for mapping in (M.M5_CHAPTER_TITLES, M.M5_CHAPTER_TITLES_VI):
        assert not any("6" in t for t in mapping.values())


def test_module_for_chapter_reverse_lookup():
    assert M.module_for_chapter("intro") == "M1"
    assert M.module_for_chapter("conclusion") == "M5"
    assert M.module_for_chapter("unknown") is None


def test_legacy_discussion_prose_is_read_as_the_conclusion_chapter():
    # A project composed before the five-chapter collapse holds its final
    # chapter under `discussion`. Dropping it would delete written work.
    out = M.chapters_from_final_sections(
        [{"chapter_name": "discussion", "prose": "Legacy final chapter."}])
    assert out["conclusion"]["prose"] == "Legacy final chapter."
    assert "discussion" not in out


def test_conclusion_wins_when_a_slice_carries_both():
    out = M.chapters_from_final_sections([
        {"chapter_name": "discussion", "prose": "Old discussion."},
        {"chapter_name": "conclusion", "prose": "Real conclusion."},
    ])
    assert out["conclusion"]["prose"] == "Real conclusion."


def test_sections_from_m5_slice_aliases_legacy_discussion():
    out = M.sections_from_m5_slice(
        {"chapters": {"discussion": {"prose": "Legacy final chapter."}}})
    assert [s["chapter_name"] for s in out] == ["conclusion"]
    assert out[0]["title"] == "Chapter 5 — Conclusions and Recommendations"


def test_compose_module_chapters_shapes_and_filters(monkeypatch):
    # Stub composition: M5 owns [conclusion]; compose_all_sections returns it
    # plus a References section that must be filtered out.
    def fake_compose(cs, chapters=None):
        assert chapters == ["conclusion"]
        return [
            {"chapter_name": "conclusion", "title": "Ch5", "prose": "Conclusion prose."},
            {"title": "References", "prose": "[1] Smith 2024"},  # no chapter_name
        ]
    monkeypatch.setattr(M, "compose_all_sections", fake_compose)

    out = M.compose_module_chapters({"m1_topic": {}}, "M5")
    assert set(out) == {"conclusion"}
    assert out["conclusion"] == {"name": "conclusion", "prose": "Conclusion prose."}
    assert "References" not in out


def test_compose_module_chapters_skips_empty_prose(monkeypatch):
    monkeypatch.setattr(M, "compose_all_sections",
                        lambda cs, chapters=None: [{"chapter_name": "intro", "prose": "   "}])
    assert M.compose_module_chapters({}, "M1") == {}


def test_compose_module_chapters_fail_open(monkeypatch):
    def boom(cs, chapters=None):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(M, "compose_all_sections", boom)
    assert M.compose_module_chapters({}, "M2") == {}
    assert M.compose_module_chapters({}, "unknown_module") == {}
