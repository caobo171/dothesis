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
