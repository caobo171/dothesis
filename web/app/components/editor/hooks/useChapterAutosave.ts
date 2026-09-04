import { useCallback, useRef, useState } from "react";
import { apiFetch } from "@/app/lib/api";


type Params = {
  projectId: string;
  chapterName: string;
  debounceMs?: number;
};


// Debounced PATCH /m5/chapters/{name}. Single-flight: the latest queued prose
// is what gets sent. Retries with exponential backoff (250ms / 1s / 4s) on
// network errors. After 3 retries, surfaces error via the returned state.
export function useChapterAutosave({ projectId, chapterName, debounceMs = 1000 }: Params) {
  const pendingProse = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const flush = useCallback(async () => {
    if (pendingProse.current === null) return;
    const prose = pendingProse.current;
    pendingProse.current = null;
    setSaving(true);
    // Backoff delays in ms: 250ms before retry 2, 1s before retry 3, 4s before
    // retry 4 (unused — we cap at 3 total attempts). Each await uses the faked
    // setTimeout so vi.advanceTimersByTimeAsync can drive retry timing in tests.
    const backoff = [250, 1000, 4000];
    let lastErr: Error | null = null;
    for (let i = 0; i < 3; i++) {
      try {
        // apiFetch, NOT a raw fetch: the POST-only API reads the auth token
        // from the JSON body (no cookies). A bare fetch sent none, so every
        // autosave 401'd and NOTHING the user typed was persisted. apiFetch
        // folds the token in and throws on non-2xx (caught below to retry).
        await apiFetch(
          `/projects/${projectId}/m5/chapters/${chapterName}`,
          { method: "PATCH", body: { prose } }
        );
        setLastSavedAt(new Date());
        setError(null);
        setSaving(false);
        return;
      } catch (e: any) {
        lastErr = e;
        // Wait before the next retry. Uses setTimeout so fake timers in tests
        // can advance through the backoff without real wall-clock delays.
        if (i < 2) await new Promise(res => setTimeout(res, backoff[i]));
      }
    }
    setError(lastErr);
    setSaving(false);
  }, [projectId, chapterName]);

  const queue = useCallback((prose: string) => {
    // Latest value wins: overwrite any pending prose before the debounce fires.
    pendingProse.current = prose;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, debounceMs);
  }, [flush, debounceMs]);

  return { queue, flush, saving, lastSavedAt, error };
}
