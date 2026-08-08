"use client";

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import { apiFetchText, triggerUploadDownload, uploadViewUrl } from "@/app/lib/api";
import type { AttachmentChipMeta } from "./widgets/types";

type Tab = "document" | "text";

function _kindOf(meta: AttachmentChipMeta): "pdf" | "docx" | "plain" {
  const name = (meta.filename || "").toLowerCase();
  const mime = (meta.mime_type || "").toLowerCase();
  if (mime === "application/pdf" || name.endsWith(".pdf")) return "pdf";
  if (name.endsWith(".docx") || mime.includes("wordprocessingml")) return "docx";
  return "plain";
}

/** The file as the student wrote it. PDFs go to the browser's own viewer;
 *  .docx is converted to HTML client-side (mammoth), which keeps headings and
 *  — the reason this matters here — real tables. */
function DocumentView({ meta }: { meta: AttachmentChipMeta }) {
  const kind = _kindOf(meta);
  const [src, setSrc] = useState<string | null>(null);
  const [html, setHtml] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        if (kind === "pdf") {
          const url = await uploadViewUrl(meta.upload_id);
          if (alive) setSrc(url);
          return;
        }
        // A .docx has no browser renderer, so the server converts it with
        // LibreOffice and we iframe the PDF: TRUE layout — real page breaks,
        // real table borders, the document as the supervisor will open it.
        const pdfUrl = await uploadViewUrl(meta.upload_id, { asPdf: true });
        const head = await fetch(pdfUrl, { method: "GET" });
        if (!alive) return;
        if (head.ok) {
          setSrc(pdfUrl);
          return;
        }
        // Conversion unavailable (no LibreOffice on the box). mammoth is the
        // fallback: an HTML approximation that still shows the tables, which
        // beats telling the student their file cannot be displayed.
        const [{ default: mammoth }, res] = await Promise.all([
          import("mammoth"),
          fetch(await uploadViewUrl(meta.upload_id)),
        ]);
        if (!res.ok) throw new Error(String(res.status));
        const out = await mammoth.convertToHtml({ arrayBuffer: await res.arrayBuffer() });
        if (alive) setHtml(out.value);
      } catch {
        if (alive) setError("Không hiển thị được tệp này. Thử tab “Văn bản” hoặc tải xuống.");
      }
    })();
    return () => { alive = false; };
  }, [meta.upload_id, kind]);

  if (error) return <p className="text-[13px] text-[#7A5B2E]">{error}</p>;

  if (kind === "plain") {
    return <p className="text-[13px] text-ink-500">Định dạng này không có bản xem tài liệu — xem tab “Văn bản”.</p>;
  }

  // Both PDFs and converted .docx land here: one native viewer, page layout
  // intact, no approximation.
  if (src) {
    return (
      <iframe src={src} title={meta.filename} className="w-full h-[70vh] rounded-lg border border-ink-200" />
    );
  }

  return html === null ? (
    <Loading />
  ) : (
    // `docx-body` styles live in globals.css: mammoth emits bare <table>,
    // <h1>, <p> with no classes, so unstyled they render as a wall of text
    // with borderless tables — which is exactly what the student came to check.
    <div className="docx-body" dangerouslySetInnerHTML={{ __html: html }} />
  );
}

function Loading() {
  return (
    <div className="flex items-center gap-2 text-[13px] text-ink-500">
      <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
      Đang mở tệp…
    </div>
  );
}

/** The extraction — what the AGENT read. Kept as its own tab because it is a
 *  different question from "what does my file look like": if a table is
 *  missing here it was missing from the turn, whatever the document shows. */
function TextView({ meta }: { meta: AttachmentChipMeta }) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const t = await apiFetchText(`/uploads/${meta.upload_id}/text`);
        if (alive) setText(t);
      } catch (e: unknown) {
        if (!alive) return;
        const status = (e as { status?: number })?.status;
        setError(
          status === 404
            ? "Chưa có bản trích xuất văn bản cho tệp này — tải xuống để mở bằng Word."
            : "Không đọc được nội dung tệp này.",
        );
      }
    })();
    return () => { alive = false; };
  }, [meta.upload_id]);

  if (error) return <p className="text-[13px] text-[#7A5B2E]">{error}</p>;
  if (text === null) return <Loading />;
  return (
    // Monospace + preserved whitespace: extracted tables come through as
    // `a | b | c` rows, and proportional text would scramble the columns.
    <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-[1.65] text-ink-800">
      {text}
    </pre>
  );
}

export function AttachmentPreview({
  meta,
  onClose,
}: {
  meta: AttachmentChipMeta;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>(_kindOf(meta) === "plain" ? "text" : "document");

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const tabCls = (t: Tab) =>
    `px-2.5 py-1 rounded-lg text-[12.5px] font-semibold transition-colors ${
      tab === t ? "bg-ink-100 text-ink-900" : "text-ink-500 hover:text-ink-800"
    }`;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4 py-8"
      role="dialog"
      aria-modal="true"
      aria-label={meta.filename}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-4xl max-h-full flex flex-col overflow-hidden"
        // The backdrop closes; the panel must not, or selecting text inside it
        // would dismiss the thing being read.
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 px-5 py-3 border-b border-ink-200 shrink-0">
          <span className="text-[13.5px] font-semibold text-ink-900 truncate">{meta.filename}</span>
          <span className="flex-1" />
          <div className="flex items-center gap-1 shrink-0">
            <button type="button" onClick={() => setTab("document")} className={tabCls("document")}>
              Tài liệu
            </button>
            {/* Named for what it is: the text the agent read, not a second copy
                of the document. */}
            <button type="button" onClick={() => setTab("text")} className={tabCls("text")}>
              Văn bản
            </button>
          </div>
          <button
            type="button"
            onClick={() => void triggerUploadDownload(meta.upload_id)}
            className="text-[12.5px] font-semibold text-primary-600 hover:underline shrink-0"
          >
            Tải xuống
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="w-7 h-7 rounded-full text-ink-500 hover:bg-ink-100 inline-flex items-center justify-center shrink-0"
          >
            <X className="w-4 h-4" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-5 py-4 min-h-[240px]">
          {tab === "document" ? <DocumentView meta={meta} /> : <TextView meta={meta} />}
        </div>
      </div>
    </div>
  );
}
