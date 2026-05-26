"""Pydantic models for module-agent widget render hints.

Each `WidgetHint` variant is serialized via `.model_dump()` into the
`messages.tool_calls_json` JSONB column. The frontend's WidgetRenderer
dispatches on `widget_type` to pick the right React component.

Future sub-projects (SP4-SP6) add new variants (e.g. `model_builder`,
`outline_editor`) to the discriminated union below — existing variants
and consumers are unaffected.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CardOption(BaseModel):
    value: str               # The schema value the click sends back
    label: str               # Display name
    description: str = ""    # Optional secondary line
    icon: str | None = None  # lucide-react icon name; SP3 ignores it


class CardGridHint(BaseModel):
    """Card grid: a labeled set of clickable cards. One click = one value."""
    widget_type: Literal["card_grid"] = "card_grid"
    field_name: str          # Which schema field this widget fills
    title: str               # Header above the grid
    options: list[CardOption]
    columns: int = 3         # Visual columns (frontend may collapse on narrow screens)


# Discriminated union — future variants land here.
WidgetHint = Annotated[Union[CardGridHint], Field(discriminator="widget_type")]
