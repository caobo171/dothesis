"use client";

import { useState } from "react";
import Link from "next/link";
import { AlertTriangle, MessageSquare, Plus } from "lucide-react";

import type { ModuleStatusMap } from "./ContextPanel";
import type { Thread } from "./ThreadsSidebar";


/**
 * Project-specific left rail. Replaces the global Dashboard / Theses / Credit
 * menu when the user is inside a thesis. Layout matches DoThesis-standalone:
 *   - Brand row (DoThesis logo + "Thesis copilot" label + home shortcut)
 *   - Project chip (clickable, shows project name + field)
 *   - WORKFLOW header with N/5 counter
 *   - Module rail (M1–M5) with ringed status badges + a vertical track
 *     connecting consecutive rows (the track turns emerald between two
 *     `done` modules, grey otherwise — visualizes progression).
 *
 * Status palette (from design):
 *   done         → emerald-600 badge, white check
 *   in_progress  → primary-600 badge, white module id
 *   needs_review → amber-50 badge, amber id, ⚠ marker
 *   locked       → ink-200 badge, muted id, 60% opacity
 *
 * Threads were temporarily moved into a right-side drawer. The design's
 * canonical shape is a Threads/Workflow TAB toggle inside this same
 * sidebar — that's planned as a follow-up; this file is the workflow tab
 * standalone for now.
 */

const MODULES: { id: ModuleId; title: string; blurb: string }[] = [
  { id: "M1", title: "Topic Discovery",    blurb: "Topic, scope, RQs, objectives." },
  { id: "M2", title: "Literature Review",  blurb: "Sources, gaps, hypotheses, Ch. 2 draft." },
  { id: "M3", title: "Research Design",    blurb: "Paradigm, model, instrument, sampling." },
  { id: "M4", title: "Data Analysis",      blurb: "Detect → outline → execute (sandboxed)." },
  { id: "M5", title: "Writing",            blurb: "Auto-fill chapters · citation manager · export." },
];

type ModuleId = "M1" | "M2" | "M3" | "M4" | "M5";
type Status = "done" | "in_progress" | "needs_review" | "locked";

const STATUS_LABEL: Record<Status, string> = {
  done:         "Done",
  in_progress:  "In progress",
  needs_review: "Needs review",
  locked:       "Locked",
};

function statusFor(
  id: ModuleId,
  current: string | null | undefined,
  statusMap: ModuleStatusMap | undefined,
): Status {
  const raw = statusMap?.[id];
  if (raw === "done") return "done";
  if (raw === "needs_review") return "needs_review";
  if (raw === "in_progress") return "in_progress";
  if (id === current) return "in_progress";
  return "locked";
}


export function WorkflowSidebar({
  projectName,
  projectSubtitle,
  currentModule,
  moduleStatus,
  tokenBalance,
  tokenCap,
  tier,
  threads,
  currentThreadId,
  onSelectThread,
  onNewThread,
  defaultTab,
}: {
  projectName?: string;
  projectSubtitle?: string;
  currentModule?: string | null;
  moduleStatus?: ModuleStatusMap;
  tokenBalance?: number;
  tokenCap?: number;
  tier?: string;
  // Threads tab data. When `threads` is undefined the Threads tab is
  // hidden entirely and the sidebar becomes workflow-only (used on the
  // editor page where threads aren't relevant).
  threads?: Thread[];
  currentThreadId?: string;
  onSelectThread?: (tid: string) => void;
  onNewThread?: () => void;
  /** Which tab opens first. Defaults to "workflow" because the workflow
   *  rail is the more useful first-touch surface in a thesis context. */
  defaultTab?: "threads" | "workflow";
}) {
  const hasThreads = threads !== undefined;
  const [tab, setTab] = useState<"threads" | "workflow">(defaultTab ?? "workflow");
  const activeTab = hasThreads ? tab : "workflow";

  const doneCount = MODULES.filter(
    m => statusFor(m.id, currentModule, moduleStatus) === "done",
  ).length;

  return (
    <aside
      className="w-[296px] min-w-[296px] flex flex-col h-full bg-white border-r border-ink-200 shrink-0"
      data-testid="workflow-sidebar"
    >
      {/* Brand row */}
      <div className="px-5 pt-[18px] pb-3.5 flex items-center gap-2.5">
        <span
          className="w-9 h-9 rounded-[10px] inline-flex items-center justify-center text-white font-extrabold font-serif text-[18px] shrink-0"
          style={{
            background: "linear-gradient(135deg, #2540FF 0%, #6A4DE0 100%)",
            boxShadow: "0 4px 12px rgba(37,64,255,.22)",
          }}
        >
          D
        </span>
        <div className="min-w-0 flex-1">
          <div className="font-extrabold text-[17.5px] tracking-[-0.01em] text-ink-900">DoThesis</div>
          <div className="text-[11px] uppercase tracking-[0.08em] text-ink-500 font-medium mt-px">
            Thesis copilot
          </div>
        </div>
        <Link
          href="/"
          aria-label="Home"
          title="Home"
          className="w-7 h-7 rounded-full text-ink-500 hover:bg-ink-50 hover:text-ink-900 inline-flex items-center justify-center text-[13px] transition-colors"
        >
          ⌂
        </Link>
      </div>

      {/* Project chip */}
      {projectName && (
        <div className="mx-[14px] mb-2.5 px-3 py-2.5 bg-ink-50 border border-ink-200 rounded-xl">
          <div className="text-[11px] uppercase tracking-[0.05em] text-ink-500 font-semibold">
            Project
          </div>
          <div
            className="text-[13px] font-semibold text-ink-900 mt-1 leading-[1.35] line-clamp-2"
            title={projectName}
          >
            {projectName}
          </div>
          {projectSubtitle && (
            <div className="flex items-center gap-1.5 mt-1.5 text-[11.5px] text-ink-500">
              <span className="truncate">{projectSubtitle}</span>
            </div>
          )}
        </div>
      )}

      {/* Tabs — only rendered when we have threads to switch between */}
      {hasThreads && (
        <div className="flex px-[14px] py-1 gap-1">
          <TabButton
            label="Threads"
            badge={String(threads.filter(t => t.status === "active").length)}
            active={activeTab === "threads"}
            onClick={() => setTab("threads")}
          />
          <TabButton
            label="Workflow"
            badge={`${doneCount}/5`}
            active={activeTab === "workflow"}
            onClick={() => setTab("workflow")}
          />
        </div>
      )}

      {/* Workflow-only header (when no tabs) */}
      {!hasThreads && (
        <div className="px-[18px] mt-1 mb-2 flex items-center justify-between">
          <div className="text-[10.5px] uppercase tracking-[0.1em] text-ink-500 font-semibold">
            Workflow
          </div>
          <div className="text-[10.5px] tabular-nums text-ink-400 font-semibold">
            {doneCount}/5
          </div>
        </div>
      )}

      {/* Tab content */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {activeTab === "threads" && hasThreads ? (
          <ThreadList
            threads={threads}
            activeId={currentThreadId}
            onSelect={onSelectThread}
            onNew={onNewThread}
          />
        ) : (
          <nav className="px-3 pb-2 flex flex-col gap-0.5">
            {MODULES.map((m, i) => {
              const status = statusFor(m.id, currentModule, moduleStatus);
              const isFocus = m.id === currentModule;
              const nextStatus = i + 1 < MODULES.length
                ? statusFor(MODULES[i + 1].id, currentModule, moduleStatus)
                : "locked";
              return (
                <ModuleRow
                  key={m.id}
                  id={m.id}
                  title={m.title}
                  blurb={m.blurb}
                  status={status}
                  isFocus={isFocus}
                  isLast={i === MODULES.length - 1}
                  connectorActive={status === "done" && nextStatus === "done"}
                />
              );
            })}
          </nav>
        )}
      </div>

      {/* Token meter card */}
      {tokenBalance !== undefined && tokenCap !== undefined && tokenCap > 0 && (
        <div className="m-3 p-3 rounded-2xl bg-ink-900 text-white">
          <div className="flex items-center justify-between mb-1.5">
            <div className="text-[10.5px] uppercase tracking-[0.1em] text-white/60 font-semibold">
              Token balance
            </div>
            {tier && (
              <div className="text-[10.5px] font-bold text-primary-300">{tier}</div>
            )}
          </div>
          <div className="text-[18px] font-bold tabular-nums">
            {formatThousands(tokenBalance)}
            <span className="text-[11px] text-white/50 font-normal"> / {formatThousands(tokenCap)}</span>
          </div>
          <div className="mt-2 h-1 rounded-full bg-white/15 overflow-hidden">
            <div
              className="h-full bg-primary-400"
              style={{
                width: `${Math.min(100, Math.round((tokenBalance / tokenCap) * 100))}%`,
              }}
            />
          </div>
        </div>
      )}
    </aside>
  );
}


function ModuleRow({
  id, title, blurb, status, isFocus, isLast, connectorActive,
}: {
  id: ModuleId;
  title: string;
  blurb: string;
  status: Status;
  isFocus: boolean;
  isLast: boolean;
  connectorActive: boolean;
}) {
  const clickable = status !== "locked";

  return (
    <div className="relative">
      {/* Vertical connecting track between this row and the next.
          Position matches the design (left: 30 from row left = center of 38px badge).
          Color shifts to emerald when BOTH this and the next module are done. */}
      {!isLast && (
        <span
          className={`absolute top-[42px] bottom-[-2px] w-[2px] opacity-70 ${
            connectorActive ? "bg-emerald-600" : "bg-ink-200"
          }`}
          style={{ left: 28 }}
          aria-hidden="true"
        />
      )}

      <button
        type="button"
        disabled={!clickable}
        className={`relative w-full text-left flex items-start gap-3 p-2.5 rounded-xl transition-colors ${
          isFocus
            ? "bg-primary-50 text-primary-700"
            : "bg-transparent text-ink-800 hover:bg-ink-50"
        } ${status === "locked" ? "opacity-60 cursor-not-allowed" : ""}`}
      >
        <StatusBadge status={status} id={id} />

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-[14px] font-semibold leading-tight truncate">{title}</span>
            {status === "needs_review" && (
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
            )}
          </div>
          <div
            className={`text-[11.5px] mt-0.5 leading-[1.35] line-clamp-2 ${
              isFocus ? "text-primary-600" : "text-ink-500"
            }`}
          >
            {blurb}
          </div>
          <div
            className={`text-[10.5px] uppercase tracking-[0.06em] font-semibold mt-1 ${
              status === "done"          ? "text-emerald-700" :
              status === "in_progress"   ? "text-primary-600" :
              status === "needs_review"  ? "text-amber-700" :
                                           "text-ink-400"
            }`}
          >
            {STATUS_LABEL[status]}
          </div>
        </div>
      </button>
    </div>
  );
}


function StatusBadge({ status, id }: { status: Status; id: ModuleId }) {
  // Design uses `box-shadow: 0 0 0 4px <ring>` for that distinctive ringed
  // look. Tailwind's `ring-*` utility gives the same effect via outline
  // box-shadow without polluting the layout box.
  const palette: Record<Status, { bg: string; fg: string; ring: string }> = {
    done:         { bg: "bg-emerald-600",  fg: "text-white",       ring: "ring-emerald-600/15" },
    in_progress:  { bg: "bg-primary-600",  fg: "text-white",       ring: "ring-primary-600/15" },
    needs_review: { bg: "bg-amber-50",     fg: "text-amber-700",   ring: "ring-amber-500/20" },
    locked:       { bg: "bg-ink-200",      fg: "text-ink-500",     ring: "ring-transparent" },
  };
  const p = palette[status];
  return (
    <span
      className={`w-[38px] h-[38px] min-w-[38px] rounded-[10px] inline-flex items-center justify-center font-extrabold text-[12.5px] tracking-[0.04em] font-serif ring-4 ${p.bg} ${p.fg} ${p.ring}`}
      aria-hidden="true"
    >
      {status === "done" ? <span className="text-[16px]">✓</span> : id}
    </span>
  );
}


function formatThousands(n: number): string {
  if (n >= 1000) {
    const k = n / 1000;
    return `${k % 1 === 0 ? k.toFixed(0) : k.toFixed(1)}k`;
  }
  return String(n);
}


// --- Threads / Workflow tab toggle ---

function TabButton({
  label, badge, active, onClick,
}: {
  label: string;
  badge: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 px-2.5 py-2 rounded-lg inline-flex items-center justify-center gap-1.5 transition-colors ${
        active
          ? "bg-primary-50 text-primary-700"
          : "text-ink-600 hover:bg-ink-50"
      }`}
    >
      <span className={`text-[12.5px] ${active ? "font-bold" : "font-semibold"}`}>{label}</span>
      <span
        className={`px-1.5 py-px rounded-full text-[10.5px] font-bold ${
          active ? "bg-white text-primary-700" : "bg-ink-100 text-ink-500"
        }`}
      >
        {badge}
      </span>
    </button>
  );
}


function ThreadList({
  threads, activeId, onSelect, onNew,
}: {
  threads: Thread[];
  activeId?: string;
  onSelect?: (tid: string) => void;
  onNew?: () => void;
}) {
  // Pin / active / archived split matches the design's ThreadList shape.
  // For now we only render two buckets (active + archived) since the API
  // doesn't expose a `pinned` flag yet — easy to add when it does.
  const active = threads.filter(t => t.status !== "archived");
  const archived = threads.filter(t => t.status === "archived");

  return (
    <div className="px-2 pb-2">
      {onNew && (
        <button
          type="button"
          onClick={onNew}
          className="w-full mb-2 px-3 py-2 rounded-full bg-primary-600 text-white inline-flex items-center justify-start gap-2 text-[13px] font-semibold hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>New thread</span>
          <span className="flex-1" />
          <span className="opacity-75 text-[10.5px] px-1.5 py-px bg-white/15 rounded">⌘N</span>
        </button>
      )}

      <div className="flex flex-col gap-0.5">
        {active.map(t => (
          <ThreadRow
            key={t.id}
            thread={t}
            active={t.id === activeId}
            onClick={() => onSelect?.(t.id)}
          />
        ))}
      </div>

      {archived.length > 0 && (
        <>
          <div className="text-[10.5px] uppercase tracking-[0.06em] text-ink-400 font-semibold px-2 pt-3 pb-1">
            Archived
          </div>
          <div className="flex flex-col gap-0.5 opacity-70">
            {archived.map(t => (
              <ThreadRow
                key={t.id}
                thread={t}
                active={t.id === activeId}
                onClick={() => onSelect?.(t.id)}
              />
            ))}
          </div>
        </>
      )}

      {active.length === 0 && archived.length === 0 && (
        <div className="text-[12px] text-ink-500 px-2 py-3">
          No threads yet — start one.
        </div>
      )}
    </div>
  );
}


function ThreadRow({
  thread, active, onClick,
}: {
  thread: Thread;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`w-full px-3 py-2 rounded-xl inline-flex items-center gap-2 text-left transition-colors ${
        active
          ? "bg-primary-50 text-primary-700 font-semibold"
          : "text-ink-700 hover:bg-ink-50 font-medium"
      }`}
    >
      <MessageSquare className="w-3.5 h-3.5 shrink-0" />
      <span className="truncate text-[13px]">{thread.name}</span>
    </button>
  );
}
