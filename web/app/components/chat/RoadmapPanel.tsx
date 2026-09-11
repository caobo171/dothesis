"use client";
import { useEffect, useState, useCallback } from "react";

import { apiFetch } from "@/app/lib/api";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";

/**
 * Backend id -> message key, written out rather than built as
 * `roadmap.substep.${id}`.
 *
 * A template literal is not a MessageKey, so the whole point of the typed
 * catalogue — a missing translation failing the BUILD — would be lost, and a
 * new spine step would reach a student as the raw key instead. Spelled out,
 * `tsc` rejects a typo here and an id with no entry falls back to the English
 * label the API already sends.
 */
const SUBSTEP_KEY: Record<string, MessageKey> = {
  frame_topic: "roadmap.substep.frame_topic",
  propose_titles: "roadmap.substep.propose_titles",
  confirm_title: "roadmap.substep.confirm_title",
  derive_questions: "roadmap.substep.derive_questions",
  familiarize: "roadmap.substep.familiarize",
  map_research_state: "roadmap.substep.map_research_state",
  find_gaps: "roadmap.substep.find_gaps",
  generate_output: "roadmap.substep.generate_output",
  define_constructs: "roadmap.substep.define_constructs",
  build_model: "roadmap.substep.build_model",
  state_hypotheses: "roadmap.substep.state_hypotheses",
  choose_method: "roadmap.substep.choose_method",
  design_instrument: "roadmap.substep.design_instrument",
  detect_data: "roadmap.substep.detect_data",
  outline_analysis: "roadmap.substep.outline_analysis",
  confirm_plan: "roadmap.substep.confirm_plan",
  run_per_step: "roadmap.substep.run_per_step",
  interpret: "roadmap.substep.interpret",
  write_conclusion: "roadmap.substep.write_conclusion",
  export: "roadmap.substep.export",
};

export const MODULE_KEY: Record<string, MessageKey> = {
  M1: "roadmap.module.M1", M2: "roadmap.module.M2", M3: "roadmap.module.M3",
  M4: "roadmap.module.M4", M5: "roadmap.module.M5",
};

/** Localized step label, falling back to whatever the API called it. */
export function useSubstepLabel() {
  const t = useT();
  return (sub: { id: string; label: string }) => {
    const key = SUBSTEP_KEY[sub.id];
    return key ? t(key) : sub.label;
  };
}

export type Sub = { id: string; label: string; state: "done" | "current" | "upcoming" };
export type Mod = { id: string; status: string; current: string | null; substeps: Sub[] };
type NextKind = "blocker" | "substep" | "confirm_module" | "next_module" | "all_done";
// `title` / `why` / `cta_options` are the API's English strings. They stay in
// the type because a `blocker` is agent-authored prose with no translation to
// find, and because an older API without `kind` must still render.
type NextAction = {
  kind?: NextKind; module: string; substep: string;
  title: string; why: string; cta_options: string[];
};
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
/**
 * @param intervalMs poll while > 0. Off by default.
 *
 * Auto Thesis writes the whole context_store from a subprocess, over twenty
 * minutes, and nothing on this page would ever hear about it: the roadmap
 * loaded once on mount and then sat there. So the right rail told a student to
 * "Confirm M3 is done" while the run was doing M3, and never showed the blocker
 * M4 raised afterwards.
 */
export function useRoadmap(projectId: string | undefined, refreshKey = 0, intervalMs = 0) {
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

  useEffect(() => {
    if (!intervalMs) return;
    const id = setInterval(() => { void load(); }, intervalMs);
    return () => clearInterval(id);
  }, [load, intervalMs]);

  return data;
}


/**
 * Rebuild the Next card in the reader's language from `kind` + the ids.
 *
 * The API composes an English sentence ("M3 has all its content — confirm it so
 * we move on"). That string is still needed there — the per-turn [NEXT] prompt
 * and the headless/partner surfaces read it — so it is not translated at the
 * source; it is RE-composed here from the same parts.
 *
 * A `blocker` is the deliberate exception: its title and why are written by the
 * agent for one situation, so there is no key to look up and the English is
 * passed through. Only its CTAs, which are fixed, get translated.
 */
function useNextCopy() {
  const t = useT();
  const substepLabel = useSubstepLabel();
  return (na: NextAction) => {
    const m = na.module;
    const mod = MODULE_KEY[m] ? t(MODULE_KEY[m]) : m;
    // Module CTAs read better with the bare id ("Start M4") than the full
    // title ("Start M4 · Analysis"), so those interpolate `m`, not `mod`.
    const step = na.substep
      ? substepLabel({ id: na.substep, label: na.title })
      : na.title;
    switch (na.kind) {
      case "substep":
        return { title: step, why: t("roadmap.next.why.substep"),
                 ctas: [step, t("roadmap.next.cta.skipModule")] };
      case "confirm_module":
        return { title: t("roadmap.next.title.confirm", { module: m }),
                 why: t("roadmap.next.why.confirm", { module: mod }),
                 ctas: [t("roadmap.next.cta.markDone", { module: m }),
                        t("roadmap.next.cta.notYet")] };
      case "next_module":
        return { title: step,
                 why: t("roadmap.next.why.nextModule", { focus: na.module, module: mod }),
                 ctas: [t("roadmap.next.cta.start", { module: m }),
                        t("roadmap.next.cta.whatInvolves", { module: m })] };
      case "all_done":
        return { title: t("roadmap.next.title.allDone"),
                 why: t("roadmap.next.why.allDone"),
                 ctas: [t("roadmap.next.cta.export"), t("roadmap.next.cta.defense"),
                        t("roadmap.next.cta.review")] };
      case "blocker":
        return { title: na.title, why: na.why,
                 ctas: [t("roadmap.next.cta.fix"), t("roadmap.next.cta.skipForNow")] };
      default:
        // No `kind`: an API older than this panel. Render what it sent.
        return { title: na.title, why: na.why, ctas: na.cta_options };
    }
  };
}

export function RoadmapPanel({
  data, onSendMessage,
}: { data: Roadmap | null; onSendMessage?: (text: string) => void }) {
  const t = useT();
  const nextCopy = useNextCopy();
  if (!data) return null;
  const na = data.next_action as NextAction;
  const hasNext = na && "title" in na;
  const copy = hasNext ? nextCopy(na) : null;

  return (
    <div className="flex flex-col gap-3" data-testid="roadmap-panel">
      {/* F11: you-are-here-vs-plan card. Only shown once the student has a
          timeline (defense date set) — keeps the plan visible every session. */}
      {data.timeline?.this_week && (
        <div className="rounded-xl border border-ink-200 p-3 text-[12.5px]" data-testid="timeline-card">
          <div className="font-semibold text-ink-800">
            {t("roadmap.timeline.thisWeek", { what: data.timeline.this_week })}
          </div>
          <div className={data.timeline.on_track ? "text-green-600" : "text-amber-600"}>
            {data.timeline.on_track
              ? t("roadmap.timeline.onTrack")
              : t("roadmap.timeline.behind", { weeks: data.timeline.weeks_behind ?? 0 })}
          </div>
        </div>
      )}
      {hasNext && (
        <div className="rounded-xl border border-primary-200 bg-primary-50 p-3">
          <div className="text-[10.5px] uppercase tracking-[0.08em] text-primary-700 font-semibold">
            {t("roadmap.next.label")}
          </div>
          <div className="text-[13.5px] font-semibold text-ink-900 mt-1">{copy!.title}</div>
          <div className="text-[12px] text-ink-600 mt-0.5">{copy!.why}</div>
          {onSendMessage && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {copy!.ctas.map((c, i) => (
                // Send the API's original English: the agent's [NEXT] contract
                // and its tool routing are written against those exact phrases,
                // so translating the wire message would break the click.
                <button key={c} type="button"
                  onClick={() => onSendMessage(na.cta_options[i] ?? c)}
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
  const t = useT();
  const label = useSubstepLabel();
  if (!substeps.length) return null;
  const done = substeps.filter(s => s.state === "done").length;
  const pct = Math.round((done / substeps.length) * 100);
  const current = substeps.find(s => s.state === "current");
  return (
    <span
      className="inline-flex items-center gap-1.5 shrink-0"
      // Hover detail without spending vertical space on it.
      title={substeps.map(s =>
        `${s.state === "done" ? "✓" : s.state === "current" ? "▸" : "·"} ${label(s)}`
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
        {current
          ? t("roadmap.steps.current", { label: label(current) })
          : t("roadmap.steps.done", { done, total: substeps.length })}
      </span>
    </span>
  );
}


/** The full sub-step list, shown when the module card is expanded. */
export function StepList({ substeps }: { substeps: Sub[] }) {
  const label = useSubstepLabel();
  if (!substeps.length) return null;
  return (
    <ul className="flex flex-col gap-0.5 mb-2.5 pb-2.5 border-b border-ink-100">
      {substeps.map((s) => (
        <li key={s.id} className={`text-[12px] ${
          s.state === "done" ? "text-ink-400"
          : s.state === "current" ? "text-primary-700 font-semibold"
          : "text-ink-500"}`}>
          {s.state === "done" ? "✓ " : s.state === "current" ? "▸ " : "· "}{label(s)}
        </li>
      ))}
    </ul>
  );
}
