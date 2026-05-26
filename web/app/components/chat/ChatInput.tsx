"use client";

import { useState } from "react";
import { Send, Paperclip } from "lucide-react";
import { FileDropZone } from "./FileDropZone";


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

  return (
    <FileDropZone onFileDrop={onFileDrop}>
      <div className="border-t border-gray-200 bg-white px-4 py-3 flex items-end gap-2">
        <button
          type="button"
          disabled={disabled}
          className="text-gray-500 hover:text-purple-600 disabled:opacity-50 pb-1"
          onClick={() => {
            // Programmatically open file picker as fallback to drag-and-drop
            const input = document.createElement("input");
            input.type = "file";
            input.accept = "application/pdf,text/plain";
            input.multiple = true;
            input.onchange = () => {
              if (input.files) onFileDrop(Array.from(input.files));
            };
            input.click();
          }}
          aria-label="attach file"
        >
          <Paperclip className="w-4 h-4" />
        </button>

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
          className="flex-1 resize-none border border-gray-200 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-purple-400 disabled:opacity-50 max-h-32"
        />

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          aria-label="send"
          className="bg-purple-600 text-white rounded-md p-2 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </FileDropZone>
  );
}
