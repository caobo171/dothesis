"use client";

import { CardGridWidget } from "./CardGridWidget";
import { FlowChartWidget } from "./FlowChartWidget";
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
    case "flow_chart":
      // M3 conceptual_model uses the merged flow_chart widget (constructs +
      // Likert items + hypothesis paths in a single canvas). See types.ts
      // for the merge rationale.
      return <FlowChartWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    default:
      return null;
  }
}
