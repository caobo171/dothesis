"use client";

/**
 * ReconstructedModulesWidget — in-chat wrapper around the shared
 * ReconstructedModules card. Emitted by the backfill_upstream_modules tool.
 *
 * Confirm posts the (edited) candidate to the SAME project-scoped endpoint the
 * /new activation card uses (/mid-journey-import/confirm), so the split-write /
 * gating guarantees hold identically. The project id is threaded down from
 * ChatPane (the chat surface is already scoped to one project).
 */
import { useState } from "react";

import { apiFetch } from "@/app/lib/api";
import {
  ReconstructedModules,
  type ReconstructedModule,
} from "../ReconstructedModules";
import type { ReconstructedModulesHint } from "./types";

export function ReconstructedModulesWidget({
  hint,
  projectId,
  disabled,
}: {
  hint: ReconstructedModulesHint;
  projectId?: string;
  disabled?: boolean;
}) {
  const [confirmed, setConfirmed] = useState<string[]>([]);
  const [skipped, setSkipped] = useState<string[]>([]);

  const onConfirm = async (module: string, edited: Record<string, unknown>) => {
    if (!projectId) return;
    await apiFetch(`/projects/${projectId}/mid-journey-import/confirm`, {
      method: "POST",
      body: { module, slice: edited },
    });
    setConfirmed((c) => [...c, module]);
  };

  return (
    <div className={disabled ? "pointer-events-none opacity-60" : undefined}>
      <ReconstructedModules
        items={hint.items as ReconstructedModule[]}
        confirmedModules={confirmed}
        skippedModules={skipped}
        onConfirm={onConfirm}
        onSkip={(m) => setSkipped((s) => [...s, m])}
      />
    </div>
  );
}
