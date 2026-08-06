"use client";

/**
 * ReconstructedModulesWidget — in-chat wrapper around the shared
 * ReconstructedModules card. Emitted by the backfill_upstream_modules tool.
 *
 * Presentational only. The tool commits each reconstruction through the store
 * as it produces it, so there is nothing for this widget to post: it reports
 * what landed. That's deliberate — the headless and partner-API surfaces run
 * the same tool with no widget mounted, and a save that lived in a click
 * handler here would simply never happen for them.
 */
import {
  ReconstructedModules,
  type ReconstructedModule,
  type SavedModule,
} from "../ReconstructedModules";
import type { ReconstructedModulesHint } from "./types";

export function ReconstructedModulesWidget({
  hint,
}: {
  hint: ReconstructedModulesHint;
}) {
  return (
    <ReconstructedModules
      items={hint.items as ReconstructedModule[]}
      saved={(hint.saved ?? []) as SavedModule[]}
    />
  );
}
