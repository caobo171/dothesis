"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";
import { NotReady } from "./not-ready";

export const DraftEditor = ({ paperId }) => {
  const { data, error, isLoading } = useSWR(
    paperId ? `/papers/${paperId}/draft` : null,
    swrFetcher,
  );

  if (isLoading) return <div style={{ padding: 32, color: "var(--ink-500)" }}>Loading draft…</div>;
  if (error) return <NotReady paperId={paperId} kind="draft" error={error} />;

  const meta = data?.meta || {};
  const wordCount = data?.word_count;

  return (
    <div className="thesis-page">
      {/* Title block from frontmatter */}
      {(meta.title || meta.author) && (
        <header className="thesis-title-block">
          {meta.project_type && (
            <div className="thesis-eyebrow">{meta.project_type}</div>
          )}
          {meta.title && <h1 className="thesis-title">{meta.title}</h1>}
          <div className="thesis-meta-grid">
            {meta.author && <MetaPair label="Author" value={meta.author} />}
            {meta.advisor && <MetaPair label="Advisor" value={meta.advisor} />}
            {meta.second_examiner && meta.second_examiner !== "N/A" && (
              <MetaPair label="Second examiner" value={meta.second_examiner} />
            )}
            {meta.institution && <MetaPair label="Institution" value={meta.institution} />}
            {meta.faculty && <MetaPair label="Faculty" value={meta.faculty} />}
            {meta.department && <MetaPair label="Department" value={meta.department} />}
            {meta.degree && <MetaPair label="Degree" value={meta.degree} />}
            {meta.location && <MetaPair label="Location" value={meta.location} />}
            {meta.date && <MetaPair label="Date" value={meta.date} />}
            {meta.word_count && <MetaPair label="Words" value={meta.word_count} />}
            {meta.pages && <MetaPair label="Pages" value={meta.pages} />}
          </div>
        </header>
      )}

      <article className="thesis-prose" dangerouslySetInnerHTML={{ __html: data.html }} />

      <footer className="thesis-footer">
        {wordCount && (
          <span>
            {wordCount.toLocaleString()} words rendered. Download the DOCX from the Export tab to revise.
          </span>
        )}
      </footer>
    </div>
  );
};

function MetaPair({ label, value }) {
  return (
    <div className="thesis-meta-pair">
      <span className="thesis-meta-label">{label}</span>
      <span className="thesis-meta-value">{value}</span>
    </div>
  );
}
