"use client";

import { useEffect, useRef } from "react";
import { ErrorBubble } from "./ErrorBubble";
import { MessageBubble } from "./MessageBubble";
import { ProgressBubble, ProgressItem } from "./ProgressBubble";
import { StreamingBubble } from "./StreamingBubble";
import { ThinkingBubble } from "./ThinkingBubble";
import type { Message } from "./hooks/useChat";
import type { WidgetSelectHandler } from "./widgets/types";


export function MessageList({
  messages,
  streamingText,
  streamingModuleTag,
  streamingProgress = [],
  streamingError = null,
  inflight = false,
  onWidgetSelect,
}: {
  messages: Message[];
  streamingText: string;
  streamingModuleTag: string | null;
  /**
   * Live engine-progress events for this in-flight stream. Used to render
   * ProgressBubble in place of ThinkingBubble while M2 phase2's citation
   * scout (or any other long backend stage) is running.
   */
  streamingProgress?: ProgressItem[];
  /**
   * Backend-emitted error message (SSE `type: error`). Rendered as an
   * ErrorBubble so failures surface as something visible instead of a
   * silent stream-end (the M2 msgpack crash showed this is bad UX).
   */
  streamingError?: string | null;
  /**
   * SSE stream is open and we're waiting on the first token. When true and
   * streamingText is empty, ThinkingBubble fills the silence so the user
   * sees the agent is working rather than a stalled UI.
   */
  inflight?: boolean;
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
      {streamingText ? (
        <StreamingBubble text={streamingText} moduleTag={streamingModuleTag} />
      ) : inflight ? (
        // No tokens yet but the stream is open. If the backend sent any
        // engine-progress events, render the ProgressBubble (live engine
        // stage); otherwise the bare ThinkingBubble.
        streamingProgress.length > 0 ? (
          <ProgressBubble
            progress={streamingProgress}
            moduleTag={streamingModuleTag}
          />
        ) : (
          <ThinkingBubble moduleTag={streamingModuleTag} />
        )
      ) : null}
      {/* Error from this turn — renders after any partial streaming bubble
          so the user can see whatever the agent managed to say before the
          failure point (e.g. tokens that arrived before an LLM timeout). */}
      {streamingError && <ErrorBubble message={streamingError} />}
      <div ref={endRef} />
    </div>
  );
}
