"use client";

import { useEffect, useRef, useState } from "react";
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
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const host = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const url = await uploadViewUrl(meta.upload_id);
        if (!alive) return;
        if (kind === "pdf") {
          setSrc(url);
          setBusy(false);
          return;
        }
        // Rendered in the BROWSER, not converted on the server.
        //
        // A round trip through LibreOffice gives a marginally truer page
        // layout, but it costs ~2s on first open and the student is opening
        // this to answer a quick question — "did my tables come through" —
        // not to proof-read pagination. docx-preview reads the .docx XML
        // directly and lays out margins, headings and tables client-side, so
        // the answer is there as fast as the file downloads.
        //
        // It also means the file never leaves our origin — no third-party
        // viewer fetching an unpublished thesis, which is the trade the
        // Office/Google embed viewers ask for.
        const [{ renderAsync }, res] = await Promise.all([
          import("docx-preview"),
          fetch(url),
        ]);
        if (!res.ok) throw new Error(String(res.status));
        const blob = await res.blob();
        if (!alive || !host.current) return;
        await renderAsync(blob, host.current, undefined, {
          className: "docx",
          inWrapper: true,
          ignoreWidth: true,      // fit the modal, don't force A4 width
          ignoreHeight: true,     // continuous scroll beats fixed page boxes here
          breakPages: false,
          experimental: true,     // needed for some table/border cases
        });
        if (alive) setBusy(false);
      } catch {
        if (alive) {
          setError("Không hiển thị được tệp này. Thử tab “Văn bản” hoặc tải xuống.");
          setBusy(false);
        }
      }
    })();
    return () => { alive = false; };
  }, [meta.upload_id, kind]);

  if (error) return <p className="text-[13px] text-[#7A5B2E]">{error}</p>;

  if (kind === "plain") {
    return <p className="text-[13px] text-ink-500">Định dạng này không có bản xem tài liệu — xem tab “Văn bản”.</p>;
  }

  if (kind === "pdf") {
    return src ? (
      <iframe src={src} title={meta.filename} className="w-full h-[70vh] rounded-lg border border-ink-200" />
    ) : (
      <Loading />
    );
  }

  return (
    <>
      {busy && <Loading />}
      {/* docx-preview writes into this node directly. `docx-body` scopes the
          styles in globals.css so they can't leak into the agent's markdown. */}
      <div ref={host} className="docx-body" />
    </>
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
