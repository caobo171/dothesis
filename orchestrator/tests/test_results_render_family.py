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
