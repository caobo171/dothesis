// web/app/components/chat/widgets/CardGridWidget.tsx
"use client";

import { useState } from "react";
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

  // When the user clicks "Other / Specify" we need them to actually type the
  // custom value — otherwise the literal label "Other / Specify" gets stored
  // as the answer (which corrupted M1's scope field in production). Show an
  // inline input below the grid; submit reuses the same onSelect contract.
  const [otherOpen, setOtherOpen] = useState(false);
  const [otherText, setOtherText] = useState("");

  const handleCardClick = (value: string, label: string) => {
    if (value === "Other") {
      setOtherOpen(true);
      return;
    }
    onSelect(hint.field_name, value, label);
  };

  const submitOther = () => {
    const v = otherText.trim();
    if (!v) return;
    onSelect(hint.field_name, v, v);
  };

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`card-grid-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>
      <div className={`grid gap-2 ${columnClass}`}>
        {hint.options.map(opt => {
          const isOther = opt.value === "Other";
          const highlighted = isOther && otherOpen;
          return (
            <button
              key={opt.value}
              type="button"
              disabled={disabled}
              onClick={() => handleCardClick(opt.value, opt.label)}
              data-testid={`card-${opt.value}`}
              className={[
                "text-left rounded-md border px-3 py-2",
                "hover:border-purple-400 hover:bg-purple-50",
                "disabled:opacity-50 disabled:cursor-not-allowed transition-colors",
                highlighted ? "border-purple-500 bg-purple-50" : "border-gray-200",
              ].join(" ")}
            >
              <div className="text-sm font-medium text-gray-900">{opt.label}</div>
              {opt.description && (
                <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{opt.description}</div>
              )}
            </button>
          );
        })}
      </div>

      {/* Inline input that appears when "Other / Specify" is picked. */}
      {otherOpen && (
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            value={otherText}
            onChange={(e) => setOtherText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") submitOther(); }}
            placeholder={`Type your ${hint.field_name.replace(/_/g, " ")}…`}
            data-testid="card-other-input"
            disabled={disabled}
            autoFocus
            className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500 disabled:opacity-50"
          />
          <button
            type="button"
            onClick={submitOther}
            disabled={disabled || !otherText.trim()}
            data-testid="card-other-submit"
            className="rounded-md bg-purple-600 px-4 py-2 text-sm font-semibold text-white hover:bg-purple-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Send
          </button>
        </div>
      )}
    </div>
  );
}
