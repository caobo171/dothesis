"use client";

import { useState } from "react";
import useSWR from "swr";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowRight,
  BookOpenCheck,
  CheckCircle2,
  Clock3,
  Loader2,
  Play,
  Plus,
  Sparkles,
  Zap,
} from "lucide-react";

import { useMe } from "@/app/lib/use-me";
import { NewProjectModal } from "./NewProjectModal";
import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";


// Mirrors ProjectOut from api/app/routers/chat.py. focus + module_status are
// nullable/empty during the dual-write window (PR #1/#2) — every consumer
// below falls back to current_module / context_store confirmed_at.
// Exported (with the helpers below) so /papers can render the same module
// bar + status derivation without duplicating the precedence rules.
export type Project = {
  id: string;
  name: string;
  field: string | null;
  language: string;
  citation_style: string;
  status: string;
  current_module: string;
  focus: string | null;
  module_status: Partial<Record<ModuleId, string>>;
  context_store: Partial<Record<SliceKey, { confirmed_at?: string | null } | null>>;
  created_at: string;
  updated_at: string;
};

type ModuleId = "M1" | "M2" | "M3" | "M4" | "M5";
type SliceKey = "m1_topic" | "m2_literature" | "m3_design" | "m4_analysis" | "m5_writing";
export type ModuleDisplayStatus = "done" | "in_progress" | "needs_review" | "locked";

export const MODULES: Array<{ id: ModuleId; slice: SliceKey; label: string }> = [
  { id: "M1", slice: "m1_topic",      label: "Topic Discovery" },
  { id: "M2", slice: "m2_literature", label: "Literature Review" },
  { id: "M3", slice: "m3_design",     label: "Research Design" },
  { id: "M4", slice: "m4_analysis",   label: "Data Analysis" },
  { id: "M5", slice: "m5_writing",    label: "Writing" },
];

// Same precedence as ContextPanel.statusFor so the home cards and the
// in-project progress panel never disagree about a module's state:
// needs_review (explicit flag) > done > focus/current > locked.
export function moduleStatus(p: Project, m: { id: ModuleId; slice: SliceKey }): ModuleDisplayStatus {
  const fromMap = p.module_status?.[m.id];
  if (fromMap === "needs_review") return "needs_review";
  if (fromMap === "done" || p.context_store?.[m.slice]?.confirmed_at) return "done";
  if (fromMap === "in_progress" || m.id === (p.focus ?? p.current_module)) return "in_progress";
  return "locked";
}

// The API has no stored progress %; derive it from module states. A done
// module is worth a full fifth, anything started counts half — matches how
// the design mock weighted its example projects (e.g. 1 done + 1 active ≈ 30%).
function progressPct(p: Project): number {
  let score = 0;
  for (const m of MODULES) {
    const s = moduleStatus(p, m);
    if (s === "done") score += 20;
    else if (s === "in_progress" || s === "needs_review") score += 10;
  }
  return score;
}

export function needsReview(p: Project): boolean {
  return MODULES.some(m => moduleStatus(p, m) === "needs_review");
}

export function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const min = Math.floor(diff / 60_000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d ago`;
  const w = Math.floor(d / 7);
  return w < 5 ? `${w}w ago` : new Date(iso).toLocaleDateString();
}

function dayPartGreeting(): string {
  const now = new Date();
  const weekday = now.toLocaleDateString("en-US", { weekday: "long" });
  const h = now.getHours();
  const part = h < 12 ? "morning" : h < 18 ? "afternoon" : "evening";
  return `${weekday} ${part}`;
}


export function HomeDashboard() {
  const { data: projects, mutate } = useSWR<Project[]>("/projects", fetcher, { dedupingInterval: 0 });
  const me = useMe();
  const [modalOpen, setModalOpen] = useState(false);
  const router = useRouter();

  // After creation: revalidate the project list and route the user directly
  // into the new project. That's the typical next action and saves a click.
  const handleCreated = (project: { id: string; name: string }) => {
    void mutate();
    setModalOpen(false);
    router.push(`/chat/projects/${project.id}`);
  };

  // /projects is ordered updated_at desc, so [0] is "where you left off".
  const current = projects?.[0];
  const reviewCount = projects?.filter(needsReview).length ?? 0;
  const firstName =
    me.data?.username || me.data?.email?.split("@")[0] || "there";

  // No own padding: the (inapp) shell already wraps pages in a padded
  // max-w-7xl container (SidebarLayout non-fullBleed branch).
  return (
    <div className="max-w-6xl mx-auto">
      <NewProjectModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onCreated={handleCreated}
      />

      <Hero
        firstName={firstName}
        current={current}
        credit={me.data?.credit}
        onNewThesis={() => setModalOpen(true)}
      />

      <StatsRow projects={projects} reviewCount={reviewCount} />

      <div className="flex items-end justify-between mt-7 mb-4 px-0.5">
        <div>
          <h2 className="m-0 text-[22px] font-extrabold tracking-tight font-serif text-ink-900">
            Your theses
          </h2>
          <div className="text-[12.5px] text-ink-500 mt-1">
            {projects
              ? `${projects.length} active${reviewCount ? ` · ${reviewCount} need${reviewCount === 1 ? "s" : ""} review` : ""}`
              : "Loading…"}
          </div>
        </div>
        <button
          type="button"
          onClick={() => setModalOpen(true)}
          className="inline-flex items-center gap-1.5 bg-primary-600 text-white pl-3 pr-4 py-2 rounded-full text-[13.5px] font-semibold hover:bg-primary-700 transition-colors"
        >
          <Plus className="w-4 h-4" /> New thesis
        </button>
      </div>

      {projects && projects.length === 0 && (
        <div className="text-center py-12 text-ink-500 bg-white border border-ink-200 rounded-2xl">
          No projects yet. Click the New thesis button to get started.
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-[18px]">
        {projects?.map(p => <ProjectCard key={p.id} p={p} />)}
      </div>

      {projects && projects.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[1.6fr_1fr] gap-[18px] mt-8">
          <RecentActivity projects={projects} />
          <ProTip />
        </div>
      )}
    </div>
  );
}


/* ---------- Hero: greeting + resume/new CTAs + token balance card ---------- */
function Hero({
  firstName,
  current,
  credit,
  onNewThesis,
}: {
  firstName: string;
  current: Project | undefined;
  credit: number | undefined;
  onNewThesis: () => void;
}) {
  const focusModule = current ? (current.focus ?? current.current_module) : null;
  const focusLabel = MODULES.find(m => m.id === focusModule)?.label;

  return (
    <section
      className="relative rounded-3xl px-9 pt-8 pb-7 text-white overflow-hidden mb-6"
      style={{ background: "linear-gradient(120deg, #0b0d1a 0%, #161827 55%, #1c2eff 130%)" }}
    >
      {/* Decorative ink-blot + line waves, straight from the design mock */}
      <svg width="360" height="260" className="absolute -top-8 -right-10 opacity-20 pointer-events-none" viewBox="0 0 360 260" aria-hidden>
        <defs>
          <radialGradient id="home-hero-blob" cx="50%" cy="40%">
            <stop offset="0%" stopColor="#5b3aa8" />
            <stop offset="100%" stopColor="#0b0d1a" stopOpacity="0" />
          </radialGradient>
        </defs>
        <ellipse cx="180" cy="120" rx="160" ry="110" fill="url(#home-hero-blob)" />
      </svg>
      <svg width="420" height="200" className="absolute -bottom-10 left-8 opacity-10 pointer-events-none" viewBox="0 0 420 200" fill="none" aria-hidden>
        <path d="M0 100 Q 60 30 140 90 T 280 90 T 420 90" stroke="white" strokeWidth="1.2" />
        <path d="M0 120 Q 60 50 140 110 T 280 110 T 420 110" stroke="white" strokeWidth="1.2" />
        <path d="M0 140 Q 60 70 140 130 T 280 130 T 420 130" stroke="white" strokeWidth="1.2" />
      </svg>

      <div className="relative flex flex-col lg:flex-row lg:items-end gap-8">
        <div className="flex-1 min-w-0">
          <div className="text-xs uppercase tracking-[0.18em] text-white/60 font-bold">
            {dayPartGreeting()}
          </div>
          <h1 className="mt-2 mb-1.5 text-[34px] font-extrabold tracking-tight font-serif leading-[1.1]">
            Hello, {firstName} —
            <br />
            <span className="text-white/75 font-semibold">
              {current ? "pick up where you left off?" : "ready to start your thesis?"}
            </span>
          </h1>
          <div className="text-sm text-white/70 max-w-[520px] mt-2 leading-relaxed">
            {current ? (
              <>
                You&apos;re in <span className="font-semibold text-white">{focusModule}</span>
                {focusLabel ? ` · ${focusLabel}` : ""} on “{current.name}” — resume to keep going.
              </>
            ) : (
              "Five modules from topic to final draft — one chat thread, your sources, page-cited."
            )}
          </div>
          <div className="flex flex-wrap gap-2.5 mt-4">
            {current && (
              <Link
                href={`/chat/projects/${current.id}`}
                className="inline-flex items-center gap-2 bg-white text-ink-900 px-5 py-[11px] rounded-full text-sm font-semibold no-underline hover:bg-ink-100 transition-colors"
              >
                <Play className="w-3.5 h-3.5" /> Resume current thesis
              </Link>
            )}
            <button
              type="button"
              onClick={onNewThesis}
              className={
                current
                  ? "inline-flex items-center gap-2 bg-white/10 text-white border border-white/20 px-5 py-[11px] rounded-full text-sm font-semibold hover:bg-white/20 transition-colors"
                  : "inline-flex items-center gap-2 bg-white text-ink-900 px-5 py-[11px] rounded-full text-sm font-semibold hover:bg-ink-100 transition-colors"
              }
            >
              <Plus className="w-4 h-4" /> Start a new thesis
            </button>
          </div>
        </div>

        {/* Token balance card. The mock showed used/quota; the API only exposes
            a credit balance, so we show the balance + top-up instead of a fake
            quota bar. */}
        <div className="w-full lg:w-[260px] shrink-0 rounded-2xl border border-white/[0.18] bg-white/[0.08] px-[18px] py-4 backdrop-blur">
          <div className="flex items-center gap-1.5 text-[11px] text-white/70 font-bold uppercase tracking-[0.08em]">
            <Zap className="w-3 h-3" />
            <span>Credit balance</span>
          </div>
          <div className="flex items-baseline gap-1.5 mt-1 tabular-nums">
            <span className="text-3xl font-extrabold tracking-tight">
              {credit !== undefined ? credit.toLocaleString() : "—"}
            </span>
            <span className="text-xs text-white/60">credits</span>
          </div>
          <div className="flex gap-1.5 mt-3">
            <Link
              href="/credit"
              className="flex-1 text-center px-2.5 py-[7px] rounded-full bg-white text-ink-900 text-[12.5px] font-bold no-underline hover:bg-ink-100 transition-colors"
            >
              + Top up
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}


/* ---------- Stats row ---------- */
function StatsRow({ projects, reviewCount }: { projects: Project[] | undefined; reviewCount: number }) {
  const modulesDone =
    projects?.reduce((acc, p) => acc + MODULES.filter(m => moduleStatus(p, m) === "done").length, 0) ?? 0;
  const modulesActive =
    projects?.reduce((acc, p) => acc + MODULES.filter(m => moduleStatus(p, m) === "in_progress").length, 0) ?? 0;

  const cells = [
    { icon: Clock3,        v: projects?.length ?? "—", l: "Active theses",     sub: "across your account", chip: "bg-primary-50 text-primary-600" },
    { icon: CheckCircle2,  v: modulesDone,             l: "Modules completed", sub: "of 5 per thesis",      chip: "bg-[var(--ok-bg)] text-[var(--ok-fg)]" },
    { icon: Loader2,       v: modulesActive,           l: "In progress",       sub: "modules being worked", chip: "bg-[#efeafd] text-[var(--accent-violet)]" },
    { icon: AlertTriangle, v: reviewCount,             l: "Needs review",      sub: reviewCount ? "open ⚠ flags" : "all clear", chip: "bg-[var(--pause-bg)] text-[var(--pause-fg)]" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-3.5 mb-7">
      {cells.map((c, i) => (
        <div key={i} className="bg-white rounded-2xl border border-ink-200 px-[18px] py-4 flex flex-col gap-1">
          <div className={`w-7 h-7 rounded-lg inline-flex items-center justify-center ${c.chip}`}>
            <c.icon className="w-4 h-4" />
          </div>
          <div className="text-[26px] font-extrabold tracking-tight tabular-nums mt-0.5 text-ink-900">{c.v}</div>
          <div className="text-[12.5px] text-ink-500 font-medium">{c.l}</div>
          <div className="text-[11px] text-ink-400 mt-0.5">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}


/* ---------- Project card with M1–M5 module bar ---------- */
export const SEGMENT_STYLE: Record<ModuleDisplayStatus, string> = {
  done:         "bg-[var(--ok-fg)] text-white",
  in_progress:  "bg-primary-600 text-white",
  needs_review: "bg-[var(--pause-fg)] text-white",
  locked:       "bg-ink-100 text-ink-500",
};

function ProjectCard({ p }: { p: Project }) {
  const review = needsReview(p);
  const pct = progressPct(p);
  const focusModule = p.focus ?? p.current_module;
  const focusLabel = MODULES.find(m => m.id === focusModule)?.label;

  return (
    <Link
      href={`/chat/projects/${p.id}`}
      className="block bg-white rounded-[18px] border border-ink-200 px-[22px] py-5 no-underline text-inherit transition-all hover:border-primary-100 hover:shadow-[var(--shadow-pop)] hover:-translate-y-px"
    >
      <div className="flex items-center gap-2 mb-2.5">
        <span className="text-[11px] text-ink-500 font-bold tracking-[0.06em] uppercase truncate max-w-[60%]">
          {p.field ?? "No field set"}
        </span>
        <span className="flex-1" />
        {review && (
          <span className="inline-flex items-center gap-1 px-2.5 py-[3px] rounded-full text-[11.5px] font-semibold bg-[var(--pause-bg)] text-[var(--pause-fg)] whitespace-nowrap shrink-0">
            <AlertTriangle className="w-3 h-3" /> Needs review
          </span>
        )}
        <span className="text-xs text-ink-500 font-semibold tabular-nums shrink-0">{pct}%</span>
      </div>

      <h3 className="m-0 text-base font-bold leading-snug font-serif text-ink-900 line-clamp-2 min-h-[44px]">
        {p.name}
      </h3>
      <div className="text-xs text-ink-500 mt-1 uppercase">
        {p.language} · {p.citation_style}
      </div>

      {/* Module bar — one segment per module, status-colored like the mock */}
      <div className="flex gap-1.5 mt-3.5">
        {MODULES.map(m => {
          const s = moduleStatus(p, m);
          return (
            <span
              key={m.id}
              title={`${m.id} · ${m.label} · ${s.replace("_", " ")}`}
              className={`flex-1 px-1 py-1.5 rounded-lg text-center text-[11px] font-bold font-serif inline-flex items-center justify-center gap-1 ${SEGMENT_STYLE[s]}`}
            >
              {m.id}
              {s === "done" && <span aria-hidden>✓</span>}
              {s === "needs_review" && <span aria-hidden>⚠</span>}
            </span>
          );
        })}
      </div>

      <div className="mt-3.5 pt-3.5 border-t border-dashed border-ink-200 flex items-center gap-2">
        <span className="text-[11.5px] text-ink-500 font-semibold uppercase tracking-[0.04em]">Next</span>
        <span className="text-[13px] text-ink-800 font-medium flex-1 truncate">
          Continue {focusModule}{focusLabel ? ` · ${focusLabel}` : ""}
        </span>
        <ArrowRight className="w-3.5 h-3.5 text-primary-600 shrink-0" />
      </div>
      <div className="text-[11px] text-ink-400 mt-1.5">
        last touched {relativeTime(p.updated_at)} · {focusModule}
      </div>
    </Link>
  );
}


/* ---------- Recent activity, derived from project recency ---------- */
// There's no activity-event API yet, so the timeline shows each project's
// latest state (most recently touched first) rather than invented events.
function RecentActivity({ projects }: { projects: Project[] }) {
  const items = projects.slice(0, 5);
  return (
    <div className="bg-white rounded-[18px] border border-ink-200 px-[22px] py-5">
      <div className="flex items-center gap-2 mb-4">
        <h3 className="m-0 text-base font-extrabold tracking-tight text-ink-900">Recent activity</h3>
      </div>
      <ol className="m-0 p-0 list-none relative">
        <span className="absolute left-[13px] top-3 bottom-3 w-0.5 bg-ink-100" aria-hidden />
        {items.map((p, i) => {
          const focusModule = p.focus ?? p.current_module;
          const focusLabel = MODULES.find(m => m.id === focusModule)?.label;
          const review = needsReview(p);
          return (
            <li key={p.id} className={`relative flex gap-3 ${i === items.length - 1 ? "" : "pb-3.5"}`}>
              <span
                className={`w-7 h-7 min-w-7 rounded-full bg-white border-2 inline-flex items-center justify-center z-[1] ${
                  review ? "border-[var(--pause-fg)] text-[var(--pause-fg)]" : "border-primary-600 text-primary-600"
                }`}
              >
                {review ? <AlertTriangle className="w-3 h-3" /> : <BookOpenCheck className="w-3 h-3" />}
              </span>
              <div className="flex-1 min-w-0">
                <div className="text-[13.5px] text-ink-900 leading-relaxed truncate">
                  {review ? "Flagged for review in " : "Working in "}
                  <span className="font-semibold">{focusModule}{focusLabel ? ` · ${focusLabel}` : ""}</span>
                </div>
                <div className="text-[11.5px] text-ink-500 mt-0.5 flex items-center gap-1.5 min-w-0">
                  <span className="font-serif font-bold text-primary-600 shrink-0">{focusModule}</span>
                  <span aria-hidden>·</span>
                  <span className="font-medium text-ink-700 truncate">{p.name}</span>
                  <span aria-hidden>·</span>
                  <span className="shrink-0">{relativeTime(p.updated_at)}</span>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}


/* ---------- Pro tip — teaches the read-vs-mutate focus rule ---------- */
function ProTip() {
  return (
    <div className="rounded-[18px] px-5 py-[18px] border border-primary-100 bg-gradient-to-br from-primary-50 to-[#f1edfe] self-start">
      <div className="flex items-center gap-1.5 text-[11px] text-primary-600 font-bold tracking-[0.08em] uppercase">
        <Sparkles className="w-3 h-3" /> Pro tip
      </div>
      <div className="text-sm font-semibold mt-1 leading-relaxed text-ink-900 font-serif">
        You can ask about any module from any other — focus only shifts on an edit, not a read.
      </div>
      <div className="flex gap-2 mt-3 flex-wrap">
        <span className="inline-flex items-center px-3 py-1.5 rounded-full text-[13px] font-medium bg-white text-ink-700 border border-ink-200">
          “What is gap G2?”
        </span>
        <span className="inline-flex items-center px-3 py-1.5 rounded-full text-[13px] font-medium bg-white text-ink-700 border border-ink-200">
          “Edit hypothesis H1”
        </span>
      </div>
    </div>
  );
}
