"use client";

import { ReactNode, useEffect } from "react";
import { X } from "lucide-react";


/**
 * Generic detail modal for context-store slice contents.
 *
 * Used by ContextPanel when the user clicks a gap chip / hypothesis / paper
 * count etc. — the panel can't show the full payload inline (each section
 * is tiny), so a click opens this modal with the full text + structured
 * detail.
 *
 * Mechanics:
 *   - Backdrop click closes (no portal — chat surface has no z-index war)
 *   - ESC closes
 *   - Max-width 720px, max-height 80vh, scrollable body
 *   - Sticky header so the title + close stay visible while scrolling
 */
export function SliceModal({
  open,
  title,
  subtitle,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    // Lock body scroll while modal open — otherwise wheel-scrolling in the
    // backdrop drifts the underlying page and feels broken.
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-ink-900/40"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="slice-modal-title"
    >
      <div
        className="relative w-full max-w-[720px] max-h-[80vh] bg-white rounded-2xl shadow-xl flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 px-5 py-3.5 border-b border-ink-200 bg-white rounded-t-2xl flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div id="slice-modal-title" className="text-[15px] font-bold text-ink-900 leading-snug">
              {title}
            </div>
            {subtitle && (
              <div className="text-[12.5px] text-ink-500 mt-0.5">{subtitle}</div>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-full text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
      </div>
    </div>
  );
}
