"use client";
import { useEffect, useState, useCallback } from "react";

import { apiFetch } from "@/app/lib/api";

type Sub = { id: string; label: string; state: "done" | "current" | "upcoming" };
type Mod = { id: string; status: string; current: string | null; substeps: Sub[] };
type NextAction = { module: string; substep: string; title: string; why: string; cta_options: string[] };
type Roadmap = { modules: Mod[]; tasks: any[]; next_action: NextAction | Record<string, never> };

/**
 * Derived coaching roadmap (F2 Task 7). Fetches POST /projects/{id}/roadmap on
 * mount and whenever `refreshKey` changes (parent bumps it on each turn's `done`
 * SSE event). Renders the single Next action + per-module sub-steps.
 *
 * Uses the shared authed POST helper (apiFetch) — not raw fetch — so the token
 * rides in the body per the POST-only convention (F0 Part C). `onSendMessage` is
 * optional: when the host can post into chat, the Next CTAs become one-click
 * actions; otherwise the card is read-only visibility (the agent still leads via
 * the injected [NEXT] line).
 */
export function RoadmapPanel({
  projectId, onSendMessage, refreshKey = 0,
}: { projectId: string; onSendMessage?: (text: string) => void; refreshKey?: number }) {
  const [data, setData] = useState<Roadmap | null>(null);

  const load = useCallback(async () => {
    try {
      const r = (await apiFetch(`/projects/${projectId}/roadmap`, { method: "POST" })) as Roadmap;
      if (r) setData(r);
    } catch {
      /* roadmap is non-critical; leave prior state rather than blanking the panel */
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);

  if (!data) return null;
  const na = data.next_action as NextAction;
  const hasNext = na && "title" in na;

  return (
    <div className="flex flex-col gap-3" data-testid="roadmap-panel">
      {hasNext && (
        <div className="rounded-xl border border-primary-200 bg-primary-50 p-3">
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-primary-700 font-semibold">Next</div>
          <div className="text-[13.5px] font-semibold text-ink-900 mt-1">{na.title}</div>
          <div className="text-[12px] text-ink-600 mt-0.5">{na.why}</div>
          {onSendMessage && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {na.cta_options.map((c) => (
                <button key={c} type="button" onClick={() => onSendMessage(c)}
                  className="px-2.5 py-1 rounded-full bg-primary-600 text-white text-[12px] font-semibold hover:bg-primary-700">
                  {c}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {data.modules.map((m) => (
        <div key={m.id} className="text-[12.5px]">
          <div className="font-semibold text-ink-800">{m.id} · {m.status}</div>
          <ul className="mt-1 ml-2 flex flex-col gap-0.5">
            {m.substeps.map((s) => (
              <li key={s.id} className={
                s.state === "done" ? "text-ink-400 line-through"
                : s.state === "current" ? "text-primary-700 font-semibold"
                : "text-ink-500"}>
                {s.state === "done" ? "✓ " : s.state === "current" ? "▸ " : "· "}{s.label}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
