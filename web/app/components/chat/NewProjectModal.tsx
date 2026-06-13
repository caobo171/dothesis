"use client";

import { useEffect, useState } from "react";
import {
  BookOpen, Check, ClipboardList, FileText, Lightbulb,
  ListChecks, ScrollText, Sigma, X,
} from "lucide-react";
import { apiFetch } from "@/app/lib/api";


/**
 * Entry wizard — 3 steps: Declare → Import → Review.
 *
 * Mirrors DoThesis-standalone's `EntryWizard` and the `dothesis-bootstrap`
 * skill at skills/dothesis-bootstrap/SKILL.md. Goal: let the user prime
 * the project's context_store from the moment of creation rather than
 * starting empty and re-typing everything into chat.
 *
 * Flow:
 *   1. Declare: checkbox grid of "what do you already have?" — topic,
 *      references, gaps, model, instrument, data, draft, or none.
 *   2. Import: for each picked item, collect the content (text fields for
 *      topic + prose-shaped fields; uploads come later).
 *   3. Review: show the inferred module status (M1/M2/M3 with done /
 *      needs_review / locked) + Create button.
 *
 * On submit: POST /projects with `name = topic`, then `onCreated` fires
 * with the new project. Caller navigates to the new project's chat; the
 * other declared content rides along as a structured first message so
 * the bootstrap skill can commit each slice on the agent's first turn.
 *
 * The "other content as first message" payload is stashed in
 * `sessionStorage` keyed by project id — the chat surface picks it up
 * on mount and sends it before the user even types. (No new backend
 * route needed.)
 */

type ItemId = "topic" | "references" | "gaps" | "model" | "instrument" | "data" | "draft";

type DeclareItem = {
  id: ItemId;
  label: string;
  hint: string;
  module: string;
  icon: React.ReactNode;
};

const ITEMS: DeclareItem[] = [
  { id: "topic",       label: "Topic",           hint: "Title or research questions", module: "M1", icon: <Lightbulb className="w-4 h-4" /> },
  { id: "references",  label: "References",      hint: "PDFs or DOI list",            module: "M2", icon: <BookOpen className="w-4 h-4" /> },
  { id: "gaps",        label: "Research gaps",   hint: "Already-identified gaps",     module: "M2", icon: <ListChecks className="w-4 h-4" /> },
  { id: "model",       label: "Conceptual model",hint: "Diagram / hypotheses",         module: "M3", icon: <Sigma className="w-4 h-4" /> },
  { id: "instrument",  label: "Instrument",      hint: "Questionnaire / interview",   module: "M3", icon: <ClipboardList className="w-4 h-4" /> },
  { id: "data",        label: "Data",            hint: ".sav · .csv · transcripts",   module: "M4", icon: <FileText className="w-4 h-4" /> },
  { id: "draft",       label: "Draft",           hint: "Partial Word/PDF",            module: "M5", icon: <ScrollText className="w-4 h-4" /> },
];


type Payload = Partial<Record<ItemId, string>>;


export function NewProjectModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (project: { id: string; name: string }) => void;
}) {
  const [step, setStep] = useState(1);
  const [have, setHave] = useState<Set<ItemId>>(new Set(["topic"]));
  const [payload, setPayload] = useState<Payload>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset state every time the modal opens.
  useEffect(() => {
    if (open) {
      setStep(1);
      setHave(new Set(["topic"]));
      setPayload({});
      setError(null);
      setSubmitting(false);
    }
  }, [open]);

  if (!open) return null;

  const toggle = (id: ItemId) => {
    setHave(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      // Drop the payload for items that get un-checked.
      if (!next.has(id)) {
        setPayload(p => { const { [id]: _, ...rest } = p; return rest; });
      }
      return next;
    });
  };

  const inferredStatus = computeStatus(have);
  const topic = (payload.topic ?? "").trim();
  const canFinish = have.has("topic") ? topic.length >= 3 : have.size > 0;

  const finish = async () => {
    setError(null);
    setSubmitting(true);
    try {
      // Project name = topic if declared; otherwise a generic fallback the
      // user can rename from the chat header later.
      const name = topic || "Untitled thesis";
      const project = await apiFetch("/projects", {
        method: "POST",
        body: { name },
      });
      // Stash the rest of the declared content so the chat surface can
      // send it as the bootstrap first message once the project loads.
      // Tied to the new project id so a second wizard run on another
      // project doesn't pick up the wrong payload.
      stashBootstrapPayload((project as { id: string }).id, have, payload);
      onCreated(project as { id: string; name: string });
    } catch (e: any) {
      setError(e?.message || "Could not create project.");
      setSubmitting(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-900/45 backdrop-blur-sm flex items-center justify-center p-6"
      onClick={onClose}
    >
      <div
        onClick={e => e.stopPropagation()}
        className="bg-white rounded-3xl shadow-xl w-full max-w-[920px] max-h-[90vh] flex flex-col overflow-hidden"
        role="dialog"
        aria-modal="true"
        aria-labelledby="entry-wizard-title"
      >
        {/* Header — DoThesis brand mark + title + stepper + close */}
        <div className="px-7 pt-5 pb-4 border-b border-ink-200 flex items-center gap-3">
          <span
            className="w-9 h-9 rounded-[10px] inline-flex items-center justify-center text-white font-extrabold font-serif text-[18px]"
            style={{ background: "linear-gradient(135deg, #2540FF 0%, #6A4DE0 100%)" }}
          >
            D
          </span>
          <div>
            <div id="entry-wizard-title" className="text-[16px] font-extrabold text-ink-900">
              Bootstrap your thesis
            </div>
            <div className="text-[12px] text-ink-500">
              One-time bootstrap — then it's one chat thread
            </div>
          </div>
          <div className="flex-1" />
          <Stepper step={step} />
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="w-8 h-8 rounded-full text-ink-500 hover:bg-ink-100 hover:text-ink-900 inline-flex items-center justify-center"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Step body */}
        <div className="flex-1 overflow-y-auto">
          {step === 1 && <StepDeclare have={have} toggle={toggle} />}
          {step === 2 && (
            <StepImport
              items={ITEMS.filter(i => have.has(i.id))}
              payload={payload}
              setPayload={setPayload}
            />
          )}
          {step === 3 && <StepReview have={have} inferred={inferredStatus} />}
        </div>

        {/* Footer */}
        <div className="px-7 py-3.5 border-t border-ink-200 bg-ink-50 flex items-center gap-3">
          <span className="text-[12px] text-ink-500">
            {step === 1 && `${have.size} declared — you can add the rest anytime`}
            {step === 2 && "Fill in what you already have; uploads come later in chat"}
            {step === 3 && "Same propagation rule as a mid-chat mutate — applied at intake"}
          </span>
          {error && <span className="text-[12px] text-red-700 font-semibold">{error}</span>}
          <span className="flex-1" />
          {step > 1 && (
            <button
              type="button"
              onClick={() => setStep(step - 1)}
              disabled={submitting}
              className="px-3.5 py-1.5 rounded-full text-[13px] font-semibold text-ink-700 hover:bg-ink-100"
            >
              ← Back
            </button>
          )}
          {step < 3 ? (
            <button
              type="button"
              onClick={() => setStep(step + 1)}
              disabled={step === 1 && have.size === 0}
              className="px-4 py-2 rounded-full text-[13px] font-semibold bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
            >
              Continue →
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void finish()}
              disabled={submitting || !canFinish}
              className="px-4 py-2 rounded-full text-[13px] font-semibold bg-primary-600 text-white hover:bg-primary-700 disabled:opacity-50"
            >
              {submitting ? "Creating…" : "Drop into chat →"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}


function Stepper({ step }: { step: number }) {
  const labels = ["Declare", "Import", "Review"];
  return (
    <div className="flex items-center gap-2">
      {labels.map((l, i) => {
        const n = i + 1;
        const active = step === n;
        const done = step > n;
        return (
          <div key={l} className="flex items-center gap-2">
            <div className="flex items-center gap-1.5">
              <span
                className={`w-[22px] h-[22px] rounded-full text-white inline-flex items-center justify-center text-[11px] font-extrabold ${
                  done ? "bg-emerald-600" : active ? "bg-primary-600" : "bg-ink-200"
                }`}
              >
                {done ? "✓" : n}
              </span>
              <span
                className={`text-[12.5px] ${
                  active || done ? "font-bold text-ink-900" : "font-medium text-ink-500"
                }`}
              >
                {l}
              </span>
            </div>
            {i < 2 && <span className="w-[18px] h-px bg-ink-200" />}
          </div>
        );
      })}
    </div>
  );
}


// --- Step 1: Declare ---

function StepDeclare({
  have, toggle,
}: {
  have: Set<ItemId>;
  toggle: (id: ItemId) => void;
}) {
  return (
    <div className="px-7 py-6">
      <div className="text-[20px] font-extrabold tracking-[-0.01em] text-ink-900">
        What do you already have?
      </div>
      <div className="text-[13.5px] text-ink-600 mt-1 mb-4">
        Tick everything you're bringing — we'll use the same parsers each module uses,
        not a separate import stack.
      </div>
      <div className="grid grid-cols-2 gap-2.5">
        {ITEMS.map(it => {
          const on = have.has(it.id);
          return (
            <button
              key={it.id}
              type="button"
              onClick={() => toggle(it.id)}
              className={`flex items-start gap-3 text-left p-3.5 rounded-2xl transition-all ${
                on
                  ? "bg-primary-50 border-[2px] border-primary-600"
                  : "bg-white border border-ink-200 hover:border-ink-300"
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
          );
        })}
      </div>
      <div className="mt-4 px-3.5 py-3 rounded-xl bg-ink-50 border border-dashed border-ink-300 flex items-center gap-2.5 text-[12.5px] text-ink-600">
        <span className="text-[16px]">ℹ</span>
        <span>
          You can also start empty and let me drive. Module locks are recommendations,
          never walls.
        </span>
      </div>
    </div>
  );
}


// --- Step 2: Import ---

function StepImport({
  items, payload, setPayload,
}: {
  items: DeclareItem[];
  payload: Payload;
  setPayload: React.Dispatch<React.SetStateAction<Payload>>;
}) {
  return (
    <div className="px-7 py-6">
      <div className="text-[20px] font-extrabold tracking-[-0.01em] text-ink-900">
        Tell me about each item
      </div>
      <div className="text-[13.5px] text-ink-600 mt-1 mb-4">
        Type or paste what you have. The agent's bootstrap skill commits each to the
        right slice once we drop into chat. Uploads (PDFs, .sav) happen there too.
      </div>
      <div className="flex flex-col gap-3">
        {items.map(it => (
          <ImportRow
            key={it.id}
            item={it}
            value={payload[it.id] ?? ""}
            onChange={v => setPayload(p => ({ ...p, [it.id]: v }))}
          />
        ))}
      </div>
    </div>
  );
}


function ImportRow({
  item, value, onChange,
}: {
  item: DeclareItem;
  value: string;
  onChange: (v: string) => void;
}) {
  const isTopic = item.id === "topic";
  return (
    <div className="flex items-start gap-3.5 p-3.5 rounded-2xl border border-ink-200 bg-white">
      <span className="w-[38px] h-[38px] rounded-[10px] bg-ink-50 text-ink-700 inline-flex items-center justify-center shrink-0">
        {item.icon}
      </span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <div className="text-[13.5px] font-bold text-ink-900">{item.label}</div>
          <span className="text-[10.5px] uppercase tracking-[0.04em] font-bold text-primary-700 bg-primary-50 px-1.5 py-0.5 rounded-md">
            {item.module}
          </span>
        </div>
        <div className="text-[11.5px] text-ink-500 mt-0.5">{item.hint}</div>
        {isTopic ? (
          <input
            type="text"
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder="e.g. Gen Z TikTok livestream buying in Hà Nội"
            className="mt-2.5 w-full rounded-[10px] border border-ink-300 px-3 py-2 text-[13.5px] focus:outline-none focus:border-primary-500"
          />
        ) : (
          <textarea
            value={value}
            onChange={e => onChange(e.target.value)}
            placeholder={importPlaceholder(item.id)}
            rows={3}
            className="mt-2.5 w-full rounded-[10px] border border-ink-300 px-3 py-2 text-[13px] focus:outline-none focus:border-primary-500 resize-y leading-relaxed"
          />
        )}
      </div>
    </div>
  );
}

function importPlaceholder(id: ItemId): string {
  switch (id) {
    case "references": return "Paste DOIs or a reference list, one per line. Or just describe what you've read so far.";
    case "gaps":       return "Describe the gaps in the literature you've already spotted. The agent can refine them.";
    case "model":      return "Describe the conceptual model — constructs, paths, hypotheses. Free-form prose is fine.";
    case "instrument": return "Paste the questionnaire / interview guide, or describe its structure.";
    case "data":       return "Describe the dataset — what's measured, what tool produced it, sample size.";
    case "draft":      return "Paste an outline or describe how much of the thesis is written.";
    default:           return "";
  }
}


// --- Step 3: Review ---

type StatusLite = "done" | "needs_review" | "locked";

function StepReview({
  have, inferred,
}: {
  have: Set<ItemId>;
  inferred: Record<string, StatusLite>;
}) {
  return (
    <div className="px-7 py-6">
      <div className="text-[20px] font-extrabold tracking-[-0.01em] text-ink-900">
        Reconciling dependencies
      </div>
      <div className="text-[13.5px] text-ink-600 mt-1 mb-4">
        Same propagation rule as a mid-chat mutate — applied at intake.
      </div>

      <div className="grid grid-cols-5 gap-2.5 mb-4">
        {(["M1", "M2", "M3", "M4", "M5"] as const).map(id => {
          const s = inferred[id];
          return (
            <div
              key={id}
              className={`p-3 rounded-xl text-center border ${
                s === "done"
                  ? "bg-emerald-50 border-emerald-200"
                  : s === "needs_review"
                    ? "bg-amber-50 border-amber-200"
                    : "bg-ink-50 border-ink-200"
              }`}
            >
              <div
                className={`font-serif font-extrabold text-[13px] ${
                  s === "done" ? "text-emerald-700"
                    : s === "needs_review" ? "text-amber-700"
                    : "text-ink-500"
                }`}
              >
                {id}
              </div>
              <div className="text-[12px] font-semibold text-ink-800 mt-1">
                {MODULE_NICK[id]}
              </div>
              <div className="text-[10.5px] text-ink-500 mt-1">
                {s === "done" ? "✓ Imported" : s === "needs_review" ? "⚠ Gap" : "○ Soft lock"}
              </div>
            </div>
          );
        })}
      </div>

      {flagsForReview(have).length > 0 && (
        <div className="px-4 py-3.5 rounded-2xl bg-amber-50 border border-amber-200">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[16px]">⚠</span>
            <span className="text-[13.5px] font-bold text-amber-700">
              Dependency hole: {flagsForReview(have).join(", ")}
            </span>
          </div>
          <div className="text-[13.5px] text-ink-800 font-serif leading-relaxed">
            “{reconcileNarrative(have)}”
          </div>
          <div className="text-[11.5px] text-amber-700 font-bold mt-2">
            Entry focus: {flagsForReview(have)[0]} · soft prompt, not enforced
          </div>
        </div>
      )}
    </div>
  );
}


const MODULE_NICK: Record<string, string> = {
  M1: "Topic", M2: "Literature", M3: "Model", M4: "Analysis", M5: "Writing",
};


// --- inference helpers ---

function computeStatus(have: Set<ItemId>): Record<string, StatusLite> {
  // Mirrors the bootstrap skill's status logic. Done when a slice's
  // primary input is declared; needs_review when a downstream slice is
  // declared without its upstream prerequisites; locked otherwise.
  const m1 = have.has("topic") ? "done" : "locked";
  const m2 =
    have.has("gaps") ? "done"
      : have.has("references") ? "needs_review"
      : (have.has("model") || have.has("draft")) ? "needs_review"
      : "locked";
  const m3 =
    have.has("model") ? "done"
      : have.has("instrument") ? "needs_review"
      : have.has("data") ? "needs_review"
      : "locked";
  const m4 = have.has("data") ? "needs_review" : "locked";
  const m5 = have.has("draft") ? "needs_review" : "locked";
  return { M1: m1 as StatusLite, M2: m2 as StatusLite, M3: m3 as StatusLite, M4: m4 as StatusLite, M5: m5 as StatusLite };
}

function flagsForReview(have: Set<ItemId>): string[] {
  const s = computeStatus(have);
  return (["M1", "M2", "M3", "M4", "M5"] as const).filter(m => s[m] === "needs_review");
}

function reconcileNarrative(have: Set<ItemId>): string {
  if (have.has("model") && !have.has("references") && !have.has("gaps")) {
    return "You've got a model but no literature backing the hypotheses yet — build the lit review now so they're grounded, or skip ahead?";
  }
  if (have.has("draft")) {
    return "You have a draft already — let me reconcile any module decisions it references but haven't been committed.";
  }
  if (have.has("data") && !have.has("model")) {
    return "Data without a model — what hypotheses are you testing?";
  }
  return "Some upstream modules need attention before downstream work locks in. I'll prompt as we go.";
}


// --- bootstrap-payload stash ---

const PAYLOAD_KEY_PREFIX = "dothesis_bootstrap_v1:";

function stashBootstrapPayload(projectId: string, have: Set<ItemId>, payload: Payload): void {
  if (typeof window === "undefined") return;
  // Only stash items the user filled in. The shape mirrors the
  // dothesis-bootstrap skill's expected input — keep keys verbatim so the
  // chat layer can drop them straight into a structured first message.
  const data: Payload = {};
  have.forEach(id => {
    const v = (payload[id] ?? "").trim();
    if (v) data[id] = v;
  });
  if (Object.keys(data).length === 0) return;
  try {
    window.sessionStorage.setItem(
      PAYLOAD_KEY_PREFIX + projectId,
      JSON.stringify(data),
    );
  } catch { /* sessionStorage may be unavailable in private modes */ }
}


/**
 * Pull (and clear) the bootstrap payload for a freshly-created project.
 *
 * Exported so the chat surface (ChatPane / project layout) can read it on
 * mount and send a structured first message to the agent before the user
 * types anything. Returns null when there is no stash, so callers can
 * branch trivially: `const seed = readBootstrapPayload(pid); if (seed)
 * void send(formatBootstrapMessage(seed))`.
 */
export function readBootstrapPayload(projectId: string): Payload | null {
  if (typeof window === "undefined") return null;
  const key = PAYLOAD_KEY_PREFIX + projectId;
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    window.sessionStorage.removeItem(key);
    return JSON.parse(raw) as Payload;
  } catch {
    return null;
  }
}

/** Compose the user-message text the chat surface sends as the first
 *  turn — matches the dothesis-bootstrap skill's expected input shape. */
export function formatBootstrapMessage(p: Payload): string {
  const lines: string[] = ["/bootstrap", ""];
  if (p.topic) lines.push(`Topic: ${p.topic}`);
  if (p.references) lines.push(`References:\n${p.references}`);
  if (p.gaps) lines.push(`Gaps:\n${p.gaps}`);
  if (p.model) lines.push(`Model:\n${p.model}`);
  if (p.instrument) lines.push(`Instrument:\n${p.instrument}`);
  if (p.data) lines.push(`Data:\n${p.data}`);
  if (p.draft) lines.push(`Draft:\n${p.draft}`);
  return lines.join("\n\n");
}
