"""Per-module chapter ownership + composition.

The pivot: instead of M5 composing the whole thesis, each module owns and
composes its own chapter(s) as it completes, so the docx grows continuously.
No LLM — compose_all_sections is stubbed at its seam.
"""
import orchestrator.tools.m5_writing as M

# Long enough for detect_language to read (it declines under 24 letters) and
# unambiguous in both directions.
VI_PROSE = ("Nghiên cứu này phân tích ảnh hưởng của chất lượng dịch vụ đến sự "
            "hài lòng của khách hàng tại các ngân hàng thương mại.")
EN_PROSE = ("This study analyses how service quality influences customer "
            "satisfaction across commercial retail banks.")


def _chapters_slice(prose: str) -> dict:
    return {"chapters": {n: {"prose": f"{prose} [{n}]"} for n in M.M5_CHAPTER_ORDER}}


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


def test_an_imported_thesis_keeps_its_own_headings_but_not_its_cover_page():
    # api/app/import_work.py stores `title = head.splitlines()[0]` — the first
    # line of the uploaded document, which on a Vietnamese thesis is the cover
    # page, not a chapter heading. Preserving every non-retired stored title
    # shipped the university's name as the Chapter 4 heading. Only a title that
    # looks like a heading (numbered "Chương"/"Chapter" prefix) is the
    # student's own; anything else falls back to the canonical title in the
    # language resolved from the prose.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "results", "title": "TRƯỜNG ĐẠI HỌC KINH TẾ TP.HCM",
         "source": "import", "prose": VI_PROSE},
        {"chapter_name": "conclusion", "title": "CHƯƠNG 5: KẾT LUẬN VÀ KIẾN NGHỊ",
         "source": "import", "prose": VI_PROSE},
    ]})
    assert [s["title"] for s in out] == [
        "Chương 4 — Kết quả", "CHƯƠNG 5: KẾT LUẬN VÀ KIẾN NGHỊ"]
    assert [s["chapter_name"] for s in out] == ["results", "conclusion"]


def test_a_cover_page_line_never_becomes_a_chapter_heading():
    # The headline bug, isolated: one imported section whose stored title is a
    # cover-page line exports the canonical Vietnamese heading instead.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "results", "title": "TRƯỜNG ĐẠI HỌC KINH TẾ TP.HCM",
         "source": "import", "prose": VI_PROSE}]})
    assert [s["title"] for s in out] == ["Chương 4 — Kết quả"]


def test_an_english_numbered_heading_is_preserved_verbatim():
    # The number prefix is the discriminator in either language.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "results", "title": "Chapter 4 — Results and Discussion",
         "source": "import", "prose": EN_PROSE}]})
    assert out[0]["title"] == "Chapter 4 — Results and Discussion"


def test_a_heading_with_no_number_prefix_falls_back_to_the_canonical_title():
    # The accepted tradeoff, pinned: a real heading written without the word
    # "Chương"/"Chapter" reads exactly like a cover-page line to this test, so
    # it is replaced. Deliberate — nothing separates the two cases (the cover
    # line is all-caps and short too), and a correct canonical heading beats
    # shipping "TRƯỜNG ĐẠI HỌC …" as Chapter 4.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "conclusion", "title": "KẾT LUẬN VÀ KIẾN NGHỊ",
         "source": "import", "prose": VI_PROSE}]})
    assert out[0]["title"] == "Chương 5 — Kết luận và Kiến nghị"


def test_a_section_with_no_title_still_gets_the_canonical_one():
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "methodology", "prose": "M"}]})
    assert out[0]["title"] == "Chapter 3 — Methodology"


def test_a_sixth_chapter_heading_is_retired_even_when_it_is_not_in_the_title_map():
    # The finding-4 guarantee cannot depend on the legacy title map listing
    # every wording a six-chapter thesis used: a heading that numbers itself
    # past the canonical order is retired by definition.
    # The prose, not the "Chương" prefix, is what makes the replacement heading
    # Vietnamese now — a one-letter placeholder tells detect_language nothing,
    # and a heading language guessed off a stored title is the bug this file's
    # newer tests cover.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "conclusion",
         "title": "Chương 6 — Kết luận và Kiến nghị", "prose": VI_PROSE}]})
    assert out[0]["title"] == "Chương 5 — Kết luận và Kiến nghị"


def test_a_merged_closing_chapter_cannot_keep_either_halfs_heading():
    # Two legacy sections fold into one Chapter 5, so neither half's heading
    # describes the result — the canonical title is the only honest one.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "discussion", "title": "Chương 5 — Thảo luận kết quả",
         "prose": f"DISC. {VI_PROSE}"},
        {"chapter_name": "conclusion", "title": "Chương 6 — Kết luận",
         "prose": f"CONC. {VI_PROSE}"},
    ]})
    assert [s["title"] for s in out] == ["Chương 5 — Kết luận và Kiến nghị"]
    assert out[0]["prose"] == f"DISC. {VI_PROSE}\n\nCONC. {VI_PROSE}"


# --- chapter-heading language ------------------------------------------------
# The headings must be in the language of the prose underneath them. This used
# to be decided two different ways on the same product: compose_export read the
# project's `language`, while sections_from_m5_slice hardcoded English for the
# `chapters` shape and guessed from a "Chương" title prefix for final_sections.
# Now ONE resolver reads the student's own prose, with the caller's language as
# the fallback for prose too short to judge.


def test_vietnamese_prose_gets_vietnamese_headings_with_no_language_argument():
    # The headline bug: a Vietnamese thesis exported "Chapter 1 — Introduction"
    # on the three paths that go through here.
    out = M.sections_from_m5_slice(_chapters_slice(VI_PROSE))
    assert [s["title"] for s in out] == [
        M.M5_CHAPTER_TITLES_VI[n] for n in M.M5_CHAPTER_ORDER]
    assert out[0]["title"] == "Chương 1 — Giới thiệu"
    assert out[-1]["title"] == "Chương 5 — Kết luận và Kiến nghị"


def test_english_prose_gets_english_headings_with_no_language_argument():
    out = M.sections_from_m5_slice(_chapters_slice(EN_PROSE))
    assert [s["title"] for s in out] == [
        M.M5_CHAPTER_TITLES[n] for n in M.M5_CHAPTER_ORDER]


def test_prose_overrides_a_stored_language_that_disagrees_with_it():
    # Content wins: `m1_topic.language` can be stale or simply wrong, and a
    # heading that contradicts the chapter under it is the defect being fixed.
    out = M.sections_from_m5_slice(_chapters_slice(VI_PROSE), language="en")
    assert out[0]["title"] == "Chương 1 — Giới thiệu"


def test_prose_too_short_to_read_falls_back_to_the_callers_language():
    # detect_language declines below 24 letters rather than guessing wrong.
    out = M.sections_from_m5_slice({"chapters": {"intro": {"prose": "x"}}},
                                   language="vi")
    assert out[0]["title"] == "Chương 1 — Giới thiệu"


def test_no_prose_and_no_language_stays_english():
    # The genuine no-information case keeps today's behaviour, so a bare caller
    # cannot silently flip language. No real call site lands here — all three
    # pass a language, and each of those defaults to "vi".
    out = M.sections_from_m5_slice({"chapters": {"intro": {"prose": "x"}}})
    assert out[0]["title"] == "Chapter 1 — Introduction"


def test_an_imported_vietnamese_thesis_gets_vietnamese_canonical_headings():
    # The case the deleted "^chương" heuristic got wrong. api/app/import_work.py
    # stores `title = head.splitlines()[0]` — a cover-page line, not a chapter
    # heading — so inferring the language from the title read a Vietnamese
    # thesis as English. The prose says otherwise.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "results", "title": "TRƯỜNG ĐẠI HỌC KINH TẾ TP.HCM",
         "source": "import", "prose": VI_PROSE},
        # Two sections fold into Chapter 5, so neither heading survives and the
        # canonical title has to be chosen — in Vietnamese.
        {"chapter_name": "discussion", "title": "TRƯỜNG ĐẠI HỌC KINH TẾ TP.HCM",
         "source": "import", "prose": VI_PROSE},
        {"chapter_name": "conclusion", "title": "TRƯỜNG ĐẠI HỌC KINH TẾ TP.HCM",
         "source": "import", "prose": VI_PROSE},
    ]})
    assert out[-1]["title"] == "Chương 5 — Kết luận và Kiến nghị"


def test_a_sections_own_heading_still_wins_over_the_resolved_language():
    # Regression guard on the own_title path: resolving the language changes
    # only the CANONICAL fallback, never a real stored heading.
    out = M.sections_from_m5_slice({"final_sections": [
        {"chapter_name": "results", "title": "Chapter 4 — What We Found",
         "prose": VI_PROSE}]})
    assert out[0]["title"] == "Chapter 4 — What We Found"


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
