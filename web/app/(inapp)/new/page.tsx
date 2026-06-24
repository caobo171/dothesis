"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, BookOpen, Check, ClipboardList, FileText, Lightbulb,
  ListChecks, Paperclip, ScrollText, Sigma, X,
} from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { tokenStore } from "@/app/lib/tokenStore";
import {
  stashBootstrapPayload,
  type BootstrapItemId,
} from "@/app/lib/bootstrap-payload";
import { Button } from "@/app/components/ui/button";
import { Input } from "@/app/components/ui/input";
import { Textarea } from "@/app/components/ui/textarea";

type FilesByItem = Partial<Record<BootstrapItemId, File[]>>;


/**
 * /new — dedicated bootstrap page.
 *
 * Replaces the old NewProjectModal. Single-page form: Project name at the
 * top (required, maps to the M1 topic), then optional checkbox grid for
 * "what else do you already have?" with inputs that appear inline below.
 *
 * On submit: POST /projects, stash the rest of the declared content keyed
 * by the new project id, then navigate to /chat/projects/[id] so the chat
 * surface can replay the stash as a structured first message.
 */


type DeclareItem = {
  id: BootstrapItemId;
  label: string;
  hint: string;
  module: string;
  icon: React.ReactNode;
  /** Override the default textarea height for items that want more space. */
  textRows?: number;
};

const ITEMS: DeclareItem[] = [
  // Order matters — these render M1 → M5 in both the grid and the per-item
  // input section. The agent walks the modules in this order, so the form
  // mirrors it.
  { id: "topic",       label: "Topic",           hint: "Title, scope, RQs, objectives", module: "M1", icon: <Lightbulb className="w-4 h-4" />,    textRows: 6 },
  { id: "references",  label: "References",      hint: "PDFs or DOI list",            module: "M2", icon: <BookOpen className="w-4 h-4" /> },
  { id: "gaps",        label: "Research gaps",   hint: "Already-identified gaps",     module: "M2", icon: <ListChecks className="w-4 h-4" /> },
  { id: "model",       label: "Conceptual model",hint: "Diagram / hypotheses",         module: "M3", icon: <Sigma className="w-4 h-4" /> },
  { id: "instrument",  label: "Instrument",      hint: "Questionnaire / interview",   module: "M3", icon: <ClipboardList className="w-4 h-4" /> },
  { id: "data",        label: "Data",            hint: ".sav · .csv · transcripts",   module: "M4", icon: <FileText className="w-4 h-4" /> },
  { id: "draft",       label: "Draft",           hint: "Partial Word/PDF",            module: "M5", icon: <ScrollText className="w-4 h-4" /> },
];


// The uploads endpoint accepts PDF + plain-text only (see
// api/app/routers/uploads.py: _ALLOWED_MIME). The file picker advertises the
// same set so the OS dialog filters correctly.
const ACCEPT_TYPES = "application/pdf,text/plain,.pdf,.txt";


export default function NewThesisPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [have, setHave] = useState<Set<BootstrapItemId>>(new Set());
  const [payload, setPayload] = useState<Partial<Record<BootstrapItemId, string>>>({});
  const [filesByItem, setFilesByItem] = useState<FilesByItem>({});
  const [submitting, setSubmitting] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggle = (id: BootstrapItemId) => {
    setHave(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
        // Drop the payload + files for items that get un-checked so we
        // don't ship stale state when the user changes their mind.
        setPayload(p => { const { [id]: _, ...rest } = p; return rest; });
        setFilesByItem(f => { const { [id]: _, ...rest } = f; return rest; });
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const trimmedName = name.trim();
  const canSubmit = !submitting;

  const addFilesFor = (itemId: BootstrapItemId, incoming: FileList | File[] | null) => {
    if (!incoming) return;
    setFilesByItem(prev => {
      const existing = prev[itemId] ?? [];
      // De-dup by (name, size) so picking the same file twice doesn't queue
      // two uploads. Common when the user re-opens the picker after losing
      // their place.
      const seen = new Set(existing.map(f => `${f.name}::${f.size}`));
      const next = [...existing];
      for (const f of Array.from(incoming)) {
        const k = `${f.name}::${f.size}`;
        if (!seen.has(k)) {
          seen.add(k);
          next.push(f);
        }
      }
      return { ...prev, [itemId]: next };
    });
  };

  const removeFileFor = (itemId: BootstrapItemId, idx: number) =>
    setFilesByItem(prev => {
      const existing = prev[itemId] ?? [];
      const next = existing.filter((_, i) => i !== idx);
      if (next.length === 0) {
        const { [itemId]: _, ...rest } = prev;
        return rest;
      }
      return { ...prev, [itemId]: next };
    });

  // Multipart upload — can't go through apiFetch (JSON-only), and the auth
  // token rides in an Authorization: Bearer header since the body is
  // multipart, not JSON. Same pattern as ChatPane's onFileDrop.
  const uploadOne = async (projectId: string, file: File): Promise<void> => {
    const token = tokenStore.get();
    const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:7100/api/v1";
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(`${base}/projects/${projectId}/uploads`, {
      method: "POST",
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      body: fd,
    });
    if (!res.ok) {
      throw new Error(`upload failed (${res.status}) for ${file.name}`);
    }
  };

  const finish = async () => {
    if (!canSubmit) return;
    setError(null);
    setSubmitting(true);
    setUploadStatus(null);
    try {
      // Nothing in the form is required — fall back to a generic name when
      // the user clicks Create without typing anything, so they can rename
      // from the chat header later.
      const projectName = trimmedName || "Untitled thesis";
      const project = await apiFetch("/projects", {
        method: "POST",
        body: { name: projectName },
      });
      const newId = (project as { id: string }).id;

      // Uploads are project-scoped, so they have to wait for the project
      // row to exist. We flatten per-item files into one sequential queue
      // and surface a per-file counter so the user sees progress for slow
      // PDFs instead of a frozen "Creating…" button.
      const allFiles: File[] = ITEMS.flatMap(it => filesByItem[it.id] ?? []);
      if (allFiles.length) {
        for (let i = 0; i < allFiles.length; i++) {
          setUploadStatus(`Uploading ${i + 1} of ${allFiles.length}…`);
          await uploadOne(newId, allFiles[i]);
        }
      }

      stashBootstrapPayload(newId, have, payload);
      router.push(`/chat/projects/${newId}`);
    } catch (e: any) {
      const code = e?.body?.error?.code;
      setError(code || e?.message || "Could not create project.");
      setSubmitting(false);
      setUploadStatus(null);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && canSubmit) {
      e.preventDefault();
      void finish();
    }
  };

  return (
    <div className="max-w-3xl mx-auto">
      {/* Back link — sidebar already gives them home, but the in-page
          affordance matches what the modal's close button used to do. */}
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-[12.5px] text-ink-500 hover:text-ink-900 no-underline mb-4"
      >
        <ArrowLeft className="w-3.5 h-3.5" /> Back to home
      </Link>

      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <span
          className="w-11 h-11 rounded-[12px] inline-flex items-center justify-center text-white font-extrabold font-serif text-[22px]"
          style={{ background: "linear-gradient(135deg, #2540FF 0%, #6A4DE0 100%)" }}
        >
          D
        </span>
        <div>
          <h1 className="m-0 text-[24px] font-extrabold font-serif tracking-tight text-ink-900">
            Bootstrap your thesis
          </h1>
          <div className="text-[13px] text-ink-500 mt-0.5">
            Everything below is optional — just hit Create to start blank, or fill in what you already have.
          </div>
        </div>
      </div>

      <div className="bg-white rounded-3xl border border-ink-200 shadow-sm overflow-hidden">
        {/* Body — single scrollable page, no steps */}
        <div className="px-7 py-6 flex flex-col gap-6">
          {/* Project name — short display label that shows up in the
              sidebar / dashboard cards. Kept separate from Topic on purpose:
              the M1 topic is a long-form artefact; the project name just
              needs to fit on a card. */}
          <div>
            <label htmlFor="project-name" className="block text-[13.5px] font-bold text-ink-900">
              Project name
            </label>
            <div className="text-[12px] text-ink-500 mt-0.5 mb-2">
              Optional — leave blank to start with "Untitled thesis" and rename in chat.
            </div>
            <Input
              id="project-name"
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="e.g. Gen Z livestream study"
              autoFocus
            />
          </div>

          {/* What do you already have? — a single M1 → M5 list. Each item's
              input (text + files) expands inline RIGHT UNDER its box the moment
              it's ticked, instead of being collected in a separate section
              below — so on mobile the input is always next to what you tapped. */}
          <div>
            <div className="text-[13.5px] font-bold text-ink-900">
              What do you already have?
            </div>
            <div className="text-[12px] text-ink-500 mt-0.5 mb-3">
              Optional — tick anything you're bringing in. The input for each appears right under it.
            </div>
            <div className="flex flex-col gap-2.5">
              {ITEMS.map(it => {
                const on = have.has(it.id);
                return (
                  <div key={it.id} className="flex flex-col">
                    <button
                      type="button"
                      onClick={() => toggle(it.id)}
                      className={`flex items-start gap-3 text-left p-3.5 transition-all ${
                        on
                          ? "bg-primary-50 border-[2px] border-b-0 border-primary-600 rounded-t-2xl"
                          : "bg-white border border-ink-200 hover:border-ink-300 rounded-2xl"
                      }`}
                    >
                      <span
                        className={`w-[34px] h-[34px] rounded-[10px] inline-flex items-center justify-center text-[16px] shrink-0 border ${
                          on
                            ? "bg-white text-primary-700 border-primary-100"
                            : "bg-ink-50 text-ink-600 border-ink-200"
                        }`}
                      >
                        {it.icon}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[13.5px] font-bold text-ink-900">{it.label}</div>
                        <div className="text-[11.5px] text-ink-500 mt-0.5">
                          → {it.module} · {it.hint}
                        </div>
                      </div>
                      <span
                        className={`w-[18px] h-[18px] rounded-[5px] inline-flex items-center justify-center text-[11px] font-extrabold shrink-0 ${
                          on
                            ? "bg-primary-600 text-white"
                            : "bg-white border-[1.5px] border-ink-300"
                        }`}
                        aria-hidden="true"
                      >
                        {on && <Check className="w-3 h-3" />}
                      </span>
                    </button>
                    {on && (
                      <ImportRow
                        compact
                        files={filesByItem[it.id] ?? []}
                        onAddFiles={fs => addFilesFor(it.id, fs)}
                        onRemoveFile={i => removeFileFor(it.id, i)}
                        submitting={submitting}
                        item={it}
                        value={payload[it.id] ?? ""}
                        onChange={v => setPayload(p => ({ ...p, [it.id]: v }))}
                      />
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>

        {/* Footer — Cancel / Create */}
        <div className="px-7 py-4 border-t border-ink-200 bg-ink-50 flex items-center gap-3">
          {error && (
            <span role="alert" className="text-[12px] text-red-700 font-semibold">
              {error}
            </span>
          )}
          {uploadStatus && !error && (
            <span className="text-[12px] text-ink-500 font-semibold">
              {uploadStatus}
            </span>
          )}
          <span className="flex-1" />
          <Button variant="ghost" asChild>
            <Link href="/">Cancel</Link>
          </Button>
          <Button type="button" onClick={() => void finish()} disabled={!canSubmit}>
            {submitting ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </div>
  );
}


function ImportRow({
  item, value, onChange, files, onAddFiles, onRemoveFile, submitting, compact = false,
}: {
  item: DeclareItem;
  value: string;
  onChange: (v: string) => void;
  files: File[];
  onAddFiles: (files: FileList | File[] | null) => void;
  onRemoveFile: (idx: number) => void;
  submitting: boolean;
  /** When true, render as a connected continuation directly under the item's
      box (rounded bottom, no top border, no repeated icon/label header). */
  compact?: boolean;
}) {
  // Data is files-only: datasets are best ingested by M4 tools as uploads,
  // not as a typed description.
  const filesOnly = item.id === "data";
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  return (
    <div
      className={
        compact
          ? "p-3.5 rounded-b-2xl border-[2px] border-t-0 border-primary-600 bg-white"
          : "flex items-start gap-3.5 p-3.5 rounded-2xl border border-ink-200 bg-white"
      }
    >
      {!compact && (
        <span className="w-[38px] h-[38px] rounded-[10px] bg-ink-50 text-ink-700 inline-flex items-center justify-center shrink-0">
          {item.icon}
        </span>
      )}
      <div className="flex-1 min-w-0">
        {!compact && (
          <>
            <div className="flex items-center gap-2">
              <div className="text-[13.5px] font-bold text-ink-900">{item.label}</div>
              <span className="text-[10.5px] uppercase tracking-[0.04em] font-bold text-primary-700 bg-primary-50 px-1.5 py-0.5 rounded-md">
                {item.module}
              </span>
            </div>
            <div className="text-[11.5px] text-ink-500 mt-0.5">{item.hint}</div>
          </>
        )}

        {!filesOnly && (
          <Textarea
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder={importPlaceholder(item.id)}
            rows={item.textRows ?? 3}
            autoFocus={compact}
            className={`${compact ? "mt-0" : "mt-2.5"} resize-y leading-relaxed`}
          />
        )}

        {/* File picker — drag-and-drop dashed area or "Choose files" button.
            Always shown; for filesOnly items it's the only input. */}
        <div
          className={`${filesOnly ? "mt-2.5" : "mt-2"} rounded-[10px] border-2 border-dashed border-ink-200 hover:border-primary-300 bg-ink-50/40 px-3 py-3 flex flex-col sm:flex-row sm:items-center gap-2 transition-colors`}
          onDragOver={e => { e.preventDefault(); }}
          onDrop={e => {
            e.preventDefault();
            onAddFiles(e.dataTransfer?.files ?? null);
          }}
        >
          <span className="flex items-center gap-2 text-[11.5px] text-ink-500 flex-1 min-w-0">
            <Paperclip className="w-3.5 h-3.5 text-ink-400 shrink-0" />
            {filesOnly ? "Drop dataset files here" : "Attach a file, or drop it here"}
          </span>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => fileInputRef.current?.click()}
            disabled={submitting}
            className="w-full sm:w-auto shrink-0"
          >
            Choose files
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPT_TYPES}
            onChange={e => {
              onAddFiles(e.target.files);
              e.target.value = "";
            }}
            className="hidden"
          />
        </div>

        {files.length > 0 && (
          <div className="mt-2 flex flex-col gap-1.5">
            {files.map((f, i) => (
              <div
                key={`${f.name}-${f.size}-${i}`}
                className="flex items-center gap-2 px-3 py-1.5 rounded-lg border border-ink-200 bg-white text-[12px]"
              >
                <FileText className="w-3.5 h-3.5 text-ink-500 shrink-0" />
                <span className="font-medium text-ink-800 truncate flex-1">{f.name}</span>
                <span className="text-ink-500 tabular-nums shrink-0">
                  {formatBytes(f.size)}
                </span>
                <button
                  type="button"
                  onClick={() => onRemoveFile(i)}
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
      </div>
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}


function importPlaceholder(id: BootstrapItemId): string {
  switch (id) {
    case "topic":      return (
      "e.g.\n" +
      "Gen Z TikTok livestream buying behaviour in Hà Nội\n\n" +
      "Scope: urban Vietnamese consumers, 18–27, last 6 months.\n" +
      "RQs:\n" +
      "  1. How does parasocial trust shape impulse purchase intent?\n" +
      "  2. Does perceived scarcity moderate that effect?\n" +
      "Objectives: validate a 5-construct UTAUT2 extension; test moderation; surface managerial implications for SME sellers."
    );
    case "references": return "Paste DOIs or a reference list, one per line. Or just describe what you've read so far.";
    case "gaps":       return "Describe the gaps in the literature you've already spotted. The agent can refine them.";
    case "model":      return "Describe the conceptual model — constructs, paths, hypotheses. Free-form prose is fine.";
    case "instrument": return "Paste the questionnaire / interview guide, or describe its structure.";
    case "data":       return "Describe the dataset — what's measured, what tool produced it, sample size.";
    case "draft":      return "Paste an outline or describe how much of the thesis is written.";
    default:           return "";
  }
}
