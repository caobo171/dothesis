---
name: dothesis-plagiarism
description: Use when the student worries about similarity or copying — "check đạo văn", "bài mình có bị trùng không", "Turnitin bao nhiêu phần trăm", "mình paraphrase vậy có bị tính đạo văn không", "plagiarism check", "check similarity" — to run the similarity check if one is configured, and to give them the citation practice that actually prevents the problem.
---

# Plagiarism — check what can be checked, teach the rest

## What this is

Three things, and the last one matters most:

1. **The document self-check** (`POST /api/v1/tools/document/similarity`) —
   .docx in, the same .docx back with findings highlighted and a summary page.
   It needs no corpus and always works: passages repeated inside their own
   document, quotations with no citation near them, citations missing from the
   reference list, and references never cited. Free scan first
   (`/document/similarity-scan`) so they see the job before paying.
2. **The corpus check** — the same run also queries the deployment's similarity
   provider when one is configured. `corpus_checked` in the report (and the
   `X-Corpus-Checked` header) says whether that happened. There is also
   `POST /api/v1/tools/plagiarism-check` for a single pasted passage.
3. The citation practice that prevents a similarity problem in the first place —
   which is the part you can always deliver.

## Read this before you answer anything

**A similarity check needs a corpus.** The web, a paper index, and every thesis
the institution has previously collected. We do not have one. There is no local
fallback, and you must not invent one:

- Never estimate a similarity percentage. A number you produced by reading the
  text is fabricated, and a student will act on it.
- Never say a passage is "safe", "clean", "0% similar", or "will pass Turnitin".
- Never claim paraphrasing makes text safe from a checker. Thesaurus-level
  rewriting is exactly what similarity software is built to catch.
- Never predict a Turnitin score. Only Turnitin, running against the
  institution's own repository, can produce one.

If the tool returns `provider_not_configured` or `provider_error`, the passage
**was not checked**. Say that plainly. `score` is `null` rather than `0.0`
specifically so this cannot be misread — do not describe it as "no matches
found". The student should go to their university's own Turnitin/iThenticate
access, which is the only result their committee will accept anyway.

## When the check does run

Report the overall score, then the individual matches with their sources, and
work through them one at a time. An overall percentage is nearly meaningless on
its own: a thesis can sit at 25% entirely from correctly-quoted, correctly-cited
method descriptions, or at 8% from one uncited stolen paragraph. The second is
the serious problem.

For each match, sort it into one of three cases:

- **Cited and quoted** — fine. Similarity software flags it; supervisors don't.
- **Cited but too close to the wording** — the fix is a real paraphrase, keeping
  the citation. Hand off to `dothesis-paraphrase`.
- **Not cited** — the actual problem. The fix is to add the citation, not to
  reword until the checker stops noticing. Say that explicitly; a student who
  learns to dodge the checker has learned the wrong lesson and will be caught by
  a human reader instead.

## The part you can always do

Even with no provider, this is genuinely useful and costs nothing:

1. **Run the document self-check** if they have a .docx. Items 1 and 2 below
   are what it does deterministically, so read its findings rather than
   eyeballing the text — but its report says `corpus_checked: false`, and so
   must you.
2. **Find the passages at risk.** Text with no citation but a specific claim, a
   statistic, a definition, or a construct's operationalisation is where
   uncited borrowing lives. The self-check flags the quoted ones; the
   unquoted-but-borrowed ones still need your reading.
3. **Verify the references exist** with `verify_citation` — a fabricated source
   is a worse integrity failure than a similarity hit, and it is the failure
   mode LLM-assisted theses actually have.
4. **Teach the quote-vs-paraphrase-vs-cite rule** on their own text, with their
   own sentences as the example.

## Never

- Never produce a similarity number that did not come from a provider. The
  document self-check deliberately reports COUNTS, never a percentage: a
  percentage over the student's own file is not commensurable with a Turnitin
  score and would be read as one.
- Never present "we couldn't check" as "we checked and it's clean".
- Never help a student evade detection. The goal is a correctly cited thesis,
  not a lower percentage — and those come apart the moment the advice becomes
  "reword it until the checker stops flagging it".
