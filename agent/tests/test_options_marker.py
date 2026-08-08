"""[OPTIONS] parsing — the marker that turns a reply into clickable cards.

A marker the parser refuses is not a formatting nitpick: the student reads the
raw `[OPTIONS] A | B | C` as prose AND loses the buttons it was meant to
produce, which is how they end up typing an answer that was supposed to be one
click.
"""
from agent.runtime import _parse_options_marker as parse


def test_marker_on_its_own_line():
    hint = parse("Lock it in?\n\n[OPTIONS:methodology_confirm] Confirm | Refine")
    assert [o["label"] for o in hint["options"]] == ["Confirm", "Refine"]
    assert hint["field_name"] == "methodology_confirm"
    assert hint["multi_select"] is False


def test_marker_trailing_the_end_of_a_sentence():
    """What the model actually does. The skill says the marker owns its line;
    models routinely glue it to the closing sentence instead, and refusing that
    cost the student the buttons over a formatting slip."""
    hint = parse(
        "Bước tiếp theo là bổ sung đủ các chương, rồi mới đánh dấu M5 done. "
        "[OPTIONS] Bổ sung đủ 6 chương | Xem lại nội dung M5 | Xuất bản hiện có"
    )
    assert [o["label"] for o in hint["options"]] == [
        "Bổ sung đủ 6 chương", "Xem lại nội dung M5", "Xuất bản hiện có",
    ]
    assert hint["field_name"] == "user_choice"


def test_multi_select_survives_the_inline_form():
    hint = parse("Pick the gaps. [OPTIONS:gap_ids multi] G1 | G2 | G3")
    assert hint["multi_select"] is True
    assert hint["field_name"] == "gap_ids"


def test_no_marker_is_not_a_widget():
    assert parse("Just a sentence with no marker at all.") is None


def test_a_marker_above_later_prose_is_ignored():
    """Only the LAST non-empty line is considered. A marker buried mid-reply is
    not the turn's question, and firing cards off it would put stale choices
    under a message that has moved on."""
    assert parse("has [OPTIONS] A | B here\nbut the reply continues after it") is None


def test_an_empty_option_list_is_not_a_widget():
    assert parse("Choose:\n\n[OPTIONS]   ") is None
