"use client";

import { useState } from "react";
import {
  AtSign, ChevronDown, Paperclip, Send, X,
} from "lucide-react";
import { FileDropZone } from "./FileDropZone";
import { ExpertAvatar, ExpertPicker } from "./ExpertPicker";
import { applyExpertPersona, type Expert } from "@/app/lib/experts";
import { Button } from "@/app/components/ui/button";


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
 *   │  [@ Methodologist · Research design, paradigms… ]      [✕]   │  ← active-expert chip
 *   │  Ask Methodologist — they'll handle this turn                │
 *   │                                                       [Send ↵]│
 *   │  ───────────────────────────────────────────────────────────  │
 *   │  [@ Ask an expert ▾]   📎 Attach   ◇ Draw model              │
 *   └──────────────────────────────────────────────────────────────┘
 *      ⌘K to jump module · Shift+↵ for newline
 *
 * Picking an expert prefixes the outgoing message with a persona directive
 * (see lib/experts.ts) so the same backend agent tunes voice + grounding
 * for that specialist — no extra credit cost, same thread. The Draw model
 * button hands a pre-filled prompt fragment into the textarea so the
 * agent picks up the intent — a shortcut to compose, not a separate tool.
 * The active LLM model name is intentionally NOT surfaced to users.
 */
export function ChatInput({
  onSubmit,
  onFileDrop,
  disabled,
  focusModule,
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
}) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  // Active expert persona for THIS turn. Cleared back to `null` after each
  // send so the chooser is an opt-in per-turn move, not a sticky channel
  // that silently rebrands every future reply. Matches the design intent
  // ("Each one has its own grounding and voice — still one thread.").
  const [expert, setExpert] = useState<Expert | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

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
    // Persona directive lives in the user-visible message text, not a
    // hidden system field — so a later read of the transcript still
    // explains why the assistant suddenly answered like a statistician.
    onSubmit(applyExpertPersona(trimmed, expert), ready);
    setText("");
    setAttachments([]);
    setExpert(null);
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

  const placeholder = expert
    ? `Ask ${expert.name} — they'll handle this turn`
    : focusModule
      ? `Reply to DoThesis (currently in ${focusModule}) — or ask about any module`
      : "Reply to DoThesis — or ask about any module";

  return (
    <FileDropZone onFileDrop={attachFiles}>
      <div className="px-6 pt-3.5 pb-5 bg-ink-50">
        <div
          className={`max-w-[880px] mx-auto bg-white border rounded-[20px] px-4 pt-2.5 pb-2 flex flex-col gap-2 transition-shadow ${
            expert ? "border-primary-600 shadow-[0_0_0_3px_rgba(28,46,255,0.12)]" : "border-ink-200"
          }`}
          style={
            expert
              ? undefined
              : { boxShadow: "0 1px 0 rgba(11,16,32,.04), 0 2px 8px rgba(11,16,32,.06)" }
          }
        >
          {/* Row -1: active-expert chip — surfaces who's answering this turn */}
          {expert && (
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl bg-primary-50 border border-primary-100">
              <ExpertAvatar expert={expert} size={26} />
              <div className="leading-tight min-w-0">
                <div className="text-[12.5px] font-bold text-primary-700 truncate">
                  Consulting {expert.name}
                </div>
                <div className="text-[11px] text-primary-700/75 truncate">
                  {expert.tagline}
                </div>
              </div>
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => setExpert(null)}
                className="px-2 py-1 rounded-md text-[11px] font-semibold text-primary-700 hover:bg-primary-100 transition-colors"
                aria-label="Clear expert"
              >
                ✕ Clear
              </button>
            </div>
          )}

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
            <Button
              type="button"
              onClick={handleSubmit}
              disabled={disabled || !text.trim()}
              aria-label="Send"
              className="rounded-full self-end mb-0.5"
            >
              Send <Send className="w-3.5 h-3.5" />
            </Button>
          </div>

          {/* Row 2: expert picker + file upload + Draw model. The active LLM
              model name is intentionally not surfaced to users — the
              "expert" chooser is a persona selector, not a model switcher. */}
          <div className="flex items-center gap-1 pt-1.5 border-t border-ink-100 relative">
            <div className="relative">
              <button
                type="button"
                onClick={() => setPickerOpen(o => !o)}
                disabled={disabled}
                aria-haspopup="dialog"
                aria-expanded={pickerOpen}
                className={`inline-flex items-center gap-2 pl-1.5 pr-3 py-1 rounded-full text-[12.5px] font-semibold border transition-colors disabled:opacity-50 ${
                  expert
                    ? "text-primary-700 border-primary-200 bg-primary-50/60 hover:bg-primary-50"
                    : pickerOpen
                      ? "text-ink-700 border-ink-200 bg-ink-100"
                      : "text-ink-700 border-ink-200 hover:bg-ink-100"
                }`}
              >
                {expert ? (
                  <ExpertAvatar expert={expert} size={20} />
                ) : (
                  <span className="w-5 h-5 rounded-full bg-ink-200 text-ink-600 inline-flex items-center justify-center">
                    <AtSign className="w-3 h-3" />
                  </span>
                )}
                <span>{expert ? expert.name : "Ask an expert"}</span>
                <ChevronDown className="w-3 h-3 opacity-55" />
              </button>

              {pickerOpen && (
                <ExpertPicker
                  focusModule={focusModule}
                  selectedId={expert?.id}
                  onSelect={e => { setExpert(e); setPickerOpen(false); }}
                  onClose={() => setPickerOpen(false)}
                />
              )}
            </div>

            <ComposerAction
              icon={<Paperclip className="w-3.5 h-3.5" />}
              label="Attach"
              onClick={openFilePicker}
              disabled={disabled}
            />
          </div>
        </div>

        {/* Keyboard-shortcut hint. ⌘K "jump module" was removed — it had no
            handler wired (dead UI) and is meaningless on touch devices. */}
        <div className="max-w-[880px] mx-auto flex justify-center items-center gap-1.5 mt-2 text-[11px] text-ink-400">
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
      {/* Mini file tile — flat primary-50 (no violet) keeps the academic
          single-hue rule; the ext label stays the only emphasis. */}
      <span
        className="w-[28px] h-[34px] rounded-md border border-ink-200 bg-primary-50 flex items-end justify-center text-[8px] font-extrabold text-primary-700 shrink-0"
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
