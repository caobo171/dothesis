"""A dataset must arrive as a profile, not as decoded bytes."""
from __future__ import annotations

import io

import pytest

from agent.data_profile import is_dataset, profile_dataset


def _xlsx_bytes() -> bytes:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    df = pd.DataFrame({
        "EX1": [5, 4, 3],
        "EX2": [4, 4, 2],
        "AGE": [21, 22, 20],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


def test_is_dataset_matches_the_four_data_formats():
    assert is_dataset("survey.xlsx")
    assert is_dataset("SURVEY.SAV")
    assert is_dataset("data.csv")
    assert not is_dataset("thesis.docx")
    assert not is_dataset("results.htm")


def test_csv_profile_reports_shape_columns_and_workspace_path():
    body = b"EX1,EX2,AGE\n5,4,21\n4,4,22\n"
    out = profile_dataset(body, "survey.csv")

    assert "2 rows x 3 columns" in out
    assert "uploads/survey.csv" in out          # the path the stats tools need
    for col in ("EX1", "EX2", "AGE"):
        assert col in out


def test_xlsx_profile_is_readable_text_not_zip_mojibake():
    body = _xlsx_bytes()
    out = profile_dataset(body, "survey.xlsx")

    assert "3 rows x 3 columns" in out
    assert "EX1" in out
    # The bug this branch exists to prevent: a .xlsx is a ZIP, so a UTF-8
    # decode yields the archive's mojibake ("PK...") instead of the data.
    assert "PK" not in out.split("Columns:")[0]


def test_unreadable_dataset_degrades_to_a_note_not_an_exception():
    out = profile_dataset(b"not really a spreadsheet", "broken.xlsx")

    assert "could not be read" in out
    assert "uploads/broken.xlsx" in out
