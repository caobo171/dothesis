"use client";

import { useState } from "react";
import {
  FileText, Paperclip, PenSquare, Send, Sigma,
} from "lucide-react";
import { FileDropZone } from "./FileDropZone";


/**
 * Bottom composer — matches the design's `Composer`:
 *
 *   ┌──────────────────────────────────────────────────────────────┐
 *   │  Reply to DoThesis (currently in M2) — or ask about any …    │
 *   │                                                       [Send ↵]│
 *   │  ───────────────────────────────────────────────────────────  │
 *   │  📎 Attach  📄 Cite PDF  ∑ Run analysis  ◇ Draw model   │ Model: Gemini · ~340 tok/turn │
 *   └──────────────────────────────────────────────────────────────┘
 *      ⌘K to jump module · Shift+↵ for newline
 *
 * The action buttons (Cite PDF, Run analysis, Draw model) hand a
 * pre-filled prompt fragment into the textarea so the agent picks up
 * the intent — they're shortcuts to compose, not separate tools. The
 * agent already knows how to handle "Cite PDF" / "Draw model" requests
 * via the conventions in its system prompt.
 */
export function ChatInput({
  onSubmit,
  onFileDrop,
  disabled,
  focusModule,
  modelName,
  tokenEstimate,
}: {
  onSubmit: (text: string) => void;
  onFileDrop: (files: File[]) => void;
  disabled: boolean;
  /** Module the conversation is currently focused on. Used in the placeholder. */
  focusModule?: string;
  /** Display name of the active model. Hidden when undefined. */
  modelName?: string;
  /** Estimated tokens per turn for the current thread context. Hidden when undefined. */
  tokenEstimate?: number;
}) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit(trimmed);
    setText("");
  };

  const openFilePicker = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf,text/plain";
    input.multiple = true;
    input.onchange = () => {
      if (input.files) onFileDrop(Array.from(input.files));
    };
    input.click();
  };

  // Inject a prompt-fragment into the textarea so the agent receives a
  // clear intent. We don't auto-send — the user still has to hit Enter
  // (or edit the message) — so a stray click doesn't fire off a request.
  const inject = (fragment: string) => {
    setText(prev => (prev ? `${prev} ${fragment}` : fragment));
  };

  const placeholder = focusModule
    ? `Reply to DoThesis (currently in ${focusModule}) — or ask about any module`
    : "Reply to DoThesis — or ask about any module";

  return (
    <FileDropZone onFileDrop={onFileDrop}>
      <div className="px-6 pt-3.5 pb-5 bg-ink-50">
        <div
          className="max-w-[880px] mx-auto bg-white border border-ink-200 rounded-[20px] px-4 pt-2.5 pb-2 flex flex-col gap-2"
          style={{ boxShadow: "0 1px 0 rgba(11,16,32,.04), 0 2px 8px rgba(11,16,32,.06)" }}
        >
          {/* Row 1: textarea + Send */}
          <div className="flex items-start gap-2.5">
            <textarea
              rows={1}
              value={text}
              onChange={e => setText(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder={placeholder}
              disabled={disabled}
              className="flex-1 resize-none border-none bg-transparent px-0 py-1.5 text-[14.5px] leading-normal text-ink-900 placeholder:text-ink-400 focus:outline-none focus:ring-0 disabled:opacity-50 max-h-40"
            />
            <button
              type="button"
              onClick={handleSubmit}
              disabled={disabled || !text.trim()}
              aria-label="Send"
              className="inline-flex items-center gap-1.5 bg-primary-600 text-white rounded-full px-4 py-2 text-[13px] font-semibold hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end mb-0.5"
            >
              Send <Send className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Row 2: action chips on the left, model pill + token estimate on the right */}
          <div className="flex items-center gap-1 pt-1.5 border-t border-ink-100">
            <ComposerAction
              icon={<Paperclip className="w-3.5 h-3.5" />}
              label="Attach"
              onClick={openFilePicker}
              disabled={disabled}
            />
            <ComposerAction
              icon={<FileText className="w-3.5 h-3.5" />}
              label="Cite PDF"
              onClick={() => inject("Cite the PDF at p.")}
              disabled={disabled}
            />
            <ComposerAction
              icon={<Sigma className="w-3.5 h-3.5" />}
              label="Run analysis"
              onClick={() => inject("Run an analysis: ")}
              disabled={disabled}
            />
            <ComposerAction
              icon={<PenSquare className="w-3.5 h-3.5" />}
              label="Draw model"
              onClick={() => inject("Draw the conceptual model.")}
              disabled={disabled}
            />
            <span className="flex-1" />
            {modelName && (
              <div className="flex items-center gap-2 text-[11.5px] text-ink-500 pr-1">
                <span>Model</span>
                <span className="px-2 py-0.5 rounded-full bg-primary-50 text-primary-700 font-bold text-[11.5px]">
                  {modelName}
                </span>
                {tokenEstimate != null && (
                  <>
                    <span>·</span>
                    <span className="tabular-nums">~{formatThousands(tokenEstimate)} tok/turn</span>
                  </>
                )}
              </div>
            )}
          </div>
        </div>

        {/* Keyboard-shortcut hint */}
        <div className="max-w-[880px] mx-auto flex justify-center items-center gap-1.5 mt-2 text-[11px] text-ink-400">
          <kbd className="px-1 py-px rounded border border-ink-200 bg-white text-[10px] font-mono">⌘K</kbd>
          <span>to jump module</span>
          <span>·</span>
          <kbd className="px-1 py-px rounded border border-ink-200 bg-white text-[10px] font-mono">Shift+↵</kbd>
          <span>for newline</span>
        </div>
      </div>
    </FileDropZone>
  );
}


function ComposerAction({
  icon, label, onClick, disabled,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[12.5px] font-medium text-ink-500 hover:bg-ink-100 hover:text-ink-700 disabled:opacity-50 transition-colors"
    >
      {icon}
      <span>{label}</span>
    </button>
  );
}


function formatThousands(n: number): string {
  if (n >= 1000) {
    const k = n / 1000;
    return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return String(n);
}
