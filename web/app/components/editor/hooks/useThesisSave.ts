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
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);
  // Separate from `pending`, which is drained for the duration of a save: this
  // is what the UI asks "is there anything to save?", and it must stay true
  // while a save is in flight so a failure does not read as clean.
  const [dirty, setDirty] = useState(false);

  const save = useCallback(async () => {
    if (pending.current.size === 0) return;
    // Drained, not read: anything typed while the request is in flight lands in
    // a fresh map and is still unsaved afterwards.
    const batch = [...pending.current.entries()];
    pending.current = new Map();
    setSaving(true);

    // Backoff delays in ms: 250ms before retry 2, 1s before retry 3. Each await
    // uses setTimeout so fake timers can drive retry timing in tests.
    const backoff = [250, 1000];
    const failed: [string, string][] = [];
    let lastErr: Error | null = null;

    for (const [chapterName, prose] of batch) {
      let ok = false;
      for (let i = 0; i < 3 && !ok; i++) {
        try {
          // apiFetch, NOT a raw fetch: the POST-only API reads the auth token
          // from the JSON body (no cookies). A bare fetch sent none, so every
          // save 401'd and NOTHING the user typed was persisted. apiFetch
          // folds the token in and throws on non-2xx (caught below to retry).
          await apiFetch(
            `/projects/${projectId}/m5/chapters/${chapterName}`,
            { method: "PATCH", body: { prose } },
          );
          ok = true;
          baseline.current.set(chapterName, prose);
        } catch (e: any) {
          lastErr = e;
          if (i < 2) await new Promise(res => setTimeout(res, backoff[i]));
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
  }, [projectId]);

  /** The chapter as the server has it. Called once, when it loads. */
  const seed = useCallback((chapterName: string, prose: string) => {
    if (!baseline.current.has(chapterName)) baseline.current.set(chapterName, prose);
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

  return { seed, track, changes, save, saving, lastSavedAt, error, dirty };
}
