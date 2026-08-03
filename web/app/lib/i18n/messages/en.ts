/**
 * English strings — the SOURCE catalogue.
 *
 * `en` defines the key set; vi.ts is typed against it, so a missing Vietnamese
 * translation is a TypeScript error at build time rather than a blank label in
 * front of a student. Add keys here first.
 *
 * Keys are namespaced by view (`new.*`, `sidebar.*`) so a view's strings can be
 * found and migrated together. Values are plain strings — no interpolation
 * engine, because nothing here needs one yet; add {placeholders} only when a
 * real case appears.
 */
export const en = {
  // --- /new — analyze-your-thesis composer ---
  "new.back": "Back to home",
  "new.title": "Analyze your thesis",
  "new.placeholder":
    "Tell me what you have so far — a draft, papers, data, or just an idea.",
  "new.attach": "Attach files",
  "new.analyze": "Analyze",
  "new.analyzing": "Analyzing…",
  "new.cancel": "Cancel",
  "new.dropHint": "Drop files to attach",
  "new.fileTypes": "PDF, Word, or text · multiple files OK",
  "new.remove": "Remove",

  // Starter chips. `.text` is what gets written into the composer — editable,
  // so it is phrased as a student would actually say it, not as a form label.
  "new.chip.draft": "I have a draft",
  "new.chip.draft.text": "I have a draft chapter written, but no literature review yet.",
  "new.chip.data": "I have data",
  "new.chip.data.text":
    "I have survey data ready for SmartPLS, but haven't run the analysis.",
  "new.chip.papers": "I have papers",
  "new.chip.papers.text":
    "I've collected papers for my literature review but haven't synthesised them.",
  // Deliberately phrased as the complaint the student actually receives, not
  // as the feature name — "humanize" is our word, "my supervisor said it reads
  // like ChatGPT" is theirs.
  "new.chip.humanize": "Mine reads like AI",
  "new.chip.humanize.text":
    "I've finished writing, but my supervisor says it reads like ChatGPT — " +
    "I want it rewritten in a more human voice without changing any numbers.",
  "new.chip.fresh": "Starting fresh",
  "new.chip.fresh.text": "I'm just starting — I have a topic idea but nothing written yet.",

  // --- project sidebar ---
  "sidebar.projectCredits": "Project credits",
  "sidebar.threads": "Threads",
  "sidebar.newThread": "New thread",
  "sidebar.project": "Project",

  // --- language switcher ---
  "lang.label": "Language",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
} as const;

export type MessageKey = keyof typeof en;
