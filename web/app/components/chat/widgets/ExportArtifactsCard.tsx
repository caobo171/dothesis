"use client";

import { Check, Download, Loader2 } from "lucide-react";
import { mintStreamToken } from "@/app/lib/api";
import { useArtifactDownload } from "../hooks/useArtifactDownload";
import { FileTypeIcon } from "../FileTypeIcon";
import type { ExportArtifactsHint, ExportArtifact } from "./types";

// Download card shown inside an assistant message after export_docx succeeds
// (Claude-artifact style). The /exports/{filename} route 302s to a signed S3
// URL but still needs auth. Browsers can't attach a body to an <a download>,
// so we mint a short-lived, scoped stream token on click and navigate with
// ?st= — the long-lived JWT must never appear in a URL (it'd leak into logs).
export function ExportArtifactsCard({ hint }: { hint: ExportArtifactsHint }) {
  const artifacts = hint.artifacts || [];
  if (artifacts.length === 0) return null;
  return (
    // data-testid: the card's visible heading is localized ("LUẬN VĂN ĐÃ
    // XUẤT") — E2E asserts on a stable hook instead of copy.
    <div className="mt-3 rounded-xl border border-ink-200 bg-ink-50/60 p-3" data-testid="export-artifacts-card">
      <div className="text-[12px] font-semibold text-ink-500 mb-2 tracking-[0.02em]">
        LUẬN VĂN ĐÃ XUẤT
      </div>
      <div className="flex flex-wrap gap-2">
        {artifacts.map(a => (
          <ArtifactButton key={a.s3_key ?? a.download_url} artifact={a} />
        ))}
      </div>
    </div>
  );
}

function ArtifactButton({ artifact }: { artifact: ExportArtifact }) {
  const label = (artifact.kind || "file").toUpperCase();
  const size =
    typeof artifact.size_bytes === "number"
      ? artifact.size_bytes >= 1024 * 1024
        ? `${(artifact.size_bytes / (1024 * 1024)).toFixed(1)} MB`
        : `${Math.max(1, Math.round(artifact.size_bytes / 1024))} KB`
      : null;

  const apiBase = process.env.NEXT_PUBLIC_API_BASE || "";
  const url = artifact.download_url.startsWith("/api/v1/")
    ? `${apiBase}${artifact.download_url.replace(/^\/api\/v1/, "")}`
    : artifact.download_url;

  const { busy, started, error, start } = useArtifactDownload();

  const onDownload = (e: React.MouseEvent) => {
    e.preventDefault();
    void start(async () => {
      const m = artifact.download_url.match(/\/projects\/([^/]+)\/exports\/([^/?]+)/);
      if (!m) throw new Error("This artifact has no downloadable URL.");
      const st = await mintStreamToken(`project-export:${m[1]}/${m[2]}`);
      const sep = url.includes("?") ? "&" : "?";
      window.location.href = `${url}${sep}st=${encodeURIComponent(st)}`;
    });
  };

  return (
    <span className="inline-flex flex-col gap-1">
      <a
        href={url}
        download
        onClick={onDownload}
        aria-busy={busy}
        aria-disabled={busy}
        className={`inline-flex items-center gap-2 rounded-lg border px-3 py-2 transition-colors group ${
          busy
            ? "border-primary-300 bg-primary-50 cursor-progress"
            : "border-ink-200 bg-white hover:border-primary-300 hover:bg-primary-50"
        }`}
      >
        <FileTypeIcon kind={artifact.kind} className="w-5 h-6 shrink-0" />
        <span className="font-serif text-[13px] font-extrabold text-ink-900">{label}</span>
        {size && <span className="text-[11.5px] text-ink-500">· {size}</span>}
        {/* Same 3.5 box in all three states so the button never resizes on click. */}
        {busy ? (
          <Loader2 className="w-3.5 h-3.5 text-primary-600 ml-1 shrink-0 animate-spin" aria-hidden />
        ) : started ? (
          <Check className="w-3.5 h-3.5 text-[#4A6B4F] ml-1 shrink-0" aria-hidden />
        ) : (
          <Download className="w-3.5 h-3.5 text-ink-400 group-hover:text-primary-600 ml-1 shrink-0" aria-hidden />
        )}
      </a>
      {/* aria-live so the phase change is announced, not just drawn. */}
      <span className="text-[11px] max-w-[220px] min-h-[14px]" aria-live="polite">
        {error ? (
          <span className="text-[#8E6B2A]">{error}</span>
        ) : busy ? (
          <span className="text-ink-500">Preparing…</span>
        ) : started ? (
          <span className="text-[#4A6B4F]">Download started</span>
        ) : null}
      </span>
    </span>
  );
}
