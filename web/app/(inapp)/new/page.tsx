"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import {
  stashAnalyzeIntent,
  type AnalyzeAttachment,
  type AnalyzeKind,
} from "@/app/lib/bootstrap-payload";
import { Button } from "@/app/components/ui/button";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { ImportSummary } from "@/app/components/chat/ImportSummary";
// Shared with the document tools: the same "poll my in-flight run" hook, because
// this screen has the same problem they do (see /runs/active).
import { useRunProgress } from "@/app/(inapp)/tools/_components/use-tool";
import { ThesisComposer, type StartMode } from "@/app/components/chat/ThesisComposer";
import {
  ReconstructedModules,
  type ReconstructedModule,
  type SavedModule,
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
  // Which job the first turn does. Only the humanize chip moves this off the
  // default; see StarterChip.kind in ThesisComposer.
  const [kind, setKind] = useState<AnalyzeKind>("assess");
  // Guided conversation vs. one unattended run. Chosen BEFORE anything is
  // typed, because it is the decision about how much of the work the student
  // wants to do — not a variation on the first message.
  const [mode, setMode] = useState<StartMode>("guided");
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
  // didn't fill (e.g. imported M4 → infer M1/M2/M3). The server SAVES these as
  // it infers them — this screen reports what landed, it doesn't gate it.
  const [reconstructed, setReconstructed] = useState<ReconstructedModule[]>([]);
  const [reconstructing, setReconstructing] = useState(false);
  // The reconstruction's own progress. It cannot come from the POST's response
  // — that arrives only when the work is already over, which is the very thing
  // we are waiting on. useRunProgress asks the server "what am I running right
  // now" instead, which is why /runs/active exists. Null until the walk reports
  // its first tick, so the button falls back to a plain spinner rather than 0/0.
  const reconstructProgress = useRunProgress(reconstructing);
  const [savedModules, setSavedModules] = useState<SavedModule[]>([]);
  // Reconstruction moves focus forward past the steps it completed, so the
  // "you're at / next" line has to follow it rather than keep quoting the
  // module the import landed on.
  const [focus, setFocus] = useState<string | null>(null);

  // Setup defaults still come from the user's cross-project memory (/me/prefs)
  // so a returning user's field/language/citation carry over — they're just no
  // longer surfaced as form fields. Best-effort; first-timers get built-ins.
  const prefsRef = useRef<{ field?: string; language?: string; citation_style?: string }>({});
  // Cancel has to ABORT the in-flight run, not navigate away: the footer button
  // was a <Link href="/">, so a student who mis-typed their prompt lost the
  // file they had attached and the note they had written just to correct it.
  const abortRef = useRef<AbortController | null>(null);
  // Shown after a cancel that happened mid-run. The work IS resumable — each
  // module is committed as it finishes and a re-run skips the ones already
  // complete — but nothing said so, so a student who stopped it assumed they
  // had thrown the whole thing away and started over, paying twice.
  const [resumable, setResumable] = useState(false);
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
    // SNAPSHOT FIRST — this line must not move inside the updater below.
    //
    // `incoming` is usually the input's LIVE FileList, and the caller clears
    // `input.value` right after calling us so the same file can be re-picked.
    // Clearing the input empties that FileList in place. Array.from() used to
    // run inside the setFiles updater, which React defers to the next render —
    // by then the list was empty and the pick was silently dropped.
    //
    // It looked like "you can only ever attach one file": React eagerly
    // evaluates the FIRST update from initial state (so file #1 landed) and
    // defers every one after it (so #2 onward vanished). Reported from the
    // field as "chỉ up dc 1 file".
    const picked = Array.from(incoming);
    if (picked.length === 0) return;
    setFiles(prev => {
      // De-dup by (name, size) so re-dropping the same file doesn't queue it twice.
      const seen = new Set(prev.map(f => `${f.name}::${f.size}`));
      const next = [...prev];
      for (const f of picked) {
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
      signal: abortRef.current?.signal,
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
    setResumable(false);
    setSubmitting(true);
    setStatus("Creating project…");
    abortRef.current = new AbortController();
    try {
      // Name is inferred later (the bootstrap turn renames from the detected
      // topic); start generic so the user never has to fill a name field.
      const prefs = prefsRef.current;
      const project = await apiFetch("/projects", {
        method: "POST",
        signal: abortRef.current?.signal,
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
      //
      // A humanize job skips the import even WITH files, because it is a
      // utility job rather than a thesis journey:
      // mid-journey-import classifies the upload into M1–M5 and then
      // reconstruct_upstream INFERS the modules it couldn't find. None of that
      // feeds the rewrite — humanize_prose reads only the language and the
      // saved anchor — so for a student who came to fix their prose it is
      // billed work nobody asked for, and it ends with them owning a
      // half-fabricated thesis project (M1–M4 all in_progress, research_gaps
      // with no literature_sources) as their first impression of the product.
      //
      // The project row is still created above: uploads, threads and billing
      // all hang off it. It just stays EMPTY rather than populated with
      // inferred state. Mapping into modules is offered afterwards, once the
      // student has the thing they actually came for.
      if (files.length > 0 && kind !== "humanize") {
        setStatus("Reading your work…");
        const res = (await apiFetch(`/projects/${newId}/mid-journey-import`, {
          method: "POST",
          signal: abortRef.current?.signal,
          body: {},
        })) as ImportResult;
        setImportResult(res);
        setImportedProjectId(newId);
        setFocus(res.focus);
        setSubmitting(false);
        setStatus(null);
        // Kick off reconstruction of the upstream modules (non-blocking — the
        // activation card renders immediately; the reconstructed steps land
        // under it as they're saved).
        if (res.imported.length > 0 && res.to_reconstruct.length > 0) {
          setReconstructing(true);
          apiFetch(`/projects/${newId}/mid-journey-import/reconstruct`, {
            method: "POST",
            signal: abortRef.current?.signal,
            body: {},
          })
            .then((r: any) => {
              setReconstructed(r?.reconstructed ?? []);
              setSavedModules(r?.saved ?? []);
              // Saving M1-M3 moves the student to M4 — the CTA has to point there.
              if (r?.focus) setFocus(r.focus);
            })
            .catch(() => setReconstructed([])) // graceful: card just shows none
            .finally(() => setReconstructing(false));
        }
        // Carry the sentence the student typed through to the chat.
        //
        // This branch used to `return` straight past stashAnalyzeIntent, so
        // attaching a file silently threw away whatever they had written in the
        // box next to it — they pressed Continue and landed in an empty thread,
        // their actual request never asked. The import is not a substitute for
        // it: it classifies files, it cannot act on "write chapter 5 in
        // English".
        //
        // preseeded: the modules are already committed, so the first turn must
        // be their request rather than the /bootstrap re-classification (see
        // formatAnalyzeMessage). Blank note => stashAnalyzeIntent writes
        // nothing and the thread opens quietly.
        stashAnalyzeIntent(newId, { kind, note, attachments, preseeded: true,
                                    autoThesis: mode === "auto_thesis" });
        return;
      }

      stashAnalyzeIntent(newId, { kind, note, attachments,
                                  autoThesis: mode === "auto_thesis" });
      router.push(`/chat/projects/${newId}?analyzing=1`);
    } catch (e: any) {
      // A cancel is not a failure. Aborting mid-flight rejects whichever fetch
      // was open, and surfacing that as a red error told the student something
      // broke when they had just pressed the button asking it to stop.
      if (e?.name === "AbortError") {
        setSubmitting(false);
        setStatus(null);
        return;
      }
      const code = e?.body?.error?.code;
      setError(code || e?.message || "Could not start. Please try again.");
      setSubmitting(false);
      setStatus(null);
    } finally {
      abortRef.current = null;
    }
  };

  // Stop the run and hand the form back exactly as it was — same file, same
  // note — so correcting a typo costs a click, not a re-upload. Any project
  // already created is left alone: it is empty, it is theirs, and deleting
  // someone's row on a cancel is a worse failure than an unused project.
  const cancelRun = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSubmitting(false);
    setStatus(null);
    setError(null);
    setResumable(true);
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
        <div className="flex flex-col gap-4">
          <ImportSummary
            imported={importResult.imported}
            focus={focus ?? importResult.focus}
            ambiguous={importResult.ambiguous}
            unreadable={importResult.unreadable}
            // ?analyzing=1 to match the note-only path. ChatPane picks the
            // stash up by project id either way, but the two entry points
            // landing on different URLs for the same handoff is how the
            // dropped-note bug stayed invisible.
            onContinue={() =>
              router.push(`/chat/projects/${importedProjectId}?analyzing=1`)
            }
            // Still gated on the same state the card below renders from, but for
            // a different reason now that nothing needs confirming: the
            // reconstruction is what decides which module they land on, so
            // leaving early would send them to the wrong one.
            reconstructing={reconstructing}
            progress={reconstructProgress}
            reconstructed={savedModules.map((s) => s.module)}
          />
          <ReconstructedModules
            items={reconstructed}
            reconstructing={reconstructing}
            saved={savedModules}
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
        onKindChange={setKind}
        mode={mode}
        onModeChange={setMode}
      />

      {/* Footer — status and the blank-start escape hatch only.
          The Analyze button lives INSIDE the composer now; a second one here
          was a leftover from the drop-zone layout and shipped two competing
          primary actions on one screen. */}
      <div className="mt-5 flex items-center gap-3">
        {error && (
          <span role="alert" className="text-[12.5px] text-red-700 font-semibold">{error}</span>
        )}
        {resumable && !submitting && !error && (
          <span className="text-[12.5px] text-ink-600 font-medium">
            {t("new.resumable")}
          </span>
        )}
        {status && !error && (
          <span className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 font-semibold">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {status}
          </span>
        )}
        <span className="flex-1" />
        {/* Two different jobs behind one label. Mid-run it STOPS the run and
            leaves the form intact; idle it is the way back out. Shipping the
            link in both states is what made "Cancel" throw away the student's
            attached file and typed note. */}
        {submitting ? (
          <Button variant="ghost" onClick={cancelRun}>{t("new.cancel")}</Button>
        ) : (
          <Button variant="ghost" asChild>
            <Link href="/">{t("new.cancel")}</Link>
          </Button>
        )}
      </div>
    </div>
  );
}

