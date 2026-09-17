"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { BookOpen, MessageCircle, ScanSearch, X } from "lucide-react";

import { swrFetcher } from "@/app/lib/api";
import { ChatPane } from "@/app/components/chat/ChatPane";
import type { Thread } from "@/app/components/chat/ThreadsSidebar";
import { SourcesRail } from "./SourcesRail";
import { Select } from "@/app/components/ui/select";
import { ReviewPanel } from "./ReviewPanel";
import { ClaimConfidencePanel, type ClaimAcceptedChapter, type ClaimReview } from "./ClaimConfidencePanel";
import type { ChapterName } from "./OutlineRail";

type Mode = "sources" | "review" | "claims" | "agent";

/**
 * Editor-native research dock. Sources and the project agent share the same
 * right-hand surface so opening chat never covers the prose or launches a
 * second page. The selected thread is real project state: messages stream
 * through the existing ChatPane/useChat path and remain visible in chat mode.
 */
export function EditorSidePanel({
  projectId,
  highlightedSource,
  onSelectChapter,
  onFlush,
  onClaimAccepted,
  onClaimReviewChange,
  claimReview,
  onOpenClaimReview,
}: {
  projectId: string;
  highlightedSource?: string | null;
  onSelectChapter?: (chapter: ChapterName) => void;
  onFlush: () => Promise<void>;
  onClaimAccepted: (chapter: ClaimAcceptedChapter) => void;
  onClaimReviewChange?: (review: ClaimReview | null) => void;
  claimReview?: ClaimReview | null;
  onOpenClaimReview?: () => void;
}) {
  const [mode, setMode] = useState<Mode>("sources");
  const [agentPrompt, setAgentPrompt] = useState<{ id: string; text: string } | null>(null);
  const [open, setOpen] = useState(true);
  const { data: threads } = useSWR<Thread[]>(`/projects/${projectId}/threads/list`, swrFetcher);
  const activeThreads = (threads ?? []).filter(thread => thread.status !== "archived");
  const [threadId, setThreadId] = useState<string | null>(null);

  useEffect(() => {
    if (threadId && activeThreads.some(thread => thread.id === threadId)) return;
    setThreadId(activeThreads[0]?.id ?? null);
  }, [threads, threadId]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!open) {
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center gap-2 border-l border-ink-100 bg-[#fbfbfa] py-3">
        <button type="button" onClick={() => { setOpen(true); setMode("sources"); }} aria-label="Open sources"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 transition hover:bg-white hover:text-primary-700">
          <BookOpen className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => { setOpen(true); setMode("agent"); }} aria-label="Open AI chat"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 transition hover:bg-white hover:text-primary-700">
          <MessageCircle className="h-4 w-4" />
        </button>
        <button type="button" onClick={() => { setOpen(true); setMode("review"); }} aria-label="Open thesis review"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-ink-500 transition hover:bg-white hover:text-primary-700">
          <ScanSearch className="h-4 w-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="editor-side-panel flex w-[380px] shrink-0 flex-col border-l border-ink-100 bg-white">
      <div className="flex h-12 shrink-0 items-center gap-1 border-b border-ink-100 bg-white px-2">
        <PanelTab active={mode === "sources"} onClick={() => setMode("sources")} icon={<BookOpen className="h-3.5 w-3.5" />}>
          Sources
        </PanelTab>
        <PanelTab active={mode === "review"} onClick={() => setMode("review")} icon={<ScanSearch className="h-3.5 w-3.5" />}>
          Review
        </PanelTab>
        <PanelTab active={mode === "agent"} onClick={() => setMode("agent")} icon={<MessageCircle className="h-3.5 w-3.5" />}>
          Ask agent
        </PanelTab>
        <button type="button" onClick={() => setOpen(false)} aria-label="Close side panel"
          className="ml-auto flex h-8 w-8 items-center justify-center rounded-lg text-ink-400 transition hover:bg-ink-100 hover:text-ink-800">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1">
        {mode === "sources" ? (
          <SourcesRail projectId={projectId} highlightedId={highlightedSource} embedded />
        ) : mode === "review" ? (
          <ReviewPanel
            projectId={projectId}
            onSelectChapter={onSelectChapter}
            onClaimConfidence={() => setMode("claims")}
            onAskAgent={(prompt) => {
              setAgentPrompt({ id: crypto.randomUUID(), text: prompt });
              setMode("agent");
            }}
          />
        ) : mode === "claims" ? (
          <ClaimConfidencePanel
            projectId={projectId}
            onBack={() => setMode("review")}
            onFlush={onFlush}
            onAccepted={onClaimAccepted}
            onSelectChapter={onSelectChapter}
            onReviewChange={onClaimReviewChange}
            reviewSnapshot={claimReview}
            onOpenReview={onOpenClaimReview}
          />
        ) : (
          <div className="flex h-full min-h-0 flex-col">
            <div className="flex shrink-0 items-center gap-2 border-b border-ink-100 bg-[#fbfbfa] px-3 py-2">
              <span className="text-[11px] font-semibold text-ink-400">THREAD</span>
              {activeThreads.length > 0 ? (
                <Select
                  value={threadId ?? ""}
                  onValueChange={setThreadId}
                  ariaLabel="Chat thread"
                  options={activeThreads.map(thread => ({ value: thread.id, label: thread.name }))}
                  size="sm"
                  className="min-w-0 flex-1 [&_button]:h-8 [&_button]:border-ink-200 [&_button]:px-2 [&_button]:text-xs [&_button]:font-medium [&_button]:shadow-none"
                />
              ) : (
                <span className="text-xs text-ink-500">No active thread</span>
              )}
            </div>
            {threadId ? (
              <div className="min-h-0 flex-1"><ChatPane projectId={projectId} threadId={threadId} compact autoPrompt={agentPrompt} /></div>
            ) : (
              <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-ink-500">
                Create a project thread to chat with the thesis agent.
              </div>
            )}
          </div>
        )}
      </div>
    </aside>
  );
}

function PanelTab({ active, onClick, icon, children }: { active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <button type="button" onClick={onClick}
      className={"inline-flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold transition " + (active ? "bg-primary-50 text-primary-700" : "text-ink-500 hover:bg-ink-50 hover:text-ink-800")}>
      {icon}{children}
    </button>
  );
}
