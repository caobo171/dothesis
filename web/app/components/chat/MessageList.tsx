"use client";

import { useEffect, useRef } from "react";
import { ErrorBubble } from "./ErrorBubble";
import { MessageBubble } from "./MessageBubble";
import { ProgressBubble, ProgressItem } from "./ProgressBubble";
import { StreamingBubble } from "./StreamingBubble";
import { ThinkingBubble } from "./ThinkingBubble";
import type { Message } from "./hooks/useChat";
import type { WidgetSelectHandler } from "./widgets/types";


// Considered "near bottom" if within this many pixels. Tokens arrive fast
// and content height grows by tiny amounts each tick; a small tolerance
// keeps us pinned through normal streaming but still lets the user scroll
// up to re-read without being yanked back.
const STICK_TOLERANCE_PX = 80;

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
  const scrollRef = useRef<HTMLDivElement | null>(null);
  // Latch true while the user is reading the tail. Once they scroll up past
  // STICK_TOLERANCE_PX, we stop pinning so they can re-read freely.
  const stickRef = useRef(true);
  // Coalesce per-token pins into one scroll per animation frame. Without
  // this, fast streams (50–80 tok/s) fire setState → effect → scrollTop
  // writes faster than the browser can settle, which Safari and Chrome
  // both render as a vertical "judder" — the page appears to bounce.
  const rafRef = useRef<number | null>(null);

  // Track whether the user is near the bottom. When they scroll up, drop
  // the stick latch so streaming tokens don't yank them back. When they
  // scroll back down to the tail, re-engage.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const dist = el.scrollHeight - el.scrollTop - el.clientHeight;
      stickRef.current = dist <= STICK_TOLERANCE_PX;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  // Pin to bottom on new messages / token deltas. INSTANT (no smooth) +
  // direct scrollTop on the scroll container — not scrollIntoView, which
  // also scrolls every scrollable ancestor (including the document, hence
  // the visible "page" jitter).
  useEffect(() => {
    if (!stickRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      el.scrollTop = el.scrollHeight;
    });
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
  }, [messages.length, streamingText]);

  const isStreaming = Boolean(streamingText);

  // DoThesis.html design: the conversation sits on the ink-50 canvas in a
  // centered ~880px column with a `space-y-5` rhythm between turns so the
  // user can scan the transcript without each bubble bleeding into the next.
  return (
    <div
      ref={scrollRef}
      className="flex-1 overflow-y-auto overscroll-contain px-6 py-6 bg-ink-50"
      // Anchor the scroll container's overflow so newly appended content
      // doesn't shift the existing rows upward when the browser tries to
      // preserve scroll position. Without this, fast token-by-token
      // appends fight scrollTop writes and the page visibly bounces.
      style={{ overflowAnchor: "none" }}
    >
      <div className="max-w-[880px] mx-auto space-y-5">
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
            failure point. */}
        {streamingError && <ErrorBubble message={streamingError} />}
        {/* Tail spacer so the last bubble doesn't kiss the composer. */}
        <div className="h-2" />
      </div>
    </div>
  );
}
