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


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


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
    const r = await fetch(`/api/v1/projects/${pid}/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "New thread" }),
    });
    const t: Thread = await r.json();
    void mutateThreads();
    router.push(`/chat/projects/${pid}/threads/${t.id}`);
  };

  return (
    <ChatShellLayout
      leftPane={
        <ThreadsSidebar
          threads={threads ?? []}
          currentThreadId={currentTid ?? ""}
          onSelectThread={tid => router.push(`/chat/projects/${pid}/threads/${tid}`)}
          onCreateThread={createThread}
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
