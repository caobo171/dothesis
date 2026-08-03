"use client";

import { type ReactNode } from "react";
import Link from "next/link";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { AlertTriangle, ArrowLeft } from "lucide-react";
import { ChatShellLayout } from "@/app/components/chat/ChatShellLayout";
import type { Thread } from "@/app/components/chat/ThreadsSidebar";
import { WorkflowSidebar } from "@/app/components/chat/WorkflowSidebar";
import {
  ContextPanel,
  type ContextStore,
  type ModuleStatusMap,
  type UploadItem,
} from "@/app/components/chat/ContextPanel";
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
            ? "This thesis no longer exists"
            : forbidden
              ? "You don’t have access to this thesis"
              : "Couldn’t load this thesis"}
        </h1>
        <p className="text-sm text-ink-500 leading-relaxed m-0">
          {notFound
            ? "It was deleted, or this link points at a project from another workspace."
            : forbidden
              ? "It belongs to a different account. Check which account you’re signed in as."
              : message || "The server didn’t respond as expected. Try again in a moment."}
        </p>
        <div className="flex items-center justify-center gap-2 mt-6">
          <Link
            href="/"
            className="inline-flex items-center gap-2 bg-primary-600 text-white px-4 py-2 rounded-full text-[13.5px] font-semibold no-underline hover:bg-primary-700 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back to your theses
          </Link>
          {!notFound && !forbidden && (
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="inline-flex items-center px-4 py-2 rounded-full text-[13.5px] font-semibold border border-ink-200 text-ink-700 hover:bg-ink-50 transition-colors"
            >
              Retry
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

  // Brief §1.4 — module_status now ships with GET /projects/{id} (PR #2).
  // focus is the canonical conversation focus; current_module stays in the
  // type for backward compat during the dual-write window (PR #2b will
  // drop the fallback).
  const { data: project, error: projectError } = useSWR<{
    name?: string;
    context_store: ContextStore;
    current_module: string;
    focus?: string | null;
    module_status?: ModuleStatusMap;
  }>(`/projects/${pid}`, fetcher);
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
        />
      }
      rightPane={
        <ContextPanel
          projectId={pid}
          contextStore={project?.context_store ?? {
            m1_topic: null, m2_literature: null, m3_design: null, m4_analysis: null, m5_writing: null,
          }}
          uploads={uploads ?? []}
          currentModule={project?.focus ?? project?.current_module}
          moduleStatus={project?.module_status}
          threadCredits={currentTid ? threadCredits?.total_credits : undefined}
        />
      }
    >
      {children}
    </ChatShellLayout>
  );
}
