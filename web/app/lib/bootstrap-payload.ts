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

/**
 * What the student came here to do.
 *
 * "assess" is the original (and default) behaviour: classify the uploads into
 * M1–M5 and report where the thesis stands. "humanize" exists because arriving
 * with a finished draft that a supervisor called AI-written is its own entry
 * point, not a variation on the assessment — the student wants a rewrite, and
 * a chip that merely prefills text would have produced an assessment and no
 * rewrite at all.
 *
 * Absent on stashes written before this field existed, so readers must treat
 * `undefined` as "assess".
 */
export type AnalyzeKind = "assess" | "humanize";

export type AnalyzeIntent = {
  kind?: AnalyzeKind;
  /** Optional free-text the user typed in the "or describe it" box. */
  note: string;
  /** Files the user dropped, already uploaded to the project. */
  attachments: AnalyzeAttachment[];
  /**
   * The project's module state was ALREADY seeded server-side, by
   * mid-journey-import + reconstruct, before this stash was written.
   *
   * It changes what the first turn should be. The normal bootstrap turn asks
   * the agent to read the uploads, classify them into M1–M5 and seed the
   * state — all of which just happened, deterministically, and paying an LLM
   * to redo it would hand the student back a worse version of work they can
   * already see on the import card. So a preseeded first turn carries only
   * what the import could not: the sentence the student actually typed.
   */
  preseeded?: boolean;
};

const KEY_PREFIX = "dothesis_analyze_v1:";

export function stashAnalyzeIntent(projectId: string, intent: AnalyzeIntent): void {
  if (typeof window === "undefined") return;
  // Nothing to hand off (blank-start) — don't write a stash, so ChatPane
  // falls through to its normal cold-start empty state.
  if (!intent.note.trim() && intent.attachments.length === 0) return;
  // Preseeded and nothing typed: the import already did the work AND already
  // reported it on the activation card. Firing a turn here would bill the
  // student to be told what is on the screen behind it.
  if (intent.preseeded && !intent.note.trim()) return;
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
export function formatAnalyzeMessage(
  note: string,
  hasFiles: boolean,
  kind: AnalyzeKind = "assess",
  preseeded = false,
): string {
  // State already seeded by the server-side import: send what the student
  // typed, and nothing else.
  //
  // Deliberately NOT "/bootstrap". That prefix's entire job is to read the
  // uploads, classify them into M1–M5 and seed the project — which the import
  // and the backfill already did, from the same files, without an LLM. Re-
  // running it would re-derive the state they can see on the card, and could
  // re-derive it DIFFERENTLY. The student's sentence is the one thing the
  // import genuinely could not act on, so it is the whole message.
  if (preseeded && kind !== "humanize") {
    return note.trim();
  }
  if (kind === "humanize") {
    // Deliberately NOT "/bootstrap". That prefix triggers dothesis-bootstrap,
    // whose whole job is to classify uploads into M1–M5 and report where the
    // thesis stands — an assessment this student did not ask for. Load the
    // humanize skill directly instead (same directive shape the chat skill
    // picker uses, see lib/skills.ts applySkillDirective).
    //
    // Nothing in humanize_prose reads module state — only the language and the
    // saved writing anchor — so seeding a thesis graph here buys the rewrite
    // nothing and bills the student for an inferred one they never requested.
    //
    // The anchor instruction is not optional politeness: dothesis-humanize
    // refuses to run unanchored ("asking a model to write more naturally
    // produces text from the same distribution detectors are trained on"), and
    // the shipped anchor library is empty by design. Without this line the turn
    // dead-ends on `no_anchor` with nothing telling the student why.
    const lines: string[] = [
      "[Use the `dothesis-humanize` skill for this turn — read " +
        "/skills/dothesis-humanize/SKILL.md and follow it.]",
      "",
      hasFiles
        ? "I've uploaded a draft I already finished, but it reads as AI-written. " +
            "Read the files and run the humanize pass on the drafted prose. Don't " +
            "set up thesis modules or assess my research design — I'm here for the " +
            "rewrite, not an assessment. If you don't already have my writing " +
            "anchor, ask me for ~150 words I wrote myself BEFORE rewriting " +
            "anything — do not rewrite from an unanchored pass. Keep every number, " +
            "statistic and citation exactly as it is."
        : "I have a draft that reads as AI-written and I want it rewritten in a more " +
            "human voice. Ask me to paste the passage, and ask for ~150 words I wrote " +
            "myself as the style anchor before rewriting anything.",
    ];
    const trimmedNote = note.trim();
    if (trimmedNote) lines.push(`My own notes:\n${trimmedNote}`);
    return lines.join("\n\n");
  }
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
