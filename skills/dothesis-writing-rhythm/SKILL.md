---
name: dothesis-writing-rhythm
description: Use when the student worries their writing sounds machine-generated and wants a concrete read on it — "bài mình có bị giống AI không", "check AI detector giúp mình", "đọc có tự nhiên không", "does this sound like ChatGPT", "will Turnitin flag this" — to give measurable writing feedback and to decide whether a humanize pass is warranted.
---

# Writing rhythm — measure the cadence, don't predict a detector

## What this is

A 0–1 score of how **mechanically even** a passage's sentence rhythm is, from
the `writing_rhythm` tool (`POST /api/v1/tools/writing-rhythm`, the same
`StylometricScorer` that drives the humanize loop). Higher means more
machine-even. It measures exactly two things:

- **burstiness** — variance in sentence length. Human academic prose swings
  between a six-word sentence and a forty-word one; generated prose tends to sit
  in a narrow band.
- **formulaic connector density** — "Hơn nữa", "Bên cạnh đó", "Đồng thời",
  "Moreover", "Furthermore" opening sentence after sentence.

## What it is NOT — say this out loud, every time

**This is not an AI detector and it does not predict Turnitin, GPTZero,
Originality.ai or any commercial tool.** It cannot see perplexity, which is
roughly half of what real detectors use. The tool's own description says so, and
so must you.

A student who reads "score 0.2" as "Turnitin will pass me" has been actively
misled by us, and they find out at submission. So:

- Report it as writing feedback, never as a verdict.
- Never say "safe", "clean", "won't be flagged", "passes AI detection", or a
  percentage that sounds like a detector's output.
- If the student asks directly "will Turnitin flag this?", the honest answer is
  that we cannot know, and that no tool that isn't Turnitin can tell them.

The useful framing is the concrete one: *"your sentences are all within four
words of each other, and eleven paragraphs in a row open with a connector"* —
that is actionable writing advice a supervisor would give, and it is true.

## How to run it

1. Needs **3+ sentences**; a single sentence has no rhythm to measure. Ask for a
   longer passage rather than scoring noise.
2. Run it per section, not per thesis. An average over 60 pages hides the one
   chapter that actually reads as generated.
3. Report the score with its two components, and quote 2–3 real sentences from
   the passage that illustrate the pattern. A number alone teaches nothing.
4. Then give the writing advice, not the verdict:
   - high evenness → "vary your sentence length deliberately; put a short
     declarative next to a long one"
   - high connector density → "most of these openers carry no information; cut
     them and the paragraph reads faster"

## When to hand off to humanize

If the score is high **and** the student wants it fixed rather than explained,
that's `dothesis-humanize`. Tell them what that involves before starting: it
needs ~150 words of their own real writing as a style anchor, it costs credits,
and it re-voices prose without touching any number or citation.

Do not run humanize automatically off a high rhythm score. A high score on a
chapter the student wrote themselves means their writing is repetitive, not that
it was generated — rewriting it against an anchor is the wrong remedy, and it
would spend their credits on a problem they didn't report.

## Never

- Never present this as an AI-detection result, in any wording.
- Never compare the score to a detector's threshold; there is no mapping.
- Never score a passage the student didn't hand you.
