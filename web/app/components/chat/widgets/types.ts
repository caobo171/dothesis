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
};

// Discriminated union — future variants (model_builder, outline_editor, ...) land here.
export type WidgetHint = CardGridHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
