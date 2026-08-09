"""Extracted document text must become markdown before it reaches the exporter.

The export contract is markdown (_sections_to_markdown → pandoc; m5_writing:253
says "prose is assumed to already be markdown"). A composer satisfies it; text
pulled out of a student's .docx does not. Shipping it raw produced three defects
on one page of a real export: the chapter collapsed into a single unbroken
paragraph, every table rendered inline as running prose, and Chapter 4
contributed no table-of-contents entries while every composed chapter did.
"""
from orchestrator.chapter_split import plaintext_to_markdown as p2md


def test_single_newlines_become_paragraph_breaks():
    """In markdown a lone newline is a soft wrap — that is what merged the
    whole chapter into one paragraph."""
    out = p2md("First paragraph.\nSecond paragraph.")
    assert "First paragraph.\n\nSecond paragraph." == out


def test_pipe_rows_become_a_real_markdown_table():
    out = p2md("Tiêu chí | Phân loại | Tần số\nGiới tính | Nam | 133\nGiới tính | Nữ | 170")
    assert "| Tiêu chí | Phân loại | Tần số |" in out
    assert "|---|---|---|" in out
    assert "| Giới tính | Nam | 133 |" in out


def test_table_rows_are_one_block_with_no_blank_lines_between_them():
    """A blank line between rows ends the table, undoing the whole fix."""
    out = p2md("A | B | C\n1 | 2 | 3\n4 | 5 | 6")
    table = [ln for ln in out.splitlines() if ln.startswith("|")]
    assert len(table) == 4                      # header + separator + 2 rows
    assert "\n\n|" not in out.split("| A |", 1)[1].split("\n\n")[0]


def test_ragged_rows_are_padded_to_a_single_width():
    """Pandoc drops the entire table if one row has the wrong column count.

    (This asserted a hardcoded 3 columns and passed vacuously: the short "1 | 2"
    row was not recognised as a row at all, so the table never formed and the
    loop had nothing to check.)
    """
    out = p2md("A | B | C\n1 | 2\n3 | 4 | 5 | 6")
    piped = [ln for ln in out.splitlines() if ln.startswith("|")]
    assert len(piped) == 4                      # header + separator + 2 rows
    assert len({ln.count("|") for ln in piped}) == 1


def test_two_column_tables_are_tables(monkeypatch):
    """The row pattern required two separators, so it saw only 3+ column tables.

    Most tables in a real thesis have two columns — the KMO/Bartlett block, both
    EFA factor-loading tables, every "Chỉ số | Giá trị" pair. Each row fell
    through to the prose branch and became its own one-line paragraph, so the
    student reported the tables as missing when they were sitting there as a
    ladder of stray lines. On one real Chapter 4 this was 5 of 17 tables.
    """
    out = p2md("Chỉ số | Giá trị\nHệ số KMO | 0.843\nBartlett Sig. | 0.000")
    assert "| Chỉ số | Giá trị |" in out
    assert "|---|---|" in out
    assert "| Hệ số KMO | 0.843 |" in out
    assert "\nHệ số KMO | 0.843" not in out       # not left behind as prose


def test_the_short_last_row_of_a_triangular_matrix_stays_in_the_table():
    """A correlation matrix prints only its upper half, so its last row is one
    cell wide. "EXP | 1" was stranded as a paragraph below the table."""
    out = p2md("Biến | PB | ATT | TR | EXP\n"
               "PB | 1 | 0.448 | 0.556 | 0.521\nATT | 1 | 0.015 | 0.146\n"
               "TR | 1 | -0.001\nEXP | 1")
    assert out.count("\n\n") == 0                 # one block, nothing spilled
    assert out.rstrip().endswith("| EXP | 1 |  |  |  |")


def test_a_short_header_is_padded_on_the_LEFT():
    """A matrix's corner cell is blank in the .docx and the extractor drops it,
    so the header row arrives one cell short. Padding it on the right like a
    body row shifts every column heading left — in a correlation matrix that
    reads as r(PB,PB) = 0.448, a wrong number rather than a missing one."""
    out = p2md("PB | ATT\nPB | 1 | 0.448\nATT | 1")
    lines = [ln for ln in out.splitlines() if ln.startswith("|")]
    assert lines[0] == "|  | PB | ATT |"
    assert lines[2] == "| PB | 1 | 0.448 |"


def test_chapter_and_section_headings_are_promoted():
    out = p2md("CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU\n4.1. Thống kê mô tả\n4.1.2 Chi tiết\nProse here.")
    assert "# CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU" in out
    assert "## 4.1 Thống kê mô tả" in out
    assert "### 4.1.2 Chi tiết" in out
    assert "\n\nProse here." in out


def test_a_decimal_in_prose_is_not_promoted_to_a_heading():
    """"4.1" alone, or a number without following text, must stay prose."""
    out = p2md("The value 4.1 was observed.")
    assert not out.startswith("#")


def test_a_lone_piped_line_is_not_treated_as_a_table():
    out = p2md("See Bảng 4.1 | trang 42")
    assert "|---" not in out


def test_empty_and_non_string_input_are_safe():
    assert p2md("") == ""
    assert p2md(None) == ""


def test_nothing_is_lost():
    """Worst case the output is the same prose, better spaced — never less."""
    src = "CHƯƠNG 4: KẾT QUẢ\n4.1. Mở đầu\nMột đoạn văn.\nA | B\n1 | 2\nKết thúc."
    out = p2md(src)
    for token in ("KẾT QUẢ", "Mở đầu", "Một đoạn văn.", "A", "B", "1", "2", "Kết thúc."):
        assert token in out
