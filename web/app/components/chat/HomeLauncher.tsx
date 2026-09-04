"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import useSWR from "swr";

import { apiFetch, swrFetcher as fetcher } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import {
  stashAnalyzeIntent,
  type AnalyzeAttachment,
  type AnalyzeKind,
} from "@/app/lib/bootstrap-payload";
import { Button } from "@/app/components/ui/button";
import { useT } from "@/app/lib/i18n/LocaleProvider";
import { ImportSummary } from "./ImportSummary";
import { useRunProgress } from "@/app/(inapp)/tools/_components/use-tool";
import { StartModeTabs } from "./StartModeTabs";
import { ThesisComposer, STARTER_CHIPS, type StartMode } from "./ThesisComposer";
import {
  ReconstructedModules,
  type ReconstructedModule,
  type SavedModule,
} from "./ReconstructedModules";
import { MODULES, moduleStatus, type Project } from "./HomeDashboard";

// Shape of POST /projects/{id}/mid-journey-import (F12) — mirrors /new.
type ImportResult = {
  imported: string[];
  ambiguous: string[];
  unreadable: string[];
  focus: string;
  to_reconstruct: string[];
};

// Keep in sync with the uploads endpoint's text-extractable set
// (api/app/routers/uploads.py). Same list the /new page advertised.
const ACCEPT_TYPES =
  "application/pdf,text/plain,text/markdown," +
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document," +
  ".pdf,.txt,.md,.markdown,.docx";

/**
 * The homepage IS the start experience now — a prompt-first launcher, not the
 * old greeting/stats/theses dashboard. This is the /new flow lifted onto `/`
 * (the create-project → upload → import → chat pipeline is unchanged, verbatim
 * from NewThesisPage), wrapped in a straight-to-the-point presentation:
 *
 *   What can I do for your thesis?
 *   [Guided | Auto Thesis]  + bold per-mode headline + tagline
 *   ┌ composer (drop / describe) ┐
 *   Your theses:  [card: M1 brief + % ring + M1→M5 bar] …  (returning user)
 *   — or —
 *   Try one of these:  [prompt card] …                     (brand-new user)
 *
 * /new redirects here so there is one start surface. The full theses list also
 * lives at /papers in the sidebar.
 */
export function HomeLauncher() {
  const router = useRouter();
  const t = useT();
  const [files, setFiles] = useState<File[]>([]);
  const [note, setNote] = useState("");
  const [kind, setKind] = useState<AnalyzeKind>("assess");
  const [mode, setMode] = useState<StartMode>("guided");
  const [submitting, setSubmitting] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importedProjectId, setImportedProjectId] = useState<string | null>(null);
  const [reconstructed, setReconstructed] = useState<ReconstructedModule[]>([]);
  const [reconstructing, setReconstructing] = useState(false);
  const reconstructProgress = useRunProgress(reconstructing);
  const [savedModules, setSavedModules] = useState<SavedModule[]>([]);
  const [focus, setFocus] = useState<string | null>(null);
  const [resumable, setResumable] = useState(false);

  // The user's theses, newest first (/projects is ordered updated_at desc), for
  // the "Your theses" grid below the composer. Undefined while loading, so the
  // grid holds off rather than flashing the new-user prompts at a returning one.
  const { data: projects } = useSWR<Project[]>("/projects/list", fetcher, { dedupingInterval: 0 });

  const prefsRef = useRef<{ field?: string; language?: string; citation_style?: string }>({});
  const abortRef = useRef<AbortController | null>(null);

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
    // SNAPSHOT FIRST — see the /new page's note: the caller clears the live
    // FileList right after, so Array.from() must run before the state updater.
    const picked = Array.from(incoming);
    if (picked.length === 0) return;
    setFiles(prev => {
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

  // Clicking a sample-prompt card prefills the composer, exactly like the inline
  // chips did (ThesisComposer.applyChip) — set the text AND reassert the intent
  // so a humanize card doesn't leave the rewrite armed behind edited text.
  const applyPrompt = (textKey: typeof STARTER_CHIPS[number]["textKey"], k?: AnalyzeKind) => {
    setNote(t(textKey));
    setKind(k ?? "assess");
  };

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
      const prefs = prefsRef.current;
      const project = await apiFetch("/projects", {
        method: "POST",
        signal: abortRef.current?.signal,
        body: {
          name: "Untitled thesis",
          field: prefs.field?.trim() || null,
          language: prefs.language || "en",
          citation_style: prefs.citation_style || "apa",
          mode: mode === "auto_thesis" ? "auto" : "chat",
        },
      });
      const newId = (project as { id: string }).id;

      const attachments: AnalyzeAttachment[] = [];
      for (let i = 0; i < files.length; i++) {
        setStatus(`Uploading ${i + 1} of ${files.length}…`);
        attachments.push(await uploadOne(newId, files[i]));
      }

      // F12 import branch — guided + real files + non-humanize only. Same rules
      // and rationale as the /new page (Auto Thesis and humanize both skip it).
      if (files.length > 0 && kind !== "humanize" && mode !== "auto_thesis") {
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
              if (r?.focus) setFocus(r.focus);
            })
            .catch(() => setReconstructed([]))
            .finally(() => setReconstructing(false));
        }
        stashAnalyzeIntent(newId, { kind, note, attachments, preseeded: true });
        return;
      }

      stashAnalyzeIntent(newId, { kind, note, attachments,
                                  autoThesis: mode === "auto_thesis" });
      router.push(`/chat/projects/${newId}?analyzing=1`);
    } catch (e: any) {
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

  const cancelRun = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setSubmitting(false);
    setStatus(null);
    setError(null);
    setResumable(true);
  };

  // Once the import lands, the launcher becomes the activation summary — the
  // first-session payoff — with a CTA into chat at the imported focus module.
  if (importResult && importedProjectId) {
    return (
      <div className="max-w-2xl mx-auto pt-6">
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
            onContinue={() =>
              router.push(`/chat/projects/${importedProjectId}?analyzing=1`)
            }
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

  const auto = mode === "auto_thesis";

  return (
    <div className="max-w-2xl mx-auto flex flex-col items-center pt-10 sm:pt-16">
      <h1 className="m-0 text-center text-[30px] sm:text-[34px] font-extrabold font-serif tracking-tight text-ink-900">
        {t("home.launcher.title")}
      </h1>

      <div className="w-full mt-7 flex flex-col items-center">
        <StartModeTabs mode={mode} onChange={setMode} busy={submitting} />
        {/* Per-mode value-prop headline (bold) — "1 prompt, full thesis" for
            Auto Thesis — then the explanatory tagline under it. */}
        <h2 className="mt-4 mb-0 text-center text-[19px] font-extrabold font-serif tracking-tight text-ink-900">
          {t(auto ? "new.auto.title" : "new.title")}
        </h2>
        <p className="mt-2 mb-0 max-w-[46ch] text-center text-[13.5px] leading-relaxed text-ink-500">
          {t(auto ? "new.auto.tagline" : "new.tagline")}
        </p>
      </div>

      <div className="w-full mt-6">
        {/* The composer's own inline chips are suppressed here — the same
            prompts render as full-body cards below, so showing both would be
            two competing prompt rows. */}
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
          showChips={false}
        />
      </div>

      {/* Footer — status + the blank-start escape hatch (cancel stops a run). */}
      <div className="w-full mt-5 flex items-center gap-3 min-h-[28px]">
        {error && (
          <span role="alert" className="text-[12.5px] text-red-700 font-semibold">{error}</span>
        )}
        {resumable && !submitting && !error && (
          <span className="text-[12.5px] text-ink-600 font-medium">{t("new.resumable")}</span>
        )}
        {status && !error && (
          <span className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 font-semibold">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> {status}
          </span>
        )}
        <span className="flex-1" />
        {submitting && (
          <Button variant="ghost" onClick={cancelRun}>{t("new.cancel")}</Button>
        )}
      </div>

      {/* Guided-mode only (Auto Thesis's next step is a paid run, not browsing).
          Returning user → their theses, each card carrying the M1 brief and the
          M1→M5 progression at its foot; brand-new user → sample prompts. While
          /projects/list is still loading (undefined) neither shows, so a
          returning user never flashes the new-user prompts. */}
      {!auto && projects && projects.length > 0 && (
        <div className="w-full mt-7">
          <div className="text-[11px] uppercase tracking-[0.08em] font-bold text-ink-400 mb-2.5 px-0.5">
            {t("home.theses")}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
            {projects.map(p => <ThesisCard key={p.id} project={p} />)}
          </div>
        </div>
      )}

      {!auto && projects && projects.length === 0 && (
        <div className="w-full mt-7">
          <div className="text-[11px] uppercase tracking-[0.08em] font-bold text-ink-400 mb-2.5 px-0.5">
            {t("home.launcher.tryTitle")}
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
            {STARTER_CHIPS.map((chip) => (
              <button
                key={chip.labelKey}
                type="button"
                onClick={() => applyPrompt(chip.textKey, chip.kind)}
                disabled={submitting}
                className="group text-left rounded-xl border border-ink-200 bg-white px-3.5 py-3 hover:border-primary-300 hover:bg-primary-50/30 transition-colors disabled:opacity-50 flex flex-col gap-1.5 min-h-[104px]"
              >
                <span className="text-[11px] font-bold text-ink-500 group-hover:text-primary-700">
                  {t(chip.labelKey)}
                </span>
                <span className="text-[12.5px] leading-relaxed text-ink-700">
                  {t(chip.textKey)}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// A thesis on the homepage, in the same card family as the sample prompts.
// Body is the M1 BRIEF — the research title read out of the m1_topic slice — not
// the project name (often "Untitled thesis") and not a chat message. The overall
// % rides top-right as a ring; the M1→M5 progression sits at the card's foot.
function ThesisCard({ project }: { project: Project }) {
  const t = useT();
  // The list read whitelists research_title into the m1_topic summary; fall back
  // to the project name, then a generic label, so the card is never blank.
  const brief = project.context_store?.m1_topic?.research_title
    || project.name
    || "Untitled thesis";
  return (
    <Link
      href={`/chat/projects/${project.id}`}
      className="group flex flex-col gap-1.5 rounded-xl border border-ink-200 bg-white px-3.5 py-3 no-underline hover:border-primary-300 hover:bg-primary-50/30 transition-colors min-h-[104px]"
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-[11px] uppercase tracking-[0.04em] font-bold text-ink-400 truncate">
          {project.field || t("home.noField")}
        </span>
        <ProgressRing pct={progressPct(project)} />
      </div>
      <span className="text-[12.5px] leading-relaxed text-ink-800 font-semibold line-clamp-3">
        {brief}
      </span>
      {/* Gray secondary content — which module the student is on. */}
      <span className="flex-1" />
      <ThesisFocusLine project={project} />
    </Link>
  );
}

// Overall completion 0–100 from module states — a done module is worth a full
// fifth, anything started counts half. Same weighting the old dashboard card
// used for its percentage.
function progressPct(p: Project): number {
  let score = 0;
  for (const m of MODULES) {
    const s = moduleStatus(p, m);
    if (s === "done") score += 20;
    else if (s === "in_progress") score += 10;
  }
  return score;
}

// Circular progress ring for the resume strip — the overall % as a ring rather
// than a bare number, with the value in the middle.
function ProgressRing({ pct }: { pct: number }) {
  const r = 16;
  const c = 2 * Math.PI * r;
  const dash = (Math.max(0, Math.min(100, pct)) / 100) * c;
  return (
    <span className="relative inline-flex items-center justify-center shrink-0" style={{ width: 40, height: 40 }}>
      <svg width="40" height="40" viewBox="0 0 40 40" className="-rotate-90" aria-hidden>
        <circle cx="20" cy="20" r={r} fill="none" stroke="var(--color-ink-100, #e8e8ec)" strokeWidth="4" />
        <circle
          cx="20" cy="20" r={r} fill="none"
          stroke="var(--color-primary-600, #1c2eff)" strokeWidth="4" strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <span className="absolute text-[10.5px] font-bold tabular-nums text-ink-700">{pct}</span>
    </span>
  );
}

// Where the student is, spelled out — "M3 · Research Design" — as the card's
// gray secondary line. Replaces the M1→M5 bar: the ring already carries the
// overall progress, this says which module is in play.
function ThesisFocusLine({ project }: { project: Project }) {
  const t = useT();
  const focusModule = project.focus ?? project.current_module;
  const focusKey = MODULES.find(m => m.id === focusModule)?.labelKey;
  if (!focusModule) return null;
  return (
    <span className="text-[11px] text-ink-400 font-medium truncate">
      {focusModule}{focusKey ? ` · ${t(focusKey)}` : ""}
    </span>
  );
}
