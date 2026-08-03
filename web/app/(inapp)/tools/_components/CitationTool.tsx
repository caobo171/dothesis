"use client";

import { useState } from "react";
import { CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { useTool } from "./use-tool";
import {
  ToolPanel, ToolTextarea, RunButton, ToolError, ToolCaveat, FileDrop,
} from "./shell";

type CitationOut = {
  ok: boolean;
  found: boolean;
  doi: string | null;
  title: string | null;
  authors: string | null;
  year: number | null;
  container: string | null;
  url: string | null;
  matched_by: string | null;
  warning: string | null;
  detail: string | null;
};

export function CitationTool() {
  const [reference, setReference] = useState("");
  const [fileBusy, setFileBusy] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { result, error, busy, run } = useTool<CitationOut>("/tools/verify-citation");

  // Three outcomes, not two. A DOI lookup is exact; a bibliographic search is
  // fuzzy — CrossRef returns its best match for ANY query, so a hit means
  // "something like this exists", not "this reference is real". Collapsing that
  // into a green tick is how a student keeps a fabricated source.
  const exact = result?.found && result.matched_by === "doi";

  return (
    <ToolPanel
      title="Citation check"
      blurb="Check a reference against CrossRef — does this source actually exist? Paste a DOI, a URL, or the whole formatted reference; it works out which it is."
    >
      <div className="flex flex-col gap-4">
        {/* A reference list usually arrives as part of a document, so the same
            attach control applies — extract, then trim to the one entry. */}
        <FileDrop
          onText={setReference}
          busy={fileBusy}
          setBusy={setFileBusy}
          onError={setFileError}
          hint="PDF, Word or text"
        />
        <ToolError message={fileError} />
        <ToolTextarea
          label="Reference"
          value={reference}
          onChange={setReference}
          rows={3}
          placeholder="10.1016/j.chb.2021.106789  ·  or  ·  Nguyen, T. (2021). Title of the paper. Journal Name."
        />

        <div>
          <RunButton
            busy={busy}
            disabled={reference.trim().length < 3 || fileBusy}
            onClick={() => void run({ reference })}
            idleLabel="Check"
            busyLabel="Checking…"
          />
        </div>

        <ToolError message={error} />

        {result && !result.ok && (
          <ToolError
            message={
              result.detail ||
              "CrossRef could not be reached, so this reference was NOT checked — that is not the same as it being fake."
            }
          />
        )}

        {result?.ok && (
          <div className="rounded-xl border border-ink-200 bg-ink-50 p-4">
            <div className="flex items-start gap-2.5">
              {!result.found ? (
                <XCircle className="w-5 h-5 text-[#8E6B2A] shrink-0 mt-px" aria-hidden />
              ) : exact ? (
                <CheckCircle2 className="w-5 h-5 text-[#3A5740] shrink-0 mt-px" aria-hidden />
              ) : (
                <HelpCircle className="w-5 h-5 text-ink-500 shrink-0 mt-px" aria-hidden />
              )}
              <div className="min-w-0">
                <div className="text-[14px] font-bold text-ink-900">
                  {!result.found
                    ? "No match found"
                    : exact
                      ? "Confirmed — exact DOI match"
                      : "Probable match (fuzzy search, not proof)"}
                </div>
                {result.found && (
                  <div className="mt-1.5 text-[13px] text-ink-800 leading-relaxed">
                    {result.title && <div className="font-medium">{result.title}</div>}
                    <div className="text-ink-600 mt-0.5">
                      {[result.authors, result.year, result.container]
                        .filter(Boolean)
                        .join(" · ")}
                    </div>
                    {result.doi && (
                      <a
                        href={`https://doi.org/${result.doi}`}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="inline-block mt-1.5 text-[12.5px] text-primary-600 underline"
                      >
                        doi.org/{result.doi}
                      </a>
                    )}
                  </div>
                )}
                {result.warning && (
                  <p className="mt-2 mb-0 text-[12px] text-[#6E5121]">{result.warning}</p>
                )}
              </div>
            </div>
          </div>
        )}

        <ToolCaveat>
          A DOI is an exact lookup and the answer is definitive. Without one this
          falls back to a bibliographic search, which is fuzzy — CrossRef returns
          its best match for any query, so a hit is evidence something similar
          exists, not proof this reference is real. Check the title and authors
          against what you cited.
        </ToolCaveat>
      </div>
    </ToolPanel>
  );
}
