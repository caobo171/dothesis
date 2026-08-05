"use client";

import { useState } from "react";

import { useT } from "@/app/lib/i18n/LocaleProvider";
import type { MessageKey } from "@/app/lib/i18n/messages/en";

import { useTool } from "./use-tool";
import {
  ToolPanel, ToolTextarea, RunButton, ToolError, ToolCaveat, FileDrop,
} from "./shell";

type RhythmOut = {
  ok: boolean;
  score: number | null;
  verdict: string;
  basis: string;
  detail: string | null;
};

// Deliberately NOT a red/green scale. Colouring "0.8" red would read as a
// verdict — "you failed" — which is precisely the claim this tool cannot make.
// A neutral ink ramp says "here is a measurement" instead.
// Returns a key rather than a string so the band is translated at render.
function bandKey(score: number): MessageKey {
  if (score >= 0.7) return "tools.rhythm.band.veryEven";
  if (score >= 0.45) return "tools.rhythm.band.fairlyEven";
  if (score >= 0.25) return "tools.rhythm.band.someVariation";
  return "tools.rhythm.band.bursty";
}

export function RhythmTool() {
  const [text, setText] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { result, error, busy, run } = useTool<RhythmOut>("/tools/writing-rhythm");
  const t = useT();

  return (
    <ToolPanel
      title={t("tools.rhythm.name")}
      blurb={t("tools.rhythm.blurb")}
    >
      <div className="flex flex-col gap-4">
        <FileDrop
          onText={setText}
          busy={fileBusy}
          setBusy={setFileBusy}
          onError={setFileError}
        />
        <ToolError message={fileError} />
        <ToolTextarea
          label={t("tools.rhythm.passageLabel")}
          value={text}
          onChange={setText}
          rows={8}
          placeholder={t("tools.rhythm.placeholder")}
        />

        <div>
          <RunButton
            busy={busy}
            disabled={!text.trim() || fileBusy}
            onClick={() => void run({ text })}
            idleLabel={t("tools.rhythm.run")}
            busyLabel={t("tools.rhythm.running")}
          />
        </div>

        <ToolError message={error} />

        {result && !result.ok && (
          <ToolError message={result.detail || t("tools.rhythm.errShort")} />
        )}

        {result?.ok && typeof result.score === "number" && (
          <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
            <div className="flex items-baseline gap-3">
              <span className="text-[34px] font-extrabold tracking-tight tabular-nums text-ink-900">
                {result.score.toFixed(2)}
              </span>
              <span className="text-[13px] text-ink-600">{t(bandKey(result.score))}</span>
            </div>
            {/* 0 = bursty/human-like, 1 = machine-even. Labelled at both ends so
                the number is never read as "percent AI". */}
            <div className="mt-3 h-1.5 rounded-full bg-ink-200 overflow-hidden">
              <div
                className="h-full bg-ink-700"
                style={{ width: `${Math.round(result.score * 100)}%` }}
              />
            </div>
            <div className="flex justify-between mt-1 text-[11px] text-ink-400">
              <span>{t("tools.rhythm.scaleLow")}</span>
              <span>{t("tools.rhythm.scaleHigh")}</span>
            </div>
            {result.detail && (
              <p className="mt-3 mb-0 text-[12.5px] text-ink-700 leading-relaxed">{result.detail}</p>
            )}
          </div>
        )}

        <ToolCaveat>
          <strong>{t("tools.rhythm.caveatLead")}</strong>
          {t("tools.rhythm.caveatBody")}
        </ToolCaveat>
      </div>
    </ToolPanel>
  );
}
