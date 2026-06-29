// Analyze-intent stash — handoff from the drop-first /new page to the chat
// surface. The /new page no longer collects per-module slices; it just takes
// the files the user dropped (already uploaded, project-scoped) plus an
// optional free-text note. We stash that handoff keyed by the freshly-created
// project id; ChatPane reads it on mount and fires ONE bootstrap turn whose
// job is to read the uploads, work out which modules (M1–M5) they cover, seed
// the project state, and report where the thesis stands — the analysis screen.

// Why a stash (sessionStorage) rather than query params: the upload metadata
// is an array of objects, and we don't want file ids sitting in the URL/history.

export type AnalyzeAttachment = {
  upload_id: string;
  filename: string;
  size_bytes: number;
  mime_type?: string;
};

export type AnalyzeIntent = {
  /** Optional free-text the user typed in the "or describe it" box. */
  note: string;
  /** Files the user dropped, already uploaded to the project. */
  attachments: AnalyzeAttachment[];
};

const KEY_PREFIX = "dothesis_analyze_v1:";

export function stashAnalyzeIntent(projectId: string, intent: AnalyzeIntent): void {
  if (typeof window === "undefined") return;
  // Nothing to hand off (blank-start) — don't write a stash, so ChatPane
  // falls through to its normal cold-start empty state.
  if (!intent.note.trim() && intent.attachments.length === 0) return;
  try {
    window.sessionStorage.setItem(KEY_PREFIX + projectId, JSON.stringify(intent));
  } catch {
    /* sessionStorage may be unavailable in private modes */
  }
}

/**
 * Pull (and clear) the analyze intent for a freshly-created project.
 * Called by the chat surface on mount; returns null when there's no stash.
 */
export function readAnalyzeIntent(projectId: string): AnalyzeIntent | null {
  if (typeof window === "undefined") return null;
  const key = KEY_PREFIX + projectId;
  const raw = window.sessionStorage.getItem(key);
  if (!raw) return null;
  try {
    window.sessionStorage.removeItem(key);
    return JSON.parse(raw) as AnalyzeIntent;
  } catch {
    return null;
  }
}

/**
 * Compose the first-turn message. Keeps the `/bootstrap` prefix because the
 * dothesis-bootstrap skill triggers on it (and skips its "what do you have?"
 * question). With the drop-first flow there are no labeled sections any more —
 * the agent has to read the attached files itself and classify them.
 */
export function formatAnalyzeMessage(note: string, hasFiles: boolean): string {
  const lines: string[] = ["/bootstrap", ""];
  if (hasFiles) {
    lines.push(
      "I've uploaded my existing thesis materials. Read every file I attached, " +
        "work out which thesis modules (M1 topic, M2 literature, M3 design, " +
        "M4 statistical analysis, M5 writing) each one covers, seed the project " +
        "state, and tell me where I stand.",
    );
  } else {
    lines.push(
      "Here's a description of my thesis so far. Work out which thesis modules " +
        "(M1 topic, M2 literature, M3 design, M4 statistical analysis, M5 writing) " +
        "it covers, seed the project state, and tell me where I stand.",
    );
  }
  const trimmed = note.trim();
  if (trimmed) lines.push(`My own notes:\n${trimmed}`);
  return lines.join("\n\n");
}
