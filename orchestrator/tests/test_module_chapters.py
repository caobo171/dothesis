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


def test_both_closing_chapters_are_concatenated_not_picked_between():
    # In the six-chapter era these were two DISTINCT written chapters:
    # `discussion` ran 1200-2000 words (5.1 summary → 5.6 future research) and
    # carried the limitations disclosure; `conclusion` was 500-800 words of
    # restatement + closing remarks. Picking a winner deletes a real chapter
    # either way, so Chapter 5 is discussion-then-conclusion, joined.
    out = M.chapters_from_final_sections([
        {"chapter_name": "discussion", "prose": "Old discussion."},
        {"chapter_name": "conclusion", "prose": "Real conclusion."},
    ])
    assert out["conclusion"]["prose"] == "Old discussion.\n\nReal conclusion."
    assert "discussion" not in out


def test_concatenation_order_does_not_depend_on_list_order():
    # `final_sections` order is not guaranteed; the discussion prose leads
    # because it carries the 5.1→5.6 flow, whichever way round it arrives.
    out = M.chapters_from_final_sections([
        {"chapter_name": "conclusion", "prose": "Real conclusion."},
        {"chapter_name": "discussion", "prose": "Old discussion."},
    ])
    assert out["conclusion"]["prose"] == "Old discussion.\n\nReal conclusion."


def test_sections_from_m5_slice_aliases_legacy_discussion():
    out = M.sections_from_m5_slice(
        {"chapters": {"discussion": {"prose": "Legacy final chapter."}}})
    assert [s["chapter_name"] for s in out] == ["conclusion"]
    assert out[0]["title"] == "Chapter 5 — Conclusions and Recommendations"


def test_sections_from_m5_slice_keeps_both_closing_chapters_and_the_dt_token():
    # The regression this guards: a legacy project with BOTH closing chapters
    # written exported a Chapter 5 that was only the short conclusion, losing
    # the longest chapter in the thesis AND its [[DT:limitations]] disclosure.
    out = M.sections_from_m5_slice({"chapters": {
        "intro": {"prose": "I"}, "lit_review": {"prose": "L"},
        "methodology": {"prose": "M"}, "results": {"prose": "R"},
        "discussion": {"prose": "DISC with [[DT:limitations]]"},
        "conclusion": {"prose": "CONC closing"},
    }})
    assert [s["chapter_name"] for s in out] == M.M5_CHAPTER_ORDER
    ch5 = out[-1]
    assert ch5["title"] == "Chapter 5 — Conclusions and Recommendations"
    assert ch5["prose"] == "DISC with [[DT:limitations]]\n\nCONC closing"
    assert "[[DT:limitations]]" in ch5["prose"]


def test_identical_closing_prose_is_not_duplicated():
    # Some legacy projects copied the same text into both keys (the two old
    # prompts overlapped heavily). Concatenating them verbatim would print the
    # chapter twice, so an exact-duplicate block is kept once.
    out = M.sections_from_m5_slice({"chapters": {
        "discussion": {"prose": "Same closing chapter."},
        "conclusion": {"prose": "Same closing chapter."},
    }})
    assert out[0]["prose"] == "Same closing chapter."


def test_retired_chapter_titles_still_resolve_to_the_canonical_chapter():
    # The agent path writes only `title`, so a pre-branch project's headings
    # are the ONLY handle on its prose. Unmapped meant dropped-whole.
    for title, prose in (
        ("Chapter 5 — Discussion", "d-en"),
        ("Chương 5 — Thảo luận", "d-vi"),
        ("Chapter 6 — Conclusion", "c-en"),
        ("Chương 6 — Kết luận", "c-vi"),
        ("Chapter 5 — Conclusion", "merged-en"),
        ("Chương 5 — Kết luận", "merged-vi"),
    ):
        out = M.chapters_from_final_sections([{"title": title, "prose": prose}])
        assert out.get("conclusion", {}).get("prose") == prose, title


def test_legacy_final_sections_export_five_sections_with_no_chapter_six():
    # The `final_sections` fallback used to pass titles through verbatim, so a
    # legacy slice still exported a literal "Chapter 6" heading. Sections are
    # re-titled from the canonical map; genuinely non-chapter sections (which
    # have no canonical identity) keep their own title.
    out = M.sections_from_m5_slice({"final_sections": [
        {"title": "Chapter 1 — Introduction", "prose": "I"},
        {"title": "Chapter 2 — Literature Review", "prose": "L"},
        {"title": "Chapter 3 — Methodology", "prose": "M"},
        {"title": "Chapter 4 — Results", "prose": "R"},
        {"title": "Chapter 5 — Discussion", "prose": "DISC"},
        {"title": "Chapter 6 — Conclusion", "prose": "CONC"},
        {"title": "References", "prose": "[1] Smith 2024"},
    ]})
    titles = [s["title"] for s in out]
    assert not any("Chapter 6" in t or "Chương 6" in t for t in titles)
    assert titles[-1] == "References"
    chapters = [s for s in out if s.get("chapter_name")]
    assert len(chapters) == 5
    assert chapters[-1]["title"] == "Chapter 5 — Conclusions and Recommendations"
    assert chapters[-1]["prose"] == "DISC\n\nCONC"


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
