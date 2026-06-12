"use client";

import { useState } from "react";
import { Send, Paperclip } from "lucide-react";
import { FileDropZone } from "./FileDropZone";


// 2026-06-10 — restyled to the DoThesis.html composer: a floating white card
// on the ink-50 canvas with a borderless textarea, an action row underneath,
// and a pill Send button. Behavior (submit guard, Enter/Shift+Enter, file
// picker fallback) is unchanged.
export function ChatInput({
  onSubmit,
  onFileDrop,
  disabled,
}: {
  onSubmit: (text: string) => void;
  onFileDrop: (files: File[]) => void;
  disabled: boolean;
}) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    // Guard: don't submit empty strings or while streaming is in progress
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText("");
  };

  const openFilePicker = () => {
    // Programmatically open file picker as fallback to drag-and-drop
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf,text/plain";
    input.multiple = true;
    input.onchange = () => {
      if (input.files) onFileDrop(Array.from(input.files));
    };
    input.click();
  };

  return (
    <FileDropZone onFileDrop={onFileDrop}>
      <div className="bg-ink-50 px-6 pt-1 pb-4">
        <div className="max-w-[880px] mx-auto bg-white border border-ink-200 rounded-[20px] shadow-[var(--shadow-card)] px-4 pt-2.5 pb-2 flex flex-col gap-1.5">
          <div className="flex items-end gap-2.5">
            <textarea
              rows={1}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={e => {
                // Enter (without Shift) submits; Shift+Enter inserts a newline
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Type a message…"
              disabled={disabled}
              className="flex-1 resize-none border-none bg-transparent px-0 py-1.5 text-[14.5px] leading-normal text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-0 disabled:opacity-50 max-h-32"
            />
            <button
              type="button"
              onClick={handleSubmit}
              disabled={disabled || !text.trim()}
              aria-label="send"
              className="inline-flex items-center gap-1.5 bg-primary-600 text-white rounded-full px-4 py-2 text-[13px] font-semibold hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors mb-0.5"
            >
              Send <Send className="w-3.5 h-3.5" />
            </button>
          </div>
          <div className="flex items-center gap-1 pt-1.5 border-t border-ink-100">
            <button
              type="button"
              disabled={disabled}
              onClick={openFilePicker}
              aria-label="attach file"
              className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12.5px] font-medium text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:opacity-50 transition-colors"
            >
              <Paperclip className="w-3.5 h-3.5" /> Attach
            </button>
            <span className="flex-1" />
            <span className="text-[11px] text-ink-400 pr-1">Shift+↵ for newline</span>
          </div>
        </div>
      </div>
    </FileDropZone>
  );
}
