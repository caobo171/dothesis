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
  onClick,
  isLast,
}: {
  module: string;
  status: ModuleStatus;
  label: string;
  onClick?: () => void;
  // Hides the vertical track segment after the final module row.
  isLast?: boolean;
}) {
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
          className={`w-[34px] h-[34px] min-w-[34px] rounded-[10px] inline-flex items-center justify-center font-serif font-extrabold text-xs tracking-[0.04em] ${BADGE_BY_STATUS[status]}`}
        >
          {status === "done" ? "✓" : module}
        </span>
        <span className="flex flex-col min-w-0 pt-px">
          <span className="text-[13px] font-semibold text-ink-900 truncate flex items-center gap-1">
            {label}
            {status === "needs_attention" && <span aria-hidden>⚠</span>}
          </span>
          <span className="text-[10.5px] text-ink-400 uppercase tracking-[0.06em] font-semibold mt-0.5">
            {STATUS_LABEL[status]}
          </span>
        </span>
      </button>
    </div>
  );
}
