import { Sparkles, Loader, CheckCircle2, AlertCircle, Play } from "lucide-react";


export type RunStatus =
  | null
  | "queued"
  | "running"
  | "paused"
  | "done"
  | "failed"
  | "canceled";

/**
 * A run that is still going, so the surfaces around it have to keep up: the
 * right rail re-reads the project while one of these is true, because the run
 * commits each module's slice from a subprocess and nothing else would say so.
 * Lives here with RunStatus rather than in a component, so importing it does
 * not drag a whole pane behind it.
 */
export const LIVE_RUN_STATUSES: ReadonlySet<string> = new Set([
  "queued", "running", "paused",
]);


// Tooltip shown on every state so the user knows what the button does before
// clicking — it kicks off the fully-automatic ("auto-approve") run that writes
// the whole thesis end-to-end without step-by-step approval.
const _TOOLTIP_IDLE =
  "Tự động viết toàn bộ luận văn hoàn chỉnh (6 chương từ M1–M4), tổng hợp " +
  "trích dẫn và xuất file Word + PDF — chạy tự động, bạn không phải duyệt từng bước.";

const _CONFIG: Record<string, { label: string; icon: typeof Sparkles; className: string; tooltip: string }> = {
  none:     { label: "Auto Thesis",       icon: Sparkles,    className: "bg-primary-600 hover:bg-primary-700 text-white", tooltip: _TOOLTIP_IDLE },
  // "ready" = all upstream modules done, no run yet. A soft ring + gentle
  // pulse turns the button into the obvious next action so the user reaches
  // for it instead of asking the chat to "write the whole thesis" (which
  // routes through the fragile conversational M5 path).
  ready:    { label: "Auto Thesis",       icon: Sparkles,    className: "bg-primary-600 hover:bg-primary-700 text-white ring-2 ring-primary-300 ring-offset-1 animate-pulse-soft", tooltip: "Tất cả module đã xong — " + _TOOLTIP_IDLE },
  running:  { label: "Đang viết…",         icon: Loader,      className: "bg-amber-500 hover:bg-amber-600 text-white", tooltip: "Đang tự động viết luận văn — quá trình này mất vài phút." },
  paused:   { label: "Resume",             icon: Play,        className: "bg-amber-500 hover:bg-amber-600 text-white", tooltip: "Lần chạy đang tạm dừng — bấm để tiếp tục." },
  done:     { label: "Done · Download",    icon: CheckCircle2,className: "bg-green-600 hover:bg-green-700 text-white", tooltip: "Luận văn đã sẵn sàng — tải file Word/PDF." },
  failed:   { label: "Failed · Retry",     icon: AlertCircle, className: "bg-red-600 hover:bg-red-700 text-white", tooltip: "Lần chạy trước thất bại — bấm để thử lại." },
};


function pick(status: RunStatus, ready: boolean) {
  // queued and canceled both show the default idle state
  if (status === "running") return _CONFIG.running;
  if (status === "paused") return _CONFIG.paused;
  if (status === "done")   return _CONFIG.done;
  if (status === "failed") return _CONFIG.failed;
  // Idle: highlight only when upstream work is complete.
  return ready ? _CONFIG.ready : _CONFIG.none;
}


export function AutoThesisButton({
  runStatus,
  onClick,
  ready = false,
}: {
  runStatus: RunStatus;
  onClick: () => void;
  /** True when M1–M4 are all done and no run is in flight — drives the
   *  "ready to draft" highlight. */
  ready?: boolean;
}) {
  const cfg = pick(runStatus, ready);
  const Icon = cfg.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      title={cfg.tooltip}
      className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[13px] font-semibold transition-colors ${cfg.className}`}
    >
      <Icon className={`w-4 h-4 ${runStatus === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </button>
  );
}
