"use client";
import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";
import { apiFetch, swrFetcher } from "../lib/api";
import { NotReady } from "./not-ready";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
const LABELS = { pdf: "PDF", docx: "Microsoft Word", tex: "LaTeX source", md: "Markdown", zip: "Full bundle (ZIP)" };

export const ExportTab = ({ paperId }) => {
  const key = paperId ? `/papers/${paperId}/exports` : null;
  const { data: exports, error, isLoading } = useSWR(key, swrFetcher);
  const [regenerating, setRegenerating] = useState(false);
  const [regenResult, setRegenResult] = useState(null);
  const [regenError, setRegenError] = useState(null);

  async function regenerate() {
    setRegenerating(true);
    setRegenError(null);
    setRegenResult(null);
    try {
      const res = await apiFetch(`/papers/${paperId}/regenerate-exports`, { method: "POST" });
      setRegenResult(res?.regenerated || []);
      if (key) globalMutate(key);
    } catch (e) {
      setRegenError(e?.message || "Re-export failed");
    } finally {
      setRegenerating(false);
    }
  }

  if (isLoading) return <div style={{ padding: 32 }}>Loading exports…</div>;
  if (error) return <NotReady paperId={paperId} kind="exports" error={error} />;

  return (
    <div className="canvas" style={{ padding: 24, maxWidth: 920, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", gap: 12, marginBottom: 16, flexWrap: "wrap" }}>
        <h2 className="section-title" style={{ margin: 0 }}>Download</h2>
        <button
          type="button"
          onClick={regenerate}
          disabled={regenerating}
          style={{
            padding: "8px 14px",
            borderRadius: 10,
            border: "1px solid var(--ink-200)",
            background: regenerating ? "var(--ink-100)" : "var(--paper)",
            color: "var(--ink-800)",
            fontSize: 13,
            fontWeight: 600,
            cursor: regenerating ? "default" : "pointer",
            opacity: regenerating ? 0.7 : 1,
          }}
          title="Re-run the DOCX/PDF exporters against the existing markdown — useful if a previous run produced broken formatting."
        >
          {regenerating ? "Re-exporting…" : "↻ Re-export from markdown"}
        </button>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: 12 }}>
        {(exports || []).map((e) => (
          <a key={e.format} className="card" style={{ padding: 16, textDecoration: "none", color: "inherit", display: "block" }}
             href={`${BASE}/papers/${paperId}/exports/${e.format}`} target="_blank" rel="noreferrer">
            <div style={{ fontWeight: 700, fontSize: 14 }}>{LABELS[e.format] || e.format.toUpperCase()}</div>
            <div style={{ fontSize: 12, color: "var(--ink-500)", marginTop: 4 }}>
              {(e.size / 1024).toFixed(0)} KB · {new Date(e.generated_at).toLocaleString()}
            </div>
          </a>
        ))}
        {(!exports || !exports.length) && <div style={{ color: "var(--ink-500)" }}>No exports yet.</div>}
      </div>

      {regenResult && (
        <div style={{ marginTop: 16, padding: 12, background: "var(--ok-bg)", color: "var(--ok-fg)", borderRadius: 10, fontSize: 13 }}>
          Re-export complete:{" "}
          {regenResult.map((r) => (
            <span key={r.format} style={{ marginRight: 12 }}>
              <b>{(LABELS[r.format] || r.format).toUpperCase()}</b>
              {r.size ? ` (${(r.size / 1024).toFixed(0)} KB)` : r.error ? ` — failed: ${r.error}` : ""}
            </span>
          ))}
        </div>
      )}
      {regenError && (
        <div style={{ marginTop: 16, padding: 12, background: "var(--stop-bg)", color: "var(--stop-fg)", borderRadius: 10, fontSize: 13 }}>
          {regenError}
        </div>
      )}
    </div>
  );
};
