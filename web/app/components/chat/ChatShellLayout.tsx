"use client";

import { createContext, ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

// Lets the chat header (rendered deep inside `children`) open the threads
// sidebar drawer (left) and the context panel drawer (right) on mobile without
// prop-threading through every page.
export const ChatSidebarContext = createContext<{ open: () => void; openContext: () => void }>({
  open: () => {},
  openContext: () => {},
});


// Width bounds for the right pane. Below the min the ContextPanel content
// truncates badly (the M3 KV labels need ~110px); above the max the chat
// column gets cramped on a laptop. localStorage persists the user's pick
// across sessions.
const RIGHT_MIN = 280;
const RIGHT_MAX = 560;
const RIGHT_DEFAULT = 340;
const STORAGE_KEY = "dothesis_right_pane_width";


/**
 * Three-pane chat shell after the design pivot:
 *   - leftPane:   project sidebar (WorkflowSidebar) — Threads + Workflow tabs
 *   - middle:     chat (header + messages + composer)
 *   - rightPane:  ContextPanel — RESIZABLE via a drag handle on its left edge
 *
 * Resize behaviour:
 *   - Hover the 4px-wide hairline between main and right → cursor turns
 *     col-resize; the line widens slightly to telegraph the affordance.
 *   - Drag to set the width; constrained to [RIGHT_MIN, RIGHT_MAX].
 *   - Width persists per browser via localStorage so the user's preference
 *     survives a refresh.
 *   - Double-click the handle to snap back to the default width.
 *
 * `useRef` for the active drag so we don't re-render on every mousemove;
 * only commit the final width to state when the user releases.
 */
export function ChatShellLayout({
  leftPane,
  rightPane,
  children,
}: {
  leftPane: ReactNode;
  rightPane: ReactNode;
  children: ReactNode;
}) {
  const [rightWidth, setRightWidth] = useState<number>(RIGHT_DEFAULT);
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null);

  // Mobile: the left sidebar is an off-canvas drawer. Close it on navigation
  // (selecting a thread / new thread routes), so it doesn't stay covering the
  // chat after the user picks something.
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => { setSidebarOpen(false); setContextOpen(false); }, [pathname]);

  // Restore width on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const n = Number(raw);
    if (Number.isFinite(n) && n >= RIGHT_MIN && n <= RIGHT_MAX) {
      setRightWidth(n);
    }
  }, []);

  // Mousemove + mouseup listeners only mount during an active drag so
  // ordinary navigation doesn't pay the cost.
  const onPointerMove = useCallback((e: PointerEvent) => {
    const drag = dragRef.current;
    if (!drag) return;
    // The handle is on the LEFT edge of the right pane; dragging right
    // shrinks the pane, dragging left grows it.
    const dx = drag.startX - e.clientX;
    const next = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, drag.startWidth + dx));
    setRightWidth(next);
  }, []);

  const onPointerUp = useCallback(() => {
    dragRef.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    // Persist the chosen width.
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(rightWidth));
    }
  }, [onPointerMove, rightWidth]);

  const startDrag = (e: React.PointerEvent) => {
    dragRef.current = { startX: e.clientX, startWidth: rightWidth };
    // Lock the cursor and selection state body-wide so the handle behaves
    // like a desktop divider — no accidental text selection while dragging.
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
  };

  const resetWidth = () => {
    setRightWidth(RIGHT_DEFAULT);
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, String(RIGHT_DEFAULT));
    }
  };

  return (
    <ChatSidebarContext.Provider value={{ open: () => setSidebarOpen(true), openContext: () => setContextOpen(true) }}>
    <div className="flex h-screen bg-white">
      {/* Mobile drawer backdrop */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-900/50 lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}
      {/* Left pane: off-canvas drawer on mobile, static column on lg+ */}
      <div
        className={`fixed inset-y-0 left-0 z-50 transition-transform duration-300 lg:static lg:z-auto lg:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {leftPane}
      </div>
      <main className="flex-1 flex flex-col min-w-0">{children}</main>

      {/* Resize handle — only meaningful on lg+ screens where the right
          pane shows at all. The handle is 6px wide so it's easy to hit
          without dominating the gap visually. */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize context panel"
        onPointerDown={startDrag}
        onDoubleClick={resetWidth}
        className="hidden lg:flex w-1.5 cursor-col-resize bg-ink-200 hover:bg-primary-300 active:bg-primary-400 transition-colors group items-center justify-center"
      >
        {/* Visual grip — small ribbon that fades in on hover. */}
        <span className="block w-px h-8 bg-ink-400 opacity-0 group-hover:opacity-100 transition-opacity" />
      </div>

      {/* Context-panel drawer backdrop (mobile) */}
      {contextOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-900/50 lg:hidden"
          onClick={() => setContextOpen(false)}
          aria-hidden="true"
        />
      )}
      {/* Right pane — static width-controlled column on lg+, slide-in drawer
          from the right on mobile (opened via the header's panel button). */}
      <div
        className={`fixed inset-y-0 right-0 z-50 flex bg-white shadow-xl transition-transform duration-300 lg:static lg:z-auto lg:shadow-none lg:flex-shrink-0 lg:translate-x-0 ${
          contextOpen ? "translate-x-0" : "translate-x-full lg:translate-x-0"
        }`}
        style={{ width: rightWidth }}
      >
        {rightPane}
      </div>
    </div>
    </ChatSidebarContext.Provider>
  );
}
