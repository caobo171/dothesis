"use client";

import { useEffect } from "react";
import { useStream } from "./useStream";


export function useAutoDraftRun(runId: string | null) {
  const stream = useStream();

  // Subscribe to run events only when a runId is available
  useEffect(() => {
    if (!runId) return;
    void stream.start(`/api/v1/runs/${runId}/events`, { method: "GET" });
    return () => stream.cancel();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runId]);

  return stream.state;
}
