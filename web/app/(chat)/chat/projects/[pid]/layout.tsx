"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useParams, useRouter, usePathname } from "next/navigation";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import { ChatShellLayout } from "@/app/components/chat/ChatShellLayout";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { Thread } from "@/app/components/chat/ThreadsSidebar";
import { WorkflowSidebar } from "@/app/components/chat/WorkflowSidebar";
import {
  ContextPanel,
  type ContextStore,
  type ModuleStatusMap,
  type UploadItem,
} from "@/app/components/chat/ContextPanel";
import { LIVE_RUN_STATUSES } from "@/app/components/chat/AutoThesisButton";
import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";


/** ApiError carries `.status`; SWR types its error as `any`. Read it defensively
 *  so a network failure (no status) doesn't get mistaken for a 404. */
function errStatus(e: unknown): number | undefined {
  return typeof e === "object" && e !== null && "status" in e
    ? (e as { status?: number }).status
    : undefined;
}


/**
 * Terminal state for a project that can't be loaded.
 *
 * Before this existed, apiFetch threw, SWR parked the error, and every consumer
 * here read only `data` — so a deleted or someone-else's project rendered the
 * full workspace with `undefined` everywhere: threads stuck on "Loading…", an
 * empty context panel claiming "Topic not set yet", and a live composer
 * inviting you to send a message into a thread the API has never heard of.
 * The console filled with 403/404s while the UI claimed everything was fine.
 */
function ProjectLoadError({ status, message }: { status?: number; message?: string }) {
  const t = useT();
  // The API is inconsistent here: chat.py answers 404 for a project that is
  // missing OR not yours, roadmap.py answers 403 for the same two cases. Treat
  // both as "you can't open this" and only differentiate the copy.
  const notFound = status === 404;
  const forbidden = status === 403;

  return (
    <div className="h-full min-h-screen flex items-center justify-center p-6 bg-ink-50">
      <div className="max-w-[420px] w-full bg-white border border-ink-200 rounded-2xl px-7 py-8 text-center">
        <div className="w-11 h-11 rounded-xl bg-[#F5EFE2] text-[#6E5121] inline-flex items-center justify-center">
          <AlertTriangle className="w-5 h-5" />
        </div>
        <h1 className="mt-4 mb-2 text-xl font-extrabold tracking-tight font-serif text-ink-900">
          {notFound
            ? t("ws.gone.title")
            : forbidden
              ? t("ws.forbidden.title")
              : t("ws.failed.title")}
        </h1>
        <p className="text-sm text-ink-500 leading-relaxed m-0">
          {notFound
            ? t("ws.gone.body")
            : forbidden
              ? t("ws.forbidden.body")
              : message || t("ws.failed.body")}
        </p>
        <div className="flex items-center justify-center gap-2 mt-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-full text-[13.5px] font-semibold no-underline hover:bg-primary-700 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> {t("ws.back")}
          </Link>
          {!notFound && !forbidden && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center px-4 py-2 rounded-full text-[13.5px] font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition-colors"
            >
              {t("ws.retry")}
            </button>
          )}
        </div>
        {status !== undefined && (
          <div className="mt-4 text-[11px] text-ink-400 tabular-nums">HTTP {status}</div>
        )}
      </div>
    </div>
  );
}


export default function ProjectLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const params = useParams<{ pid: string; tid?: string }>();
  const pid = params.pid;
  const currentTid = params.tid;

  // Editor mode hides the context store to give the document the full width.
  // The editor route (/chat/projects/{pid}/editor) is nested UNDER this layout,
  // so the ContextPanel would otherwise wrap the editor and eat ~340px. The
  // editor carries its own outline rail + sources, so the context store is pure
  // redundancy there.
  const pathname = usePathname();
  const isEditor = pathname?.endsWith("/editor") ?? false;

  // Is a run in flight? Drives the polling below and the right rail's own.
  // Cheap: the same key ChatPane polls, so SWR serves both from one request.
  const { data: latestRun } = useSWR<{ run: { status?: string } | null }>(
    `/projects/${pid}/runs/list?latest=true`, fetcher, { refreshInterval: 10000 },
  );
  const runLive = LIVE_RUN_STATUSES.has(latestRun?.run?.status ?? "");

  // Brief §1.4 — module_status now ships with GET /projects/{id} (PR #2).
  // focus is the canonical conversation focus; current_module stays in the
  // type for backward compat during the dual-write window (PR #2b will
  // drop the fallback).
  const { data: project, error: projectError } = useSWR<{
    name?: string;
    /** "auto" | "chat" | null — an auto project's workspace is the run screen. */
    mode?: string | null;
    context_store: ContextStore;
    current_module: string;
    focus?: string | null;
    module_status?: ModuleStatusMap;
    /** Modules whose content predates a later upstream edit — drives the
     *  "may be out of date" note. Advisory; never gates anything. */
    stale_modules?: string[];
  }>(`/projects/${pid}`, fetcher, {
    // While Auto Thesis runs, the project row IS the progress: a subprocess
    // commits each module's slice as it finishes. Fetched once, the right rail
    // froze at whatever was on screen when the page loaded — five locked
    // modules for twenty minutes, then a finished thesis on the next reload.
    // Same key ChatPane and the run screen already poll, so SWR dedupes it.
    refreshInterval: runLive ? 10000 : 0,
  });
  const { data: threads, error: threadsError, mutate: mutateThreads } = useSWR<Thread[]>(
    `/projects/${pid}/threads/list`, fetcher,
  );
  const { data: uploads } = useSWR<UploadItem[]>(`/projects/${pid}/uploads/list`, fetcher);

  // Credit totals: thread (right panel) + project (left panel). POST per the
  // POST-only convention; refreshes on focus so the totals catch up after a
  // response without extra plumbing from ChatPane.
  const postFetcher = (url: string) => apiFetch(url, { method: "POST" });
  const { data: threadCredits } = useSWR<{ total_credits: number; total_tokens: number }>(
    currentTid ? `/threads/${currentTid}/credits` : null, postFetcher,
  );
  const { data: projectCredits } = useSWR<{ total_credits: number; total_tokens: number }>(
    `/projects/${pid}/credits`, postFetcher,
  );

  const createThread = async () => {
    // apiFetch injects access_token into the body — the bare fetch above
    // used to 401 silently because there's no cookie-session anymore.
    const t = (await apiFetch(`/projects/${pid}/threads`, {
      method: "POST",
      body: { name: "New thread" },
    })) as Thread;
    void mutateThreads();
    router.push(`/chat/projects/${pid}/threads/${t.id}`);
  };

  // The project fetch gates the whole workspace: if it failed there is no
  // thread list, no context store and no thread to post into, so render the
  // failure instead of a shell full of empty affordances.
  if (projectError) {
    return (
      <ProjectLoadError
        status={errStatus(projectError)}
        message={(projectError as Error)?.message}
      />
    );
  }

  return (
    <ChatShellLayout
      // Project sidebar — brand + project chip + Threads/Workflow tab toggle.
      // Threads tab carries the thread list; Workflow tab carries the M1-M5
      // rail. Single source of project navigation.
      leftPane={
        <WorkflowSidebar
          projectName={project?.name}
          threads={threads}
          threadsFailed={Boolean(threadsError)}
          currentThreadId={currentTid}
          onSelectThread={tid => router.push(`/chat/projects/${pid}/threads/${tid}`)}
          onNewThread={createThread}
          projectCredits={projectCredits?.total_credits}
          hideThreads={project?.mode === "auto" || runLive}
        />
      }
      rightPane={
        isEditor ? null : (
          <ContextPanel
            projectId={pid}
            loading={!project}
            contextStore={project?.context_store ?? {
              m1_topic: null, m2_literature: null, m3_design: null, m4_analysis: null, m5_writing: null,
            }}
            uploads={uploads ?? []}
            currentModule={project?.focus ?? project?.current_module}
            moduleStatus={project?.module_status}
            staleModules={project?.stale_modules}
            runLive={runLive}
            threadCredits={currentTid ? threadCredits?.total_credits : undefined}
          />
        )
      }
    >
      {children}
    </ChatShellLayout>
  );
}
