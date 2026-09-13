import { useCallback, useRef, useState } from "react";
import { apiFetch } from "@/app/lib/api";


type Params = {
  projectId: string;
  chapterName: string;
};


/**
 * Explicit save for one chapter — PATCH /m5/chapters/{name}.
 *
 * This used to fire on a 1s debounce after every keystroke, which is a write
 * per sentence per student for as long as the editor is open. `track()` now
 * only remembers what changed; the request happens when `save()` is called,
 * which is the Save button.
 *
 * Retries with exponential backoff (250ms / 1s / 4s) on network errors and
 * surfaces the failure after three attempts — losing a save matters more now
 * that they are deliberate and further apart.
 */
export function useChapterSave({ projectId, chapterName }: Params) {
  const pendingProse = useRef<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);
  // Separate from `pendingProse`, which is cleared for the duration of a save:
  // this is what the UI asks "is there anything to save?", and it must stay
  // true while a save is in flight so a failure does not read as clean.
  const [dirty, setDirty] = useState(false);

  const save = useCallback(async () => {
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
        // save 401'd and NOTHING the user typed was persisted. apiFetch
        // folds the token in and throws on non-2xx (caught below to retry).
        await apiFetch(
          `/projects/${projectId}/m5/chapters/${chapterName}`,
          { method: "PATCH", body: { prose } }
        );
        setLastSavedAt(new Date());
        setError(null);
        setSaving(false);
        // Only clean if nothing was typed while the request was in flight.
        if (pendingProse.current === null) setDirty(false);
        return;
      } catch (e: any) {
        lastErr = e;
        // Wait before the next retry. Uses setTimeout so fake timers in tests
        // can advance through the backoff without real wall-clock delays.
        if (i < 2) await new Promise(res => setTimeout(res, backoff[i]));
      }
    }
    // Put it BACK in the queue. `flush` clears `pendingProse` before the first
    // attempt, so after three failures the student's text existed only inside
    // the in-memory TipTap document: a retry no-opped and a reload lost it.
    // Anything typed during the failed save has already replaced it and wins —
    // that value is strictly newer.
    if (pendingProse.current === null) pendingProse.current = prose;
    setError(lastErr);
    setSaving(false);
  }, [projectId, chapterName]);

  /** Record an edit. No request — that is what `save` is for. */
  const track = useCallback((prose: string) => {
    // Latest value wins: whatever is on screen is what Save sends.
    pendingProse.current = prose;
    setDirty(true);
  }, []);

  return { track, save, saving, lastSavedAt, error, dirty };
}
