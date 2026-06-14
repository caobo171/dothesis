"use client";

import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";

import type { SlashItem } from "./extensions/SlashCommand";


export type SlashCommandListHandle = {
  // Returns true when the key was consumed by the menu (so the editor ignores it).
  onKeyDown: (props: { event: KeyboardEvent }) => boolean;
};

type Props = {
  items: SlashItem[];
  // Provided by @tiptap/suggestion: runs the selected item's command.
  command: (item: SlashItem) => void;
};


// Notion-style command palette shown while typing "/". Keyboard-first:
// ↑/↓ move, Enter selects, Esc is handled by the extension. The active row is
// scrolled into view so long lists stay navigable.
export const SlashCommandList = forwardRef<SlashCommandListHandle, Props>(
  function SlashCommandList({ items, command }, ref) {
    const [selected, setSelected] = useState(0);
    const rowRefs = useRef<(HTMLButtonElement | null)[]>([]);

    // Reset highlight whenever the filtered list changes (new query).
    useEffect(() => setSelected(0), [items]);

    useEffect(() => {
      rowRefs.current[selected]?.scrollIntoView({ block: "nearest" });
    }, [selected]);

    useImperativeHandle(
      ref,
      () => ({
        onKeyDown: ({ event }) => {
          if (items.length === 0) return false;
          if (event.key === "ArrowUp") {
            setSelected(s => (s + items.length - 1) % items.length);
            return true;
          }
          if (event.key === "ArrowDown") {
            setSelected(s => (s + 1) % items.length);
            return true;
          }
          if (event.key === "Enter") {
            const item = items[selected];
            if (item) command(item);
            return true;
          }
          return false;
        },
      }),
      [items, selected, command],
    );

    if (items.length === 0) {
      return (
        <div className="w-64 rounded-xl border border-ink-200 bg-white shadow-lg p-3 text-[12.5px] text-ink-500">
          No matching blocks
        </div>
      );
    }

    return (
      <div className="w-64 max-h-72 overflow-y-auto rounded-xl border border-ink-200 bg-white shadow-lg p-1.5">
        {items.map((item, i) => (
          <button
            key={item.title}
            ref={el => { rowRefs.current[i] = el; }}
            type="button"
            // Use onMouseDown (not onClick) so the editor selection isn't lost
            // before the command runs.
            onMouseDown={e => { e.preventDefault(); command(item); }}
            onMouseEnter={() => setSelected(i)}
            className={`w-full flex items-start gap-2.5 px-2.5 py-1.5 rounded-lg text-left transition-colors ${
              i === selected ? "bg-primary-50" : "hover:bg-ink-50"
            }`}
          >
            <span className="shrink-0 mt-0.5 w-7 h-7 rounded-md border border-ink-200 bg-ink-50 inline-flex items-center justify-center text-[12px] font-bold text-ink-700">
              {item.icon}
            </span>
            <span className="min-w-0">
              <span className="block text-[13px] font-semibold text-ink-900 leading-tight">
                {item.title}
              </span>
              <span className="block text-[11.5px] text-ink-500 leading-tight mt-0.5 truncate">
                {item.subtitle}
              </span>
            </span>
          </button>
        ))}
      </div>
    );
  },
);
