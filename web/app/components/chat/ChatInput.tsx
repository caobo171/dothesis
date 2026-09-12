"use client";

import { type ClipboardEvent, ReactNode, useRef, useState } from "react";
import {
  AtSign, ChevronDown, Paperclip, Send, X,
} from "lucide-react";
import { FileDropZone } from "./FileDropZone";
import { FileTypeIcon } from "./FileTypeIcon";
import { UPLOAD_ACCEPT } from "./uploadAccept";
import { SkillAvatar, SkillPicker } from "./SkillPicker";
import { QuickActionsMenu } from "./QuickActionsMenu";
import { applySkillDirective, type Skill } from "@/app/lib/skills";
import { Button } from "@/app/components/ui/button";


/**
 * A locally-tracked attachment chip — what's about to ride along with the
 * next message. The agent's tool can read these uploads on the next turn,
 * so the chip is informational. Removing a chip via the X button only
 * clears it from the local preview (the underlying upload is managed
 * separately from the Uploads pane); for now that's the right level of
 * trade-off — better than no preview at all.
 */
// How long Send will hold for an upload before calling it failed.
//
// Four minutes looks absurd for a 299KB file until you see what the upload does
// with it: POST /uploads extracts text synchronously, and for a .docx that means
// agent.docx_extract vision-transcribing every pasted screenshot, up to
// _MAX_IMAGES = 25 sequential model calls. A SmartPLS results document is
// nothing BUT result screenshots, so it is the worst case by construction and a
// legitimately slow request. A tighter bound would mark real uploads as failed.
//
// The honest fix is to stop doing that work inside the request — see the note in
// api/app/routers/uploads.py — at which point this can drop back to seconds.
const UPLOAD_WAIT_MS = 240_000;

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
 *   │  [@ Humanize · re-voice AI-sounding prose ]            [✕]   │  ← active-skill chip
 *   │  Ask Methodologist — they'll handle this turn                │
 *   │                                                       [Send ↵]│
 *   │  ───────────────────────────────────────────────────────────  │
 *   │  [@ Skills ▾]          📎 Attach   ◇ Draw model              │
 *   └──────────────────────────────────────────────────────────────┘
 *      ⌘K to jump module · Shift+↵ for newline
 *
 * Picking a skill prefixes the outgoing message with a directive naming the
 * skill (see lib/skills.ts), so the agent READS /skills/<id>/SKILL.md. This
 * replaced an "expert persona" chooser that only nudged tone —
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
  autoThesisButton,
  exportArtifacts,
  onQuickPrompt,
}: {
  /** Submit handler. `attachments` carries the chip metadata (server-side
   *  upload_id + filename + size) so the caller can ship the ids to the
   *  backend AND populate the optimistic user bubble's chips immediately
   *  — without waiting for SWR to revalidate from the server. */
  onSubmit: (
    text: string,
    attachments: { upload_id: string; filename: string; size_bytes: number; mime_type?: string }[],
    /** Resolves to the same chips with real `upload_id`s once every upload
     *  lands, or rejects if one failed. The caller paints the optimistic bubble
     *  from `attachments` first and awaits this only before the network call —
     *  so a slow upload never blocks the composer. */
    settleUploads?: () => Promise<{ upload_id: string; filename: string; size_bytes: number }[]>,
  ) => void;
  /** Upload handler. Returns the `upload_id` for each file (in input
   *  order) so the chip can flip from "Uploading…" → "Ready" + carry the
   *  id through to `onSubmit`. Caller is responsible for the actual
   *  POST + token auth. */
  onFileDrop: (files: File[]) => Promise<(string | null)[]> | void;
  disabled: boolean;
  /** Module the conversation is currently focused on. Used in the placeholder. */
  focusModule?: string;
  /** Quick actions — moved here from the header to reclaim its space. Rendered
   *  in the toolbar row, opening upward. Omitting all three (e.g. the run view)
   *  hides the menu. */
  autoThesisButton?: ReactNode;
  exportArtifacts?: { kind: string; download_url: string }[];
  onQuickPrompt?: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  // Active skill for THIS turn. Cleared back to `null` after each
  // send so the chooser is an opt-in per-turn move, not a sticky channel
  // that silently rebrands every future reply. Matches the design intent
  // ("Each one has its own grounding and voice — still one thread.").
  const [skill, setSkill] = useState<Skill | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  // The ref, not the state, is what submit reads.
  //
  // `handleSubmit` awaits in-flight uploads, and when it resumes the upload's
  // `setAttachments` has been *called* but React has not necessarily re-rendered
  // — so anything sourced from the render (state, or a ref assigned during
  // render) still says "uploading" and the freshly-arrived upload_id is invisible.
  // Every mutation therefore goes through `updateAttachments`, which writes the
  // ref synchronously and hands the same value to React for painting.
  const attachmentsRef = useRef<Attachment[]>([]);
  const updateAttachments = (next: (prev: Attachment[]) => Attachment[]) => {
    attachmentsRef.current = next(attachmentsRef.current);
    setAttachments(attachmentsRef.current);
  };
  // Per-attachment promise of its server-side upload id (null if it failed).
  // Keyed by chip uid so it survives the composer being cleared on send — the
  // send is already on screen by then and still needs the id.
  const uploadPromisesRef = useRef<Map<string, Promise<string | null>>>(new Map());

  // Submit is SYNCHRONOUS again, on purpose.
  //
  // An earlier cut awaited the in-flight uploads here, which fixed the silent
  // file-dropping but made Send feel dead: a .docx full of result screenshots
  // holds the upload POST open for minutes (see UPLOAD_WAIT_MS), and the whole
  // composer sat on it. The message now goes up immediately — chips and all —
  // and the WAIT MOVES DOWNSTREAM: `settleUploads` hands the caller a promise
  // for the real upload ids, which it awaits after painting the optimistic
  // bubble but before the network call that needs them.
  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;

    const snapshot = attachmentsRef.current;
    // Chips for the optimistic bubble. A file still uploading has no id yet;
    // it renders as an inert chip until server truth replaces it on revalidate.
    const chips = snapshot.map(a => ({
      upload_id: a.uploadId ?? "",
      filename: a.name,
      size_bytes: a.size,
    }));

    const promises = snapshot.map(a => uploadPromisesRef.current.get(a.uid));
    const settleUploads = async () => {
      const ids = await Promise.all(
        snapshot.map(async (a, i) => {
          if (a.uploadId) return a.uploadId;
          const p = promises[i];
          if (!p) return null;
          // Bounded: a request that never settles must fail the send rather
          // than leave the turn pending forever.
          return await Promise.race([
            p,
            new Promise<null>(resolve => setTimeout(() => resolve(null), UPLOAD_WAIT_MS)),
          ]);
        }),
      );
      // All-or-nothing. Shipping the ones that made it is how a message ended
      // up saying "here are my SmartPLS results" with no results attached.
      if (ids.some(id => !id)) throw new Error("upload_failed");
      return snapshot.map((a, i) => ({
        upload_id: ids[i] as string,
        filename: a.name,
        size_bytes: a.size,
      }));
    };

    for (const a of snapshot) uploadPromisesRef.current.delete(a.uid);

    // Persona directive lives in the user-visible message text, not a
    // hidden system field — so a later read of the transcript still
    // explains why the assistant suddenly answered like a statistician.
    onSubmit(
      applySkillDirective(trimmed, skill),
      chips,
      chips.length > 0 ? settleUploads : undefined,
    );
    setText("");
    updateAttachments(() => []);
    setSkill(null);
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
    updateAttachments(prev => [...prev, ...fresh]);
    // Fire the parent's upload; when it resolves with the per-file
    // upload_ids, flip each chip to "ready" + stamp the id so handleSubmit
    // can ship it. Null/missing ids → "error" chip (user can remove + retry).
    const settled: Promise<(string | null)[]> = Promise.resolve(onFileDrop(files))
      .then(ids => {
        const idsArr = Array.isArray(ids) ? ids : [];
        updateAttachments(prev =>
          prev.map(a => {
            const idx = uids.indexOf(a.uid);
            if (idx < 0) return a;
            const id = idsArr[idx];
            return id
              ? { ...a, state: "ready" as const, uploadId: id }
              : { ...a, state: "error" as const };
          }),
        );
        return uids.map((_, i) => idsArr[i] ?? null);
      })
      .catch(() => {
        updateAttachments(prev =>
          prev.map(a => (uids.includes(a.uid) ? { ...a, state: "error" as const } : a)),
        );
        return uids.map(() => null);
      });
    // Keep each file's id reachable by uid. `handleSubmit` clears the composer
    // the instant it fires, so the send that is already on screen can no longer
    // read the chip state — but it can still await this.
    fresh.forEach((a, i) => {
      uploadPromisesRef.current.set(a.uid, settled.then(ids => ids[i] ?? null));
    });
  };

  const removeAttachment = (uid: string) => {
    updateAttachments(prev => prev.filter(a => a.uid !== uid));
  };

  // Cmd/Ctrl+V with a screenshot on the clipboard attaches it like picking a
  // file — the ordinary way students share SmartPLS output from a screen grab.
  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (disabled) return;
    const files = clipboardImageFiles(e.clipboardData);
    if (files.length === 0) return;
    e.preventDefault();
    attachFiles(files);
  };

  const openFilePicker = () => {
    const input = document.createElement("input");
    input.type = "file";
    // Was a hand-written "application/pdf,text/plain", which greyed out .docx —
    // the format most drafts arrive in — even though the uploads endpoint has
    // always extracted it. Drag-drop worked, so only the picker looked broken.
    input.accept = UPLOAD_ACCEPT;
    input.multiple = true;
    input.onchange = () => {
      if (input.files) attachFiles(Array.from(input.files));
    };
    input.click();
  };

  // The placeholder used to announce the internal stage — "(currently in M2)",
  // "ask about any module". Same problem as the module chip: the student is
  // talking to one assistant, and naming the pipeline makes it sound like they
  // have to know which part of it they are in. `focusModule` still drives
  // routing; it just isn't quoted at the student.
  const placeholder = skill
    ? `${skill.name} will handle this turn`
    : "Reply to DoThesis — ask anything about your thesis";

  return (
    <FileDropZone onFileDrop={attachFiles}>
      {/* White, like the transcript above it. The band used to be bg-ink-50,
          which read as a grey slab under the composer card — most visible once
          an attachment chip made the card taller. */}
      <div className="px-6 pt-3.5 pb-5 bg-white">
        <div
          className={`max-w-[880px] mx-auto bg-white border rounded-[20px] px-4 pt-2.5 pb-2 flex flex-col gap-2 transition-shadow ${
            skill ? "border-primary-600 shadow-[0_0_0_3px_rgba(28,46,255,0.12)]" : "border-ink-200"
          }`}
          style={
            skill
              ? undefined
              : { boxShadow: "0 1px 0 rgba(11,16,32,.04), 0 2px 8px rgba(11,16,32,.06)" }
          }
        >
          {/* Row -1: active-skill chip — surfaces which pass runs this turn */}
          {skill && (
            <div className="flex items-center gap-2.5 px-2 py-1.5 rounded-xl bg-primary-50 border border-primary-100">
              <SkillAvatar name={skill.name} size={26} />
              <div className="leading-tight min-w-0">
                <div className="text-[12.5px] font-bold text-primary-700 truncate">
                  Using {skill.name}
                </div>
                <div className="text-[11px] text-primary-700/75 truncate">
                  {skill.description}
                </div>
              </div>
              <span className="flex-1" />
              <button
                type="button"
                onClick={() => setSkill(null)}
                className="px-2 py-1 rounded-md text-[11px] font-semibold text-primary-700 hover:bg-primary-100 transition-colors"
                aria-label="Clear skill"
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
              onPaste={handlePaste}
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

          {/* Row 2: skill picker + file upload + Draw model. The active LLM
              model name is intentionally not surfaced to users — the
              skill chooser picks a capability, not a model. */}
          <div className="flex items-center gap-1 pt-1.5 border-t border-ink-100 relative">
            <div className="relative">
              <button
                type="button"
                onClick={() => setPickerOpen(o => !o)}
                disabled={disabled}
                aria-haspopup="dialog"
                aria-expanded={pickerOpen}
                className={`inline-flex items-center gap-2 pl-1.5 pr-3 py-1 rounded-full text-[12.5px] font-semibold border transition-colors disabled:opacity-50 ${
                  skill
                    ? "text-primary-700 border-primary-200 bg-primary-50/60 hover:bg-primary-50"
                    : pickerOpen
                      ? "text-ink-700 border-ink-200 bg-ink-100"
                      : "text-ink-700 border-ink-200 hover:bg-ink-100"
                }`}
              >
                {skill ? (
                  <SkillAvatar name={skill.name} size={20} />
                ) : (
                  <span className="w-5 h-5 rounded-full bg-ink-200 text-ink-600 inline-flex items-center justify-center">
                    <AtSign className="w-3 h-3" />
                  </span>
                )}
                <span>{skill ? skill.name : "Skills"}</span>
                <ChevronDown className="w-3 h-3 opacity-55" />
              </button>

              {pickerOpen && (
                <SkillPicker
                  focusModule={focusModule}
                  selectedId={skill?.id}
                  onSelect={s => { setSkill(s); setPickerOpen(false); }}
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

            {/* Quick actions sits at the far right of the toolbar and opens
                upward — a downward menu would be clipped by the viewport edge
                the composer rests on. Rendered only when the host wires the
                actions in (the run view omits them).

                NOT tied to the composer's `disabled`: the text field disables
                while a turn streams or when credits run out, but export,
                history, and Auto Thesis (which gates its own run on credits
                downstream) must stay reachable — the header menu it replaced
                was never disabled either. */}
            {autoThesisButton && (
              <>
                <span className="flex-1" />
                <QuickActionsMenu
                  autoThesisButton={autoThesisButton}
                  exportArtifacts={exportArtifacts}
                  onQuickPrompt={onQuickPrompt}
                  placement="up"
                />
              </>
            )}
          </div>
        </div>

        {/* Keyboard-shortcut hint. ⌘K "jump module" was removed — it had no
            handler wired (dead UI) and is meaningless on touch devices. */}
        <div className="max-w-[880px] mx-auto flex flex-wrap justify-center items-center gap-x-3 gap-y-1 mt-2 text-[11px] text-ink-400">
          <span className="inline-flex items-center gap-1.5">
            <kbd className="px-1 py-px rounded border border-ink-200 bg-white text-[10px] font-mono">Shift+↵</kbd>
            <span>for newline</span>
          </span>
          <span className="inline-flex items-center gap-1.5">
            <kbd className="px-1 py-px rounded border border-ink-200 bg-white text-[10px] font-mono">⌘V</kbd>
            <span>to paste a screenshot</span>
          </span>
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
      {/* Same icon the context panel and message chips use. This used to be a
          hand-rolled lavender tile with the extension printed in it, so the one
          place you look while a file uploads was the one place that didn't show
          a recognisable Word/Excel/PDF icon. */}
      <FileTypeIcon kind={ext} className="w-[28px] h-[34px] shrink-0" />
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

function clipboardImageFiles(data: DataTransfer): File[] {
  const files: File[] = [];
  const stamp = Date.now();
  for (const item of Array.from(data.items)) {
    if (!item.type.startsWith("image/")) continue;
    const blob = item.getAsFile();
    if (!blob) continue;
    const sub = item.type.split("/")[1]?.replace("jpeg", "jpg") || "png";
    files.push(new File(
      [blob],
      `pasted-screenshot-${stamp}-${files.length + 1}.${sub}`,
      { type: blob.type },
    ));
  }
  return files;
}
