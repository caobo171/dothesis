"use client";

import Link from "next/link";
import { Home, MessageSquare, Plus } from "lucide-react";

import { LocaleSwitcher } from "../LocaleSwitcher";
import { BrandMark } from "../layout/Brand";
import { useT } from "../../lib/i18n/LocaleProvider";
import type { Thread } from "./ThreadsSidebar";


/**
 * Project-specific left rail. Replaces the global Dashboard / Theses / Credit
 * menu when the user is inside a thesis. Layout:
 *   - Brand row (DoThesis logo + "Thesis copilot" label + home shortcut)
 *   - Project chip (project name + optional subtitle)
 *   - Threads list (+ New thread button)
 *   - Project credits footer
 *
 * The Workflow tab (M1-M5 module rail) was removed — the right-hand
 * ContextPanel already surfaces module status.
 */
export function WorkflowSidebar({
  projectName,
  projectSubtitle,
  threads,
  currentThreadId,
  onSelectThread,
  onNewThread,
  projectCredits,
  threadsFailed = false,
  hideThreads = false,
}: {
  projectName?: string;
  projectSubtitle?: string;
  /** Total credits spent across the whole project — shown at the bottom. */
  projectCredits?: number;
  threads?: Thread[];
  /** The thread list request failed. Without this, `threads === undefined`
   *  means both "still fetching" and "the fetch died", and the rail sat on
   *  "Loading…" forever while the console filled with 404s. */
  threadsFailed?: boolean;
  currentThreadId?: string;
  onSelectThread?: (tid: string) => void;
  onNewThread?: () => void;
  /**
   * Drop the conversation list. True for an auto-mode project and for any
   * project with a live run — in both, the run screen owns the workspace and
   * nothing in this list is actionable: it holds one thread, and "New
   * conversation" invites the student to start a second one in the middle of a
   * job whose whole premise is that nobody types anything.
   *
   * The project chip, the home link and the credits stay. Hiding the list must
   * not strand anyone, and the thread itself is still right there in the main
   * pane — this removes the switcher, not the conversation.
   */
  hideThreads?: boolean;
}) {
  const t = useT();
  return (
    <aside
      className="w-[296px] min-w-[296px] flex flex-col h-full bg-white border-r border-ink-200 shrink-0"
      data-testid="workflow-sidebar"
    >
      {/* Brand row */}
      <div className="px-5 pt-[18px] pb-3.5 flex items-center gap-2.5">
        {/* Was a hand-rolled gradient square with a letter "D". Using the shared
            mark means this rail can't fall out of step with the auth screens and
            the global sidebar when logo-mark.png changes — which is exactly how
            it drifted last time. */}
        <BrandMark size={36} className="rounded-[10px]" />
        <div className="min-w-0 flex-1">
          <div className="font-extrabold text-[17.5px] tracking-[-0.01em] text-ink-900">DoThesis</div>
          <div className="text-[11px] uppercase tracking-[0.08em] text-ink-500 font-medium mt-px">
            Thesis copilot
          </div>
        </div>
        {/* Was the Unicode glyph "⌂" (U+2302), which renders as a thin,
            off-baseline house that looked broken. A real vector icon fixes it. */}
        <Link
          href="/"
          aria-label="Home"
          title="Home"
          className="w-7 h-7 rounded-full text-ink-500 hover:bg-ink-50 hover:text-ink-900 inline-flex items-center justify-center transition-colors shrink-0"
        >
          <Home className="w-4 h-4" />
        </Link>
      </div>

      {/* Project chip */}
      {projectName && (
        <div className="mx-[14px] mb-2.5 px-3 py-2.5 bg-ink-50 border border-ink-200 rounded-xl">
          <div className="text-[11px] uppercase tracking-[0.05em] text-ink-500 font-semibold">
            {t("sidebar.project")}
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

      {/* Threads header */}
      {hideThreads ? (
        <div className="flex-1" />
      ) : (
      <>
      <div className="px-[18px] mt-1 mb-2 flex items-center justify-between">
        <div className="text-[10.5px] uppercase tracking-[0.1em] text-ink-500 font-semibold">
          {t("sidebar.threads")}
        </div>
        {threads && (
          <div className="text-[10.5px] tabular-nums text-ink-400 font-semibold">
            {/* `th`, not `t` — `t` is the translator in this scope now. */}
            {threads.filter(th => th.status === "active").length}
          </div>
        )}
      </div>

      {/* Thread list */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {threads ? (
          <ThreadList
            threads={threads}
            activeId={currentThreadId}
            onSelect={onSelectThread}
            onNew={onNewThread}
          />
        ) : threadsFailed ? (
          <div className="text-[12px] text-[#6E5121] px-5 py-3 leading-relaxed">
            {t("ws.threadsFailed")}{" "}
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="underline font-semibold hover:no-underline"
            >
              {t("ws.retry")}
            </button>
          </div>
        ) : (
          <div className="text-[12px] text-ink-500 px-5 py-3">{t("sidebar.loading")}</div>
        )}
      </div>
      </>
      )}

      {/* Project credit total — sum of every response's cost across all
          threads of this project. */}
      {typeof projectCredits === "number" && (
        <div className="px-4 py-3 border-t border-ink-200 flex items-center justify-between text-[12px]">
          <span className="text-ink-500">{t("sidebar.projectCredits")}</span>
          <span className="font-bold text-ink-900 tabular-nums">
            {projectCredits.toLocaleString()}
          </span>
        </div>
      )}

      {/* Language lives here because this rail is on screen for the whole
          working session — a student who got the wrong auto-detected language
          shouldn't have to hunt through settings to fix it. */}
      <div className="px-4 pb-3 pt-1">
        <LocaleSwitcher />
      </div>
    </aside>
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
  const tr = useT();
  const active = threads.filter(t => t.status !== "archived");
  const archived = threads.filter(t => t.status === "archived");

  return (
    // px-[14px] matches the project chip's mx-[14px] directly above. At px-2
    // this block sat 6px further left than everything else in the rail, so the
    // New-thread pill and the selected row read as pushed against the border.
    <div className="px-[14px] pb-2">
      {onNew && (
        <button
          type="button"
          onClick={onNew}
          className="w-full mb-2 px-3 py-2 rounded-full bg-primary-600 text-white inline-flex items-center justify-start gap-2 text-[13px] font-semibold hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" />
          <span>{tr("sidebar.newThread")}</span>
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
            {tr("sidebar.archived")}
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
          {tr("sidebar.noThreads")}
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
        // Selection is a QUIET surface, not a second brand colour. The blue
        // tint competed with the New-thread pill right above it, so the rail
        // had two things shouting at once. Weight + a neutral fill carry the
        // state; hover stays one step lighter so it still reads as reachable.
        active
          ? "bg-ink-100 text-ink-900 font-semibold"
          : "text-ink-700 hover:bg-ink-50 font-medium"
      }`}
    >
      <MessageSquare className="w-3.5 h-3.5 shrink-0" />
      <span className="truncate text-[13px]">{thread.name}</span>
    </button>
  );
}
