"use client";

import { CardGridWidget } from "./CardGridWidget";
import { ListEditorWidget } from "./ListEditorWidget";
import type { WidgetHint, WidgetSelectHandler } from "./types";


export function WidgetRenderer({
  hint,
  onSelect,
  disabled,
}: {
  hint: WidgetHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  switch (hint.widget_type) {
    case "card_grid":
      return <CardGridWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    case "list_editor":
      return <ListEditorWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    default:
      return null;
  }
}
