---
name: dothesis-grammar
description: Use when the student asks for grammar, spelling, punctuation or academic-register fixes on prose they already wrote — "sửa lỗi ngữ pháp", "check chính tả", "câu này viết đúng chưa", "sửa lại cho academic hơn", "grammar check", "proofread my chapter" — or when a supervisor returned a draft marked up for language rather than content.
---

# Grammar — fix the language, never the findings

## What this is

A proofreading pass over prose the student already wrote. It corrects grammar,
spelling, punctuation, agreement, tense consistency and academic register. It
does not restructure arguments, add content, or change what the text claims.

This is not `dothesis-humanize`. Humanize changes how the prose *sounds* to
escape the LLM cadence and needs a style anchor to work. Grammar fixes what is
*wrong*, needs no anchor, and can run on anything. If the student's complaint is
"my supervisor said it reads like ChatGPT", that is humanize, not this.

It is also not `dothesis-m5-writing`. If there is no draft yet, there is nothing
to proofread — write first.

## The frozen set

Identical to humanize, and non-negotiable. These must come out byte-for-byte as
they went in:

- every number, percentage, p-value, β, t-statistic, R², sample size
- every table and figure reference ("Bảng 4.2", "Figure 3")
- every in-text citation and every author name and year
- every construct/variable name, including its capitalisation

A grammar fix that "corrects" `p < 0.05` to `p < 0,05`, renames a construct, or
tidies `(Nguyen & Tran, 2021)` into `(Nguyen and Tran, 2021)` has changed the
student's findings or broken their citation style. If a change to a frozen item
looks genuinely required, **say so and leave it alone** — do not apply it
silently.

## How to run it

1. **Work on a bounded passage.** A section or a chapter, not "my whole thesis".
   Ask which part if the student hasn't said.
2. **Match the document's language.** A Vietnamese thesis gets Vietnamese
   corrections. Never translate as a side effect of proofreading — that is a
   different request, and a destructive one to do unasked.
3. **Respect the citation style already in use** (`citation_style` on the
   project). Do not normalise APA to Vancouver because it reads better.
4. **Return the corrected passage**, then a short list of what changed and why,
   grouped by kind (agreement, tense, register…). Students learn from the list;
   the corrected text alone teaches nothing.
5. **Flag, don't fix, anything ambiguous.** "Câu này mình không chắc bạn muốn nói
   X hay Y" beats guessing, because a wrong guess about meaning is invisible in a
   proofread and lands in the submitted thesis.

## Academic register

Beyond correctness, tighten these when they appear — but only these, and only
where the meaning is unchanged:

- first person where the field expects impersonal construction (check the
  document's own convention first; some Vietnamese faculties require "nhóm
  nghiên cứu")
- contractions and colloquialisms
- hedging stacked on hedging ("có thể có khả năng là")
- filler openers that carry no information ("Như chúng ta đã biết,")

## Never

- Never rewrite for style beyond register. That is humanize or paraphrase.
- Never add a citation. If a claim needs one, say which sentence and let the
  student supply it — an invented source is the single worst failure this
  product can produce.
- Never delete a sentence because it seems redundant. Redundancy is a content
  judgement; report it and let the student decide.
- Never claim the chapter is now "error-free". Report what you changed.
