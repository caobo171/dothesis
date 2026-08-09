"""The student's imported chapter cannot be summarised away.

An imported thesis lands its real Chapter 4 in M5 `final_sections` — on the
project this was written for, 28,144 characters and 17 tables. Nothing stopped
the model from reading it, condensing it to a 575-character paragraph, and
committing the condensation over the original: the EFA, KMO, correlation and
regression tables were gone and the only trace was a Chapter 4 that had become
one paragraph.

Preservation at import is worthless if the very next commit can undo it.
"""
import json

from agent.tools.state_tools import (
    _IMPORTED_CHAPTER_MIN_RATIO, _protect_imported_chapters,
)


_LONG = "Bảng 4.5: KMO = 0.812\n\n| Chỉ số | Giá trị |\n" + ("Kết quả phân tích. " * 400)


def _imported(name="results", prose=_LONG, title="CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU"):
    return {"chapter_name": name, "title": title, "prose": prose, "source": "import"}


def test_a_summary_of_an_imported_chapter_is_refused():
    out, notes = _protect_imported_chapters(
        [{"chapter_name": "results", "title": "CHƯƠNG 4", "prose": "Nghiên cứu dùng 303 mẫu."}],
        [_imported()])
    assert out[0]["prose"] == _LONG, "the student's chapter was replaced by a summary"
    assert out[0]["source"] == "import", "the mark must survive, or the next commit wins"
    # The note names both sizes, so the model can tell the student what happened
    # rather than reporting "a guard fired".
    assert notes and str(len(_LONG)) in notes[0] and "summarised" in notes[0]


def test_a_translation_is_allowed_through():
    """vi→en runs slightly LONGER. Translating is the one transformation a
    preserved chapter is supposed to undergo."""
    english = "Table 4.5: KMO = 0.812\n\n| Indicator | Value |\n" + ("Analysis results. " * 420)
    out, notes = _protect_imported_chapters(
        [{"chapter_name": "results", "title": "Chapter 4", "prose": english}], [_imported()])
    assert out[0]["prose"] == english
    assert notes == []


def test_a_substantial_edit_is_allowed_through():
    """A real edit that trims a fifth is not a summary."""
    trimmed = _LONG[: int(len(_LONG) * 0.8)]
    out, notes = _protect_imported_chapters(
        [{"chapter_name": "results", "prose": trimmed}], [_imported()])
    assert out[0]["prose"] == trimmed and notes == []


def test_the_boundary_is_where_the_constant_says():
    prior = _imported()
    just_over = "x" * (int(len(_LONG) * _IMPORTED_CHAPTER_MIN_RATIO) + 10)
    just_under = "x" * (int(len(_LONG) * _IMPORTED_CHAPTER_MIN_RATIO) - 10)
    assert _protect_imported_chapters([{"chapter_name": "results", "prose": just_over}],
                                      [prior])[1] == []
    assert _protect_imported_chapters([{"chapter_name": "results", "prose": just_under}],
                                      [prior])[1] != []


def test_our_own_prose_is_not_protected():
    """Composed chapters are ours to rewrite at any length."""
    composed = {"chapter_name": "intro", "title": "Introduction", "prose": "x" * 9000}
    out, notes = _protect_imported_chapters(
        [{"chapter_name": "intro", "prose": "short"}], [composed])
    assert out[0]["prose"] == "short" and notes == []


def test_a_section_that_lost_its_chapter_name_is_still_matched_by_title():
    out, notes = _protect_imported_chapters(
        [{"title": "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU", "prose": "tóm tắt"}], [_imported()])
    assert out[0]["prose"] == _LONG and notes


def test_other_chapters_pass_through_untouched():
    out, _ = _protect_imported_chapters(
        [{"chapter_name": "intro", "prose": "new intro"}, {"chapter_name": "results", "prose": "x"}],
        [_imported()])
    assert out[0] == {"chapter_name": "intro", "prose": "new intro"}


def test_malformed_input_is_inert():
    assert _protect_imported_chapters("not a list", [_imported()]) == ("not a list", [])
    assert _protect_imported_chapters([None, 3], [_imported()]) == ([None, 3], [])
    assert _protect_imported_chapters([{"chapter_name": "results", "prose": "x"}], []) == (
        [{"chapter_name": "results", "prose": "x"}], [])


# --- through the real commit_slice tool --------------------------------------

def test_commit_slice_keeps_the_imported_chapter_and_says_so(tmp_path):
    from agent.state import ProjectStateStore
    from agent.tools.state_tools import make_state_tools

    store = ProjectStateStore(str(tmp_path))
    store.commit_slice("M5", {"final_sections": [_imported()]}, "import")

    tools = {t.name: t for t in make_state_tools(store)}
    raw = tools["commit_slice"].func(
        module="M5", reason="tidy up",
        writes={"final_sections": [{"chapter_name": "results", "title": "CHƯƠNG 4",
                                    "prose": "Nghiên cứu dùng 303 mẫu, ba giả thuyết được chấp nhận."}]})
    out = json.loads(raw)
    assert "error" not in out
    assert out["imported_chapters_kept"], "the guard did not report what it did"

    stored = store.load()["contextStore"]["final_sections"]
    assert stored[0]["prose"] == _LONG, "the student's Chapter 4 was overwritten anyway"
