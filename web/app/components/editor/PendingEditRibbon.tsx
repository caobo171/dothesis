"use client";


export type PendingEdit = {
  id: string;
  source: "paraphrase" | "translate" | "cite" | "chat_rewrite" | "proofread" | "improve" | "humanize" | "expand" | "shorten";
  oldText: string;
  newText: string;
  from_offset: number;
  to_offset: number;
};


type Props = {
  edit: PendingEdit;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  stale: boolean;
};


const _LABEL: Record<PendingEdit["source"], string> = {
  paraphrase: "Paraphrase",
  translate:  "Translate",
  cite:       "Cite",
  chat_rewrite: "Chat rewrite",
  proofread:  "Proofread",
  improve:    "Improve",
  humanize:   "Humanize",
  expand:     "Expand",
  shorten:    "Shorten",
};


// Floating ribbon rendered next to each AiPending mark. Actual portal mounting
// is handled by ChapterEditor's NodeView companion; this is pure presentation.
export function PendingEditRibbon({ edit, onAccept, onReject, stale }: Props) {
  if (stale) {
    return (
      <span className="inline-flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs px-2 py-0.5 rounded">
        <span>Stale ({_LABEL[edit.source]})</span>
        <button type="button" onClick={() => onReject(edit.id)} className="font-medium hover:underline">
          Discard
        </button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 bg-gray-900 text-white text-xs px-2 py-0.5 rounded">
      <span className="opacity-70">{_LABEL[edit.source]}</span>
      <button type="button" aria-label="Accept" onClick={() => onAccept(edit.id)}
              className="text-green-300 hover:text-green-200 font-medium">
        ✓ Accept
      </button>
      <button type="button" aria-label="Reject" onClick={() => onReject(edit.id)}
              className="text-red-300 hover:text-red-200 font-medium">
        ✗ Reject
      </button>
    </span>
  );
}
