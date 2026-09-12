"use client";

import { useEffect, useRef, useState } from "react";
import { Download, FileText, Loader2, X } from "lucide-react";

import { apiFetchText, triggerUploadDownload, uploadViewUrl } from "@/app/lib/api";
import type { AttachmentChipMeta } from "./widgets/types";

type Tab = "document" | "text";

function polishDocxPreview(root: HTMLElement) {
  // Word questionnaires commonly store an empty checkbox as a font glyph.
  // Its weight and baseline vary wildly across platforms, so replace only the
  // preview DOM with a stable CSS-drawn control; the uploaded file is untouched.
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  while (walker.nextNode()) nodes.push(walker.currentNode as Text);

  for (const node of nodes) {
    if (!/[□☐]/.test(node.data)) continue;
    const fragment = document.createDocumentFragment();
    node.data.split(/([□☐])/).forEach((part) => {
      if (part === "□" || part === "☐") {
        const box = document.createElement("span");
        box.className = "docx-checkbox";
        box.setAttribute("role", "checkbox");
        box.setAttribute("aria-checked", "false");
        box.setAttribute("aria-label", "Unchecked option");
        fragment.appendChild(box);
      } else if (part) {
        fragment.appendChild(document.createTextNode(part));
      }
    });
    node.replaceWith(fragment);
  }
}

/** Scale the rendered page down until it fits the canvas, and keep it fitting.
 *
 *  `ignoreWidth: false` (below) is deliberate — it gives `section.docx` the
 *  document's REAL page width, which is the whole point of this tab. But that
 *  width is a constant: an A4 page is 794px plus the wrapper's padding, ~906px
 *  in total, and nothing ever reduced it. Any canvas narrower than that — a
 *  smaller window, a split screen, or just browser zoom, which shrinks the CSS
 *  viewport — clipped the right-hand side of the student's document. Measured
 *  before this fix: a 780px modal overflowed by 144px, a 560px one by 364px,
 *  at every zoom level until the canvas could shrink to compensate.
 *
 *  Scaling rather than reflowing is the point. Dropping `ignoreWidth` would let
 *  paragraphs and tables re-wrap to the panel, which answers a DIFFERENT
 *  question than "what does my Word file look like" — the line breaks and table
 *  widths would stop matching what the student sees in Word, which is exactly
 *  what they opened this to check.
 *
 *  The zoom is applied to `.docx-wrapper` while the intrinsic width is read
 *  from it once, at zoom 1. Reading it back after a zoom would feed the scale
 *  into its own input and converge on garbage.
 */
function fitDocxToWidth(host: HTMLElement): () => void {
  const wrapper = host.querySelector<HTMLElement>(".docx-wrapper");
  const canvas = host.closest<HTMLElement>("[data-docx-canvas]");
  if (!wrapper || !canvas) return () => {};

  const apply = () => {
    wrapper.style.removeProperty("zoom");
    const intrinsic = wrapper.scrollWidth;
    if (!intrinsic) return;

    const pad = 24;
    const available = Math.max(280, canvas.clientWidth - pad);
    // Floor at 0.55: below that the page is unreadable; horizontal scroll is
    // preferable to a postage-stamp preview floating in grey space.
    const scale = Math.max(0.55, Math.min(1, available / intrinsic));
    wrapper.style.zoom = String(scale);
  };
  apply();

  const ro = new ResizeObserver(apply);
  ro.observe(canvas);
  return () => ro.disconnect();
}

type Kind = "pdf" | "docx" | "data" | "plain";

function _kindOf(meta: AttachmentChipMeta): Kind {
  const name = (meta.filename || "").toLowerCase();
  const mime = (meta.mime_type || "").toLowerCase();
  if (mime === "application/pdf" || name.endsWith(".pdf")) return "pdf";
  if (name.endsWith(".docx") || mime.includes("wordprocessingml")) return "docx";
  if (/\.(csv|xlsx|xls|sav)$/.test(name)) return "data";
  return "plain";
}

/** Only these two have something to render as a document. Everything else has
 *  exactly one useful view — the extracted text — so offering a "Tài liệu" tab
 *  just routes the student to docx-preview choking on a spreadsheet. */
function _hasDocumentView(kind: Kind): boolean {
  return kind === "pdf" || kind === "docx";
}

const _SUBTITLE: Record<Kind, string> = {
  pdf: "PDF preview",
  docx: "Word document preview",
  data: "Bộ dữ liệu — xem cấu trúc bên dưới",
  plain: "Văn bản",
};

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
    // Holds the ResizeObserver disposer from fitDocxToWidth. Assigned inside the
    // async body, so cleanup has to read it from here rather than return it.
    let stopFit: (() => void) | undefined;
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
          // Decision: this surface answers "what does my Word file look like?"
          // Preserve its page geometry instead of stretching every paragraph
          // and table across the modal like generic HTML.
          ignoreWidth: false,
          ignoreHeight: false,
          breakPages: true,
          experimental: true,     // needed for some table/border cases
        });
        polishDocxPreview(host.current);
        stopFit = fitDocxToWidth(host.current);
        if (alive) setBusy(false);
      } catch {
        if (alive) {
          setError("Không hiển thị được tệp này. Thử tab “Văn bản” hoặc tải xuống.");
          setBusy(false);
        }
      }
    })();
    return () => { alive = false; stopFit?.(); };
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
    <div data-docx-canvas className="relative w-full min-h-[240px]">
      {busy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#e9edf2]">
          <Loading />
        </div>
      )}
      {/* docx-preview writes into this node directly. `docx-body` scopes the
          styles in globals.css so they can't leak into the agent's markdown. */}
      <div ref={host} className={`docx-body ${busy ? "invisible" : ""}`} />
    </div>
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
  const kind = _kindOf(meta);
  const hasDocumentView = _hasDocumentView(kind);
  const [tab, setTab] = useState<Tab>(hasDocumentView ? "document" : "text");
  const documentCanvas = tab === "document" && hasDocumentView;

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
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/55 p-3 backdrop-blur-[2px] sm:p-5 lg:pr-[min(360px,calc(100vw-480px))]"
      role="dialog"
      aria-modal="true"
      aria-label={meta.filename}
      onClick={onClose}
    >
      <div
        className="flex h-[min(calc(100dvh-1.5rem),920px)] w-full max-w-[min(1200px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-white/60 bg-white shadow-[0_24px_80px_rgba(24,31,45,0.28)]"
        // The backdrop closes; the panel must not, or selecting text inside it
        // would dismiss the thing being read.
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex min-h-16 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-ink-200 bg-white px-4 py-3 sm:px-5">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary-50 text-primary-700">
            <FileText className="h-4.5 w-4.5" aria-hidden />
          </span>
          <div className="min-w-0">
            <div className="truncate text-[13.5px] font-semibold text-ink-900">{meta.filename}</div>
            {/* `truncate` here too. The filename had it and the subtitle did
                not, so in a cramped header the filename stayed on one line
                while "Word document preview" wrapped to three and shoved
                itself under the tabs — measured at 460px and below. */}
            <div className="truncate text-[11px] text-ink-400">{_SUBTITLE[kind]}</div>
          </div>
          <span className="flex-1" />
          <div className="flex items-center gap-1 shrink-0">
            {hasDocumentView && (
              <button type="button" onClick={() => setTab("document")} className={tabCls("document")}>
                Tài liệu
              </button>
            )}
            {/* Named for what it is: the text the agent read, not a second copy
                of the document. */}
            <button type="button" onClick={() => setTab("text")} className={tabCls("text")}>
              Văn bản
            </button>
          </div>
          <button
            type="button"
            onClick={() => void triggerUploadDownload(meta.upload_id)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-2 text-[12.5px] font-semibold text-primary-600 transition-colors hover:bg-primary-50 active:translate-y-px"
          >
            <Download className="h-3.5 w-3.5" aria-hidden />
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

        <div className={`min-h-0 flex-1 overflow-auto ${
          documentCanvas ? "bg-[#e9edf2]" : "bg-white px-5 py-4"
        }`}>
          {tab === "document" ? <DocumentView meta={meta} /> : <TextView meta={meta} />}
        </div>
      </div>
    </div>
  );
}
