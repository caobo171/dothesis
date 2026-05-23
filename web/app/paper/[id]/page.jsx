"use client";

import { Suspense } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import useSWR from "swr";
import { Sidebar } from "../../components/shared";
import { PaperShell } from "../../components/paper-shell";
import { AgentRun } from "../../components/agent-run";
import { DraftEditor } from "../../components/draft-editor";
import { Citations } from "../../components/citations";
import { ExportTab } from "../../components/export-tab";
import { swrFetcher } from "../../lib/api";

const CITATION_STYLE_FALLBACK = "APA";

function PaperPageInner() {
  const { id } = useParams();
  const sp = useSearchParams();
  const router = useRouter();
  const tab = sp.get("tab") || "run";

  const { data, error, isLoading, mutate } = useSWR(`/papers/${id}`, swrFetcher, {
    refreshInterval: tab === "run" ? 5000 : 0,
  });

  const paper = data?.paper || {
    id,
    title: "Loading…",
    level: "",
    discipline: "",
    status: "running",
    progress: 0,
    words: 0,
    citations: 0,
  };
  const jobId = data?.latest_job?.id;
  const style = paper.citation_style || CITATION_STYLE_FALLBACK;

  const setTab = (newTab) => router.push(`/paper/${id}?tab=${newTab}`);

  let body;
  if (tab === "run") body = <AgentRun jobId={jobId} paper={paper} />;
  else if (tab === "editor") body = <DraftEditor paperId={id} citationStyle={style} />;
  else if (tab === "citations") body = <Citations paperId={id} citationStyle={style} />;
  else if (tab === "export") body = <ExportTab paperId={id} citationStyle={style} />;
  else body = <AgentRun jobId={jobId} paper={paper} />;

  return (
    <div className="app">
      <Sidebar />
      <PaperShell paper={paper} jobId={jobId} latestJob={data?.latest_job} tab={tab} setTab={setTab} onJobChanged={() => mutate()}>
        {isLoading ? (
          <div style={{ padding: 32 }}>Loading…</div>
        ) : error ? (
          <div style={{ padding: 32, color: "var(--danger-fg)" }}>
            Error: {error.message}
          </div>
        ) : (
          body
        )}
      </PaperShell>
    </div>
  );
}

export default function PaperPage() {
  return (
    <Suspense fallback={null}>
      <PaperPageInner />
    </Suspense>
  );
}
