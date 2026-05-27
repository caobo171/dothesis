"use client";

import { useState } from "react";
import useSWR from "swr";
import { useChat } from "./hooks/useChat";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { AutoDraftButton, type RunStatus } from "./AutoDraftButton";
import { AutoDraftModal } from "./AutoDraftModal";
import { AutoDraftDrawer } from "./AutoDraftDrawer";
import { synthesizeWidgetSelection } from "./widgets/synthesize";
import type { WidgetSelectHandler } from "./widgets/types";


const fetcher = async (url: string) => {
  const res = await fetch(`/api/v1${url}`);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
};


export function ChatPane({ projectId, threadId }: { projectId: string; threadId: string }) {
  const { messages, streamingText, inflight, send } = useChat(threadId);
  // SP6.5: include m5_writing.chapters so we can gate the "Open editor" link in
  // ChatHeader — the link must only appear once at least one chapter exists.
  const { data: project } = useSWR<{
    name: string;
    context_store: {
      m1_topic?: { research_title?: string } | null;
      m5_writing?: { chapters?: Record<string, unknown> } | null;
    };
  }>(
    `/projects/${projectId}`, fetcher,
  );
  const { data: thread } = useSWR<{ name: string }>(`/threads/${threadId}`, fetcher);
  const { data: latestRun, mutate: mutateRun } = useSWR<{ run: { id: string; status: RunStatus } | null }>(
    `/projects/${projectId}/runs?latest=true`, fetcher,
  );

  // SP6.5: gate is true only when at least one chapter entry exists.
  // Defaults to false while the project data is still loading.
  const hasChapters =
    Object.keys(project?.context_store?.m5_writing?.chapters ?? {}).length > 0;

  const [modalOpen, setModalOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const onAutoDraftClick = () => {
    const status = latestRun?.run?.status ?? null;
    // If a run is active/done/failed, open the drawer to show its progress
    if (status === "running" || status === "paused" || status === "done" || status === "failed") {
      setDrawerOpen(true);
    } else {
      setModalOpen(true);
    }
  };

  const confirmAutoDraft = async (topic: string) => {
    setModalOpen(false);
    const r = await fetch(`/api/v1/projects/${projectId}/runs`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "auto", topic }),
    });
    if (r.ok) {
      void mutateRun();
      setDrawerOpen(true);
    }
  };

  const onWidgetSelect: WidgetSelectHandler = (fieldName, value, label) => {
    // SP3: translate widget click into a natural-language user message that
    // the agent's free-text extractor can parse. Click thus reuses the
    // existing send path — no new backend protocol needed.
    const text = synthesizeWidgetSelection(fieldName, value, label);
    void send(text);
  };

  const onFileDrop = async (files: File[]) => {
    for (const f of files) {
      const fd = new FormData();
      fd.append("file", f);
      await fetch(`/api/v1/projects/${projectId}/uploads`, { method: "POST", body: fd });
    }
  };

  return (
    <>
      <ChatHeader
        projectName={project?.name ?? "…"}
        threadName={thread?.name ?? "…"}
        autoDraftButton={
          <AutoDraftButton runStatus={latestRun?.run?.status ?? null} onClick={onAutoDraftClick} />
        }
        projectId={projectId}
        hasChapters={hasChapters}
      />
      <MessageList
        messages={messages}
        streamingText={inflight ? streamingText : ""}
        streamingModuleTag={null}
        onWidgetSelect={onWidgetSelect}
      />
      <ChatInput onSubmit={send} onFileDrop={onFileDrop} disabled={inflight} />

      <AutoDraftModal
        open={modalOpen}
        projectId={projectId}
        defaultTopic={project?.context_store?.m1_topic?.research_title ?? ""}
        onClose={() => setModalOpen(false)}
        onConfirm={confirmAutoDraft}
      />
      {drawerOpen && latestRun?.run && (
        <AutoDraftDrawer runId={latestRun.run.id} onClose={() => setDrawerOpen(false)} />
      )}
    </>
  );
}
