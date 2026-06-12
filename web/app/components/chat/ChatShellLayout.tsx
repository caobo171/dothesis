"use client";

import { ReactNode, useEffect, useState } from "react";
import { MessageSquare, Plus, X } from "lucide-react";


/**
 * Three-pane chat shell. The threads pane (left) used to be a permanent
 * column; design feedback was that 240px of "Main" sitting empty was a
 * waste of real estate. Now it lives inside a drawer that slides in from
 * the left when the user clicks the threads icon. Right pane (context)
 * stays as-is — it carries the M1–M5 progress + slice viewer that's
 * useful at-a-glance.
 *
 * Drawer mechanics:
 *   - closed: zero footprint; only the toggle button is on screen.
 *   - open:   400ms slide-in over a dimmed backdrop. ESC, backdrop click,
 *             or the X button closes.
 *
 * No portal — the drawer is just a fixed div. That's fine for chat where
 * there's no z-index war with modals.
 */
export function ChatShellLayout({
  leftPane,
  rightPane,
  children,
  onNewThread,
}: {
  leftPane: ReactNode;
  rightPane: ReactNode;
  // Center pane: header + message list + chat input stacked as a flex column
  children: ReactNode;
  // When provided, renders a "+ new thread" pill button OUTSIDE the drawer
  // (next to the threads toggle). Lets the user spawn a thread without
  // having to open the drawer first. Used to live inside ThreadsSidebar's
  // footer; design feedback asked for it to surface in the persistent UI.
  onNewThread?: () => void;
}) {
  const [threadsOpen, setThreadsOpen] = useState(false);

  // Close on ESC. Mounted only while the drawer is open so we don't
  // leak listeners on every chat page mount.
  useEffect(() => {
    if (!threadsOpen) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setThreadsOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [threadsOpen]);

  return (
    <div className="relative flex h-[calc(100vh-4rem)] bg-white">
      {/* Threads toggle — a vertical "tab handle" anchored to the right
          edge, vertically centered. The context pane occupies the right
          column on lg+ screens; the handle floats over its edge. Hidden
          while the drawer is open (drawer's own X button takes over). */}
      {!threadsOpen && (
        <div className="absolute right-0 top-1/2 -translate-y-1/2 z-30 flex flex-col gap-2 items-end">
          <button
            type="button"
            onClick={() => setThreadsOpen(true)}
            aria-label="Show threads"
            title="Show threads"
            className="h-16 w-7 rounded-l-lg bg-white border border-r-0 border-ink-200 text-ink-500 hover:bg-primary-50 hover:text-primary-700 inline-flex items-center justify-center shadow-sm transition-colors"
          >
            <MessageSquare className="w-4 h-4" />
          </button>
          {onNewThread && (
            <button
              type="button"
              onClick={onNewThread}
              aria-label="New thread"
              title="New thread"
              className="h-9 w-7 rounded-l-lg bg-white border border-r-0 border-ink-200 text-ink-500 hover:bg-primary-50 hover:text-primary-700 inline-flex items-center justify-center shadow-sm transition-colors"
            >
              <Plus className="w-4 h-4" />
            </button>
          )}
        </div>
      )}

      {/* Drawer backdrop — only renders when open so it doesn't intercept
          clicks on the main pane. */}
      {threadsOpen && (
        <div
          className="fixed inset-0 z-40 bg-ink-900/30 transition-opacity"
          onClick={() => setThreadsOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Threads drawer — fixed-position overlay, slides from the right.
          translate-x animation gives a 300ms slide. The inner
          ThreadsSidebar carries its own "THREADS" heading; we add only a
          floating close button (no second header bar) so the user doesn't
          see the label twice. */}
      <aside
        className={[
          "fixed top-0 right-0 z-50 h-full w-[260px] bg-white shadow-xl",
          "transform transition-transform duration-300 ease-out",
          threadsOpen ? "translate-x-0" : "translate-x-full",
        ].join(" ")}
        aria-hidden={!threadsOpen}
      >
        <button
          type="button"
          onClick={() => setThreadsOpen(false)}
          aria-label="Close threads"
          className="absolute top-2 right-2 z-10 w-7 h-7 rounded-full text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
        {/* The actual ThreadsSidebar render. onClick={} on the wrapper so
            a thread click auto-closes the drawer — otherwise the user has
            to dismiss it manually after every navigation. */}
        <div className="overflow-y-auto h-full" onClick={() => setThreadsOpen(false)}>
          {leftPane}
        </div>
      </aside>

      {/* Middle pane — chat */}
      <main className="flex-1 flex flex-col min-w-0">{children}</main>

      {/* Right pane — context — hidden below lg to preserve mobile screen space */}
      <div className="hidden lg:flex flex-shrink-0">{rightPane}</div>
    </div>
  );
}
