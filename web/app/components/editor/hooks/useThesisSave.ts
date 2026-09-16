import { useCallback, useRef, useState } from "react";
import { apiFetch } from "@/app/lib/api";


/**
 * Explicit save for the whole thesis — one PATCH per changed chapter.
 *
 * Two things were wrong with doing this per chapter. It fired on a 1s debounce
 * after every keystroke, which is a request per sentence per student for as
 * long as the tab is open. And the state lived inside each ChapterEditor, so
 * the editor — which stacks all five chapters as one continuous page — grew
 * five separate "Unsaved changes · Save" bars scattered down it, none of which
 * could answer the only question a student has: is my thesis saved?
 *
 * So the pending prose is keyed by chapter and the state is one set of flags.
 * `track()` records; `save()` sends every chapter that changed.
 *
 * Retries with exponential backoff (250ms / 1s / 4s) on network errors and
 * surfaces the failure after three attempts — losing a save matters more now
 * that saves are deliberate and further apart.
 */
export function useThesisSave({ projectId }: { projectId: string }) {
  const pending = useRef<Map<string, string>>(new Map());
  // What the SERVER holds for each chapter. Seeded when a chapter loads and
  // replaced on every successful save, so "what have I changed" can be answered
  // without re-fetching — the editor is the only place that knows both halves.
  const baseline = useRef<Map<string, string>>(new Map());
  // The API accepts this optional optimistic-concurrency token. Keeping it next
  // to the baseline means an older tab can never replace prose saved by a
  // pending-edit acceptance or another editor session.
  const fingerprints = useRef<Map<string, string>>(new Map());
  const saveInFlight = useRef<Promise<void> | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);
  // Separate from `pending`, which is drained for the duration of a save: this
  // is what the UI asks "is there anything to save?", and it must stay true
  // while a save is in flight so a failure does not read as clean.
  const [dirty, setDirty] = useState(false);

  const save = useCallback(async () => {
    // SaveBar disables itself while saving, but this guard also covers two
    // keyboard/programmatic submissions in the same React turn.
    if (saveInFlight.current) return saveInFlight.current;
    const run = async () => {
    if (pending.current.size === 0) return;
    // Drained, not read: anything typed while the request is in flight lands in
    // a fresh map and is still unsaved afterwards.
    const batch = [...pending.current.entries()].map(([chapterName, prose]) => ({
      chapterName,
      prose,
      fingerprint: fingerprints.current.get(chapterName),
    }));
    pending.current = new Map();
    setSaving(true);

    // Backoff delays in ms: 250ms before retry 2, 1s before retry 3. Each await
    // uses setTimeout so fake timers can drive retry timing in tests.
    const backoff = [250, 1000];
    const failed: [string, string][] = [];
    let lastErr: Error | null = null;

    for (const { chapterName, prose, fingerprint } of batch) {
      let ok = false;
      for (let i = 0; i < 3 && !ok; i++) {
        try {
          // apiFetch, NOT a raw fetch: the POST-only API reads the auth token
          // from the JSON body (no cookies). A bare fetch sent none, so every
          // save 401'd and NOTHING the user typed was persisted. apiFetch
          // folds the token in and throws on non-2xx (caught below to retry).
          const saved: any = await apiFetch(
            `/projects/${projectId}/m5/chapters/${chapterName}`,
            { method: "PATCH", body: {
              prose,
              ...(fingerprint ? { expected_document_fingerprint: fingerprint } : {}),
            } },
          );
          ok = true;
          baseline.current.set(chapterName, prose);
          if (typeof saved?.document_fingerprint === "string") {
            fingerprints.current.set(chapterName, saved.document_fingerprint);
          }
        } catch (e: any) {
          lastErr = e;
          // A 4xx is a real response, especially stale_document (409). Retrying
          // it would merely delay the conflict while keeping the student's local
          // prose safely queued for an intentional resolution.
          const retryable = typeof e?.status !== "number" || e.status >= 500;
          if (i < 2 && retryable) await new Promise(res => setTimeout(res, backoff[i]));
          if (!retryable) break;
        }
      }
      // A chapter that never landed goes BACK in the queue — after three
      // failures its text exists only inside the in-memory TipTap document, so
      // without this a retry found nothing to send and a reload lost it.
      // Anything typed since has already replaced it and wins, being newer.
      if (!ok) failed.push([chapterName, prose]);
    }

    for (const [name, prose] of failed) {
      if (!pending.current.has(name)) pending.current.set(name, prose);
    }
    setSaving(false);
    setError(lastErr && failed.length ? lastErr : null);
    if (failed.length === 0 && batch.length) setLastSavedAt(new Date());
    setDirty(pending.current.size > 0);
    };
    const promise = run();
    saveInFlight.current = promise;
    try {
      await promise;
    } finally {
      saveInFlight.current = null;
    }
  }, [projectId]);

  /** The chapter as the server has it. Called once, when it loads. */
  const seed = useCallback((chapterName: string, prose: string, fingerprint?: string) => {
    if (!baseline.current.has(chapterName)) baseline.current.set(chapterName, prose);
    if (fingerprint && !fingerprints.current.has(chapterName)) fingerprints.current.set(chapterName, fingerprint);
  }, []);

  /**
   * Adopt server prose only after the mounted editor has already decided that
   * it is safe to display it. This clears an older queued PATCH after an inline
   * action/acceptance, preventing a later document-wide Save from reverting it.
   */
  const reconcileServer = useCallback((chapterName: string, prose: string, fingerprint?: string) => {
    baseline.current.set(chapterName, prose);
    pending.current.delete(chapterName);
    if (fingerprint) fingerprints.current.set(chapterName, fingerprint);
    setDirty(pending.current.size > 0);
    setError(null);
  }, []);

  /** Update the saved base after a child-side inline PATCH while keeping prose
   * typed after that request in the pending queue. */
  const updateServerBaseline = useCallback((chapterName: string, prose: string, fingerprint?: string) => {
    baseline.current.set(chapterName, prose);
    if (fingerprint) fingerprints.current.set(chapterName, fingerprint);
    setDirty(pending.current.size > 0);
  }, []);

  /** Record an edit to one chapter. No request — that is what `save` is for. */
  const track = useCallback((chapterName: string, prose: string) => {
    const original = baseline.current.get(chapterName);
    if (original !== undefined && original === prose) {
      // Typed and undone, or TipTap re-serialising on mount: nothing to send,
      // and calling that "unsaved changes" trains the student to ignore the
      // warning that matters.
      pending.current.delete(chapterName);
      setDirty(pending.current.size > 0);
      return;
    }
    // Latest value wins: whatever is on screen is what Save sends.
    pending.current.set(chapterName, prose);
    setDirty(true);
  }, []);

  /** Every chapter that differs from what the server holds. */
  const changes = useCallback(
    (): { chapter: string; before: string; after: string }[] =>
      [...pending.current.entries()].map(([chapter, after]) => ({
        chapter, after, before: baseline.current.get(chapter) ?? "",
      })),
    []);

  return { seed, reconcileServer, updateServerBaseline, track, changes, save, saving, lastSavedAt, error, dirty };
}
