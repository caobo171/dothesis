"""The parser runs against the REAL sidecar that exposed the bug.

`_Result.docx` was uploaded to project 500319a8 at 06:07 UTC on 2026-09-15 and
extracted successfully: 13,634 bytes, 125 pipe rows, 102 of them carrying
coefficients. `m4_analysis.results` stayed `{}` for the rest of the thread.
Parsing a synthetic fixture would prove nothing about that.
"""
from pathlib import Path

import pytest

from orchestrator.doctor import parse_results_tables

FIXTURE = Path(__file__).parent / "fixtures" / "result_docx_sidecar.txt"


@pytest.fixture
def sidecar() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_returns_one_dict_keyed_by_table(sidecar):
    out = parse_results_tables(sidecar)
    assert isinstance(out, dict), "results is ONE dict keyed by table, never a list"
    assert out, "the real file has 102 coefficient rows — parsing none is a bug"


def test_outer_loadings_carry_the_real_numbers(sidecar):
    out = parse_results_tables(sidecar)
    flat = [row for rows in out.values() for row in rows]
    att1 = [r for r in flat if r.get("label") == "ATT_1"]
    assert att1, f"ATT_1 missing; tables found: {list(out)}"
    assert 0.854 in att1[0]["values"]


def test_the_six_canonical_tables_are_named(sidecar):
    """The document's seven headings collapse to six canonical tables.

    Getting here took three fixes the fixture found and a synthetic file
    would not have: captions filed every table under `[Hình N]`; the header
    and `| :--- |` rows made the parser recompute the heading from an emptied
    buffer and file all 102 rows under `untitled`; and the note under
    OUTER LOADINGS ("…đạt yêu cầu về độ tin cậy…") out-matched the heading
    itself, filing loadings under reliability.
    """
    out = parse_results_tables(sidecar)
    assert {"outer_loadings", "reliability", "discriminant_validity",
            "collinearity", "explained_variance", "path_coefficients"} <= set(out)


def test_outer_loadings_are_not_filed_under_reliability(sidecar):
    out = parse_results_tables(sidecar)
    labels = {r["label"] for r in out.get("reliability", [])}
    assert "ATT_1" not in labels, "an item loading landed in the reliability table"
    assert "ATT_1" in {r["label"] for r in out["outer_loadings"]}


def test_a_continuation_table_keeps_the_previous_heading(sidecar):
    # Outer loadings span two images; the second has no heading of its own.
    out = parse_results_tables(sidecar)
    labels = {r["label"] for r in out["outer_loadings"]}
    assert {"ATT_1", "INSP_1"} <= labels, "the second loadings page was orphaned"


def test_every_coefficient_row_is_accounted_for_once(sidecar):
    """All the rows, each exactly once.

    102 lines carry a decimal with 2+ places; one of them is a duplicate. A wide
    matrix is exported as several overlapping screenshots and the overlap column
    repeats a row verbatim — here INSP_1 — which counted as six INSP items
    against a five-item scale and read as a questionnaire/results mismatch that
    did not exist. Dropping rows silently is the opposite failure, so the count
    is pinned from both ends.
    """
    import re
    lines = [l for l in sidecar.splitlines()
             if l.strip().startswith("|") and re.search(r"-?\d+\.\d{2,}", l)]
    assert len(lines) == 102
    got = sum(len(rows) for rows in parse_results_tables(sidecar).values())
    assert got == 101, f"expected 102 rows minus 1 duplicate, parsed {got}"


def test_each_construct_has_the_five_items_the_questionnaire_asked(sidecar):
    from collections import Counter
    per = Counter(r["label"].split("_")[0]
                  for rows in parse_results_tables(sidecar).values()
                  for r in rows if "_" in r["label"])
    assert set(per) == {"ATT", "DEC", "ECONN", "EXP", "INSP", "INT", "SIMI", "TRUST"}
    assert all(n == 5 for n in per.values()), dict(per)


def test_a_sidecar_with_no_coefficient_table_yields_nothing():
    # A partial parse is worse than none: it reads as a finished analysis.
    assert parse_results_tables("Chương 1\n\nKhông có bảng số liệu nào ở đây.") == {}
    assert parse_results_tables("") == {}


def test_integers_alone_are_not_results():
    # Item counts and sample sizes are not coefficients.
    assert parse_results_tables("Mẫu\n| n | 303 |\n| items | 45 |\n") == {}


def test_an_unrecognised_heading_keeps_its_own_text_as_the_key():
    raw = ("Bảng lạ không ai biết\n"
           "| X_1 | 0.911 |\n"
           "| X_2 | 0.902 |\n")
    out = parse_results_tables(raw)
    assert out, "an unknown heading must not drop the table"
    assert any("lạ" in k for k in out), f"heading text not preserved: {list(out)}"


def test_htmt_is_not_filed_under_reliability():
    # "HTMT" blocks often mention AVE in the same heading; specific wins.
    out = parse_results_tables("HTMT và AVE\n| ATT | 0.81 |\n")
    assert "discriminant_validity" in out, list(out)


# --- source figures ---------------------------------------------------------

def test_the_students_own_screenshots_are_mapped_to_figure_kinds(sidecar):
    """results_render prefers the screenshot over any table we can build —
    "a SmartPLS screenshot is visibly output from the software, and a
    supervisor reads that as evidence in a way retyped numbers are not". The
    mechanism already existed; nothing populated it, so twelve extracted images
    sat unreferenced while every export rendered retyped tables."""
    from orchestrator.doctor import parse_source_figures
    figs = parse_source_figures(sidecar)
    assert figs["measurement_model"] == "uploads/_Result.docx.img/hinh-02.png"
    assert figs["discriminant_validity"] == "uploads/_Result.docx.img/hinh-05.png"
    assert figs["structural_paths"] == "uploads/_Result.docx.img/hinh-09.png"
    assert figs["r2_q2"] == "uploads/_Result.docx.img/hinh-07.png"


def test_a_caption_is_never_mistaken_for_a_heading(sidecar):
    # The caption sits between the heading and its table. Reading it as the
    # heading is what once keyed all ten tables to "[Hình N]".
    from orchestrator.doctor import parse_source_figures
    assert all(not v.startswith("[") for v in parse_source_figures(sidecar).values())


def test_the_first_screenshot_of_a_split_table_wins():
    # A wide matrix is exported as several overlapping screenshots; the table
    # should be represented by its first page, not its continuation.
    from orchestrator.doctor import parse_source_figures
    raw = ("OUTER LOADINGS\n[Hình 2] (ảnh gốc: uploads/a.img/hinh-02.png)\n"
           "| ATT_1 | 0.854 |\n"
           "tiếp theo\n[Hình 3] (ảnh gốc: uploads/a.img/hinh-03.png)\n"
           "| INSP_1 | 0.835 |\n")
    assert parse_source_figures(raw)["measurement_model"] == "uploads/a.img/hinh-02.png"


def test_a_document_with_no_images_maps_nothing():
    from orchestrator.doctor import parse_source_figures
    assert parse_source_figures("OUTER LOADINGS\n| ATT_1 | 0.854 |\n") == {}
    assert parse_source_figures("") == {}


def test_code_fences_around_a_table_are_not_its_heading():
    from orchestrator.doctor import parse_results_tables
    text = ("OUTER LOADINGS\n```markdown\n| | ATT |\n|---|---|\n| ATT_1 | 0.854 |\n```\n"
            "PATH COEFFICIENTS\n```\n| | O |\n|---|---|\n| INT -> DEC | 0.606 |\n```\n")
    tables = parse_results_tables(text)
    assert not any(k.startswith("```") for k in tables)
    assert tables["outer_loadings"][0]["values"] == [0.854]
    assert tables["path_coefficients"][0]["values"] == [0.606]
