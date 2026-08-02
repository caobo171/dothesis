"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import { stashAnalyzeIntent, type AnalyzeAttachment } from "@/app/lib/bootstrap-payload";
import { Button } from "@/app/components/ui/button";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { ImportSummary } from "@/app/components/chat/ImportSummary";
import { ThesisComposer } from "@/app/components/chat/ThesisComposer";
import {
  ReconstructedModules,
  type ReconstructedModule,
} from "@/app/components/chat/ReconstructedModules";

// Shape of POST /projects/{id}/mid-journey-import (F12).
type ImportResult = {
  imported: string[];
  ambiguous: string[];
  unreadable: string[];
  focus: string;
  to_reconstruct: string[]; // upstream modules we can infer from the import
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
  const t = useT();
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // F12: when the user drops files, we run a server-side import and show an
  // activation summary ("here's where you are, next do X") before chat instead
  // of firing a blind bootstrap turn. Note-only (describe-it) keeps the old
  // straight-to-chat path — see analyze().
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importedProjectId, setImportedProjectId] = useState<string | null>(null);
  // Phase 2 of import: reconstruct the upstream modules the import evidences but
  // didn't fill (e.g. imported M4 → infer M1/M2/M3). Candidates only — the
  // student confirms/edits each before it's committed.
  const [reconstructed, setReconstructed] = useState<ReconstructedModule[]>([]);
  const [reconstructing, setReconstructing] = useState(false);
  const [confirmedModules, setConfirmedModules] = useState<string[]>([]);
  const [skippedModules, setSkippedModules] = useState<string[]>([]);

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
        // Kick off reconstruction of the upstream modules (non-blocking — the
        // activation card renders immediately; suggestions stream in after).
        if (res.imported.length > 0 && res.to_reconstruct.length > 0) {
          setReconstructing(true);
          apiFetch(`/projects/${newId}/mid-journey-import/reconstruct`, {
            method: "POST",
            body: {},
          })
            .then((r: any) => setReconstructed(r?.reconstructed ?? []))
            .catch(() => setReconstructed([])) // graceful: card just shows none
            .finally(() => setReconstructing(false));
        }
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
    const confirmModule = async (module: string, edited: Record<string, unknown>) => {
      await apiFetch(`/projects/${importedProjectId}/mid-journey-import/confirm`, {
        method: "POST",
        body: { module, slice: edited },
      });
      setConfirmedModules((c) => [...c, module]);
    };
    return (
      <div className="max-w-2xl mx-auto">
        <div className="text-center mb-7">
          <h1 className="m-0 text-[26px] font-extrabold font-serif tracking-tight text-ink-900">
            Here&apos;s where you are
          </h1>
        </div>
        <div className="flex flex-col gap-4">
          <ImportSummary
            imported={importResult.imported}
            focus={importResult.focus}
            ambiguous={importResult.ambiguous}
            unreadable={importResult.unreadable}
            onContinue={() => router.push(`/chat/projects/${importedProjectId}`)}
            // Gate on the SAME state the card below renders from. Continuing
            // mid-reconstruction navigates away from steps the student has not
            // reviewed yet — and the confirm/skip choices are made on this
            // screen, so leaving early silently drops them.
            reconstructing={reconstructing}
          />
          <ReconstructedModules
            items={reconstructed}
            reconstructing={reconstructing}
            confirmedModules={confirmedModules}
            skippedModules={skippedModules}
            onConfirm={confirmModule}
            onSkip={(m) => setSkippedModules((s) => [...s, m])}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 hover:text-ink-900 no-underline mb-6"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> {t("new.back")}
      </Link>

      <div className="text-center mb-7">
        <h1 className="m-0 text-[26px] font-extrabold font-serif tracking-tight text-ink-900">
          {t("new.title")}
        </h1>
      </div>

      {/* The composer IS the page now. Subtitle deleted on purpose: the
          placeholder and the starter chips already say what to do, and three
          restatements of the same instruction is noise, not guidance. */}
      <ThesisComposer
        value={note}
        onChange={setNote}
        files={files}
        onAddFiles={addFiles}
        onRemoveFile={removeFile}
        onSubmit={() => void analyze()}
        canSubmit={canSubmit}
        busy={submitting}
        accept={ACCEPT_TYPES}
      />

      {/* Footer — status and the blank-start escape hatch only.
          The Analyze button lives INSIDE the composer now; a second one here
          was a leftover from the drop-zone layout and shipped two competing
          primary actions on one screen. */}
      <div className="mt-5 flex items-center gap-3">
        {error && (
          <span role="alert" className="text-[12.5px] text-red-700 font-semibold">{error}</span>
        )}
        {status && !error && (
          <span className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 font-semibold">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {status}
          </span>
        )}
        <span className="flex-1" />
        <Button variant="ghost" asChild>
          <Link href="/">{t("new.cancel")}</Link>
        </Button>
      </div>
    </div>
  );
}

