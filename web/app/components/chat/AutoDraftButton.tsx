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
  running:  { label: "Auto-drafting…",     icon: Loader,      className: "bg-amber-500 hover:bg-amber-600 text-white" },
  paused:   { label: "Resume",             icon: Play,        className: "bg-amber-500 hover:bg-amber-600 text-white" },
  done:     { label: "Done · Download",    icon: CheckCircle2,className: "bg-green-600 hover:bg-green-700 text-white" },
  failed:   { label: "Failed · Retry",     icon: AlertCircle, className: "bg-red-600 hover:bg-red-700 text-white" },
};


function pick(status: RunStatus) {
  // queued and canceled both show the default "Auto-draft" idle state
  if (status === "running") return _CONFIG.running;
  if (status === "paused") return _CONFIG.paused;
  if (status === "done")   return _CONFIG.done;
  if (status === "failed") return _CONFIG.failed;
  return _CONFIG.none;
}


export function AutoDraftButton({ runStatus, onClick }: { runStatus: RunStatus; onClick: () => void }) {
  const cfg = pick(runStatus);
  const Icon = cfg.icon;
  return (
    <button
      type="button"
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-[13px] font-semibold transition-colors ${cfg.className}`}
    >
      <Icon className={`w-4 h-4 ${runStatus === "running" ? "animate-spin" : ""}`} />
      {cfg.label}
    </button>
  );
}
