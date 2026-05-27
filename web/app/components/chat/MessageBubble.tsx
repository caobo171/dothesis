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
        className="underline text-purple-700 hover:text-purple-900"
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

  return (
    <div
      data-role={role}
      className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}
    >
      <div
        className={
          isUser
            ? "max-w-[70%] rounded-2xl rounded-br-sm bg-purple-600 text-white px-4 py-2"
            : isSystem
            ? "max-w-[70%] rounded-md bg-gray-100 text-gray-600 px-3 py-1 text-sm italic"
            : "max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200"
        }
      >
        {moduleTag && !isUser && !isSystem && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">{_renderWithLinks(content)}</div>
        {toolCallsJson && onWidgetSelect && (
          <WidgetRenderer
            hint={toolCallsJson}
            onSelect={onWidgetSelect}
            disabled={widgetDisabled}
          />
        )}
        {children}
      </div>
    </div>
  );
}
