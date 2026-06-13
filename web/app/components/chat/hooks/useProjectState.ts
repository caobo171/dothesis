"use client";

import { useEffect, useMemo } from "react";
import { useStream } from "./useStream";
import { tokenStore } from "@/app/lib/tokenStore";


export function useProjectState(threadId: string) {
  const stream = useStream();

  // Subscribe to the SSE state endpoint on mount / threadId change.
  // POST-only: the access_token rides in the JSON body so the JWT never
  // appears in the stream URL.
  useEffect(() => {
    if (!threadId) return;
    const token = tokenStore.get();
    void stream.start(`/api/v1/threads/${threadId}/state`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: token }),
    });
    return () => stream.cancel();
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
