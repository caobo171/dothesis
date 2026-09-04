"""A study gets the tables it actually computed, not the richest set we can draw.

Rendered against a real SPSS multiple-regression thesis, the Chapter 4 tables
came out as PLS-SEM: a measurement model with CR and AVE columns (metrics the
study never computed), an f² column, and a caption promising "R² / Q²" over a
table with no Q². Four of six columns in the first table were em-dashes.

Two causes. detect_family's only caller never passes `methodology`, so every
branch keyed on it was dead and anything with a measurement_model fell through
to pls_sem — while the software the student used was sitting in the results the
function already had, as structural_model.tool. And the column lists are fixed,
so a study without a statistic got a column of dashes asserting the statistic
exists and is unknown.
"""
from orchestrator.tools.results_render import (
    _section_chapter, detect_family, ensure_rendered, render_results_tables,
)


# Exactly the shape _infer_analysis_results produces from an SPSS thesis.
_SPSS = {
    "descriptives": {"n": 303},
    "structural_model": {"r2": {"PB": 0.716}, "tool": "SPSS",
                         "method": "hồi quy tuyến tính đa biến theo phương pháp Enter"},
    "measurement_model": [{"construct": "AT", "cronbach_alpha": 0.837},
                          {"construct": "TR", "cronbach_alpha": 0.86}],
    "hypothesis_tests": [
        {"id": "H1", "path": "ATT → PB", "decision": "supported",
         "numbers": {"beta": 0.371, "t": 11.921, "p": "0.000"}}],
}
_PLS = {
    "structural_model": {"r2": {"PB": 0.61}, "q2": {"PB": 0.34}, "tool": "SmartPLS 4"},
    "measurement_model": [{"construct": "AT", "cronbach_alpha": 0.84,
                           "composite_reliability": 0.89, "ave": 0.62,
                           "items": [{"item": "AT1", "loading": 0.81}]}],
    "hypothesis_tests": [{"id": "H1", "path": "AT → PB", "decision": "supported",
                          "numbers": {"beta": 0.4, "t": 5.1, "p": "0.000", "f2": 0.18}}],
}


def _md(ar, kind, language="en"):
    return next((b["markdown"] for b in render_results_tables(ar, language)
                 if b["kind"] == kind), "")


# --- family -------------------------------------------------------------------

def test_spss_is_not_pls_sem():
    assert detect_family(_SPSS) == "regression"


def test_smartpls_still_is():
    assert detect_family(_PLS) == "pls_sem"


def test_the_tool_is_read_off_the_results_not_only_the_argument():
    """The only caller passes no methodology; the evidence has to come from the
    data or the branch is dead code."""
    assert detect_family(_SPSS, methodology=None) == "regression"


def test_a_measurement_model_with_no_tool_named_keeps_the_old_default():
    """Additive change: absent an explicit tool, behaviour is unchanged."""
    assert detect_family({"measurement_model": [{"construct": "A", "ave": 0.5}]}) == "pls_sem"


# --- columns ------------------------------------------------------------------

def test_an_spss_reliability_table_has_no_cr_or_ave_column():
    md = _md(_SPSS, "measurement_model")
    assert "0.837" in md
    for absent in ("CR", "AVE", "Loading", "Item"):
        assert f"| {absent} " not in md, f"{absent} column rendered for a study without it"


def test_an_spss_reliability_table_is_not_captioned_convergent_validity():
    assert "Scale reliability" in _md(_SPSS, "measurement_model")
    assert "convergent validity" not in _md(_SPSS, "measurement_model")


def test_a_pls_measurement_table_keeps_every_column():
    md = _md(_PLS, "measurement_model")
    for present in ("CR", "AVE", "Loading", "Item"):
        assert f"| {present} " in md or f" {present} |" in md
    assert "convergent validity" in md


def test_no_f2_column_when_nothing_reports_f2():
    assert "f²" not in _md(_SPSS, "structural_paths")
    assert "f²" in _md(_PLS, "structural_paths")


def test_the_caption_does_not_promise_a_q2_that_is_absent():
    assert "R² / Q²" not in _md(_SPSS, "r2_q2")
    assert "R²" in _md(_SPSS, "r2_q2")
    assert "R² / Q²" in _md(_PLS, "r2_q2")


def test_the_numbers_themselves_are_untouched():
    md = _md(_SPSS, "structural_paths")
    for n in ("0.371", "11.921", "0.000"):
        assert n in md


# --- which sections the export-time net covers --------------------------------

def test_a_vietnamese_chapter_is_recognised():
    """The title map was English-only, so the net never fired on a Vietnamese
    thesis — which is the whole market."""
    assert _section_chapter({"title": "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU"}) == "results"
    assert _section_chapter({"title": "CHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN NGHỊ"}) == "conclusion"
    assert _section_chapter({"title": "CHƯƠNG 3: PHƯƠNG PHÁP NGHIÊN CỨU"}) == "methodology"


def test_the_canonical_name_beats_the_title():
    assert _section_chapter({"chapter_name": "results", "title": "Chương bốn"}) == "results"


def test_a_discussion_titled_chapter_routes_to_conclusion_not_results():
    """A closing-chapter title containing BOTH a "results" needle and a
    "conclusion" needle (thao luan ket qua = "discussion of results") must not
    mis-route to Results just because the results needle happens to sit
    earlier in an unordered NEEDLE list — conclusion is the real chapter this
    prose belongs to since the five-chapter collapse."""
    assert _section_chapter({"title": "Chương 5: Thảo luận kết quả nghiên cứu"}) == "conclusion"
    assert _section_chapter({"title": "Chapter 5 — Results Discussion"}) == "conclusion"


def test_an_imported_chapter_is_left_alone():
    """It already carries the student's own tables; ours would be duplicates."""
    sec = {"chapter_name": "results", "title": "CHƯƠNG 4: KẾT QUẢ", "source": "import",
           "prose": "| A | B |\n|---|---|\n| 1 | 2 |"}
    out = ensure_rendered([dict(sec)], {"m4_analysis": {"analysis_results": _SPSS}}, "vi")
    assert out[0]["prose"] == sec["prose"]


def test_a_composed_vietnamese_chapter_is_covered():
    out = ensure_rendered(
        [{"chapter_name": "results", "title": "CHƯƠNG 4: KẾT QUẢ", "prose": "Phân tích."}],
        {"m4_analysis": {"analysis_results": _SPSS}}, "vi")
    assert out[0]["prose"].count("dt-rendered:begin") == 3


def test_weave_removes_internal_token_when_source_block_is_unavailable():
    from orchestrator.tools.results_render import weave

    prose = "Giới thiệu.\n\n[[DT:data_cleaning]]\n\nKết thúc."
    out = weave(prose, [])
    assert "[[DT:" not in out
    assert "Giới thiệu" in out and "Kết thúc" in out


# --- table numbering ----------------------------------------------------------
#
# The captions carried hardcoded numbers ("Bảng 4.1", "Bảng 4.3"). Woven into a
# chapter the student wrote — one that already runs to Bảng 4.14 — the document
# ended up with two Bảng 4.1, which is the kind of thing a supervisor sends back
# over.

from orchestrator.tools.results_render import next_table_number  # noqa: E402


_HOST = ("Bảng 4.1: Đặc điểm mẫu khảo sát\n\n| a | b |\n\n"
         "Bảng 4.9: Kết quả EFA\n\nBảng 4.14: Ma trận tương quan\n")


def test_the_next_number_continues_the_chapter():
    assert next_table_number(_HOST, "4.1") == "4.15"


def test_a_chapter_with_no_tables_keeps_the_default():
    assert next_table_number("Chương này trình bày kết quả.", "4.1") == "4.1"
    assert next_table_number("", "4.1") == "4.1"
    assert next_table_number(None, "4.1") == "4.1"


def test_english_captions_are_read_too():
    assert next_table_number("Table 3.2 — Screening\nTable 3.7 — Something", "3.1") == "3.8"


def test_the_highest_chapter_wins_over_a_stray_cross_reference():
    """A results chapter that cites "Bảng 3.2" from the methodology must still
    number its own tables in chapter 4."""
    assert next_table_number("as shown in Bảng 3.2\nBảng 4.6: Hồi quy", "4.1") == "4.7"


def test_rendered_captions_continue_the_host_chapter():
    nums = [b["markdown"].split("**")[1].split(" — ")[0] for b in
            render_results_tables(_SPSS, "vi", host_prose=_HOST)]
    assert nums == ["Bảng 4.15", "Bảng 4.16", "Bảng 4.17"]


def test_a_block_that_renders_nothing_does_not_burn_a_number():
    """Several builders return None for a study without that data; consuming a
    number for one would leave a hole in the chapter's sequence."""
    nums = [b["markdown"].split("**")[1].split(" — ")[0] for b in
            render_results_tables(_SPSS, "vi", host_prose="Bảng 4.2: X")]
    assert nums == ["Bảng 4.3", "Bảng 4.4", "Bảng 4.5"]


def test_without_a_host_the_fixed_numbers_are_unchanged():
    """A chapter we composed ourselves has no sequence to continue."""
    md = _md(_SPSS, "structural_paths", "vi")
    assert "Bảng 4.3 — " in md
