"use client";

import { useRef } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { useStream } from "./useStream";
import type { WidgetHint } from "../widgets/types";
// (WidgetHint imported above is reused for the optimistic-message cast
//  where we pack the attachments-shape variant into tool_calls_json.)
import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";


// SWR fetcher routed through apiFetch as a POST (POST-only API) so the
// access_token rides in the JSON body — never the URL. Replaces the bare
// fetch("/api/v1...") that was relying on the now-gone session cookie.
const fetcher = (url: string) => apiFetch(url, { method: "POST" });


export type Message = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  module_tag?: string | null;
  tool_calls_json?: WidgetHint | null;
  // Per-response cost + latency (assistant rows). Shown in the message footer.
  cost_credits?: number;
  duration_ms?: number;
  total_tokens?: number;
  created_at: string;
};


export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate, isLoading: messagesLoading } = useSWR<Message[]>(
    `/threads/${threadId}/messages/list`,
    fetcher,
  );

  // Accumulate token events into a single streaming text string
  // Cast via unknown first since SSEEvent uses an index signature for extra fields
  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as unknown as { text: string }).text)
    .join("");

  // Keep the streamed text on screen across the stream-end → message-arrived
  // handoff.
  //
  // The bubble used to be gated on `inflight` alone, which goes false the
  // instant the SSE stream closes — but the persisted assistant message only
  // appears after mutate()'s round-trip to /messages/list. For the length of
  // that fetch the streamed text was gone and the real message had not landed,
  // so the finished answer blanked out and then reappeared.
  //
  // DERIVED from the message list rather than a flag cleared in send(): the
  // same render that brings the new message also flips this false, so there is
  // no in-between frame showing the bubble and the message together. A flag
  // set after `await mutate()` would land one render late and double-render the
  // answer instead — trading a blank flash for a duplicate one.
  const assistantCount = (messages ?? []).filter(m => m.role === "assistant").length;
  const awaitingAssistantRef = useRef<number | null>(null);
  const awaitingPersist =
    awaitingAssistantRef.current !== null && assistantCount <= awaitingAssistantRef.current;
  if (awaitingAssistantRef.current !== null && !awaitingPersist) {
    awaitingAssistantRef.current = null;   // reply landed; stop holding it over
  }
  // What the bubble should show: live tokens, then the same text held over
  // until the server's copy of it is in the list.
  const displayStreamingText =
    stream.state.inflight || awaitingPersist ? streamingText : "";

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

  // P4: collect live `progress` events so the UI shows what's happening right
  // now instead of a bare typing dot during the long first-token wait. The
  // backend (chat_v3) feeds this from both engine progress (M2 citation scout)
  // and deep-agent tool activity — already translated to student-facing labels
  // there (where the tool args live), so we just pass the payload through.
  const streamingProgress = stream.state.events
    .filter(e => e.type === "progress")
    .map(e => (e as unknown as { payload: { stage: string; message: string } }).payload)
    // Drop consecutive duplicate lines so repeated tool calls with the same
    // label don't make the bubble stutter the identical line.
    .filter((p, i, arr) => i === 0 || p.message !== arr[i - 1].message);

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
    // Attachment chip metadata from the composer. We need (a) the
    // upload_ids for the POST body so the backend materializes the bytes
    // and (b) filename+size so the optimistic user bubble can render
    // chips immediately — without flicker between optimistic and
    // server-truth. Backend persists the same shape onto the user
    // Message row (chat_v3.send_message_v3 + Message.tool_calls_json),
    // so SWR revalidation is a no-op for the chip render path.
    attachments?: { upload_id: string; filename: string; size_bytes: number; mime_type?: string }[],
  ) => {
    // Optimistic update: show user message immediately before server confirms
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      tool_calls_json:
        attachments && attachments.length > 0
          ? ({ attachments } as unknown as WidgetHint)
          : null,
    };
    void mutate([...(messages ?? []), optimistic], false);
    // Remember how many assistant replies existed before this turn, so the
    // streamed text can be held on screen until reply N+1 actually arrives.
    awaitingAssistantRef.current = (messages ?? []).filter(m => m.role === "assistant").length;

    // Bypass Next.js dev rewrites for the streaming POST. Turbopack's HTTP
    // proxy buffers `text/event-stream` chunked responses — engine progress
    // events fire on the backend (visible in dev.sh as [v3-yield] lines)
    // but never reach the browser EventStream until the request closes.
    // Hitting localhost:7100 directly sidesteps the buffer.
    // access_token rides in the JSON body (jwt_auth.AuthedBody pattern);
    // we no longer rely on the dothesis_session cookie, so `credentials`
    // can stay default and the cross-origin SameSite trap is gone.
    const apiBase = process.env.NEXT_PUBLIC_API_BASE;
    const streamUrl = apiBase
      ? `${apiBase}/threads/${threadId}/messages`
      : `/api/v1/threads/${threadId}/messages`;
    const accessToken = tokenStore.get();
    try {
      await stream.start(streamUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text,
          widget_payload: widgetPayload ?? null,
          upload_ids: (attachments ?? []).map(a => a.upload_id),
          access_token: accessToken,
        }),
      });
    } catch {
      // Restore server truth: the optimistic bubble represented a message the
      // API explicitly rejected (read-only admin view, stale thread, etc.).
      awaitingAssistantRef.current = null;
      void mutate(messages ?? [], false);
      return;
    }

    // Revalidate to replace the optimistic message with server truth
    void mutate();
    // Refresh the thread + project credit totals (rendered in the side panels
    // by the layout) now that this response recorded its cost. Key-matcher
    // mutate hits both `/threads/{id}/credits` and `/projects/{id}/credits`.
    void globalMutate(
      key => typeof key === "string" && key.includes("/credits"),
      undefined,
      { revalidate: true },
    );
    // The turn debited the user's balance — revalidate /auth/me so the
    // dashboard + sidebar credit balance reflect the spend immediately.
    void globalMutate("/auth/me");
  };

  return {
    messages: messages ?? [],
    // An undefined SWR payload is not an empty thread. Consumers use this to
    // avoid flashing onboarding/next-step copy before history has arrived.
    messagesLoading,
    // Already gated for the stream-end handoff — callers must NOT re-gate this
    // on `inflight`, which is what reintroduced the blank frame.
    streamingText: displayStreamingText,
    streamingToolCalls,
    streamingProgress,
    streamingError,
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
