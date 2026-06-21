"use client";

// 2026-06-10 — restyled to match the Home.html design system used by the
// root dashboard (serif headings, pill buttons, status tags, M1–M5 module
// bar). Drafts ARE orchestrator projects (this page reads /projects, see the
// 2026-06 fix), so the table reuses HomeDashboard's status helpers — the
// list and the dashboard cards can never disagree about a draft's state.
import useSWR from "swr";
import Link from "next/link";
import { AlertTriangle, ArrowRight, Plus } from "lucide-react";

import {
  MODULES,
  SEGMENT_STYLE,
  moduleStatus,
  needsReview,
  relativeTime,
  type Project,
} from "@/app/components/chat/HomeDashboard";
import { swrFetcher as fetcher } from "@/app/lib/api";


// One coarse status per draft, same precedence as the dashboard card:
// finished > flagged > started > untouched.
type DraftStatus = "done" | "needs_review" | "in_progress" | "draft";

function draftStatus(p: Project): DraftStatus {
  if (p.current_module === "DONE") return "done";
  if (needsReview(p)) return "needs_review";
  if (MODULES.some(m => moduleStatus(p, m) !== "locked")) return "in_progress";
  return "draft";
}

const STATUS_TAG: Record<DraftStatus, { label: string; cls: string }> = {
  done:         { label: "Done",         cls: "bg-[var(--ok-bg)] text-[var(--ok-fg)]" },
  needs_review: { label: "Needs review", cls: "bg-[var(--pause-bg)] text-[var(--pause-fg)]" },
  in_progress:  { label: "In progress",  cls: "bg-primary-50 text-primary-700" },
  draft:        { label: "Draft",        cls: "bg-ink-100 text-ink-500" },
};


export default function PapersPage() {
  const { data: papers, error, isLoading } = useSWR<Project[]>("/projects/list", fetcher);

  const list = papers ?? [];

  return (
    <section className="max-w-6xl mx-auto w-full">
      <div className="flex items-end justify-between gap-2 mb-4 px-0.5">
        <div>
          <h1 className="m-0 text-[22px] font-extrabold tracking-tight font-serif text-ink-900">
            Theses
          </h1>
          <div className="text-[12.5px] text-ink-500 mt-1">
            {isLoading
              ? "Loading…"
              : `${list.length} ${list.length === 1 ? "thesis" : "theses"} in your workspace`}
          </div>
        </div>
        <Link
          href="/new"
          className="inline-flex items-center gap-1.5 bg-primary-600 text-white pl-3 pr-4 py-2 rounded-full text-[13.5px] font-semibold hover:bg-primary-700 transition-colors no-underline"
        >
          <Plus className="w-4 h-4" /> New thesis
        </Link>
      </div>

      {error && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {(error as Error).message || "Could not load theses"}
        </div>
      )}

      {!isLoading && list.length === 0 && !error && (
        <div className="bg-white rounded-2xl border border-dashed border-ink-200 p-12 text-center">
          <h2 className="text-base font-bold font-serif text-ink-900">No theses yet</h2>
          <p className="text-sm text-ink-500 mt-2">
            <Link
              href="/new"
              className="text-primary-600 font-medium hover:underline no-underline"
            >
              Start your first one →
            </Link>
          </p>
        </div>
      )}

      {list.length > 0 && (
        <div className="bg-white rounded-[18px] border border-ink-200 overflow-hidden">
          {/* Desktop table */}
          <table className="min-w-full hidden md:table">
            <thead>
              <tr className="border-b border-ink-100">
                <Th className="pl-6 w-14">No</Th>
                <Th>Draft title</Th>
                <Th className="w-44">Modules</Th>
                <Th className="w-32">Status</Th>
                <Th className="w-32">Updated</Th>
                <th className="py-3 pr-6 w-24" />
              </tr>
            </thead>
            <tbody>
              {list.map((p, idx) => (
                <DraftRow key={p.id} p={p} index={idx + 1} />
              ))}
            </tbody>
          </table>

          {/* Mobile cards */}
          <div className="md:hidden divide-y divide-ink-100">
            {list.map(p => (
              <DraftMobileRow key={p.id} p={p} />
            ))}
          </div>
        </div>
      )}
    </section>
  );
}


function Th({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return (
    <th
      className={`py-3 pr-3 text-left text-[11px] font-bold uppercase tracking-[0.06em] text-ink-500 ${className}`}
    >
      {children}
    </th>
  );
}


// Compact version of the dashboard card's module bar — same colors, same
// status derivation, sized for a table row.
function ModuleMiniBar({ p }: { p: Project }) {
  return (
    <div className="flex gap-1 max-w-[160px]">
      {MODULES.map(m => {
        const s = moduleStatus(p, m);
        return (
          <span
            key={m.id}
            title={`${m.id} · ${m.label} · ${s.replace("_", " ")}`}
            className={`flex-1 px-0.5 py-1 rounded-md text-center text-[10px] font-bold font-serif inline-flex items-center justify-center ${SEGMENT_STYLE[s]}`}
          >
            {m.id}
          </span>
        );
      })}
    </div>
  );
}


function StatusTag({ p }: { p: Project }) {
  const s = STATUS_TAG[draftStatus(p)];
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-[3px] rounded-full text-[11.5px] font-semibold whitespace-nowrap ${s.cls}`}>
      {draftStatus(p) === "needs_review" && <AlertTriangle className="w-3 h-3" />}
      {s.label}
    </span>
  );
}


function DraftRow({ p, index }: { p: Project; index: number }) {
  return (
    <tr className="border-b border-ink-100 last:border-b-0 hover:bg-ink-50/60 transition-colors">
      <td className="py-4 pl-6 pr-3 whitespace-nowrap text-sm text-ink-400 tabular-nums">
        {index.toString().padStart(2, "0")}.
      </td>
      <td className="py-4 pr-3">
        <div className="text-sm font-bold font-serif text-ink-900 truncate max-w-[300px] lg:max-w-[400px]">
          {p.name || "Untitled"}
        </div>
        <div className="text-[11px] text-ink-500 mt-0.5 uppercase tracking-[0.04em] truncate">
          {p.field || "No field set"} · {p.language}
        </div>
      </td>
      <td className="py-4 pr-3"><ModuleMiniBar p={p} /></td>
      <td className="py-4 pr-3"><StatusTag p={p} /></td>
      <td className="py-4 pr-3 whitespace-nowrap text-sm text-ink-500">
        {p.updated_at ? relativeTime(p.updated_at) : "—"}
      </td>
      <td className="py-4 pr-6 whitespace-nowrap text-right">
        <Link
          href={`/chat/projects/${p.id}`}
          className="inline-flex items-center gap-1 px-4 py-1.5 border-[1.5px] border-primary-600 text-primary-600 text-[13px] font-semibold rounded-full hover:bg-primary-50 transition-colors no-underline"
        >
          Open <ArrowRight className="w-3 h-3" />
        </Link>
      </td>
    </tr>
  );
}


function DraftMobileRow({ p }: { p: Project }) {
  return (
    <Link
      href={`/chat/projects/${p.id}`}
      className="block px-4 py-3.5 no-underline text-inherit hover:bg-ink-50/60 transition-colors"
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-bold font-serif text-ink-900 truncate">
          {p.name || "Untitled"}
        </span>
        <StatusTag p={p} />
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <ModuleMiniBar p={p} />
        <span className="text-[11px] text-ink-400 shrink-0">
          {p.updated_at ? relativeTime(p.updated_at) : "—"}
        </span>
      </div>
    </Link>
  );
}
