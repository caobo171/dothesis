"use client";

import { type ReactNode } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
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


export default function ProjectLayout({ children }: { children: ReactNode }) {
  const router = useRouter();
  const params = useParams<{ pid: string; tid?: string }>();
  const pid = params.pid;
  const currentTid = params.tid;

  // Brief §1.4 — module_status now ships with GET /projects/{id} (PR #2).
  // focus is the canonical conversation focus; current_module stays in the
  // type for backward compat during the dual-write window (PR #2b will
  // drop the fallback).
  const { data: project } = useSWR<{
    name?: string;
    context_store: ContextStore;
    current_module: string;
    focus?: string | null;
    module_status?: ModuleStatusMap;
  }>(`/projects/${pid}`, fetcher);
  const { data: threads, mutate: mutateThreads } = useSWR<Thread[]>(
    `/projects/${pid}/threads`, fetcher,
  );
  const { data: uploads } = useSWR<UploadItem[]>(`/projects/${pid}/uploads`, fetcher);

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

  return (
    <ChatShellLayout
      // Project sidebar — brand + project chip + Threads/Workflow tab toggle.
      // Threads tab carries the thread list; Workflow tab carries the M1-M5
      // rail. Single source of project navigation.
      leftPane={
        <WorkflowSidebar
          projectName={project?.name}
          currentModule={project?.focus ?? project?.current_module}
          moduleStatus={project?.module_status}
          threads={threads}
          currentThreadId={currentTid}
          onSelectThread={tid => router.push(`/chat/projects/${pid}/threads/${tid}`)}
          onNewThread={createThread}
          // Default to Threads tab on the bare project page (no thread
          // selected yet) — the user is shopping for one. Inside a thread,
          // Workflow is the more useful default.
          defaultTab={currentTid ? "workflow" : "threads"}
          projectCredits={projectCredits?.total_credits}
        />
      }
      rightPane={
        <ContextPanel
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
