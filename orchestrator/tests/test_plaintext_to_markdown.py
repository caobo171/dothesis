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


def test_ragged_rows_are_padded_to_the_header_width():
    """Pandoc drops the entire table if one row has the wrong column count."""
    out = p2md("A | B | C\n1 | 2\n3 | 4 | 5 | 6")
    for line in (ln for ln in out.splitlines() if ln.startswith("|")):
        assert line.count("|") == 4             # 3 columns → 4 pipes


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
