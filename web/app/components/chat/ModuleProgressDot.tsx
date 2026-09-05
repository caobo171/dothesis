import { Loader2 } from "lucide-react";

export type ModuleStatus = "done" | "active" | "locked" | "needs_attention";

// 2026-06-10 — DoThesis.html design: each module row gets a 34px serif
// status badge (✓ when done, the module number otherwise) with a status
// ring, instead of the old 8px dot. Status → palette mapping mirrors the
// design's StatusBadge (done green, active primary, locked muted, needs
// attention amber).
const BADGE_BY_STATUS: Record<ModuleStatus, string> = {
  done:            "bg-[var(--ok-fg)] text-white ring-4 ring-[#14854a]/15",
  active:          "bg-primary-600 text-white ring-4 ring-[#1c2eff]/15",
  locked:          "bg-ink-200 text-ink-500 ring-0",
  needs_attention: "bg-[var(--pause-bg)] text-[var(--pause-fg)] ring-4 ring-[#b7860b]/15",
};

const STATUS_LABEL: Record<ModuleStatus, string> = {
  done: "Done",
  active: "In progress",
  locked: "Locked",
  needs_attention: "Needs review",
};


export function ModuleProgressDot({
  module,
  status,
  label,
  detail,
  onClick,
  isLast,
}: {
  module: string;
  status: ModuleStatus;
  label: string;
  /**
   * What this module is doing RIGHT NOW, in place of the generic status word.
   *
   * On an unattended run "In progress" is the least informative thing the row
   * could say for the twenty minutes M2 spends searching — the live line ("42
   * sources, screening") is the only evidence the student has that anything is
   * happening.
   */
  detail?: string;
  onClick?: () => void;
  // Hides the vertical track segment after the final module row.
  isLast?: boolean;
}) {
  // The one row the student is waiting on. On a 20-minute unattended run this
  // is the whole question they have, and the only spinner used to be up beside
  // the page headline, nowhere near the step it described.
  const running = status === "active";
  // Waiting on the student. The run cannot clear this one itself, which is why
  // it must not keep spinning as though it could.
  const blocked = status === "needs_attention";
  return (
    <div className="relative">
      {/* vertical track connecting the badges, green once the module is done */}
      {!isLast && (
        <span
          aria-hidden
          className={`absolute left-[27px] top-[44px] bottom-[-2px] w-0.5 opacity-70 ${
            status === "done" ? "bg-[var(--ok-fg)]" : "bg-ink-200"
          }`}
        />
      )}
      <button
        type="button"
        onClick={onClick}
        className={`relative flex items-start gap-3 w-full text-left py-2 px-2.5 rounded-xl hover:bg-ink-50 transition-colors ${
          status === "locked" ? "opacity-60" : ""
        }`}
      >
        <span
          data-testid={`dot-${module}`}
          className={`w-[34px] h-[34px] min-w-[34px] rounded-[10px] inline-flex items-center justify-center font-serif font-extrabold text-xs tracking-[0.04em] ${BADGE_BY_STATUS[status]} ${
            running ? "animate-pulse" : ""
          }`}
        >
          {status === "done" ? "✓" : module}
        </span>
        <span className="flex flex-col min-w-0 pt-px">
          <span className="text-[13px] font-semibold text-ink-900 truncate flex items-center gap-1">
            {label}
            {status === "needs_attention" && <span aria-hidden>⚠</span>}
          </span>
          {/* The status word stays on every row, including this one. It used to
              be REPLACED by the activity line, which left the running step as
              the only row on screen that never said what state it was in: the
              locked rows below it said LOCKED and it said "tool: research_scout". */}
          <span className={`text-[10.5px] uppercase tracking-[0.06em] font-semibold mt-0.5 ${
            running ? "text-primary-600" : "text-ink-400"
          }`}>
            {STATUS_LABEL[status]}
          </span>
          {/* Running: what it is doing. Blocked: what it is waiting for. Not a
              finished module — that one kept the last beat it wrote, so three
              green ✓ rows sat there all reporting the same "saving this step"
              from minutes earlier. */}
          {detail && (running || blocked) && (
            <span
              data-testid={`${running ? "busy" : "blocked"}-${module}`}
              role="status"
              className={`mt-1 flex items-center gap-1.5 text-[11.5px] min-w-0 ${
                blocked ? "text-[var(--pause-fg)]" : "text-ink-500"
              }`}
            >
              {running
                ? <Loader2 className="w-3 h-3 shrink-0 animate-spin text-primary-600" aria-hidden />
                : <span className="shrink-0" aria-hidden>⚠</span>}
              <span className="truncate">{detail}</span>
            </span>
          )}
        </span>
      </button>
    </div>
  );
}
