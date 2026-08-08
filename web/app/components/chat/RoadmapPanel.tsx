"use client";
import { useEffect, useState, useCallback } from "react";

import { apiFetch } from "@/app/lib/api";

export type Sub = { id: string; label: string; state: "done" | "current" | "upcoming" };
export type Mod = { id: string; status: string; current: string | null; substeps: Sub[] };
type NextAction = { module: string; substep: string; title: string; why: string; cta_options: string[] };
// F11: progress-vs-plan. {} (no keys) when the student hasn't set a defense date.
type Timeline = { this_week?: string; on_track?: boolean; weeks_behind?: number };
type Roadmap = {
  modules: Mod[]; tasks: any[]; next_action: NextAction | Record<string, never>;
  timeline?: Timeline;
};

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
/**
 * The roadmap fetch, shared.
 *
 * Lifted out of the panel because the per-module sub-steps now live ON the
 * module cards (ContextPanel's CtxSection) rather than in a second list under
 * this one — the panel used to render every module twice, once as a
 * strikethrough checklist here and once as a card below, which was most of the
 * scroll height for information the student had already read.
 */
export function useRoadmap(projectId: string | undefined, refreshKey = 0) {
  const [data, setData] = useState<Roadmap | null>(null);

  const load = useCallback(async () => {
    if (!projectId) return;
    try {
      const r = (await apiFetch(`/projects/${projectId}/roadmap`, { method: "POST" })) as Roadmap;
      if (r) setData(r);
    } catch {
      /* roadmap is non-critical; leave prior state rather than blanking the panel */
    }
  }, [projectId]);

  useEffect(() => { load(); }, [load, refreshKey]);
  return data;
}


export function RoadmapPanel({
  data, onSendMessage,
}: { data: Roadmap | null; onSendMessage?: (text: string) => void }) {
  if (!data) return null;
  const na = data.next_action as NextAction;
  const hasNext = na && "title" in na;

  return (
    <div className="flex flex-col gap-3" data-testid="roadmap-panel">
      {/* F11: you-are-here-vs-plan card. Only shown once the student has a
          timeline (defense date set) — keeps the plan visible every session. */}
      {data.timeline?.this_week && (
        <div className="rounded-xl border border-ink-200 p-3 text-[12.5px]" data-testid="timeline-card">
          <div className="font-semibold text-ink-800">This week: {data.timeline.this_week}</div>
          <div className={data.timeline.on_track ? "text-green-600" : "text-amber-600"}>
            {data.timeline.on_track ? "On track" : `~${data.timeline.weeks_behind} week(s) behind`}
          </div>
        </div>
      )}
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
    </div>
  );
}


/**
 * A module's sub-steps as one bar plus a count, for the module card header.
 *
 * Replaces the strikethrough checklist this panel used to print for all five
 * modules. On a finished thesis that was 23 struck-through lines the student
 * had to scroll past to reach the content — the same modules were already
 * listed below as cards, so the progress was stated twice and the detail was
 * only ever glanced at.
 *
 * The steps are still reachable: the title attribute lists them on hover, and
 * expanding the card shows them in full (see StepList).
 */
export function StepBar({ substeps }: { substeps: Sub[] }) {
  if (!substeps.length) return null;
  const done = substeps.filter(s => s.state === "done").length;
  const pct = Math.round((done / substeps.length) * 100);
  const current = substeps.find(s => s.state === "current");
  return (
    <span
      className="inline-flex items-center gap-1.5 shrink-0"
      // Hover detail without spending vertical space on it.
      title={substeps.map(s =>
        `${s.state === "done" ? "✓" : s.state === "current" ? "▸" : "·"} ${s.label}`
      ).join("\n")}
    >
      <span className="w-14 h-1 rounded-full bg-ink-100 overflow-hidden" aria-hidden>
        <span
          className={`block h-full transition-[width] duration-500 ${
            done === substeps.length ? "bg-emerald-500" : "bg-primary-600"}`}
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="text-[11px] text-ink-500 tabular-nums">
        {done}/{substeps.length}
      </span>
      <span className="sr-only">
        {current ? `Current step: ${current.label}` : `${done} of ${substeps.length} steps done`}
      </span>
    </span>
  );
}


/** The full sub-step list, shown when the module card is expanded. */
export function StepList({ substeps }: { substeps: Sub[] }) {
  if (!substeps.length) return null;
  return (
    <ul className="flex flex-col gap-0.5 mb-2.5 pb-2.5 border-b border-ink-100">
      {substeps.map((s) => (
        <li key={s.id} className={`text-[12px] ${
          s.state === "done" ? "text-ink-400"
          : s.state === "current" ? "text-primary-700 font-semibold"
          : "text-ink-500"}`}>
          {s.state === "done" ? "✓ " : s.state === "current" ? "▸ " : "· "}{s.label}
        </li>
      ))}
    </ul>
  );
}
