"use client";

/**
 * ReconstructedModules — editable confirm/skip cards for backfilled modules.
 *
 * Shared by BOTH surfaces (single source of truth for the "review a
 * reconstructed prerequisite" UX):
 *   - the /new activation card (mid-journey import), and
 *   - the in-thread chat widget (agent-triggered backfill).
 *
 * The candidate fields were INFERRED from the student's existing work, so every
 * card is explicitly "Suggested — not saved yet": the student edits and Confirms
 * (persist as in_progress, reviewable) or Skips (discard — nothing persisted).
 * The parent owns the confirm call; this component owns only the edit buffer.
 */
import { useState } from "react";

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

export type ReconstructedModulesProps = {
  items: ReconstructedModule[];
  reconstructing?: boolean; // show skeleton rows while the LLM infers
  confirmedModules?: string[];
  skippedModules?: string[];
  onConfirm: (module: string, edited: Record<string, unknown>) => Promise<void> | void;
  onSkip?: (module: string) => void;
};

// A field the user can edit inline. Strings and string-arrays are editable;
// nested objects (e.g. conceptual_model) are shown read-only with a hint to
// refine them in chat — a form can't sensibly edit an arbitrary graph.
const isMeta = (k: string) => k.startsWith("_") || k === "confirmed_at";

function ModuleCard({
  item,
  confirmed,
  skipped,
  onConfirm,
  onSkip,
}: {
  item: ReconstructedModule;
  confirmed: boolean;
  skipped: boolean;
  onConfirm: ReconstructedModulesProps["onConfirm"];
  onSkip?: (module: string) => void;
}) {
  const editableKeys = Object.keys(item.candidate).filter((k) => !isMeta(k));
  const [buf, setBuf] = useState<Record<string, unknown>>(() => ({ ...item.candidate }));
  const [busy, setBusy] = useState(false);

  if (skipped) return null;

  const setField = (k: string, v: unknown) => setBuf((b) => ({ ...b, [k]: v }));

  const confirm = async () => {
    setBusy(true);
    try {
      await onConfirm(item.module, buf);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-ink-200 bg-white p-4 flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-[13px] font-bold text-ink-900">
          {item.module} · {label(item.module)}
        </div>
        <span
          className={
            confirmed
              ? "text-[11px] font-bold text-green-700"
              : "text-[11px] font-semibold text-amber-700 bg-amber-50 rounded px-1.5 py-0.5"
          }
        >
          {confirmed ? "✓ Confirmed" : "Suggested — not saved yet"}
        </span>
      </div>

      {item.rationale && (
        <p className="text-[12px] text-ink-500 m-0 italic">Why: {item.rationale}</p>
      )}

      {!confirmed && (
        <div className="flex flex-col gap-2">
          {editableKeys.map((k) => {
            const v = buf[k];
            if (Array.isArray(v)) {
              return (
                <label key={k} className="flex flex-col gap-1">
                  <span className="text-[11.5px] font-semibold text-ink-700">{k}</span>
                  <textarea
                    className="rounded-lg border border-ink-200 px-2 py-1 text-[12.5px] min-h-[52px]"
                    value={(v as unknown[]).map(String).join("\n")}
                    onChange={(e) =>
                      setField(
                        k,
                        e.target.value.split("\n").map((s) => s.trim()).filter(Boolean),
                      )
                    }
                  />
                </label>
              );
            }
            if (typeof v === "string") {
              return (
                <label key={k} className="flex flex-col gap-1">
                  <span className="text-[11.5px] font-semibold text-ink-700">{k}</span>
                  <input
                    className="rounded-lg border border-ink-200 px-2 py-1 text-[12.5px]"
                    value={v}
                    onChange={(e) => setField(k, e.target.value)}
                  />
                </label>
              );
            }
            // Objects / numbers: read-only preview; refine in chat.
            return (
              <div key={k} className="flex flex-col gap-1">
                <span className="text-[11.5px] font-semibold text-ink-700">
                  {k} <span className="font-normal text-ink-400">(refine in chat)</span>
                </span>
                <pre className="rounded-lg bg-ink-50 px-2 py-1 text-[11px] text-ink-600 overflow-x-auto m-0">
                  {JSON.stringify(v, null, 2)}
                </pre>
              </div>
            );
          })}
        </div>
      )}

      {!confirmed && item.review.length > 0 && (
        <p className="text-[11.5px] text-ink-400 m-0">
          Still thin: {item.review.join(", ")} — you can fill these now or later in chat.
        </p>
      )}

      {!confirmed && (
        <div className="flex gap-2 mt-1">
          <button
            type="button"
            disabled={busy}
            onClick={confirm}
            className="rounded-lg bg-primary-600 px-3 py-1.5 text-[12.5px] font-bold text-white hover:bg-primary-700 disabled:opacity-50"
          >
            {busy ? "Saving…" : "Confirm"}
          </button>
          {onSkip && (
            <button
              type="button"
              disabled={busy}
              onClick={() => onSkip(item.module)}
              className="rounded-lg border border-ink-200 px-3 py-1.5 text-[12.5px] font-semibold text-ink-600 hover:bg-ink-50"
            >
              Skip
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export function ReconstructedModules({
  items,
  reconstructing = false,
  confirmedModules = [],
  skippedModules = [],
  onConfirm,
  onSkip,
}: ReconstructedModulesProps) {
  if (!reconstructing && items.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Reconstructed modules"
      className="flex flex-col gap-2"
    >
      <div className="text-[13px] font-bold text-ink-900">
        Earlier steps we reconstructed — review before we count them
      </div>

      {reconstructing && items.length === 0 && (
        <div className="rounded-xl border border-ink-200 bg-white p-4 text-[12.5px] text-ink-500">
          Reconstructing earlier steps from what you imported…
        </div>
      )}

      {items.map((item) => (
        <ModuleCard
          key={item.module}
          item={item}
          confirmed={confirmedModules.includes(item.module)}
          skipped={skippedModules.includes(item.module)}
          onConfirm={onConfirm}
          onSkip={onSkip}
        />
      ))}
    </div>
  );
}
