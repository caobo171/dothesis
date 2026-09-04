"use client";

/**
 * ImportSummary — the mid-journey activation card (F12 Task 3).
 *
 * After a returning student drops their existing work, the server-side import
 * route (POST /projects/{id}/mid-journey-import) reports which modules it could
 * reconstruct, where the student now stands (focus), and any files it couldn't
 * auto-slot. This card turns that into the first-session payoff: "here's where
 * you are, next do X" — instead of dropping them at a blank M1.
 *
 * Purely presentational: the page owns the import call and the continue action.
 */

const MODULE_LABELS: Record<string, string> = {
  M1: "Topic",
  M2: "Literature",
  M3: "Design",
  M4: "Analysis",
  M5: "Discussion & Conclusion",
};

const label = (m: string) => MODULE_LABELS[m] ?? m;

export type ImportSummaryProps = {
  imported: string[]; // module ids reconstructed from uploads, e.g. ["M1","M3"]
  focus: string; // module id the student now stands at, e.g. "M2"
  ambiguous?: string[]; // filenames we couldn't confidently slot (e.g. raw datasets)
  unreadable?: string[]; // filenames with no extractable text
  onContinue?: () => void;
  /** Reconstruction still running below. It decides which module the student
   *  lands on, so the button waits for it rather than sending them to a focus
   *  that's about to change. */
  reconstructing?: boolean;
  /** How far the reconstruction has got, once it has counted its modules.
   *  Null while it hasn't — a bare spinner beats a misleading 0/0. */
  progress?: { done: number; total: number } | null;
  /** Modules the backfill reconstructed and saved. */
  reconstructed?: string[];
};

export function ImportSummary({
  imported,
  focus,
  ambiguous = [],
  unreadable = [],
  onContinue,
  reconstructing = false,
  progress = null,
  reconstructed = [],
}: ImportSummaryProps) {
  const importedLabels = imported.map(label).join(", ");

  return (
    <div
      role="region"
      aria-label="Import summary"
      className="rounded-2xl border border-ink-200 bg-white p-5 flex flex-col gap-3"
    >
      <div className="text-[15px] font-bold text-ink-900">
        {imported.length > 0
          ? "We picked up where you left off"
          : "Ready when you are"}
      </div>

      {imported.length > 0 && (
        <p className="text-[13px] text-ink-700 m-0">
          <span className="font-semibold">Imported:</span>{" "}
          {imported.map((m) => `${m} (${label(m)})`).join(", ")}
          {" · "}
          <span className="font-semibold">You&apos;re at:</span> {focus} ({label(focus)})
          {" · "}
          <span className="font-semibold">Next:</span> {label(focus)}
        </p>
      )}

      {imported.length === 0 && (
        <p className="text-[13px] text-ink-700 m-0">
          Nothing to import yet — we&apos;ll start you at {focus} ({label(focus)}).
        </p>
      )}

      {/* The reconstructed steps COUNT — they're saved as done and the focus
          above has already moved past them. Say both, because a student who
          imported an M4 and is now told they're at M4 needs to know the earlier
          chapters exist rather than assuming we skipped them. */}
      {reconstructed.length > 0 && (
        <p className="text-[12.5px] text-ink-600 m-0 rounded-lg bg-green-50 border border-green-200 px-3 py-2">
          <span className="font-semibold text-green-800">
            Reconstructed: {reconstructed.map((m) => `${m} (${label(m)})`).join(", ")}
          </span>
          {" — "}
          filled in from your own work and saved, which is why you pick up at{" "}
          {focus} ({label(focus)}). Ask in chat to change any of it.
        </p>
      )}

      {ambiguous.length > 0 && (
        <p className="text-[12.5px] text-ink-500 m-0">
          Couldn&apos;t auto-place: {ambiguous.join(", ")} — tell us in chat where these fit.
        </p>
      )}

      {unreadable.length > 0 && (
        <p className="text-[12.5px] text-ink-500 m-0">
          Couldn&apos;t read: {unreadable.join(", ")}.
        </p>
      )}

      {onContinue && (
        <button
          type="button"
          onClick={onContinue}
          disabled={reconstructing}
          aria-busy={reconstructing}
          className="self-start mt-1 rounded-xl bg-primary-600 px-4 py-2 text-[13px] font-bold text-white hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:bg-primary-600 inline-flex items-center gap-2"
        >
          {reconstructing && (
            <span
              aria-hidden="true"
              className="w-3.5 h-3.5 rounded-full border-2 border-white/40 border-t-white animate-spin"
            />
          )}
          {reconstructing
            ? progress && progress.total > 0
              // Grounding made this a minute-plus of real search, and a spinner
              // with no number is what makes a student reload the page — which
              // pays for the whole reconstruction a second time.
              ? `Reconstructing… ${progress.done}/${progress.total}`
              : "Reconstructing…"
            : `Continue to ${label(focus)} →`}
        </button>
      )}
      {reconstructing && progress && progress.total > 0 && (
        <div
          className="h-1 w-full max-w-[220px] rounded-full bg-ink-100 overflow-hidden"
          role="progressbar"
          aria-valuenow={progress.done}
          aria-valuemin={0}
          aria-valuemax={progress.total}
        >
          <div
            className="h-full bg-primary-600 transition-[width] duration-500"
            style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }}
          />
        </div>
      )}

      {/* aria-hidden marker kept simple: importedLabels available for future summaries */}
      <span className="sr-only">{importedLabels}</span>
    </div>
  );
}
