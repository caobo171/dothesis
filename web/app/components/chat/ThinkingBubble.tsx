import { Loader2 } from "lucide-react";

import { useT } from "@/app/lib/i18n/LocaleProvider";

/**
 * Three-dot "agent is thinking" indicator.
 *
 * Rendered between when the user's message lands and when the first SSE token
 * arrives — that gap is the LLM latency window (extraction → routing → next
 * question generation), which previously felt like a stalled UI. Shares
 * AssistantFrame with StreamingBubble so the transition from thinking →
 * streaming is seamless.
 */
export function ThinkingBubble({ moduleTag }: { moduleTag?: string | null }) {
  // Through the catalogue: this string was hardcoded Vietnamese, so an
  // English-locale student watched "Đang suy nghĩ…" on every turn.
  const t = useT();
  return (
    // Same shape as ProgressBubble's headline — spinner + one quiet line — so
    // the hand-off from "thinking" to the first named step is a word changing,
    // not the block changing. Three bouncing dots in a serif prose frame read
    // as a chat app; this reads as the machine working.
    // No module chip — see AssistantFrame.
    <div data-role="assistant" data-testid="thinking-bubble" className="flex flex-col">
      <div className="flex items-center gap-2 text-[13px] text-ink-500"
           aria-label={t("chat.stream.thinking")} aria-live="polite">
        <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" aria-hidden />
        <span>{t("chat.stream.thinking")}</span>
      </div>
    </div>
  );
}
