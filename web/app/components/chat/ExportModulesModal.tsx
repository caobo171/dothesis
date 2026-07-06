"use client";

import { useState } from "react";
import { Check, FileDown, FileText } from "lucide-react";

import { SliceModal } from "./SliceModal";
import { Button } from "@/app/components/ui/button";

const MODS: { id: string; label: string }[] = [
  { id: "M1", label: "Topic" },
  { id: "M2", label: "Literature" },
  { id: "M3", label: "Design" },
  { id: "M4", label: "Analysis" },
];

/**
 * Export-to-Word picker. ONE tile row + ONE confirm button (previously the
 * "Full thesis" tile confirmed on click — the confirm button was only for
 * modules, which was inconsistent). The user picks a mode:
 *   - Full thesis (default) → agent runs export_docx(scope="full"): 6 chapters.
 *   - Specific modules → tick M1..M4, combined into one .docx via
 *     export_docx(scope="M1,M3,…"), returned in canonical M1→M4 order.
 * Bottom "Export → .docx" is the single confirm.
 */
export function ExportModulesModal({
  open,
  onClose,
  onExport,
}: {
  open: boolean;
  onClose: () => void;
  onExport: (modules: string[]) => void;
}) {
  // Mode + module selection. Default to "full" so the common case is one click.
  const [mode, setMode] = useState<"full" | "modules">("full");
  const [sel, setSel] = useState<Set<string>>(new Set());
  const toggle = (id: string) =>
    setSel(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const ordered = MODS.filter(m => sel.has(m.id)).map(m => m.id);

  const close = () => { setMode("full"); setSel(new Set()); onClose(); };

  const canExport = mode === "full" || ordered.length > 0;
  const buttonLabel =
    mode === "full"
      ? "Export → .docx"
      : ordered.length > 1
        ? `Export ${ordered.length} modules → .docx`
        : "Export → .docx";

  const submit = () => {
    if (!canExport) return;
    onExport(mode === "full" ? ["full"] : ordered);
    close();
  };

  return (
    <SliceModal
      open={open}
      title="Export to Word"
      subtitle="Export the full thesis, or pick specific modules to combine into one .docx for your professor"
      onClose={close}
    >
      {/* Full thesis — a SELECTABLE option (was a confirm-on-click button).
          Selecting it clears any per-module ticks so the two modes stay
          mutually exclusive. */}
      <button
        type="button"
        onClick={() => { setMode("full"); setSel(new Set()); }}
        aria-pressed={mode === "full"}
        className={`w-full flex items-start gap-3 px-3.5 py-3 rounded-xl border text-left transition-colors ${
          mode === "full"
            ? "border-primary-500 bg-primary-50/50"
            : "border-ink-200 hover:border-ink-300"
        }`}
      >
        <span
          className={`w-[18px] h-[18px] rounded-full inline-flex items-center justify-center shrink-0 mt-0.5 ${
            mode === "full" ? "bg-primary-600 text-white" : "bg-white border-[1.5px] border-ink-300"
          }`}
          aria-hidden="true"
        >
          {mode === "full" && <span className="w-[7px] h-[7px] rounded-full bg-white" />}
        </span>
        <FileText className="w-5 h-5 text-primary-600 shrink-0 mt-0.5" />
        <span className="flex flex-col">
          <span className="text-[14px] font-bold text-ink-900">Full thesis</span>
          <span className="text-[12px] text-ink-500 leading-snug">
            All 6 chapters — Introduction, Literature, Methodology, Results,
            Discussion, Conclusion + references.
          </span>
        </span>
      </button>

      <div className="flex items-center gap-3 my-3 text-[11px] uppercase tracking-[0.05em] font-semibold text-ink-400">
        <span className="flex-1 h-px bg-ink-100" />
        or pick specific modules
        <span className="flex-1 h-px bg-ink-100" />
      </div>

      <div className="flex flex-col gap-2">
        {MODS.map(m => {
          const on = mode === "modules" && sel.has(m.id);
          return (
            <button
              key={m.id}
              type="button"
              onClick={() => {
                // Picking a module switches to modules mode + toggles the row,
                // so the user doesn't have to "unselect Full thesis" first.
                if (mode !== "modules") setMode("modules");
                toggle(m.id);
              }}
              className={`flex items-center gap-3 px-3.5 py-3 rounded-xl border text-left transition-colors ${
                on ? "border-primary-500 bg-primary-50/50" : "border-ink-200 hover:border-ink-300"
              }`}
            >
              <span
                className={`w-[18px] h-[18px] rounded-[5px] inline-flex items-center justify-center shrink-0 ${
                  on ? "bg-primary-600 text-white" : "bg-white border-[1.5px] border-ink-300"
                }`}
                aria-hidden="true"
              >
                {on && <Check className="w-3 h-3" />}
              </span>
              <span className="text-[12px] font-bold text-primary-700 w-6">{m.id}</span>
              <span className="text-[14px] font-semibold text-ink-900">{m.label}</span>
            </button>
          );
        })}
      </div>

      <Button
        type="button"
        disabled={!canExport}
        onClick={submit}
        className="w-full mt-4"
      >
        <FileDown className="w-4 h-4 mr-1.5" />
        {buttonLabel}
      </Button>
    </SliceModal>
  );
}
