"use client";

import useSWR from "swr";
import { useStream } from "./useStream";

const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

export type Message = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  module_tag?: string | null;
  created_at: string;
};


export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate } = useSWR<Message[]>(
    `/threads/${threadId}/messages`,
    fetcher,
  );

  // Accumulate token events into a single streaming text string
  // Cast via unknown first since SSEEvent uses an index signature for extra fields
  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as unknown as { text: string }).text)
    .join("");

  const send = async (text: string) => {
    // Optimistic update: show user message immediately before server confirms
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    void mutate([...(messages ?? []), optimistic], false);

    await stream.start(`/api/v1/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    // Revalidate to replace the optimistic message with server truth
    void mutate();
  };

  return {
    messages: messages ?? [],
    streamingText,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
