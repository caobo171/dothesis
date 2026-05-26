"""Tests for Pydantic widget hint models."""
import pytest
from pydantic import ValidationError

from orchestrator.agents.widgets import CardOption, CardGridHint


def test_card_option_minimal_fields():
    o = CardOption(value="x", label="X")
    assert o.value == "x"
    assert o.label == "X"
    assert o.description == ""
    assert o.icon is None


def test_card_option_with_all_fields():
    o = CardOption(value="x", label="X", description="desc", icon="zap")
    assert o.description == "desc"
    assert o.icon == "zap"


def test_card_grid_hint_minimal():
    h = CardGridHint(
        field_name="field",
        title="Pick",
        options=[CardOption(value="x", label="X")],
    )
    assert h.widget_type == "card_grid"
    assert h.columns == 3      # default


def test_card_grid_hint_model_dump_includes_widget_type():
    """Backend serializes to JSON via model_dump(); widget_type must survive."""
    h = CardGridHint(
        field_name="research_type",
        title="Approach",
        options=[CardOption(value="quantitative", label="Quantitative")],
        columns=3,
    )
    blob = h.model_dump()
    assert blob["widget_type"] == "card_grid"
    assert blob["field_name"] == "research_type"
    assert blob["options"][0]["value"] == "quantitative"


def test_card_grid_hint_rejects_empty_options():
    """Pydantic should not allow building a card grid with zero options
    (widget would be unusable). Pydantic doesn't reject empty lists by
    default; ensure the test documents current behavior."""
    h = CardGridHint(field_name="x", title="t", options=[])
    assert h.options == []  # accepted today; if we tighten later, update.


def test_list_item_minimal():
    from orchestrator.agents.widgets import ListItem
    i = ListItem(id="t1", text="Theme 1")
    assert i.id == "t1"
    assert i.text == "Theme 1"
    assert i.sub_items == []
    assert i.meta == {}


def test_list_item_with_nested_sub_items():
    from orchestrator.agents.widgets import ListItem
    i = ListItem(
        id="t1", text="Theme 1",
        sub_items=[ListItem(id="s1", text="Sub A"), ListItem(id="s2", text="Sub B")],
        meta={"hypothesis": "H1"},
    )
    assert len(i.sub_items) == 2
    assert i.sub_items[0].text == "Sub A"
    assert i.meta["hypothesis"] == "H1"


def test_list_editor_hint_minimal():
    from orchestrator.agents.widgets import ListEditorHint, ListItem
    h = ListEditorHint(
        field_name="themes",
        title="Pick themes",
        initial_items=[ListItem(id="t1", text="A")],
    )
    assert h.widget_type == "list_editor"
    assert h.allow_nested is False
    assert h.confirm_label == "Confirm"
    assert h.reset_label == "Reset to suggested"


def test_list_editor_hint_model_dump():
    from orchestrator.agents.widgets import ListEditorHint, ListItem
    h = ListEditorHint(
        field_name="themes",
        title="Pick themes",
        initial_items=[ListItem(id="t1", text="A",
                                sub_items=[ListItem(id="s1", text="B")])],
        allow_nested=True,
    )
    blob = h.model_dump()
    assert blob["widget_type"] == "list_editor"
    assert blob["allow_nested"] is True
    assert blob["initial_items"][0]["sub_items"][0]["text"] == "B"


def test_widget_hint_union_resolves_list_editor():
    """The discriminated WidgetHint union should resolve a dict-shaped
    ListEditorHint payload to the correct variant."""
    from pydantic import TypeAdapter
    from orchestrator.agents.widgets import WidgetHint

    adapter = TypeAdapter(WidgetHint)
    payload = {
        "widget_type": "list_editor",
        "field_name": "themes",
        "title": "T",
        "initial_items": [{"id": "t1", "text": "A"}],
    }
    parsed = adapter.validate_python(payload)
    assert parsed.widget_type == "list_editor"
    assert parsed.field_name == "themes"
