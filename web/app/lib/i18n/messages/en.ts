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

  // --- app shell: master nav + chrome ---
  // The nav labels are the FIRST thing every signed-in student reads, on every
  // page, so they were the loudest remaining English in the product. They lived
  // as literals in use-sections.ts, which predates this catalogue.
  "nav.workspace": "Workspace",
  "nav.dashboard": "Dashboard",
  "nav.theses": "Theses",
  // No "nav.tools": the three tools are their own menu entries and take their
  // names from the tools.* catalogue below, so a name can never drift between
  // the sidebar and the panel it opens.
  "nav.account": "Account",
  "nav.credit": "Credit",
  "nav.transactions": "Transactions",
  "nav.mcp": "MCP",
  "nav.admin": "Admin",
  "nav.users": "Users",
  "nav.papers": "Papers",
  "nav.jobs": "Jobs",
  "nav.announcements": "Announcements",
  "nav.orders": "Orders",
  "nav.connectors": "Connectors",
  "nav.toolUsage": "Tool usage",

  "shell.tagline": "Draft with conviction",
  "shell.collapse": "Collapse",
  "shell.signOut": "Sign out",
  // Screen-reader-only labels. Translated for the same reason as visible text —
  // a Vietnamese student running a Vietnamese screen reader hears these.
  "shell.openSidebar": "Open sidebar",
  "shell.closeSidebar": "Close sidebar",
  "shell.notifications": "View notifications",
  "shell.userMenu": "Open user menu",

  // --- /tools — standalone jobs, no thesis project ---
  // This page shipped with its labels in English and two of its placeholders
  // already in Vietnamese, so a student saw both languages in one form. Every
  // string it renders lives here now, including the ones thrown as errors from
  // use-tool.ts (those take `t` as an argument — a module-scope helper cannot
  // call a hook).
  "tools.title": "Tools",
  "tools.blurb":
    "One job, one answer — no thesis project needed. For anything that needs to " +
    "know your research, work in a thesis thread instead.",
  "tools.credits": "{count} credits",

  // "Humanize" is kept untranslated in both catalogues: it is the feature's name
  // and the word Vietnamese students already use for this job.
  "tools.humanize.name": "Humanize",
  "tools.humanize.tagline": "Make drafted prose read as human-written",
  "tools.humanize.blurb":
    "Re-voice prose you already wrote so it stops reading as AI-generated. It " +
    "changes how the text sounds, never what it says — every number, statistic " +
    "and citation is frozen and verified afterwards.",
  "tools.humanize.modePassage": "A passage",
  "tools.humanize.modeDocument": "Whole document (.docx)",
  "tools.humanize.passageLabel": "Your passage",
  "tools.humanize.placeholder":
    "Paste the passage you want rewritten — or attach a file above.",
  "tools.humanize.anchorLabel": "Your own writing (style anchor)",
  "tools.humanize.anchorSaved_one": "{count} word saved",
  "tools.humanize.anchorSaved_other": "{count} words saved",
  "tools.humanize.anchorPlaceholderSaved":
    "Using your saved sample. Paste new writing here only if you want to replace it.",
  "tools.humanize.anchorPlaceholder":
    "~150 words you wrote yourself, before using AI — an old essay, a report, anything.",
  "tools.humanize.anchorTooShort": "Needs ~150 words to carry any rhythm",
  "tools.humanize.anchorSaving": "Saving…",
  "tools.humanize.anchorReplace": "Replace saved sample",
  "tools.humanize.anchorSave": "Save style anchor",
  "tools.humanize.anchorWillUse": "Saved sample will be used.",
  "tools.humanize.anchorRequired":
    "Required — the rewrite is anchored on real human writing.",
  "tools.humanize.anchorCountShort": "{count} words — aim for ~150.",
  "tools.humanize.anchorCountEnough": "{count} words — that’s enough.",
  "tools.humanize.anchorSavedMsg":
    "Saved — {count} words. Future rewrites will use this automatically.",
  "tools.humanize.anchorSaveFailed": "Could not save that sample.",
  "tools.humanize.running": "Rewriting…",
  "tools.humanize.errNoAnchor":
    "Add ~150 words of your own writing above, then run it again.",
  "tools.humanize.errFrozen":
    "The rewrite would have altered a number or citation, so your original was kept unchanged.",
  "tools.humanize.errFailed": "The rewrite did not complete.",
  "tools.humanize.badgeRewritten": "Rewritten",
  "tools.humanize.badgeNoChange": "No change needed",
  "tools.humanize.badgeVerified": "numbers & citations verified",
  "tools.humanize.caveat":
    "A rewrite that would have changed any number, statistic or citation is " +
    "discarded and your original returned — this can never quietly alter a " +
    "finding. It also makes no claim about what an AI detector will say.",

  "tools.rhythm.name": "Writing rhythm",
  "tools.rhythm.tagline": "Measure how mechanical your sentences are",
  "tools.rhythm.blurb":
    "Measures how mechanical your sentence rhythm is — variation in sentence " +
    "length, and how often paragraphs open with the same connectors. Concrete " +
    "writing feedback, the kind a supervisor gives.",
  "tools.rhythm.passageLabel": "Passage (3+ sentences)",
  "tools.rhythm.placeholder":
    "Paste a passage — at least 3 sentences are needed to measure rhythm.",
  "tools.rhythm.run": "Measure",
  "tools.rhythm.running": "Measuring…",
  "tools.rhythm.errShort": "Not enough text to measure a rhythm.",
  "tools.rhythm.band.veryEven": "Very even — sentences land at near-identical lengths",
  "tools.rhythm.band.fairlyEven": "Fairly even",
  "tools.rhythm.band.someVariation": "Some variation",
  "tools.rhythm.band.bursty": "Bursty — reads like natural human rhythm",
  "tools.rhythm.scaleLow": "0 · varied",
  "tools.rhythm.scaleHigh": "1 · metronome",
  // Split so the lead sentence can be bold. It is the whole point of the box —
  // a student reading this score as a Turnitin prediction has been misled.
  "tools.rhythm.caveatLead": "This is not an AI detector.",
  "tools.rhythm.caveatBody":
    " It measures sentence-length variation and connector density — it cannot " +
    "see perplexity, which is roughly half of what real detectors use. It does " +
    "not predict Turnitin, GPTZero or any commercial tool, and a low number is " +
    "not a pass. Use it as writing feedback: if your sentences are all the same " +
    "length, vary them.",

  // Renamed from "Citation check": checking one reference is now the smallest
  // of three modes, and the one students arrive for is the .docx that comes
  // back cited.
  "tools.citation.name": "Citations",
  "tools.citation.tagline": "Cite what isn’t, verify what is",
  "tools.citation.blurb":
    "Attach your thesis and get it back with its reference list rebuilt from " +
    "CrossRef and its uncited claims sourced — formatting untouched. Or check a " +
    "single reference, or a list you paste in.",
  "tools.citation.refLabel": "Citation to check",
  // An example, not prose: identical in both catalogues on purpose.
  "tools.citation.placeholder":
    "10.1016/j.chb.2021.106789  ·  or  ·  Nguyen, T. (2021). Title of the paper. Journal Name.",
  "tools.citation.run": "Check",
  "tools.citation.running": "Checking…",
  // Named for WHAT YOU GIVE IT, not for the mechanism behind it.
  "tools.citation.modeDocx": "Whole thesis (.docx)",
  "tools.citation.modeList": "Pasted list",
  "tools.citation.modeOne": "One citation",
  "tools.citation.listLabel": "Reference list, or the whole thesis",
  "tools.citation.listPlaceholder":
    "Paste your reference list — or attach the thesis above and the list will be " +
    "found in it.",
  "tools.citation.runAll": "Check all",
  "tools.citation.summary_one": "{count} reference checked",
  "tools.citation.summary_other": "{count} references checked",
  "tools.citation.countConfirmed": "{count} confirmed",
  "tools.citation.countProbable": "{count} probable",
  "tools.citation.countMissing": "{count} not found",
  "tools.citation.itemUnchecked": "Not checked — CrossRef unreachable",
  "tools.citation.truncated":
    "Only the first {checked} of {detected} references were checked. Split the " +
    "list and run it again for the rest.",
  "tools.citation.errNoRefs":
    "No references found. This looks for lines carrying a year or a DOI, usually " +
    "under a “Tài liệu tham khảo” / “References” heading — paste the reference " +
    "list itself, or the whole document.",
  "tools.citation.errUnreachable":
    "CrossRef could not be reached, so this reference was NOT checked — that is " +
    "not the same as it being fake.",
  "tools.citation.none": "No match found",
  "tools.citation.exact": "Confirmed — exact DOI match",
  "tools.citation.probable": "Probable match (fuzzy search, not proof)",
  "tools.citation.caveat":
    "A DOI is an exact lookup and the answer is definitive. Without one this " +
    "falls back to a bibliographic search, which is fuzzy — CrossRef returns its " +
    "best match for any query, so a hit is evidence something similar exists, " +
    "not proof this reference is real. Check the title and authors against what " +
    "you cited.",

  // --- whole-document citing (.docx in, .docx out) ---
  "tools.cite.found_one": "{count} source cited in this thesis",
  "tools.cite.found_other": "{count} sources cited in this thesis",
  "tools.cite.willResolve": "each one looked up in CrossRef and formatted in APA 7",
  "tools.cite.willCost": "{count} credits — you pay per source we go and check",
  "tools.cite.willLink":
    "every citation becomes a link — click it to jump to its entry in the list",
  "tools.cite.willReplaceList":
    "your current reference list ({count} entries) is replaced by the rebuilt one",
  "tools.cite.willCreateList": "no reference list found — one will be added at the end",
  "tools.cite.willKeepFormat":
    "{count} headings, plus tables and numbering, are left untouched",
  "tools.cite.addMissing": "Also cite claims that have no source",
  "tools.cite.addMissingHint":
    "Scans {count} body paragraphs for claims a reader would expect a source for, " +
    "searches CrossRef, and inserts a citation only when a real paper is confirmed " +
    "to support it. Anything unconfirmed is marked [citation needed] instead of " +
    "guessed. This part runs a model, so it costs extra on top of the price " +
    "above — billed on what it actually uses, which a scan cannot predict.",
  "tools.cite.run": "Cite the document",
  "tools.cite.running": "Citing…",
  "tools.cite.errFailed": "The document could not be cited.",
  "tools.cite.doneResolved": "{count} citations resolved against CrossRef",
  "tools.cite.doneUnresolved": "{count} could not be found — your own entry is kept and labelled",
  "tools.cite.doneWeak":
    "{count} matched on name and year only (not in your list) — check these yourself",
  "tools.cite.doneUncited": "{count} entries in your list are not cited anywhere in the text",
  "tools.cite.doneAdded": "{count} new citations inserted",
  "tools.cite.doneMarked": "{count} claims marked [citation needed]",
  "tools.cite.doneLinked": "{count} citations linked to their reference entry",
  "tools.cite.caveat":
    "Nothing is cited that CrossRef did not return and a second check did not " +
    "confirm supports that specific claim — an unsupported claim gets a visible " +
    "marker instead of a plausible-looking source. Nothing in your list is " +
    "deleted: an entry that could not be resolved is kept as you wrote it and " +
    "labelled, and one matched on name and year alone says so, so you know what " +
    "still needs checking. Tables, headings and numbering are not touched; bold " +
    "or italic inside a rewritten sentence is not preserved.",

  // --- whole-document rewrite ---
  "tools.doc.choose": "Choose a .docx",
  "tools.doc.wordOnly": "Word only — a PDF has no editable paragraphs",
  "tools.doc.readFailed": "Could not read that document.",
  "tools.doc.willRewrite_one": "{count} paragraph will be rewritten",
  "tools.doc.willRewrite_other": "{count} paragraphs will be rewritten",
  "tools.doc.headings": "{count} headings left untouched — they’re structure, not prose",
  "tools.doc.tables": "{count} tables left untouched — they’re data",
  "tools.doc.captions": "{count} captions and short lines skipped",
  "tools.doc.runsAs_one":
    "Runs as {count} rewrite (paragraphs are batched by section). You’re charged " +
    "for the tokens actually used — the exact amount lands in Transactions.",
  "tools.doc.runsAs_other":
    "Runs as {count} rewrites (paragraphs are batched by section). You’re charged " +
    "for the tokens actually used — the exact amount lands in Transactions.",
  "tools.doc.run": "Humanize document",
  "tools.doc.errEmpty":
    "Nothing to rewrite — this document is headings, tables and captions only.",
  "tools.doc.downloaded": "{name} downloaded",
  "tools.doc.rewritten_one": "{count} paragraph rewritten",
  "tools.doc.rewritten_other": "{count} paragraphs rewritten",
  "tools.doc.skipped_one":
    "{count} paragraph kept its original text — its rewrite failed or would " +
    "have changed a number or citation.",
  "tools.doc.skipped_other":
    "{count} paragraphs kept their original text — their rewrite failed or " +
    "would have changed a number or citation.",
  "tools.doc.unchanged": "Headings, tables and numbering are unchanged.",
  "tools.doc.caveatBefore":
    "Tables and headings are never rewritten, and any batch whose rewrite would " +
    "have altered a number or citation keeps its original text. One real loss: " +
    "bold or italic ",
  "tools.doc.caveatEm": "inside",
  "tools.doc.caveatAfter":
    " a sentence isn’t preserved — paragraph styles, heading levels, tables and " +
    "numbering are.",

  // --- file attach control, shared by every tool ---
  "tools.file.attach": "Attach a file",
  "tools.file.reading": "Reading…",
  "tools.file.types": "PDF, Word or text",
  "tools.file.orDrop": "{hint} · or drop one here",
  "tools.file.loaded": "{name} — text loaded below, edit it freely",
  "tools.file.readFailed": "Could not read that file.",

  // --- tool request failures ---
  "tools.err.request": "Request failed.",
  "tools.err.unsupported": "That file type isn’t supported — use PDF, Word or a text file.",
  "tools.err.tooLarge": "That file is too large.",
  "tools.err.readFile": "Could not read the file ({status}).",
  "tools.err.noText": "No text could be read from this file.",
  "tools.err.needDocx":
    "Document rewriting needs a .docx — a PDF has no editable paragraphs.",
  "tools.err.readDoc": "Could not read the document ({status}).",
  "tools.err.rewriteFailed": "The rewrite did not complete ({status}).",
  "tools.err.docTimeout":
    "This took too long and we stopped waiting. Your document was not changed — " +
    "try again, or split it into smaller files.",
  "tools.err.docConnection":
    "The connection to the server was lost before the document came back. Your " +
    "document was not changed — try again.",

  // --- /transactions — where a student goes to ask what happened to their credits ---
  "txn.title": "Transactions",
  "txn.balance": "{count} Credit",
  "txn.col.date": "Date",
  "txn.col.activity": "Activity",
  "txn.col.amount": "Amount",
  "txn.col.tool": "Tool",
  "txn.col.result": "Result",
  "txn.col.credits": "Credits",
  "txn.loading": "Loading…",
  "txn.empty": "No credit usage yet.",
  "txn.prev": "Previous",
  "txn.next": "Next",

  "txn.reason.chatTurn": "Chat / writing run",
  "txn.reason.autoRun": "Auto-approve run",
  "txn.reason.paperRun": "Thesis run",
  "txn.reason.purchase": "Top-up",
  "txn.reason.refund": "Refund",

  // Tool names as a STUDENT knows them, not the server's slugs — which is what
  // this list showed until the tools started billing under their own names.
  "txn.tool.humanize": "Humanize a passage",
  "txn.tool.humanizeDocx": "Humanize a document",
  "txn.tool.citeDocx": "Cite a document",
  "txn.tool.verifyCitation": "Check one reference",
  "txn.tool.verifyCitations": "Check a reference list",
  "txn.tool.rhythm": "Writing rhythm",
  "txn.tool.plagiarism": "Similarity check",
  "txn.tool.extractText": "Read a file",
  "txn.tool.scanDocx": "Scan a document",
  "txn.tool.scanCiteDocx": "Scan citations",

  "txn.tools.title": "Tool runs",
  "txn.tools.blurb":
    "Everything you ran outside a thesis project. Runs that cost nothing are " +
    "listed too, so this answers why your credits moved as well as why they didn't.",
  "txn.tools.empty": "You haven't run any tools yet.",
  "txn.tools.ok": "Done",
  "txn.tools.failed": "Didn't finish",
  "txn.tools.free": "Free",
  // --- artifacts + live progress ---
  "txn.tools.running": "Running — {done}/{total}",
  "txn.tools.runningPlain": "Running…",
  "txn.tools.partial":
    "{done} rewritten · {skipped} kept their original text",
  "txn.tools.dlInput": "Original file",
  "txn.tools.dlOutput": "Result",
  "txn.tools.rerun": "Run again",
  "txn.tools.rerunning": "Running…",
  "txn.tools.rerunConfirm":
    "Run this document through the tool again? It costs credits, the same as the first run.",
  "txn.tools.keptUntil": "kept until {date}",
  "txn.tools.deleteFiles": "Delete files",
  "txn.tools.deleteConfirm":
    "Delete the stored files for this run? This cannot be undone — the run itself stays in your history.",
  "txn.tools.units": "· {count} sources",
  "txn.tools.shortfall": "{count} not charged — your balance was short",

  // --- language switcher ---
  "lang.label": "Language",
  "lang.en": "English",
  "lang.vi": "Tiếng Việt",
} as const;

export type MessageKey = keyof typeof en;
