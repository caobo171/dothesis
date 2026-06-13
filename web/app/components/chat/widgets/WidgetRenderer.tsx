"use client";

import { CardGridWidget } from "./CardGridWidget";
import { FlowChartWidget } from "./FlowChartWidget";
import { ListEditorWidget } from "./ListEditorWidget";
import { PapersPanel } from "./PapersPanel";
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
  // AttachmentsHint piggybacks on the same `tool_calls_json` slot (used by
  // user-message bubbles to render linked-file chips). It has no
  // `widget_type` and isn't a clickable widget — bail out so the discriminator
  // switch below stays exhaustive over real widget variants.
  if (!("widget_type" in hint)) return null;
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
    case "papers_panel":
      // Foundational citations — read-only by default. Wires onCite + onFlag
      // through `onSelect` so the chat input gets the right action text
      // (e.g., "Insert cite: <paperId>") without inventing a new transport.
      return (
        <PapersPanel
          hint={hint}
          onCite={(paperId, quote) =>
            onSelect("paper_cite", paperId, `Insert citation for ${paperId}: "${quote.slice(0, 60)}…"`)
          }
          onFlag={(paperId) =>
            onSelect("paper_flag", paperId, `Flag paper ${paperId}`)
          }
        />
      );
    default:
      return null;
  }
}
