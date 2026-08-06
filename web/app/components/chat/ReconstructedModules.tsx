"use client";

/**
 * ReconstructedModules — what the backfill filled in, already saved.
 *
 * Shared by BOTH surfaces (single source of truth for the "we reconstructed an
 * earlier step" UX):
 *   - the /new activation card (mid-journey import), and
 *   - the in-thread chat widget (agent-triggered backfill).
 *
 * This used to be an editable form gated behind per-module Confirm/Skip: every
 * card said "Suggested — not saved yet" and nothing counted until the student
 * approved each one. That gate is gone. The reconstruction is inferred from the
 * student's OWN work, so making them re-approve it was asking them to sign off
 * on what they had already done — and the form under it rendered structured
 * fields (conceptual_model, research_gaps) as raw JSON, which is not something
 * anyone can meaningfully review anyway.
 *
 * So: the server saves, this reports. It renders through ModuleBody — the same
 * renderers as the chat context panel, mermaid model diagram included — so a
 * backfilled M3 looks exactly like an M3 the student built step by step. To
 * change anything, they ask in chat.
 */
import { ModuleBody } from "./ModuleSlices";

const MODULE_LABELS: Record<string, string> = {
  M1: "Topic",
  M2: "Literature",
  M3: "Design",
  M4: "Analysis",
  M5: "Writing",
};
const label = (m: string) => MODULE_LABELS[m] ?? m;

export type ReconstructedModule = {
  module: string;
  candidate: Record<string, unknown>;
  rationale?: string | null;
  ready_to_confirm: boolean;
  review: string[];
};

/** What the server actually committed, per module. */
export type SavedModule = {
  module: string;
  status: string; // "done" | "in_progress"
};

export type ReconstructedModulesProps = {
  items: ReconstructedModule[];
  reconstructing?: boolean; // show skeleton rows while the LLM infers
  saved?: SavedModule[];
};

function ModuleCard({
  item,
  status,
}: {
  item: ReconstructedModule;
  status?: string;
}) {
  // A backfill too thin to earn a `done` still saved — say which it was rather
  // than drawing every card the same green tick. `undefined` means the caller
  // didn't report per-module results (the /new card before the save lands).
  const partial = status === "in_progress";
  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[13px] font-bold text-ink-900">
          {item.module} · {label(item.module)}
        </div>
        <span
          className={
            partial
              ? "text-[11px] font-semibold text-amber-700 bg-amber-50 rounded px-1.5 py-0.5"
              : "text-[11px] font-bold text-green-700"
          }
        >
          {partial ? "Saved — still thin" : "✓ Saved"}
        </span>
      </div>

      {item.rationale && (
        <p className="text-[12px] text-ink-500 m-0 italic">Why: {item.rationale}</p>
      )}

      <ModuleBody module={item.module} data={item.candidate as Record<string, any>} />

      {item.review.length > 0 && (
        <p className="text-[11.5px] text-ink-400 m-0">
          Still thin: {item.review.join(", ")} — ask in chat to fill these in.
        </p>
      )}
    </div>
  );
}

export function ReconstructedModules({
  items,
  reconstructing = false,
  saved = [],
}: ReconstructedModulesProps) {
  if (!reconstructing && items.length === 0) return null;
  const statusOf = new Map(saved.map((s) => [s.module, s.status]));

  return (
    <div
      role="region"
      aria-label="Reconstructed modules"
      className="flex flex-col gap-2"
    >
      <div className="text-[13px] font-bold text-ink-900">
        Earlier steps we reconstructed — saved and counted
      </div>
      <p className="text-[12px] text-ink-500 m-0">
        Built from the work you imported. Want any of it changed? Just say so in chat.
      </p>

      {reconstructing && items.length === 0 && (
        <div className="rounded-xl border border-ink-200 bg-white p-4 text-[12.5px] text-ink-500 flex items-center gap-2.5">
          {/* A bare line of grey text read as an empty box — several seconds of
              silence with nothing moving looks like a failed load. A spinner is
              the difference between "working" and "broken". */}
          <span
            aria-hidden="true"
            className="w-4 h-4 shrink-0 rounded-full border-2 border-ink-200 border-t-primary-600 animate-spin"
          />
          Reconstructing earlier steps from what you imported…
        </div>
      )}

      {items.map((item) => (
        <ModuleCard
          key={item.module}
          item={item}
          status={statusOf.get(item.module)}
        />
      ))}
    </div>
  );
}
