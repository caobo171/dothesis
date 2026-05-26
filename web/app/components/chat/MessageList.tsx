"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";
import type { Message } from "./hooks/useChat";
import type { WidgetSelectHandler } from "./widgets/types";


export function MessageList({
  messages,
  streamingText,
  streamingModuleTag,
  onWidgetSelect,
}: {
  messages: Message[];
  streamingText: string;
  streamingModuleTag: string | null;
  onWidgetSelect?: WidgetSelectHandler;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom whenever new messages arrive or streaming text updates.
  // scrollIntoView may be absent in jsdom test environments; guard defensively.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  const isStreaming = Boolean(streamingText);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 bg-white">
      {messages.map((m, idx) => {
        // SP3: widget on a "spent" message (not last, or streaming in progress)
        // is disabled so the user can't fire a stale selection.
        const isLast = idx === messages.length - 1;
        const widgetDisabled = !isLast || isStreaming;
        return (
          <MessageBubble
            key={m.id}
            role={m.role}
            content={m.content}
            moduleTag={m.module_tag}
            toolCallsJson={m.tool_calls_json}
            onWidgetSelect={onWidgetSelect}
            widgetDisabled={widgetDisabled}
          />
        );
      })}
      {streamingText && (
        <StreamingBubble text={streamingText} moduleTag={streamingModuleTag} />
      )}
      <div ref={endRef} />
    </div>
  );
}
