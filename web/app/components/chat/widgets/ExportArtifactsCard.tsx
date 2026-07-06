"use client";

import { Download } from "lucide-react";
import { mintStreamToken } from "@/app/lib/api";
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
    <div className="mt-3 rounded-xl border border-ink-200 bg-ink-50/60 p-3">
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

  const onDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    const m = artifact.download_url.match(/\/projects\/([^/]+)\/exports\/([^/?]+)/);
    if (!m) return;
    const st = await mintStreamToken(`project-export:${m[1]}/${m[2]}`);
    const sep = url.includes("?") ? "&" : "?";
    window.location.href = `${url}${sep}st=${encodeURIComponent(st)}`;
  };

  return (
    <a
      href={url}
      download
      onClick={onDownload}
      className="inline-flex items-center gap-2 rounded-lg border border-ink-200 bg-white px-3 py-2 hover:border-primary-300 hover:bg-primary-50 transition-colors group"
    >
      <FileTypeIcon kind={artifact.kind} className="w-5 h-6 shrink-0" />
      <span className="font-serif text-[13px] font-extrabold text-ink-900">{label}</span>
      {size && <span className="text-[11.5px] text-ink-500">· {size}</span>}
      <Download className="w-3.5 h-3.5 text-ink-400 group-hover:text-primary-600 ml-1 shrink-0" aria-hidden />
    </a>
  );
}
