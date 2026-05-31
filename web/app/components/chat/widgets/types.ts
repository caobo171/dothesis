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

// Discriminated union — future variants (e.g. canvas_editor) land here.
export type WidgetHint = CardGridHint | ListEditorHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
