"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { useTool } from "./use-tool";
import { HumanizeDocument } from "./HumanizeDocument";
import {
  ToolPanel, ToolTextarea, RunButton, ToolError, ToolCaveat, FileDrop,
} from "./shell";

type HumanizeOut = {
  ok: boolean;
  text: string;
  changed: boolean;
  error: string | null;
  hint: string | null;
  anchor: string | null;
  frozen_ok: boolean | null;
  score: number | null;
  rounds: number | null;
  credits_charged: number;
};

type AnchorOut = {
  ok: boolean;
  has_anchor: boolean;
  words: number;
  preview: string | null;
  error: string | null;
  detail: string | null;
};

export function HumanizeTool() {
  // Two ways in, because they fail differently. A passage is paste-and-go; a
  // whole document has to keep its headings, tables and numbering, which is
  // impossible once it has been flattened to text.
  const [mode, setMode] = useState<"passage" | "document">("passage");
  const [text, setText] = useState("");
  const [anchor, setAnchor] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { result, error, busy, run } = useTool<HumanizeOut>("/humanize");

  // Saved-anchor state. Loaded on mount so a student who supplied their sample
  // weeks ago isn't asked for ~150 words again — the pass falls back to the
  // stored anchor server-side, and the UI should say so rather than look
  // broken-but-working.
  const [saved, setSaved] = useState<AnchorOut | null>(null);
  const [savingAnchor, setSavingAnchor] = useState(false);
  const [anchorMsg, setAnchorMsg] = useState<string | null>(null);
  const [anchorErr, setAnchorErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setSaved((await apiFetch("/tools/writing-anchor", { method: "POST" })) as AnchorOut);
      } catch {
        /* non-critical: the box just asks for a sample as before */
      }
    })();
  }, []);

  const anchorWords = anchor.trim() ? anchor.trim().split(/\s+/).length : 0;

  // Saving is its OWN action, not a side effect of a successful rewrite. It was
  // the latter, which meant the sample the feature refuses to run without could
  // only be stored by first paying for a rewrite — and a rewrite that failed
  // verification threw the sample away with it.
  const saveAnchor = async () => {
    setSavingAnchor(true);
    setAnchorMsg(null);
    setAnchorErr(null);
    try {
      const r = (await apiFetch("/tools/writing-anchor/save", {
        method: "POST",
        body: { anchor },
      })) as AnchorOut;
      if (r.ok) {
        setSaved(r);
        setAnchorMsg(`Saved — ${r.words} words. Future rewrites will use this automatically.`);
      } else {
        setAnchorErr(r.detail || "Could not save that sample.");
      }
    } catch (e) {
      setAnchorErr((e as Error)?.message || "Could not save that sample.");
    } finally {
      setSavingAnchor(false);
    }
  };

  return (
    <ToolPanel
      title="Humanize"
      blurb="Re-voice prose you already wrote so it stops reading as AI-generated. It changes how the text sounds, never what it says — every number, statistic and citation is frozen and verified afterwards."
    >
      <div className="flex flex-col gap-4">
        <div className="inline-flex self-start rounded-full border border-ink-200 p-0.5 bg-white">
          {(["passage", "document"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMode(m)}
              aria-pressed={mode === m}
              className={`px-3.5 py-1.5 rounded-full text-[12.5px] font-semibold transition-colors ${
                mode === m ? "bg-primary-600 text-white" : "text-ink-600 hover:text-ink-900"
              }`}
            >
              {m === "passage" ? "A passage" : "Whole document (.docx)"}
            </button>
          ))}
        </div>

        {mode === "document" && <HumanizeDocument />}

        {mode === "passage" && (
        <div className="flex flex-col gap-2">
          <FileDrop
            onText={setText}
            busy={fileBusy}
            setBusy={setFileBusy}
            onError={setFileError}
          />
          <ToolTextarea
            label="Your passage"
            value={text}
            onChange={setText}
            rows={9}
            placeholder="Dán đoạn văn bạn muốn viết lại — hoặc đính kèm tệp ở trên."
          />
          <ToolError message={fileError} />
        </div>
        )}

        {mode === "passage" && (
        <div className="rounded-xl border border-ink-200 p-3.5">
          <div className="flex items-center justify-between gap-3 mb-1.5">
            <span className="text-[12px] font-semibold text-ink-700">
              Your own writing (style anchor)
            </span>
            {saved?.has_anchor && (
              <span className="inline-flex items-center gap-1 text-[11.5px] text-[#3A5740] font-semibold shrink-0">
                <Check className="w-3 h-3" aria-hidden />
                {saved.words} words saved
              </span>
            )}
          </div>
          <ToolTextarea
            value={anchor}
            onChange={setAnchor}
            rows={4}
            placeholder={
              saved?.has_anchor
                ? "Using your saved sample. Paste new writing here only if you want to replace it."
                : "~150 words you wrote yourself, before using AI — an old essay, a report, anything."
            }
          />
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => void saveAnchor()}
              disabled={savingAnchor || anchorWords < 50}
              title={anchorWords < 50 ? "Needs ~150 words to carry any rhythm" : undefined}
              className="inline-flex items-center gap-1.5 rounded-full border border-ink-200 px-3.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {savingAnchor ? "Saving…" : saved?.has_anchor ? "Replace saved sample" : "Save style anchor"}
            </button>
            <span className="text-[11.5px] text-ink-500">
              {anchorWords === 0
                ? saved?.has_anchor
                  ? "Saved sample will be used."
                  : "Required — the rewrite is anchored on real human writing."
                : `${anchorWords} words${anchorWords < 100 ? " — aim for ~150." : " — that's enough."}`}
            </span>
          </div>
          {anchorMsg && (
            <div className="mt-2 text-[12px] text-[#3A5740]">{anchorMsg}</div>
          )}
          <ToolError message={anchorErr} />
        </div>
        )}

        {mode === "passage" && (
        <div>
          <RunButton
            busy={busy}
            disabled={!text.trim() || fileBusy}
            onClick={() => void run({ text, user_anchor: anchor.trim() || null, language: "vi" })}
            idleLabel="Humanize"
            busyLabel="Rewriting…"
          />
        </div>
        )}

        {mode === "passage" && <ToolError message={error} />}

        {mode === "passage" && result && !result.ok && (
          <ToolError
            message={
              result.error === "no_anchor"
                ? result.hint || "Add ~150 words of your own writing above, then run it again."
                : result.error === "frozen_violation"
                  ? "The rewrite would have altered a number or citation, so your original was kept unchanged."
                  : result.hint || result.error || "The rewrite did not complete."
            }
          />
        )}

        {mode === "passage" && result?.ok && (
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2 text-[11.5px]">
              <span className="px-2 py-0.5 rounded-full bg-[#EEF4EE] text-[#3A5740] font-semibold">
                {result.changed ? "Rewritten" : "No change needed"}
              </span>
              {result.frozen_ok && (
                <span className="px-2 py-0.5 rounded-full bg-ink-100 text-ink-700">
                  numbers &amp; citations verified
                </span>
              )}
              {result.credits_charged > 0 && (
                <span className="text-ink-500 tabular-nums">
                  {result.credits_charged} credits
                </span>
              )}
            </div>
            <div className="rounded-xl border border-ink-200 bg-ink-50 p-4 text-[14px] leading-relaxed whitespace-pre-wrap text-ink-900">
              {result.text}
            </div>
          </div>
        )}

        {mode === "passage" && (
        <ToolCaveat>
          A rewrite that would have changed any number, statistic or citation is
          discarded and your original returned — this can never quietly alter a
          finding. It also makes no claim about what an AI detector will say.
        </ToolCaveat>
        )}
      </div>
    </ToolPanel>
  );
}
