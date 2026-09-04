"use client";


// Loading placeholder for the thesis editor. Mirrors the real three-column
// shell (outline rail · toolbar + document · sources rail) so the transition to
// loaded content doesn't jump — replaces the bare centered "Loading…" that read
// as a broken/blank page while the chapters fetch was in flight.
export function EditorSkeleton() {
  return (
    <div className="flex flex-col h-full animate-pulse" aria-busy="true" aria-label="Đang tải trình soạn thảo">
      {/* Export bar */}
      <div className="h-12 border-b border-ink-100 flex items-center justify-between px-5">
        <div className="h-3.5 w-40 rounded bg-ink-100" />
        <div className="h-7 w-24 rounded-md bg-ink-100" />
      </div>

      <div className="flex flex-1 min-h-0">
        {/* Outline rail */}
        <div className="w-48 shrink-0 border-r border-ink-100 py-4 px-3 space-y-2">
          <div className="h-2.5 w-16 rounded bg-ink-100 mb-3" />
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-8 rounded-md bg-ink-100" style={{ opacity: 1 - i * 0.1 }} />
          ))}
        </div>

        {/* Center: toolbar + document lines */}
        <div className="flex-1 flex flex-col min-h-0">
          {/* Toolbar */}
          <div className="h-11 border-b border-ink-100 flex items-center gap-2 px-3">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="h-6 w-8 rounded bg-ink-100" />
            ))}
            <div className="ml-auto h-3 w-12 rounded bg-ink-100" />
          </div>
          {/* Page body */}
          <div className="flex-1 overflow-hidden px-8 py-8 space-y-6">
            <div className="h-6 w-2/3 rounded bg-ink-100" />
            <div className="space-y-3">
              {["100%", "97%", "92%", "99%", "85%"].map((w, i) => (
                <div key={i} className="h-3.5 rounded bg-ink-100" style={{ width: w }} />
              ))}
            </div>
            <div className="h-5 w-1/2 rounded bg-ink-100 mt-8" />
            <div className="space-y-3">
              {["98%", "90%", "96%", "88%"].map((w, i) => (
                <div key={i} className="h-3.5 rounded bg-ink-100" style={{ width: w }} />
              ))}
            </div>
          </div>
        </div>

        {/* Sources rail */}
        <div className="w-56 shrink-0 border-l border-ink-100 py-4 px-3 space-y-2">
          <div className="h-2.5 w-20 rounded bg-ink-100 mb-3" />
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-12 rounded bg-ink-100" style={{ opacity: 1 - i * 0.15 }} />
          ))}
        </div>
      </div>
    </div>
  );
}
