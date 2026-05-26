// web/app/components/chat/widgets/ListEditorWidget.tsx
"use client";

import { useState } from "react";
import { summarizeList } from "./synthesize";
import type { ListEditorHint, ListItem, WidgetSelectHandler } from "./types";


// Local editable shape — same as ListItem but allows tracking new draft rows.
type EditableItem = ListItem & { _draft?: boolean };


function cloneItems(items: ListItem[]): EditableItem[] {
  return items.map(i => ({
    ...i,
    sub_items: i.sub_items ? cloneItems(i.sub_items) : [],
  }));
}


export function ListEditorWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: ListEditorHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<EditableItem[]>(() => cloneItems(hint.initial_items));

  const addItem = () => {
    const id = `new_${Date.now()}_${items.length}`;
    setItems([...items, { id, text: "", sub_items: [], _draft: true }]);
  };

  const removeItem = (id: string) => {
    setItems(items.filter(i => i.id !== id));
  };

  const editItemText = (id: string, text: string) => {
    setItems(items.map(i => i.id === id ? { ...i, text } : i));
  };

  const addSubItem = (parentId: string) => {
    const subId = `${parentId}_sub_${Date.now()}`;
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: [...(i.sub_items ?? []),
                            { id: subId, text: "", _draft: true } as EditableItem] }
      : i));
  };

  const removeSubItem = (parentId: string, subId: string) => {
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: (i.sub_items ?? []).filter(s => s.id !== subId) }
      : i));
  };

  const editSubItemText = (parentId: string, subId: string, text: string) => {
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: (i.sub_items ?? []).map(s => s.id === subId ? { ...s, text } : s) }
      : i));
  };

  const reset = () => setItems(cloneItems(hint.initial_items));

  const confirm = () => {
    // Strip the _draft local-only flag before serialization — backend must
    // not receive internal widget state flags.
    const clean: ListItem[] = items.map(i => ({
      id: i.id, text: i.text,
      sub_items: (i.sub_items ?? []).map(s => ({ id: s.id, text: s.text })),
      meta: i.meta,
    }));
    onSelect(hint.field_name, JSON.stringify(clean), summarizeList(clean, hint.field_name));
  };

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`list-editor-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>

      <div className="space-y-2">
        {items.map(item => (
          <div key={item.id} className="rounded-md border border-gray-200 bg-gray-50 p-2">
            <div className="flex items-start gap-2">
              {disabled ? (
                <span className="text-sm text-gray-900 flex-1">{item.text}</span>
              ) : (
                <input
                  type="text"
                  className="text-sm text-gray-900 flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400"
                  value={item.text}
                  onChange={e => editItemText(item.id, e.target.value)}
                  placeholder="Type item text..."
                  data-testid={`list-item-${item.id}-input`}
                />
              )}
              {!disabled && (
                <button
                  type="button"
                  className="text-gray-400 hover:text-red-500"
                  onClick={() => removeItem(item.id)}
                  data-testid={`list-item-${item.id}-remove`}
                >
                  ✕
                </button>
              )}
            </div>

            {hint.allow_nested && (
              <div className="ml-4 mt-1 space-y-1">
                {(item.sub_items ?? []).map(sub => (
                  <div key={sub.id} className="flex items-start gap-2 text-xs text-gray-600">
                    {disabled ? (
                      <span className="flex-1">• {sub.text}</span>
                    ) : (
                      <>
                        <span>•</span>
                        <input
                          type="text"
                          className="flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400"
                          value={sub.text}
                          onChange={e => editSubItemText(item.id, sub.id, e.target.value)}
                          data-testid={`list-sub-${sub.id}-input`}
                        />
                        <button
                          type="button"
                          className="text-gray-300 hover:text-red-500"
                          onClick={() => removeSubItem(item.id, sub.id)}
                          data-testid={`list-sub-${sub.id}-remove`}
                        >
                          ✕
                        </button>
                      </>
                    )}
                  </div>
                ))}
                {!disabled && (
                  <button
                    type="button"
                    className="text-xs text-gray-500 border border-dashed border-gray-300 rounded px-2 py-0.5 hover:bg-purple-50"
                    onClick={() => addSubItem(item.id)}
                    data-testid={`list-item-${item.id}-add-sub`}
                  >
                    + Sub-item
                  </button>
                )}
              </div>
            )}
          </div>
        ))}

        {!disabled && (
          <button
            type="button"
            className="w-full text-sm text-gray-500 border border-dashed border-gray-300 rounded-md py-1.5 hover:bg-purple-50 hover:border-purple-400"
            onClick={addItem}
            data-testid="list-editor-add"
          >
            + Add item
          </button>
        )}
      </div>

      {!disabled && (
        <div className="flex gap-2 mt-3 justify-end">
          <button
            type="button"
            className="text-xs text-gray-600 border border-gray-200 rounded-md px-3 py-1 hover:bg-gray-50"
            onClick={reset}
            data-testid="list-editor-reset"
          >
            {hint.reset_label ?? "Reset to suggested"}
          </button>
          <button
            type="button"
            className="text-xs font-medium text-white bg-purple-600 border border-purple-600 rounded-md px-3 py-1 hover:bg-purple-700"
            onClick={confirm}
            data-testid="list-editor-confirm"
          >
            {hint.confirm_label ?? "Confirm"}
          </button>
        </div>
      )}
    </div>
  );
}
