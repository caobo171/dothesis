"use client";

import { useState } from "react";

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
function bandLabel(score: number): string {
  if (score >= 0.7) return "Very even — sentences land at near-identical lengths";
  if (score >= 0.45) return "Fairly even";
  if (score >= 0.25) return "Some variation";
  return "Bursty — reads like natural human rhythm";
}

export function RhythmTool() {
  const [text, setText] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { result, error, busy, run } = useTool<RhythmOut>("/tools/writing-rhythm");

  return (
    <ToolPanel
      title="Writing rhythm"
      blurb="Measures how mechanical your sentence rhythm is — variation in sentence length, and how often paragraphs open with the same connectors. Concrete writing feedback, the kind a supervisor gives."
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
          label="Passage (3+ sentences)"
          value={text}
          onChange={setText}
          rows={8}
          placeholder="Dán một đoạn — cần ít nhất 3 câu để đo được nhịp văn."
        />

        <div>
          <RunButton
            busy={busy}
            disabled={!text.trim() || fileBusy}
            onClick={() => void run({ text })}
            idleLabel="Measure"
            busyLabel="Measuring…"
          />
        </div>

        <ToolError message={error} />

        {result && !result.ok && (
          <ToolError message={result.detail || "Not enough text to measure a rhythm."} />
        )}

        {result?.ok && typeof result.score === "number" && (
          <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
            <div className="flex items-baseline gap-3">
              <span className="text-[34px] font-extrabold tracking-tight tabular-nums text-ink-900">
                {result.score.toFixed(2)}
              </span>
              <span className="text-[13px] text-ink-600">{bandLabel(result.score)}</span>
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
              <span>0 · varied</span>
              <span>1 · metronome</span>
            </div>
            {result.detail && (
              <p className="mt-3 mb-0 text-[12.5px] text-ink-700 leading-relaxed">{result.detail}</p>
            )}
          </div>
        )}

        <ToolCaveat>
          <strong>This is not an AI detector.</strong> It measures sentence-length
          variation and connector density — it cannot see perplexity, which is
          roughly half of what real detectors use. It does not predict Turnitin,
          GPTZero or any commercial tool, and a low number is not a pass. Use it
          as writing feedback: if your sentences are all the same length, vary
          them.
        </ToolCaveat>
      </div>
    </ToolPanel>
  );
}
