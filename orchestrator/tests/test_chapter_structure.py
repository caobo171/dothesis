"""The interactive export ends in ONE concluding chapter, like the VN template.

Vietnamese universities set a five-chapter thesis: the discussion is written
inside "Kết luận và khuyến nghị", not as a chapter of its own. An imported
thesis reads "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU / CHƯƠNG 5: KẾT LUẬN VÀ KHUYẾN
NGHỊ", and the interactive export was handing back SIX chapters — pushing the
student's conclusion to Chapter 6 and adding a Discussion chapter nobody asked
for. The partner pipeline had merged since it shipped; only this path had not.
"""
from orchestrator.tools.compose_export import wants_merged_conclusion


def test_merged_by_default():
    assert wants_merged_conclusion({}) is True
    assert wants_merged_conclusion({"m5_writing": {}}) is True


def test_a_thesis_with_both_chapters_written_keeps_them():
    """Follow the project's own evidence — don't delete a chapter it wrote."""
    cs = {"m5_writing": {"chapters": {
        "discussion": {"prose": "We interpret the paths…"},
        "conclusion": {"prose": "In closing…"},
    }}}
    assert wants_merged_conclusion(cs) is False


def test_a_discussion_alone_still_merges():
    """One of the two is the normal generated shape — merging is what turns it
    into the single concluding chapter."""
    cs = {"m5_writing": {"chapters": {"discussion": {"prose": "interpretation"}}}}
    assert wants_merged_conclusion(cs) is True


def test_empty_prose_is_not_a_written_chapter():
    cs = {"m5_writing": {"chapters": {
        "discussion": {"prose": "  "}, "conclusion": {"prose": ""},
    }}}
    assert wants_merged_conclusion(cs) is True


def test_final_sections_in_vietnamese_are_recognised():
    cs = {"m5_writing": {"final_sections": [
        {"title": "Chương 5 — Thảo luận", "prose": "x" * 40},
        {"title": "Chương 6 — Kết luận", "prose": "y" * 40},
    ]}}
    assert wants_merged_conclusion(cs) is False


def test_structure_does_not_follow_language():
    """Writing in English does not make it an Anglo thesis — the university's
    template governs, so a Vietnamese student writing in English still gets
    five chapters."""
    assert wants_merged_conclusion({"m1_topic": {"language": "en"}}) is True
