"use client";

import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";

import { apiFetchText, triggerUploadDownload } from "@/app/lib/api";
import type { AttachmentChipMeta } from "./widgets/types";

/**
 * Read what was actually attached, without leaving the thread.
 *
 * The chip used to be inert: a student who attached the wrong draft, or who
 * wanted to check whether their result tables survived extraction, had to
 * download the file and open Word to find out. This shows the EXTRACTED text —
 * deliberately, not a rendered .docx — because the extraction is what the
 * agent read. If a table is missing here, it was missing from the turn, and
 * that is the thing worth being able to see.
 */
export function AttachmentPreview({
  meta,
  onClose,
}: {
  meta: AttachmentChipMeta;
  onClose: () => void;
}) {
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    // async/await rather than .then().catch(): the handler is attached in the
    // same tick as the call, so a synchronously-rejecting fetch cannot surface
    // as an unhandled rejection before the chain is wired up.
    (async () => {
      try {
        const t = await apiFetchText(`/uploads/${meta.upload_id}/text`);
        if (alive) setText(t);
      } catch (e: unknown) {
        if (!alive) return;
        // 404 is its own case: the file is stored, the text extraction is not.
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

  // Escape closes, matching every other dismissible layer in the app.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/40 px-4 py-8"
      role="dialog"
      aria-modal="true"
      aria-label={meta.filename}
      onClick={onClose}
    >
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-3xl max-h-full flex flex-col overflow-hidden"
        // The backdrop closes; the panel must not, or selecting text inside it
        // would dismiss the thing being read.
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center gap-3 px-5 py-3.5 border-b border-ink-200 shrink-0">
          <span className="text-[13.5px] font-semibold text-ink-900 truncate">
            {meta.filename}
          </span>
          <span className="flex-1" />
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

        <div className="flex-1 overflow-y-auto px-5 py-4 min-h-[200px]">
          {error ? (
            <p className="text-[13px] text-[#7A5B2E]">{error}</p>
          ) : text === null ? (
            <div className="flex items-center gap-2 text-[13px] text-ink-500">
              <Loader2 className="w-4 h-4 animate-spin" aria-hidden />
              Đang đọc tệp…
            </div>
          ) : (
            // Monospace + preserved whitespace: extracted tables come through
            // as `a | b | c` rows, and proportional text would scramble the
            // columns the student is checking for.
            <pre className="whitespace-pre-wrap break-words font-mono text-[12.5px] leading-[1.65] text-ink-800">
              {text}
            </pre>
          )}
        </div>
      </div>
    </div>
  );
}
