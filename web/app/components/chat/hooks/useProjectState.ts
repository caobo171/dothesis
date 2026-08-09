"use client";

import { useEffect, useMemo } from "react";
import { useStream } from "./useStream";
import { tokenStore } from "@/app/lib/tokenStore";


/** How often to re-snapshot project state. The endpoint closes after one
 *  event, so this is the refresh cadence for anything committed outside the
 *  chat stream (e.g. the background citation job). */
const STATE_POLL_MS = 5000;

export function useProjectState(threadId: string) {
  const stream = useStream();

  // Poll the SSE state endpoint on mount / threadId change, then on an interval.
  //
  // The endpoint emits ONE context_update snapshot and closes by design — its
  // docstring expects the client to be an EventSource, which reconnects on its
  // own every ~3s. This client is not: useStream issues a POST fetch (the
  // access_token rides in the body so the JWT never appears in a URL), and a
  // fetch does not reconnect. So the panel took a single snapshot at mount and
  // never updated again.
  //
  // What that broke: work committed OUTSIDE the chat stream never showed up.
  // The background citation job fills m2_literature.research_gaps a few minutes
  // after an import, and the card sat on its mount-time snapshot reading
  // "research_gaps is empty" until a full page reload — which made the gaps
  // look like they were found at random.
  useEffect(() => {
    if (!threadId) return;
    let stopped = false;
    const poll = () => {
      if (stopped) return;
      const token = tokenStore.get();
      void stream.start(`/api/v1/threads/${threadId}/state`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ access_token: token }),
      });
    };
    poll();
    // Matches the ~3s EventSource reconnect the endpoint was written against.
    const id = setInterval(poll, STATE_POLL_MS);
    return () => {
      stopped = true;
      clearInterval(id);
      stream.cancel();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  // Merge context_update patches into a single snapshot object
  const latest = useMemo(() => {
    return stream.state.events.reduce((acc, ev) => {
      if (ev.type === "context_update") {
        // Cast via unknown: SSEEvent uses an index signature so direct cast requires unknown first
        return { ...acc, ...((ev as unknown as { patch: Record<string, unknown> }).patch) };
      }
      return acc;
    }, {} as Record<string, unknown>);
  }, [stream.state.events]);

  const remoteUpdates = stream.state.events.filter(e => e.type === "remote_update");

  return { latest, remoteUpdates, inflight: stream.state.inflight };
}
