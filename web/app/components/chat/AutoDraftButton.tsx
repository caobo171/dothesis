import { Sparkles, Loader, CheckCircle2, AlertCircle, Play } from "lucide-react";


export type RunStatus =
  | null
  | "queued"
  | "running"
  | "paused"
  | "done"
  | "failed"
  | "canceled";


const _CONFIG: Record<string, { label: string; icon: typeof Sparkles; className: string }> = {
  none:     { label: "Auto-draft",         icon: Sparkles,    className: "bg-primary-600 hover:bg-primary-700 text-white" },
  // "ready" = all upstream modules done, no run yet. A soft ring + gentle
  // pulse turns the button into the obvious next action so the user reaches
  // for it instead of asking the chat to "write the whole thesis" (which
  // routes through the fragile conversational M5 path).
  ready:    { label: "Viết luận văn",      icon: Sparkles,    className: "bg-primary-600 hover:bg-primary-700 text-white ring-2 ring-primary-300 ring-offset-1 animate-pulse-soft" },
  running:  { label: "Auto-drafting…",     icon: Loader,      className: "bg-amber-500 hover:bg-amber-600 text-white" },
  paused:   { label: "Resume",             icon: Play,        className: "bg-amber-500 hover:bg-amber-600 text-white" },
  done:     { label: "Done · Download",    icon: CheckCircle2,className: "bg-green-600 hover:bg-green-700 text-white" },
  failed:   { label: "Failed · Retry",     icon: AlertCircle, className: "bg-red-600 hover:bg-red-700 text-white" },
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


export function AutoDraftButton({
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
  const title =
    cfg === _CONFIG.ready
      ? "Tất cả module đã xong — tạo luận văn hoàn chỉnh (DOCX + PDF)"
      : undefined;
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[13px] font-semibold transition-colors ${cfg.className}`}
    >
      <Icon className={`w-4 h-4 ${runStatus === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </button>
  );
}
