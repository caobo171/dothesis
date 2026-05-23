"use client";
import useSWR from "swr";
import { swrFetcher } from "../lib/api";
import { NotReady } from "./not-ready";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
const LABELS = { pdf: "PDF", docx: "Microsoft Word", tex: "LaTeX source", md: "Markdown", zip: "Full bundle (ZIP)" };

export const ExportTab = ({ paperId, citationStyle }) => {
  const { data: exports, error, isLoading } = useSWR(
    paperId ? `/papers/${paperId}/exports` : null,
    swrFetcher,
  );

  if (isLoading) return <div style={{ padding: 32 }}>Loading exports…</div>;
  if (error) return <NotReady paperId={paperId} kind="exports" error={error} />;

  return (
    <div className="canvas" style={{ padding: 24 }}>
      <h2 className="section-title" style={{ marginBottom: 16 }}>Download</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
        {(exports || []).map((e) => (
          <a key={e.format} className="card" style={{ padding: 16, textDecoration: "none", color: "inherit" }}
             href={`${BASE}/papers/${paperId}/exports/${e.format}`} target="_blank" rel="noreferrer">
            <div style={{ fontWeight: 700, fontSize: 14 }}>{LABELS[e.format] || e.format.toUpperCase()}</div>
            <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4 }}>
              {(e.size / 1024).toFixed(0)} KB · {new Date(e.generated_at).toLocaleString()}
            </div>
          </a>
        ))}
        {(!exports || !exports.length) && <div style={{ color: "var(--ink-500)" }}>No exports yet.</div>}
      </div>
    </div>
  );
};
