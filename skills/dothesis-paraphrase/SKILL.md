---
name: dothesis-paraphrase
description: Use when the student wants a specific sentence or paragraph reworded — "viết lại câu này", "diễn đạt lại đoạn này", "paraphrase giúp mình", "câu này giống bài gốc quá", "làm cho gọn hơn", "rephrase this" — including rewording a quoted source into their own words so it can be cited rather than copied.
---

# Paraphrase — reword a passage, keep the claim

## What this is

A short-range rewrite: one sentence to one paragraph, reworded on request. It is
the smallest of the three rewriting skills, and picking the right one matters:

| The student says | Skill |
|---|---|
| "it reads like ChatGPT" / a detector or supervisor flagged it | `dothesis-humanize` |
| "there are grammar mistakes" | `dothesis-grammar` |
| "reword this bit" / "this is too close to the source" | **this one** |

The distinction is not pedantic. Humanize runs a verified, anchored, metered
rewrite over a whole chapter and refuses to run unanchored. Paraphrase is a
targeted edit the student asked for on a passage they pointed at.

## The two jobs, and they are different

**1. Rewording the student's own prose.** Straightforward: restate the same
claim in different words at the same level of formality. Offer 2–3 variants when
the passage is a single sentence — students choose better than they specify.

**2. Rewording someone else's prose so it can be cited.** This is the one that
carries academic risk, and it has a hard rule:

> A paraphrase of a source still needs the citation. Always.

Changing the words does not transfer authorship. If the student pastes source
text and asks for a paraphrase, the output **must** carry the in-text citation,
and you must say so explicitly rather than assuming they know. If they haven't
told you the source, ask for it before rewriting — a paraphrase handed back
without a citation is the exact mechanism by which students commit plagiarism
accidentally. See `dothesis-plagiarism` when they want to check what they've
already written.

Never paraphrase a passage into something that reads as the student's original
idea. "Nguyen (2021) lập luận rằng…" is a paraphrase; the same sentence with the
attribution stripped is not.

## Frozen content

Same frozen set as `dothesis-grammar` and `dothesis-humanize`: numbers,
statistics, table/figure references, citations, author names, years, and
construct names come through unchanged. A paraphrase that softens "β = 0.42
(p < 0.01)" into "a fairly strong effect" has destroyed a result.

Definitions of technical constructs are also effectively frozen. Rewording
"perceived usefulness" into "how helpful users think it is" changes an
operationalised variable into an informal gloss.

## How to run it

1. Confirm the exact passage. If the student pasted a whole page and said "this
   bit", ask which.
2. Ask whether it is their prose or a source's — the citation rule above hangs
   on the answer, and you cannot tell by looking.
3. Match the document's language and citation style.
4. For a single sentence, return 2–3 variants; for a paragraph, return one
   rewrite plus a note on what you changed (tightened / de-nominalised /
   reordered for flow).
5. If the passage is longer than a paragraph, this is the wrong skill — the
   student wants humanize (whole-chapter, verified) and should be told why.

## Never

- Never return a paraphrase of a source without its citation.
- Never paraphrase by thesaurus-substitution. Swapping words while keeping the
  original sentence structure is exactly what similarity checkers catch, and it
  reads worse than the original.
- Never claim a paraphrase makes text "safe" from a plagiarism checker. You
  cannot know that, and `dothesis-plagiarism` is explicit about the limits.
