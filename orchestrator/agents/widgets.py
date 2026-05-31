"""Pydantic models for module-agent widget render hints.

Each `WidgetHint` variant is serialized via `.model_dump()` into the
`messages.tool_calls_json` JSONB column. The frontend's WidgetRenderer
dispatches on `widget_type` to pick the right React component.

Future sub-projects (SP5-SP6) add new variants (e.g. `model_builder`,
`outline_editor`) to the discriminated union below — existing variants
and consumers are unaffected.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CardOption(BaseModel):
    value: str
    label: str
    description: str = ""
    icon: str | None = None


class CardGridHint(BaseModel):
    widget_type: Literal["card_grid"] = "card_grid"
    field_name: str
    title: str
    options: list[CardOption]
    columns: int = 3
    # When True the frontend tracks a set of selected card values and only
    # fires onSelect when the user clicks Submit. Used by phase3 gap selection
    # because users typically pick multiple gaps together; default False keeps
    # every existing emitter (M1 scope/field/Other, M3 quant/qual, M5 chapter
    # picker) on the original fire-on-first-click flow.
    multi_select: bool = False


# --- SP4: list_editor variant -------------------------------------------------

class ListItem(BaseModel):
    """One row in a ListEditorHint. sub_items lets the widget render a single
    level of nesting (e.g. themes → sub-themes). meta is a free-form bag for
    variant-specific extras (e.g. {"hypothesis": "H1"} on conceptual_model paths)."""
    id: str
    text: str
    sub_items: list["ListItem"] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


ListItem.model_rebuild()


class ListEditorHint(BaseModel):
    """Editable list. User edits locally, clicks Confirm to submit one final-state
    message (per Q5 decision in the SP4 design spec). Pairs with the
    summarizeList helper on the frontend that turns the final items into
    a bulleted natural-language message."""
    widget_type: Literal["list_editor"] = "list_editor"
    field_name: str
    title: str
    initial_items: list[ListItem]
    allow_nested: bool = False
    confirm_label: str = "Confirm"
    reset_label: str = "Reset to suggested"


# Discriminated union — future variants land here.
WidgetHint = Annotated[
    Union[CardGridHint, ListEditorHint],
    Field(discriminator="widget_type"),
]
