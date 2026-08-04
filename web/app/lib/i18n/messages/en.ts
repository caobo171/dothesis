/**
 * English strings — the SOURCE catalogue.
 *
 * `en` defines the key set; vi.ts is typed against it, so a missing Vietnamese
 * translation is a TypeScript error at build time rather than a blank label in
 * front of a student. Add keys here first.
 *
 * Keys are namespaced by view (`new.*`, `sidebar.*`) so a view's strings can be
 * found and migrated together.
 *
 * `{placeholders}` are filled by t(key, params) — keep the variable INSIDE the
 * string rather than concatenating at the call site, so each locale can place
 * it where its grammar wants it.
 *
 * Counted nouns come in `_one` / `_other` pairs selected by tn(). Vietnamese
 * does not inflect for number, so its two entries are identical BY DESIGN —
 * that is not a copy-paste slip.
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
  "sidebar.loading": "Loading…",
  "sidebar.archived": "Archived",
  "sidebar.noThreads": "No threads yet — start one.",

  // --- module names — shared vocabulary, used by the dashboard, the chat
  // header and the theses list, so they live here rather than in any one of
  // them. Keyed by module id so a consumer translates from `m.labelKey`.
  "module.M1": "Topic Discovery",
  "module.M2": "Literature Review",
  "module.M3": "Research Design",
  "module.M4": "Data Analysis",
  "module.M5": "Writing",

  // --- home dashboard ---
  "home.greeting.morning": "Good morning",
  "home.greeting.afternoon": "Good afternoon",
  "home.greeting.evening": "Good evening",
  "home.hello": "Hello, {name} —",
  "home.resumePrompt": "pick up where you left off?",
  "home.startPrompt": "ready to start your thesis?",
  "home.blurb":
    "Five modules from topic to final draft — one chat thread, your sources, page-cited.",
  "home.inModule": "You're in {module} · {label} on “{name}” — resume to keep going.",
  "home.resume": "Resume current thesis",
  "home.startNew": "Start a new thesis",
  "home.credits": "Credit balance",
  "home.creditsUnit": "credits",
  "home.topUp": "+ Top up",

  "home.stat.active": "Active theses",
  "home.stat.activeSub": "across your account",
  "home.stat.done": "Modules completed",
  "home.stat.doneSub": "of 5 per thesis",
  "home.stat.progress": "In progress",
  "home.stat.progressSub": "modules being worked",
  "home.stat.review": "Needs review",
  "home.stat.reviewOpen": "open ⚠ flags",
  "home.stat.reviewClear": "all clear",

  "home.theses": "Your theses",
  "home.thesesCount_one": "{count} active",
  "home.thesesCount_other": "{count} active",
  "home.reviewCount_one": "{count} needs review",
  "home.reviewCount_other": "{count} need review",
  "home.newThesis": "New thesis",
  "home.empty": "No projects yet. Click the New thesis button to get started.",
  "home.noField": "No field set",
  "home.next": "Next",
  "home.continue": "Continue {module}",
  "home.lastTouched": "last touched {when}",
  "home.recent": "Recent activity",
  "home.flaggedIn": "Flagged for review in",
  "home.workingIn": "Working in",
  "home.needsReview": "Needs review",
  "home.proTip": "Pro tip",
  "home.proTipBody":
    "You can ask about any module from any other — focus only shifts on an edit, not a read.",

  // Relative time. Short forms stay untranslated-looking on purpose (10m, 3h)
  // because Vietnamese students read those abbreviations as-is.
  "time.justNow": "just now",
  "time.minutes": "{n}m ago",
  "time.hours": "{n}h ago",
  "time.days": "{n}d ago",
  "time.weeks": "{n}w ago",

  // --- workspace load failures ---
  "ws.gone.title": "This thesis no longer exists",
  "ws.gone.body": "It was deleted, or this link points at a project from another workspace.",
  "ws.forbidden.title": "You don’t have access to this thesis",
  "ws.forbidden.body":
    "It belongs to a different account. Check which account you’re signed in as.",
  "ws.failed.title": "Couldn’t load this thesis",
  "ws.failed.body": "The server didn’t respond as expected. Try again in a moment.",
  "ws.back": "Back to your theses",
  "ws.retry": "Retry",
  "ws.threadsFailed": "Couldn’t load threads.",
  "ws.threadGone.title": "This thread no longer exists",
  "ws.threadGone.body":
    "It was deleted, or the link is out of date. Pick another thread from the left rail.",
  "ws.threadFailed.title": "Couldn’t load this thread",
  "ws.threadFailed.body": "Try again in a moment.",
  "ws.threadsEmpty": "No threads in this thesis yet — start one from the left rail.",
  "ws.loadingThread": "Loading thread…",
  "ws.projectThreadsFailed": "Couldn’t load this project’s threads.",

  // --- language switcher ---
  "lang.label": "Language",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
} as const;

export type MessageKey = keyof typeof en;
