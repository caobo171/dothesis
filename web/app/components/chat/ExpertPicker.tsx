"use client";

import { useEffect, useRef } from "react";
import { Check } from "lucide-react";
import { EXPERTS, type Expert, type ModuleId } from "@/app/lib/experts";


/**
 * Square-rounded primary avatar with the expert's glyph initial.
 * Sized via the `size` prop so it scales for both the picker rows (32px)
 * and the active-expert chip in the composer (20–26px).
 */
export function ExpertAvatar({
  expert, size = 32,
}: {
  expert: Expert;
  size?: number;
}) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex items-center justify-center bg-primary-600 text-white font-extrabold shrink-0"
      style={{
        width: size,
        height: size,
        borderRadius: Math.round(size * 0.24),
        fontSize: Math.round(size * 0.5),
        letterSpacing: "-0.02em",
      }}
    >
      {expert.avatar}
    </span>
  );
}


/**
 * Popover that drops UP from the composer toolbar. Grouped into "Suggested
 * for {focus}" (experts whose `modules` include the current focus) and
 * "All experts" (the rest). Selecting one calls onSelect; the empty
 * "Use base DoThesis" footer button clears the selection.
 *
 * Closes on outside-click (mousedown handler owned by the parent) and on
 * Escape. The parent owns the open/closed state so the trigger button can
 * stay positioned relative to the popover.
 */
export function ExpertPicker({
  focusModule,
  selectedId,
  onSelect,
  onClose,
}: {
  focusModule?: string;
  selectedId?: string | null;
  onSelect: (expert: Expert | null) => void;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDoc);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDoc);
    };
  }, [onClose]);

  const focus = (focusModule as ModuleId | undefined) ?? undefined;
  const suggested = focus
    ? EXPERTS.filter(e => e.modules.includes(focus))
    : [];
  const others = focus
    ? EXPERTS.filter(e => !e.modules.includes(focus))
    : EXPERTS;

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Pick a specialist"
      className="absolute left-0 bottom-[calc(100%+8px)] w-[380px] max-h-[460px] bg-white rounded-2xl border border-ink-200 z-30 flex flex-col overflow-hidden"
      style={{ boxShadow: "var(--shadow-pop)" }}
    >
      <div className="px-3.5 pt-2.5 pb-2 border-b border-ink-100">
        <div className="text-[12.5px] font-bold text-ink-900">
          Pick a specialist
        </div>
        <div className="text-[11px] text-ink-500 mt-0.5 leading-snug">
          Each one has its own grounding and voice — still one thread.
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-1.5 pt-1 pb-2">
        {suggested.length > 0 && (
          <PickerGroup label={`Suggested for ${focus}`}>
            {suggested.map(e => (
              <ExpertOption
                key={e.id}
                expert={e}
                selected={selectedId === e.id}
                onClick={() => onSelect(e)}
              />
            ))}
          </PickerGroup>
        )}
        <PickerGroup label="All experts">
          {others.map(e => (
            <ExpertOption
              key={e.id}
              expert={e}
              selected={selectedId === e.id}
              onClick={() => onSelect(e)}
            />
          ))}
        </PickerGroup>
      </div>

      <div className="flex items-center gap-2 px-3.5 py-2 border-t border-ink-100 bg-ink-50">
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="text-[11.5px] text-ink-600 font-semibold px-2 py-1 rounded-md hover:bg-ink-100 transition-colors"
        >
          ← Use base DoThesis
        </button>
        <span className="flex-1" />
        <span className="text-[10.5px] text-ink-400">
          {EXPERTS.length} experts · no extra credit cost
        </span>
      </div>
    </div>
  );
}


function PickerGroup({
  label, children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="mt-1">
      <div className="px-2.5 pt-2 pb-1 text-[10.5px] font-bold text-ink-500 tracking-[0.08em] uppercase">
        {label}
      </div>
      <div className="flex flex-col gap-0.5">{children}</div>
    </div>
  );
}


function ExpertOption({
  expert, selected, onClick,
}: {
  expert: Expert;
  selected: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-start gap-2.5 px-2.5 py-2 rounded-[10px] text-left transition-colors ${
        selected
          ? "bg-primary-50 border border-primary-100"
          : "border border-transparent hover:bg-ink-50"
      }`}
    >
      <ExpertAvatar expert={expert} size={32} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] font-bold text-ink-900">{expert.name}</span>
          {expert.modules.map(m => (
            <span
              key={m}
              className="text-[10px] font-bold px-1.5 rounded text-ink-600 bg-ink-100"
            >
              {m}
            </span>
          ))}
        </div>
        <div className="text-[11.5px] text-ink-500 mt-0.5 leading-snug">
          {expert.tagline}
        </div>
        <div className="text-[11px] text-ink-400 mt-1 italic font-serif">
          “{expert.sample}”
        </div>
      </div>
      {selected && (
        <Check className="w-3.5 h-3.5 text-primary-600 shrink-0 mt-1" />
      )}
    </button>
  );
}
