"use client";

import { type ReactNode } from "react";
import useSWR from "swr";
import { useParams, useRouter } from "next/navigation";
import { ChatShellLayout } from "@/app/components/chat/ChatShellLayout";
import { ThreadsSidebar, type Thread } from "@/app/components/chat/ThreadsSidebar";
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
    context_store: ContextStore;
    current_module: string;
    focus?: string | null;
    module_status?: ModuleStatusMap;
  }>(`/projects/${pid}`, fetcher);
  const { data: threads, mutate: mutateThreads } = useSWR<Thread[]>(
    `/projects/${pid}/threads`, fetcher,
  );
  const { data: uploads } = useSWR<UploadItem[]>(`/projects/${pid}/uploads`, fetcher);

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
      onNewThread={createThread}
      leftPane={
        <ThreadsSidebar
          threads={threads ?? []}
          currentThreadId={currentTid ?? ""}
          onSelectThread={tid => router.push(`/chat/projects/${pid}/threads/${tid}`)}
        />
      }
      rightPane={
        <ContextPanel
          contextStore={project?.context_store ?? {
            m1_topic: null, m2_literature: null, m3_design: null, m4_analysis: null, m5_writing: null,
          }}
          uploads={uploads ?? []}
          // Prefer focus (brief §1.4 — fluid conversation focus) over
          // current_module. current_module is the dual-write fallback for
          // older projects whose focus column is still NULL.
          currentModule={project?.focus ?? project?.current_module}
          moduleStatus={project?.module_status}
        />
      }
    >
      {children}
    </ChatShellLayout>
  );
}
