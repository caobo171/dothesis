import { ReactNode } from "react";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type { WidgetHint, WidgetSelectHandler } from "./widgets/types";

/**
 * Parses minimal markdown-link syntax [label](url) and renders them as anchors.
 * Preserves plain text and whitespace. Memoizes by content to avoid unnecessary
 * re-parsing on re-renders.
 *
 * Decision: Inline parsing rather than external markdown library keeps the
 * component lightweight and avoids dependency bloat for a single use-case.
 * Regex is simple and performant for the expected message lengths.
 */
function _renderWithLinks(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const regex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;

  while ((match = regex.exec(text)) !== null) {
    // Add text before the match
    if (match.index > last) {
      out.push(text.slice(last, match.index));
    }
    // Add the anchor
    out.push(
      <a
        key={`lnk-${key++}`}
        href={match[2]}
        className="underline text-primary-600 hover:text-primary-700"
      >
        {match[1]}
      </a>
    );
    last = match.index + match[0].length;
  }

  // Add remaining text after last match
  if (last < text.length) {
    out.push(text.slice(last));
  }

  return out;
}


// 2026-06-10 — DoThesis.html design: assistant turns are an avatar + a name
// row ("DoThesis" + serif module chip) above a white card with an asymmetric
// 4/18 radius. Exported as a frame so Streaming/Thinking/Error/Progress
// bubbles share the exact same silhouette and the thinking → streaming →
// final transition doesn't jump.
export function AssistantFrame({
  moduleTag,
  children,
  ...rest
}: {
  moduleTag?: string | null;
  children: ReactNode;
  [key: string]: unknown;
}) {
  return (
    <div data-role="assistant" className="flex items-start gap-3 py-3" {...rest}>
      <span
        aria-hidden
        className="w-[34px] h-[34px] min-w-[34px] rounded-[10px] inline-flex items-center justify-center text-white font-extrabold font-serif text-[15px] mt-[22px] shadow-[0_4px_12px_rgba(28,46,255,.22)]"
        style={{ background: "linear-gradient(135deg, #1c2eff 0%, #5b3aa8 100%)" }}
      >
        D
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1.5">
          <span className="text-[13px] font-bold text-ink-900">DoThesis</span>
          {moduleTag && (
            <span className="px-[7px] py-[2px] rounded-md bg-primary-50 text-primary-700 font-serif font-extrabold text-[11px] tracking-[0.03em]">
              {moduleTag}
            </span>
          )}
        </div>
        <div className="max-w-[85%] inline-block bg-white border border-ink-200 rounded-[18px] rounded-tl-[4px] px-[18px] py-3.5 text-[14.5px] leading-relaxed text-ink-800 shadow-[var(--shadow-card)]">
          {children}
        </div>
      </div>
    </div>
  );
}


export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  // SP3: widget bubble support — when both fields present, render the widget
  // inside the assistant bubble. widgetDisabled prevents clicks once a newer
  // user message has arrived (a "spent" widget shouldn't refire).
  toolCallsJson?: WidgetHint | null;
  onWidgetSelect?: WidgetSelectHandler;
  widgetDisabled?: boolean;
  children?: ReactNode;
};


export function MessageBubble({
  role,
  content,
  moduleTag,
  toolCallsJson,
  onWidgetSelect,
  widgetDisabled,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  if (isUser) {
    return (
      <div data-role={role} className="flex justify-end py-3">
        <div className="max-w-[70%] rounded-[18px] rounded-br-[4px] bg-primary-600 text-white px-4 py-[11px] text-[14.5px] leading-normal shadow-[0_1px_0_rgba(11,13,26,.04)]">
          <div className="whitespace-pre-wrap">{_renderWithLinks(content)}</div>
          {children}
        </div>
      </div>
    );
  }

  if (isSystem) {
    return (
      <div data-role={role} className="flex justify-start py-1.5">
        <div className="max-w-[70%] rounded-lg bg-ink-100 text-ink-500 px-3 py-1 text-sm italic">
          <div className="whitespace-pre-wrap">{_renderWithLinks(content)}</div>
          {children}
        </div>
      </div>
    );
  }

  return (
    <AssistantFrame moduleTag={moduleTag}>
      <div className="whitespace-pre-wrap">{_renderWithLinks(content)}</div>
      {toolCallsJson && onWidgetSelect && (
        <WidgetRenderer
          hint={toolCallsJson}
          onSelect={onWidgetSelect}
          disabled={widgetDisabled}
        />
      )}
      {children}
    </AssistantFrame>
  );
}
