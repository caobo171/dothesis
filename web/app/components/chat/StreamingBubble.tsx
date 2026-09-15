import { Loader2 } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

import { AssistantFrame, humanizeTechnicalCopy } from "./MessageBubble";

// Shares AssistantFrame with the final MessageBubble so the in-flight and
// settled turns have identical silhouettes (no layout jump on stream end).
export function StreamingBubble({ text, moduleTag }: { text: string; moduleTag?: string | null }) {
  const t = useT();
  // Hide the raw `{{cite: …}}` grounding markers while streaming — they render
  // as pills only once the message settles (MessageBubble). Showing the raw
  // marker mid-stream looks like a glitch. Keep the label so the sentence reads.
  const clean = humanizeTechnicalCopy(
    text.replace(/\{\{cite:\s*([^{}|]+?)(?:\|[^{}]*)?\}\}/g, "$1"),
  ).trimEnd();
  return (
    <AssistantFrame moduleTag={moduleTag}>
      <div className="whitespace-pre-wrap">{clean}</div>
      {/*
        A moving indicator on its own line, not a caret inline.

        This was a 2px-wide `animate-pulse` bar. At 16px serif it is almost
        invisible, and `animate-pulse` only fades opacity — there is no motion
        to catch the eye. A student watching a turn that takes 160 seconds
        could not tell a streaming reply from a finished one, and read a
        half-written answer as the whole answer.

        Same silhouette as ThinkingBubble (spinner + one quiet line) on
        purpose: thinking → answering → done then reads as one continuous
        state where only the word changes, which is what ThinkingBubble's own
        comment says it was aiming for.
      */}
      <div
        data-testid="streaming-cursor"
        className="mt-2 flex items-center gap-2 text-[13px] text-ink-500"
        aria-live="polite"
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" aria-hidden />
        <span>{t("chat.stream.answering")}</span>
      </div>
    </AssistantFrame>
  );
}
