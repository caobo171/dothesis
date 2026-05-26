"use client";

import { useMemo } from "react";
import useSWR from "swr";
import { X, Pause, Play, XCircle } from "lucide-react";
import { ModuleProgressDot, type ModuleStatus } from "./ModuleProgressDot";
import { useAutoDraftRun } from "./hooks/useAutoDraftRun";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};

const MODULES = [
  { module: "M1", label: "Topic Discovery" },
  { module: "M2", label: "Literature Review" },
  { module: "M3", label: "Research Design" },
  { module: "M4", label: "Data Analysis" },
  { module: "M5", label: "Writing" },
];


export function AutoDraftDrawer({ runId, onClose }: { runId: string; onClose: () => void }) {
  const { data: run, mutate: mutateRun } = useSWR(`/runs/${runId}`, fetcher, { refreshInterval: 5000 });
  const { events } = useAutoDraftRun(runId);

  const statusByModule = useMemo(() => {
    // Default all modules to locked; update as events arrive
    const status: Record<string, ModuleStatus> = {
      M1: "locked", M2: "locked", M3: "locked", M4: "locked", M5: "locked",
    };
    for (const ev of events) {
      const m = (ev as { module?: string }).module;
      if (!m) continue;
      if (ev.type === "module_complete") status[m] = "done";
      else if (ev.type === "activity" && status[m] === "locked") status[m] = "active";
    }
    return status;
  }, [events]);

  const activity = events.filter(e => e.type === "activity").slice(-50);
  const tokenCost = events.filter(e => e.type === "token_cost")
    .reduce((acc, e) => acc + ((e as { tokens?: number }).tokens ?? 0), 0);
  const exports = events.find(e => e.type === "job_done") as { exports?: Record<string, string> } | undefined;

  const pause  = async () => { await fetch(`/api/v1/runs/${runId}/pause`,  { method: "POST" }); void mutateRun(); };
  const resume = async () => { await fetch(`/api/v1/runs/${runId}/resume`, { method: "POST" }); void mutateRun(); };
  const cancel = async () => { await fetch(`/api/v1/runs/${runId}/cancel`, { method: "POST" }); void mutateRun(); };

  return (
    <aside className="fixed right-0 top-14 bottom-0 w-[480px] bg-white border-l border-gray-200 shadow-xl z-40 flex flex-col">
      <header className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Run {runId.slice(0, 8)}</h3>
          <p className="text-xs text-gray-500">Status: {run?.status ?? "loading…"}</p>
        </div>
        <button type="button" onClick={onClose} aria-label="close drawer">
          <X className="w-5 h-5 text-gray-500" />
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mb-2">Progress</h4>
        {MODULES.map(m => (
          <ModuleProgressDot
            key={m.module}
            module={m.module}
            label={m.label}
            status={statusByModule[m.module]}
          />
        ))}

        <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold mt-6 mb-2">
          Activity feed
        </h4>
        <div className="bg-gray-50 rounded-md p-3 text-xs space-y-1 max-h-64 overflow-y-auto font-mono">
          {activity.map((ev, i) => (
            <div key={i} className="text-gray-700">
              <span className="text-purple-600 mr-2">{(ev as { module?: string }).module ?? "•"}</span>
              {(ev as { text?: string }).text ?? JSON.stringify(ev)}
            </div>
          ))}
        </div>

        {tokenCost > 0 && (
          <div className="mt-4 text-xs text-gray-600">
            Tokens used: <span className="font-medium">{tokenCost.toLocaleString()}</span>
          </div>
        )}

        {exports?.exports && (
          <div className="mt-6 space-y-2">
            <h4 className="text-xs uppercase tracking-wider text-gray-500 font-semibold">Exports</h4>
            {Object.entries(exports.exports).map(([kind, uri]) => (
              <a
                key={kind}
                href={uri as string}
                className="block text-sm text-purple-600 hover:underline"
              >
                Download {kind.toUpperCase()}
              </a>
            ))}
          </div>
        )}
      </div>

      <footer className="px-6 py-3 border-t border-gray-200 flex gap-2">
        {run?.status === "running" && (
          <button onClick={pause} className="flex items-center gap-1 text-sm text-gray-700 hover:bg-gray-100 px-3 py-1.5 rounded">
            <Pause className="w-4 h-4" /> Pause
          </button>
        )}
        {run?.status === "paused" && (
          <button onClick={resume} className="flex items-center gap-1 text-sm bg-purple-600 text-white hover:bg-purple-700 px-3 py-1.5 rounded">
            <Play className="w-4 h-4" /> Resume
          </button>
        )}
        {(run?.status === "running" || run?.status === "paused") && (
          <button onClick={cancel} className="flex items-center gap-1 text-sm text-red-600 hover:bg-red-50 px-3 py-1.5 rounded ml-auto">
            <XCircle className="w-4 h-4" /> Cancel
          </button>
        )}
      </footer>
    </aside>
  );
}
