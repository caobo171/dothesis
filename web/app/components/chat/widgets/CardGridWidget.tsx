// web/app/components/chat/widgets/CardGridWidget.tsx
"use client";

import { CardGridHint, WidgetSelectHandler } from "./types";


// Map columns count to static Tailwind class strings. Tailwind's JIT doesn't
// pick up dynamically-computed class names, so we enumerate the supported values.
const COLUMN_CLASSES: Record<number, string> = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
};


export function CardGridWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: CardGridHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const columnClass = COLUMN_CLASSES[hint.columns ?? 3] ?? COLUMN_CLASSES[3];
  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`card-grid-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>
      <div className={`grid gap-2 ${columnClass}`}>
        {hint.options.map(opt => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(hint.field_name, opt.value, opt.label)}
            data-testid={`card-${opt.value}`}
            className="text-left rounded-md border border-gray-200 px-3 py-2 hover:border-purple-400 hover:bg-purple-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <div className="text-sm font-medium text-gray-900">{opt.label}</div>
            {opt.description && (
              <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{opt.description}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
