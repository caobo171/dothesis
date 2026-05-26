"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";
import type { Message } from "./hooks/useChat";


export function MessageList({
  messages,
  streamingText,
  streamingModuleTag,
}: {
  messages: Message[];
  streamingText: string;
  streamingModuleTag: string | null;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to bottom whenever new messages arrive or streaming text updates.
  // scrollIntoView may be absent in jsdom test environments; guard defensively.
  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 bg-white">
      {messages.map(m => (
        <MessageBubble
          key={m.id}
          role={m.role}
          content={m.content}
          moduleTag={m.module_tag}
        />
      ))}
      {streamingText && (
        <StreamingBubble text={streamingText} moduleTag={streamingModuleTag} />
      )}
      <div ref={endRef} />
    </div>
  );
}
