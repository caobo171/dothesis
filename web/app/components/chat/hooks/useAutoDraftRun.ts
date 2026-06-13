"use client";

import { useEffect } from "react";
import { useStream } from "./useStream";
import { tokenStore } from "@/app/lib/tokenStore";


export function useAutoDraftRun(runId: string | null) {
  const stream = useStream();

  // Subscribe to run events only when a runId is available.
  useEffect(() => {
    if (!runId) return;
    // POST (not GET/EventSource) so the access_token rides in the body — the
    // API is POST-only and there's no cookie auth. Hit NEXT_PUBLIC_API_BASE
    // (localhost:7100) directly: the Next dev proxy buffers text/event-stream,
    // which would stall live progress (same reason the chat stream does this).
    const base = process.env.NEXT_PUBLIC_API_BASE || "/api/v1";
    void stream.start(`${base}/runs/${runId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: tokenStore.get() }),
    });
    return () => stream.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return stream.state;
}
