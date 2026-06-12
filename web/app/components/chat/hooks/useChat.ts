"use client";

import useSWR from "swr";
import { useStream } from "./useStream";
import type { WidgetHint } from "../widgets/types";
import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";


// SWR fetcher routed through apiFetch so the access_token rides on the GET
// (query string) just like every other authenticated read. Replaces the
// bare fetch("/api/v1...") that was relying on the now-gone session cookie.
const fetcher = (url: string) => apiFetch(url);

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

  // P6: backend yields `{type: error, message}` SSE events when graph.astream
  // raises (e.g. msgpack serialization, LLM timeouts, provider 5xx). Surface
  // the latest one so the UI can show a banner — silent failure was the
  // worst part of the M2 msgpack crash because users couldn't tell anything
  // had broken; their messages just echoed back with no reply.
  const streamingError = stream.state.events
    .filter(e => e.type === "error")
    .map(e => (e as unknown as { message: string }).message)
    .at(-1) ?? null;

  const send = async (
    text: string,
    // Structured payload from a rich-widget click (FlowChart, ListEditor).
    // When set, the backend uses `value` verbatim for `field_name` and
    // skips LLM extraction — necessary for nested shapes (M3
    // conceptual_model: {nodes,edges}) the text extractor was silently
    // flattening to {paths:[...]}.
    widgetPayload?: { field_name: string; value: unknown },
  ) => {
    // Optimistic update: show user message immediately before server confirms
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    void mutate([...(messages ?? []), optimistic], false);

    // Bypass Next.js dev rewrites for the streaming POST. Turbopack's HTTP
    // proxy buffers `text/event-stream` chunked responses — engine progress
    // events fire on the backend (visible in dev.sh as [v3-yield] lines)
    // but never reach the browser EventStream until the request closes.
    // Hitting localhost:7100 directly sidesteps the buffer.
    // access_token rides in the JSON body (jwt_auth.AuthedBody pattern);
    // we no longer rely on the opendraft_session cookie, so `credentials`
    // can stay default and the cross-origin SameSite trap is gone.
    const apiBase = process.env.NEXT_PUBLIC_API_BASE;
    const streamUrl = apiBase
      ? `${apiBase}/threads/${threadId}/messages`
      : `/api/v1/threads/${threadId}/messages`;
    const accessToken = tokenStore.get();
    await stream.start(streamUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text,
        widget_payload: widgetPayload ?? null,
        access_token: accessToken,
      }),
    });

    // Revalidate to replace the optimistic message with server truth
    void mutate();
  };

  return {
    messages: messages ?? [],
    streamingText,
    streamingToolCalls,
    streamingProgress,
    streamingError,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
