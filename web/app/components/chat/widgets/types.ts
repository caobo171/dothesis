// web/app/components/chat/widgets/types.ts
export type CardOption = {
  value: string;
  label: string;
  description?: string;
  icon?: string | null;
};

export type CardGridHint = {
  widget_type: "card_grid";
  field_name: string;
  title: string;
  options: CardOption[];
  columns?: number;
  // When true the widget tracks a Set of picks and only fires onSelect on
  // Submit, sending a comma-joined string of values + a human-readable label.
  // Used by M2 phase3 gap selection where users routinely pick 2-3 gaps.
  multi_select?: boolean;
};

// SP4: list_editor variant
export type ListItem = {
  id: string;
  text: string;
  sub_items?: ListItem[];
  meta?: Record<string, unknown>;
};

export type ListEditorHint = {
  widget_type: "list_editor";
  field_name: string;
  title: string;
  initial_items: ListItem[];
  allow_nested?: boolean;
  confirm_label?: string;
  reset_label?: string;
};

// flow_chart variant — design merge (2026-06). The M3 conceptual_model
// widget used to be two separate bubbles (list_editor for paths, then
// another list_editor for scale items per construct). Splitting them
// produced an empty-second-widget bug and asked the user to repeat the
// same construct list twice. flow_chart ships nodes (constructs with
// attached Likert items) + edges (hypothesis paths with effect_type) in
// one canvas so structure + measurement co-exist. Mirrors Survify's
// AdvanceModelType. Confirm emits {nodes:[...], edges:[...]} which is
// the new on-the-wire shape for the `conceptual_model` schema field.
export type FlowChartNode = {
  id: string;
  label: string;
  questions: string[];
};

export type FlowChartEdge = {
  id: string;
  source: string;
  target: string;
  hypothesis: string;
  effect_type: "positive" | "negative";
};

export type FlowChartHint = {
  widget_type: "flow_chart";
  field_name: string;
  title: string;
  initial_nodes: FlowChartNode[];
  initial_edges: FlowChartEdge[];
  confirm_label?: string;
  reset_label?: string;
};

// Discriminated union — future variants (e.g. canvas_editor) land here.
export type WidgetHint = CardGridHint | ListEditorHint | FlowChartHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
