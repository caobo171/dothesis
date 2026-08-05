"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";

import { apiFetch } from "@/app/lib/api";
import { useT, useTn } from "@/app/lib/i18n/LocaleProvider";

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
  const t = useT();
  const tn = useTn();

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
        setAnchorMsg(t("tools.humanize.anchorSavedMsg", { count: r.words }));
      } else {
        setAnchorErr(r.detail || t("tools.humanize.anchorSaveFailed"));
      }
    } catch (e) {
      setAnchorErr((e as Error)?.message || t("tools.humanize.anchorSaveFailed"));
    } finally {
      setSavingAnchor(false);
    }
  };

  return (
    <ToolPanel
      title={t("tools.humanize.name")}
      blurb={t("tools.humanize.blurb")}
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
              {m === "passage"
                ? t("tools.humanize.modePassage")
                : t("tools.humanize.modeDocument")}
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
            label={t("tools.humanize.passageLabel")}
            value={text}
            onChange={setText}
            rows={9}
            placeholder={t("tools.humanize.placeholder")}
          />
          <ToolError message={fileError} />
        </div>
        )}

        {mode === "passage" && (
        <div className="rounded-xl border border-ink-200 p-3.5">
          <div className="flex items-center justify-between gap-3 mb-1.5">
            <span className="text-[12px] font-semibold text-ink-700">
              {t("tools.humanize.anchorLabel")}
            </span>
            {saved?.has_anchor && (
              <span className="inline-flex items-center gap-1 text-[11.5px] text-[#3A5740] font-semibold shrink-0">
                <Check className="w-3 h-3" aria-hidden />
                {tn(
                  "tools.humanize.anchorSaved_one",
                  "tools.humanize.anchorSaved_other",
                  saved.words,
                )}
              </span>
            )}
          </div>
          <ToolTextarea
            value={anchor}
            onChange={setAnchor}
            rows={4}
            placeholder={
              saved?.has_anchor
                ? t("tools.humanize.anchorPlaceholderSaved")
                : t("tools.humanize.anchorPlaceholder")
            }
          />
          <div className="mt-2 flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              onClick={() => void saveAnchor()}
              disabled={savingAnchor || anchorWords < 50}
              title={anchorWords < 50 ? t("tools.humanize.anchorTooShort") : undefined}
              className="inline-flex items-center gap-1.5 rounded-full border border-ink-200 px-3.5 py-1.5 text-[12.5px] font-semibold text-ink-700 hover:bg-ink-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {savingAnchor
                ? t("tools.humanize.anchorSaving")
                : saved?.has_anchor
                  ? t("tools.humanize.anchorReplace")
                  : t("tools.humanize.anchorSave")}
            </button>
            <span className="text-[11.5px] text-ink-500">
              {anchorWords === 0
                ? saved?.has_anchor
                  ? t("tools.humanize.anchorWillUse")
                  : t("tools.humanize.anchorRequired")
                : t(
                    anchorWords < 100
                      ? "tools.humanize.anchorCountShort"
                      : "tools.humanize.anchorCountEnough",
                    { count: anchorWords },
                  )}
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
            idleLabel={t("tools.humanize.name")}
            busyLabel={t("tools.humanize.running")}
          />
        </div>
        )}

        {mode === "passage" && <ToolError message={error} />}

        {mode === "passage" && result && !result.ok && (
          <ToolError
            message={
              result.error === "no_anchor"
                ? result.hint || t("tools.humanize.errNoAnchor")
                : result.error === "frozen_violation"
                  ? t("tools.humanize.errFrozen")
                  : result.hint || result.error || t("tools.humanize.errFailed")
            }
          />
        )}

        {mode === "passage" && result?.ok && (
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2 text-[11.5px]">
              <span className="px-2 py-0.5 rounded-full bg-[#EEF4EE] text-[#3A5740] font-semibold">
                {result.changed
                  ? t("tools.humanize.badgeRewritten")
                  : t("tools.humanize.badgeNoChange")}
              </span>
              {result.frozen_ok && (
                <span className="px-2 py-0.5 rounded-full bg-ink-100 text-ink-700">
                  {t("tools.humanize.badgeVerified")}
                </span>
              )}
              {result.credits_charged > 0 && (
                <span className="text-ink-500 tabular-nums">
                  {t("tools.credits", { count: result.credits_charged })}
                </span>
              )}
            </div>
            <div className="rounded-xl border border-ink-200 bg-ink-50 p-4 text-[14px] leading-relaxed whitespace-pre-wrap text-ink-900">
              {result.text}
            </div>
          </div>
        )}

        {mode === "passage" && (
        <ToolCaveat>{t("tools.humanize.caveat")}</ToolCaveat>
        )}
      </div>
    </ToolPanel>
  );
}
