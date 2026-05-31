"use client";

import useSWR from "swr";
import { useStream } from "./useStream";
import type { WidgetHint } from "../widgets/types";


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
  tool_calls_json?: WidgetHint | null;
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

  // SP3: parse tool_calls SSE events from the in-flight stream. Exposed but
  // not consumed by ChatPane today — MessageBubble renders widgets off
  // Message.tool_calls_json once SWR revalidates after the stream completes
  // (revalidation runs immediately in send() below, so the user sees the
  // widget moments after stream-end). Kept exported because (1) it locks
  // down the SSE event-parsing path under test (see useChat.test.tsx) and
  // (2) SP4+ may want a mid-stream widget preview — the wire is in place.
  const streamingToolCalls = (stream.state.events
    .filter(e => e.type === "tool_calls")
    .map(e => (e as unknown as { payload: WidgetHint }).payload)
    .at(-1)) ?? null;

  // P4: collect live engine progress events (M2 phase2 scout, etc.) so the
  // UI can render a banner with what's happening right now instead of a
  // bare typing dot during the 30-60s wait. Most recent event is the
  // primary message; the previous ones stay in the list for fade-out.
  const streamingProgress = stream.state.events
    .filter(e => e.type === "progress")
    .map(e => (e as unknown as {
      payload: { stage: string; message: string };
    }).payload);

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
    streamingToolCalls,
    streamingProgress,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
