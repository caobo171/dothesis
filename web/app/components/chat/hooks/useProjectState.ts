"use client";

import { useEffect, useMemo } from "react";
import { useStream } from "./useStream";


export function useProjectState(threadId: string) {
  const stream = useStream();

  // Subscribe to the SSE state endpoint on mount / threadId change
  useEffect(() => {
    if (!threadId) return;
    void stream.start(`/api/v1/threads/${threadId}/state`, { method: "GET" });
    return () => stream.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [threadId]);

  // Merge context_update patches into a single snapshot object
  const latest = useMemo(() => {
    return stream.state.events.reduce((acc, ev) => {
      if (ev.type === "context_update") {
        return { ...acc, ...((ev as { patch: Record<string, unknown> }).patch) };
      }
      return acc;
    }, {} as Record<string, unknown>);
  }, [stream.state.events]);

  const remoteUpdates = stream.state.events.filter(e => e.type === "remote_update");

  return { latest, remoteUpdates, inflight: stream.state.inflight };
}
