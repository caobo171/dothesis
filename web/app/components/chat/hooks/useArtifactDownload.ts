"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Click feedback for the "mint a scoped token, then hand the URL to the
 * browser" download path.
 *
 * Every download button in the app used to be `void triggerExportDownload(...)`
 * — fire-and-forget, with the promise explicitly discarded. That meant the
 * token mint (a real round trip) showed nothing while it was in flight, and a
 * failure showed nothing at all: no navigation, no message, just an unhandled
 * rejection in the console. Six buttons, one behaviour, so it lives here.
 *
 * `started` rather than `done` because there is no completion signal to wait
 * on: the export route 302s to S3 with Content-Disposition, which the browser
 * turns into a file save with no navigation or load event a component can
 * observe. Spinning until "finished" would spin forever, so we acknowledge the
 * handoff and fall back to idle.
 */
export type DownloadPhase = "idle" | "preparing" | "started";

export function useArtifactDownload(resetMs = 2500) {
  const [phase, setPhase] = useState<DownloadPhase>("idle");
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  // Mirrors `phase` for the re-entrancy guard: `start` is memoised, so reading
  // the state variable inside it would read the value captured at creation and
  // never block the second click.
  const phaseRef = useRef<DownloadPhase>("idle");

  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  const set = (next: DownloadPhase) => {
    phaseRef.current = next;
    setPhase(next);
  };

  const start = useCallback(async (run: () => Promise<void>) => {
    if (phaseRef.current === "preparing") return;  // ignore double-clicks mid-mint
    set("preparing");
    setError(null);
    try {
      await run();
      set("started");
      if (timer.current !== null) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => set("idle"), resetMs);
    } catch (e) {
      set("idle");
      setError((e as Error)?.message || "Download failed.");
    }
  }, [resetMs]);

  return {
    phase,
    busy: phase === "preparing",
    started: phase === "started",
    error,
    start,
  };
}
