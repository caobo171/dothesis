"""The run detail view must show what actually moved.

"80 đoạn đã viết lại" is a number. A supervisor asking "what did this tool do to
my chapter", and a student checking their own numbers survived, both need the
words. These tests pin the two properties that make the view trustworthy: the
diff is word-level (so a rewritten sentence reads as a few small swaps, not one
opaque delete-then-insert), and it refuses to pair paragraphs when the documents
no longer line up.
"""
from __future__ import annotations

import io

from docx import Document

from orchestrator.tools.docx_diff import diff_docx, word_segments


def _docx(paragraphs: list[str]) -> bytes:
    d = Document()
    for p in paragraphs:
        d.add_paragraph(p)
    buf = io.BytesIO(); d.save(buf)
    return buf.getvalue()


# --- word-level segments --------------------------------------------------

def test_a_reworded_clause_shows_as_a_small_swap_not_a_whole_paragraph():
    segs = word_segments(
        "Kết quả cho thấy rằng mô hình phù hợp với dữ liệu.",
        "Kết quả cho thấy mô hình phù hợp với dữ liệu.")
    assert [s.op for s in segs].count("del") == 1
    assert "rằng" in "".join(s.text for s in segs if s.op == "del")
    # Everything either side of the change is preserved as equal text.
    kept = "".join(s.text for s in segs if s.op == "equal")
    assert "Kết quả cho thấy" in kept and "mô hình phù hợp" in kept


def test_a_replacement_shows_both_sides():
    segs = word_segments("mẫu 245 quan sát", "mẫu 245 người tham gia")
    ops = [s.op for s in segs]
    assert "del" in ops and "ins" in ops


def test_neighbouring_changes_are_merged_into_one_span():
    """Fewer, larger spans read better than a stutter of one-word spans."""
    segs = word_segments("a b c d e", "a x y z e")
    assert sum(1 for s in segs if s.op == "del") == 1
    assert sum(1 for s in segs if s.op == "ins") == 1


def test_identical_text_is_all_equal():
    segs = word_segments("không có gì thay đổi", "không có gì thay đổi")
    assert [s.op for s in segs] == ["equal"]


# --- document level -------------------------------------------------------

def test_the_diff_counts_changed_and_unchanged_paragraphs():
    before = _docx(["Đoạn một chưa đổi.", "Kết quả cho thấy rằng mô hình phù hợp.",
                    "Đoạn ba chưa đổi."])
    after = _docx(["Đoạn một chưa đổi.", "Kết quả cho thấy mô hình phù hợp.",
                   "Đoạn ba chưa đổi."])
    d = diff_docx(before, after)
    assert d.aligned
    assert d.total == 3 and d.changed == 1 and d.unchanged == 2
    assert [i.index for i in d.items] == [1]      # changed_only by default


def test_unchanged_paragraphs_can_be_included():
    before = _docx(["giữ nguyên", "Kết quả cho thấy rằng mô hình phù hợp."])
    after = _docx(["giữ nguyên", "Kết quả cho thấy mô hình phù hợp."])
    d = diff_docx(before, after, changed_only=False)
    assert [i.index for i in d.items] == [0, 1]


def test_misaligned_documents_refuse_to_pair_paragraphs():
    """Pairing across a length mismatch would attribute one paragraph's text to
    another — worse than showing nothing."""
    d = diff_docx(_docx(["a", "b", "c"]), _docx(["a", "b"]))
    assert d.aligned is False
    assert d.items == []


def test_a_long_document_is_truncated_rather_than_unbounded():
    n = 30
    before = _docx([f"Đoạn số {i} với nội dung ban đầu." for i in range(n)])
    after = _docx([f"Đoạn số {i} với nội dung đã sửa." for i in range(n)])
    d = diff_docx(before, after, limit=10)
    assert d.changed == n              # counted in full
    assert len(d.items) == 10          # but only ten carried
    assert d.truncated is True
