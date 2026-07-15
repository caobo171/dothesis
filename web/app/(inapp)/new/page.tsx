"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, FileText, Loader2, UploadCloud, X } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import { stashAnalyzeIntent, type AnalyzeAttachment } from "@/app/lib/bootstrap-payload";
import { Button } from "@/app/components/ui/button";
import { Textarea } from "@/app/components/ui/textarea";
import { ImportSummary } from "@/app/components/chat/ImportSummary";

// Shape of POST /projects/{id}/mid-journey-import (F12).
type ImportResult = {
  imported: string[];
  ambiguous: string[];
  unreadable: string[];
  focus: string;
};

/**
 * /new — drop-first onboarding.
 *
 * The old multi-section bootstrap form (project name → defaults → M1–M5
 * checklist) made starting feel like paperwork. This page does the opposite:
 * ONE primary action — drop whatever you have — and a secondary "describe it
 * instead" note for users with nothing to upload. Everything else (name,
 * field, language, citation) is inferred or defaulted; the user can rename and
 * re-frame from chat later.
 *
 * On Analyze: create the project, upload each file, stash an analyze-intent
 * keyed by the new project id, then navigate to chat with ?analyzing=1. The
 * chat surface fires a single bootstrap turn that reads the uploads and reports
 * where the thesis stands (the analysis screen) before handing off to chat.
 */

// Keep in sync with the uploads endpoint's text-extractable set
// (api/app/routers/uploads.py: _ALLOWED_MIME / _ALLOWED_EXT). The file picker
// advertises the same set so the OS dialog filters. PDF, Word (.docx), and
// plain text / markdown — every format we can pull real text from.
const ACCEPT_TYPES =
  "application/pdf,text/plain,text/markdown," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  ".pdf,.txt,.md,.markdown,.docx";

export default function NewThesisPage() {
  const router = useRouter();
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // F12: when the user drops files, we run a server-side import and show an
  // activation summary ("here's where you are, next do X") before chat instead
  // of firing a blind bootstrap turn. Note-only (describe-it) keeps the old
  // straight-to-chat path — see analyze().
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importedProjectId, setImportedProjectId] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Setup defaults still come from the user's cross-project memory (/me/prefs)
  // so a returning user's field/language/citation carry over — they're just no
  // longer surfaced as form fields. Best-effort; first-timers get built-ins.
  const prefsRef = useRef<{ field?: string; language?: string; citation_style?: string }>({});
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const prefs = (await apiFetch("/me/prefs", { method: "POST", body: {} })) as {
          field?: string; language?: string; citation_style?: string;
        };
        if (alive && prefs) prefsRef.current = prefs;
      } catch {
        /* no prefs yet / not logged in — keep built-in defaults */
      }
    })();
    return () => { alive = false; };
  }, []);

  const addFiles = (incoming: FileList | File[] | null) => {
    if (!incoming) return;
    setFiles(prev => {
      // De-dup by (name, size) so re-dropping the same file doesn't queue it twice.
      const seen = new Set(prev.map(f => `${f.name}::${f.size}`));
      const next = [...prev];
      for (const f of Array.from(incoming)) {
        const k = `${f.name}::${f.size}`;
        if (!seen.has(k)) { seen.add(k); next.push(f); }
      }
      return next;
    });
  };

  const removeFile = (idx: number) =>
    setFiles(prev => prev.filter((_, i) => i !== idx));

  const canSubmit = !submitting && (files.length > 0 || note.trim().length > 0);

  // Multipart upload — can't go through apiFetch (JSON-only); the auth token
  // rides in an Authorization: Bearer header. Returns the upload metadata so we
  // can attach it to the analyze turn. Same pattern as ChatPane's onFileDrop.
  const uploadOne = async (projectId: string, file: File): Promise<AnalyzeAttachment> => {
    const token = tokenStore.get();
    const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${base}/projects/${projectId}/uploads`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: fd,
    });
    if (!res.ok) throw new Error(`upload failed (${res.status}) for ${file.name}`);
    const body = await res.json();
    return {
      upload_id: body.upload_id as string,
      filename: body.filename as string,
      size_bytes: body.size_bytes as number,
      mime_type: body.mime_type as string | undefined,
    };
  };

  const analyze = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    setStatus("Creating project…");
    try {
      // Name is inferred later (the bootstrap turn renames from the detected
      // topic); start generic so the user never has to fill a name field.
      const prefs = prefsRef.current;
      const project = await apiFetch("/projects", {
        method: "POST",
        body: {
          name: "Untitled thesis",
          field: prefs.field?.trim() || null,
          language: prefs.language || "en",
          citation_style: prefs.citation_style || "apa",
        },
      });
      const newId = (project as { id: string }).id;

      // Uploads are project-scoped, so they wait for the project row. Sequential
      // with a per-file counter so slow PDFs show progress, not a frozen button.
      const attachments: AnalyzeAttachment[] = [];
      for (let i = 0; i < files.length; i++) {
        setStatus(`Uploading ${i + 1} of ${files.length}…`);
        attachments.push(await uploadOne(newId, files[i]));
      }

      // F12: if the student dropped real files, import them server-side
      // (deterministic classify → infer → commit in MODULES order → focus on
      // the first not-imported module) and show the activation summary. The
      // note-only "describe it" path has nothing to import, so it keeps the
      // original bootstrap-turn analysis flow (and is what the onboarding E2E
      // exercises).
      if (files.length > 0) {
        setStatus("Reading your work…");
        const res = (await apiFetch(`/projects/${newId}/mid-journey-import`, {
          method: "POST",
          body: {},
        })) as ImportResult;
        setImportResult(res);
        setImportedProjectId(newId);
        setSubmitting(false);
        setStatus(null);
        return;
      }

      stashAnalyzeIntent(newId, { note, attachments });
      router.push(`/chat/projects/${newId}?analyzing=1`);
    } catch (e: any) {
      const code = e?.body?.error?.code;
      setError(code || e?.message || "Could not start. Please try again.");
      setSubmitting(false);
      setStatus(null);
    }
  };

  // F12: once the import lands, the page becomes the activation summary — the
  // first-session payoff — with a CTA into chat at the imported focus module.
  if (importResult && importedProjectId) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-7">
          <h1 className="m-0 text-[26px] font-extrabold font-serif tracking-tight text-ink-900">
            Here&apos;s where you are
          </h1>
        </div>
        <ImportSummary
          imported={importResult.imported}
          focus={importResult.focus}
          ambiguous={importResult.ambiguous}
          unreadable={importResult.unreadable}
          onContinue={() => router.push(`/chat/projects/${importedProjectId}`)}
        />
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 hover:text-ink-900 no-underline mb-6"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> Back to home
      </Link>

      <div className="text-center mb-7">
        <h1 className="m-0 text-[26px] font-extrabold font-serif tracking-tight text-ink-900">
          Analyze your thesis
        </h1>
        <p className="text-[14px] text-ink-500 mt-1.5">
          Drop whatever you have — a draft, papers, a proposal, a questionnaire —
          and we'll tell you where your quantitative thesis stands.
        </p>
      </div>

      {/* PRIMARY: the drop zone. Big, centered, the obvious thing to do. */}
      <button
        type="button"
        onClick={() => fileInputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => {
          e.preventDefault();
          setDragging(false);
          addFiles(e.dataTransfer?.files ?? null);
        }}
        disabled={submitting}
        className={`w-full rounded-3xl border-2 border-dashed px-8 py-14 flex flex-col items-center justify-center gap-3 text-center transition-colors ${
          dragging
            ? "border-primary-500 bg-primary-50"
            : "border-ink-300 bg-white hover:border-primary-400 hover:bg-primary-50/30"
        } disabled:opacity-60`}
      >
        <span className="w-14 h-14 rounded-2xl bg-primary-50 text-primary-600 inline-flex items-center justify-center">
          <UploadCloud className="w-7 h-7" />
        </span>
        <span className="text-[15px] font-bold text-ink-900">
          Drop files here
        </span>
        <span className="text-[12.5px] text-ink-500">
          or click to browse · PDF, Word, or text · multiple files OK
        </span>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPT_TYPES}
          onChange={e => { addFiles(e.target.files); e.target.value = ""; }}
          className="hidden"
        />
      </button>

      {/* Queued files */}
      {files.length > 0 && (
        <div className="mt-3 flex flex-col gap-1.5">
          {files.map((f, i) => (
            <div
              key={`${f.name}-${f.size}-${i}`}
              className="flex items-center gap-2 px-3 py-2 rounded-xl border border-ink-200 bg-white text-[12.5px]"
            >
              <FileText className="w-4 h-4 text-ink-500 shrink-0" />
              <span className="font-medium text-ink-800 truncate flex-1">{f.name}</span>
              <span className="text-ink-500 tabular-nums shrink-0">{formatBytes(f.size)}</span>
              <button
                type="button"
                onClick={() => removeFile(i)}
                disabled={submitting}
                aria-label={`Remove ${f.name}`}
                className="w-5 h-5 rounded-full text-ink-400 hover:bg-ink-100 hover:text-ink-700 inline-flex items-center justify-center shrink-0 disabled:opacity-50"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* SECONDARY: describe it instead. Collapsed by default so it stays a
          sub-action — the drop zone is the headline. */}
      <div className="mt-5">
        {!noteOpen ? (
          <button
            type="button"
            onClick={() => setNoteOpen(true)}
            className="text-[13px] text-ink-500 hover:text-primary-700 font-medium"
          >
            ▸ Nothing to upload? Describe it instead
          </button>
        ) : (
          <div>
            <label htmlFor="note" className="block text-[13px] font-semibold text-ink-700 mb-1.5">
              Describe what you have so far
            </label>
            <Textarea
              id="note"
              value={note}
              onChange={e => setNote(e.target.value)}
              placeholder={
                "e.g. I have a topic — Gen Z TikTok livestream buying in Hà Nội — a conceptual model with 5 hypotheses, and survey data ready for SmartPLS, but no literature review yet."
              }
              rows={4}
              className="resize-y leading-relaxed"
              autoFocus
            />
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="mt-7 flex items-center gap-3">
        {error && (
          <span role="alert" className="text-[12.5px] text-red-700 font-semibold">{error}</span>
        )}
        {status && !error && (
          <span className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 font-semibold">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {status}
          </span>
        )}
        <span className="flex-1" />
        {/* Blank start escape hatch — create an empty project, skip analysis. */}
        <Button variant="ghost" asChild>
          <Link href="/">Cancel</Link>
        </Button>
        <Button type="button" onClick={() => void analyze()} disabled={!canSubmit}>
          {submitting ? "Analyzing…" : "Analyze"}
        </Button>
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}
