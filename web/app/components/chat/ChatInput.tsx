"use client";

import { useState } from "react";
import {
  FileText, Paperclip, PenSquare, Send, Sigma, X,
} from "lucide-react";
import { FileDropZone } from "./FileDropZone";


/**
 * A locally-tracked attachment chip — what's about to ride along with the
 * next message. The agent's tool can read these uploads on the next turn,
 * so the chip is informational. Removing a chip via the X button only
 * clears it from the local preview (the underlying upload is managed
 * separately from the Uploads pane); for now that's the right level of
 * trade-off — better than no preview at all.
 */
type Attachment = {
  // Local id so React keys don't collide if the same filename is picked twice.
  uid: string;
  name: string;
  size: number;
  // "uploading" while the parent's onFileDrop is still in flight, "ready"
  // once it resolves with an upload_id (the chat router needs it to look
  // the file up on send). "error" when the upload route returned no id.
  state: "uploading" | "ready" | "error";
  // Server-side row id from POST /uploads — required to ship the file
  // through to the model on send. Populated when state flips to "ready".
  uploadId?: string;
};


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
  /** Submit handler. `attachments` carries the chip metadata (server-side
   *  upload_id + filename + size) so the caller can ship the ids to the
   *  backend AND populate the optimistic user bubble's chips immediately
   *  — without waiting for SWR to revalidate from the server. */
  onSubmit: (
    text: string,
    attachments: { upload_id: string; filename: string; size_bytes: number; mime_type?: string }[],
  ) => void;
  /** Upload handler. Returns the `upload_id` for each file (in input
   *  order) so the chip can flip from "Uploading…" → "Ready" + carry the
   *  id through to `onSubmit`. Caller is responsible for the actual
   *  POST + token auth. */
  onFileDrop: (files: File[]) => Promise<(string | null)[]> | void;
  disabled: boolean;
  /** Module the conversation is currently focused on. Used in the placeholder. */
  focusModule?: string;
  /** Display name of the active model. Hidden when undefined. */
  modelName?: string;
  /** Estimated tokens per turn for the current thread context. Hidden when undefined. */
  tokenEstimate?: number;
}) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    // The agent runtime materializes these on the backend and ships the
    // file bytes inline as multimodal blocks — the user message text
    // itself doesn't need to carry the file refs anymore (the marker
    // was a stopgap for the read_file workflow).
    // Only ready chips ship — uploading/error chips are silently dropped.
    // The user can re-attach or wait; we'd rather send than block on a
    // half-uploaded file when the text alone is meaningful.
    const ready = attachments
      .filter(a => a.state === "ready" && a.uploadId)
      .map(a => ({
        upload_id: a.uploadId as string,
        filename: a.name,
        size_bytes: a.size,
      }));
    onSubmit(trimmed, ready);
    setText("");
    setAttachments([]);
  };

  // Add chips immediately when files are picked (so the user gets instant
  // visual feedback), THEN fire the parent's upload handler. Flip each
  // chip from "uploading" → "ready" as a best-effort signal — we don't
  // have per-file callbacks today, so we time-tick a single resolution.
  const attachFiles = (files: File[]) => {
    if (files.length === 0) return;
    const fresh: Attachment[] = files.map(f => ({
      uid: `${f.name}-${f.size}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      name: f.name,
      size: f.size,
      state: "uploading",
    }));
    const uids = fresh.map(a => a.uid);
    setAttachments(prev => [...prev, ...fresh]);
    // Fire the parent's upload; when it resolves with the per-file
    // upload_ids, flip each chip to "ready" + stamp the id so handleSubmit
    // can ship it. Null/missing ids → "error" chip (user can remove + retry).
    void Promise.resolve(onFileDrop(files)).then(ids => {
      const idsArr = Array.isArray(ids) ? ids : [];
      setAttachments(prev =>
        prev.map(a => {
          const idx = uids.indexOf(a.uid);
          if (idx < 0) return a;
          const id = idsArr[idx];
          return id
            ? { ...a, state: "ready" as const, uploadId: id }
            : { ...a, state: "error" as const };
        }),
      );
    }).catch(() => {
      setAttachments(prev =>
        prev.map(a => (uids.includes(a.uid) ? { ...a, state: "error" as const } : a)),
      );
    });
  };

  const removeAttachment = (uid: string) => {
    setAttachments(prev => prev.filter(a => a.uid !== uid));
  };

  const openFilePicker = () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf,text/plain";
    input.multiple = true;
    input.onchange = () => {
      if (input.files) attachFiles(Array.from(input.files));
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
    <FileDropZone onFileDrop={attachFiles}>
      <div className="px-6 pt-3.5 pb-5 bg-ink-50">
        <div
          className="max-w-[880px] mx-auto bg-white border border-ink-200 rounded-[20px] px-4 pt-2.5 pb-2 flex flex-col gap-2"
          style={{ boxShadow: "0 1px 0 rgba(11,16,32,.04), 0 2px 8px rgba(11,16,32,.06)" }}
        >
          {/* Row 0: attachment chips (only when something is queued) */}
          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pb-1">
              {attachments.map(a => (
                <AttachmentChip
                  key={a.uid}
                  attachment={a}
                  onRemove={() => removeAttachment(a.uid)}
                />
              ))}
            </div>
          )}

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


// --- Attachment chip — file preview riding above the textarea ---

function AttachmentChip({
  attachment, onRemove,
}: {
  attachment: Attachment;
  onRemove: () => void;
}) {
  const ext = extOf(attachment.name);
  return (
    <div
      className="inline-flex items-center gap-2 pl-1.5 pr-1 py-1 rounded-lg bg-ink-50 border border-ink-200 max-w-[260px] group"
      title={attachment.name}
    >
      {/* Mini file tile — gradient stripe + ext label, same idiom as the
          PapersPanel PDF tile so attachments look like first-class
          citations once they're uploaded. */}
      <span
        className="w-[28px] h-[34px] rounded-md border border-ink-200 flex items-end justify-center text-[8px] font-extrabold text-primary-700 shrink-0"
        style={{
          background: "linear-gradient(135deg, #F1F3FF 0%, #F4F0FF 100%)",
        }}
        aria-hidden="true"
      >
        {ext}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-medium text-ink-900 truncate">
          {attachment.name}
        </div>
        <div className="text-[11px] text-ink-500">
          {formatBytes(attachment.size)}
          {attachment.state === "uploading" && <> · Uploading…</>}
          {attachment.state === "error" && <span className="text-red-700"> · Upload failed</span>}
        </div>
      </div>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remove ${attachment.name}`}
        className="w-6 h-6 rounded-full text-ink-400 hover:bg-ink-200 hover:text-ink-700 inline-flex items-center justify-center transition-colors shrink-0"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

function extOf(name: string): string {
  const i = name.lastIndexOf(".");
  if (i === -1 || i === name.length - 1) return "FILE";
  return name.slice(i + 1).slice(0, 4).toUpperCase();
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
