"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";
import { NotReady } from "./not-ready";

const READ_ONLY = true;

export const DraftEditor = ({ paperId, citationStyle }) => {
  const { data, error, isLoading } = useSWR(
    paperId ? `/papers/${paperId}/draft` : null,
    swrFetcher,
  );

  if (isLoading) return <div style={{ padding: 32 }}>Loading draft…</div>;
  if (error) return <NotReady paperId={paperId} kind="draft" error={error} />;

  return (
    <div className="canvas" style={{ maxWidth: 880, margin: "0 auto", padding: "32px 24px" }}>
      <article className="prose" dangerouslySetInnerHTML={{ __html: data.html }} />
      {READ_ONLY && (
        <div style={{ marginTop: 24, padding: 12, background: "var(--ink-50)", borderRadius: 8, fontSize: 12, color: "var(--ink-500)" }}>
          Editing is coming soon. For now, download the DOCX from the Export tab to revise.
        </div>
      )}
    </div>
  );
};
