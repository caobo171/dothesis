---
name: dothesis-humanize
description: Use when a supervisor, reviewer, or AI detector says the writing reads as AI-generated — "bị chê là toàn AI", "giáo viên nói giống ChatGPT", "viết lại cho tự nhiên hơn", "humanize", "làm cho giống người viết", "check đạo văn AI" — or when the student asks to rewrite a drafted chapter in a more human voice.
---

# Humanize — make drafted prose read as human-written

## What this is

A rewrite pass that re-voices already-written prose. It changes **how** the text
sounds, never **what** it says. Every number, p-value, β, table reference and
citation is frozen and verified after the rewrite; a rewrite that moved one is
thrown away and the original is kept.

Use it on a chapter the student already has. It is not a drafting tool — if
there is no draft yet, that's `dothesis-m5-writing`.

## The one rule that makes this work

**The rewrite is anchored on real human prose. Without an anchor, do not run it.**

This isn't a style preference, it's the finding the whole feature is built on:
asking a model to "write more naturally" produces text from the same
distribution detectors are trained on. Measured across 12 texts and two
detectors, an unanchored rewrite scored the same or worse than the original —
while *reading* better, which is the dangerous part. Anchoring the rewrite on
prose that sits outside the training distribution is what actually moves it.

Two sources qualify:

| Anchor | Where it comes from |
|---|---|
| Library anchor | Installed in `references/anchors/` — real pre-2022 Vietnamese academic writing |
| The student's own writing | ~150 words they wrote themselves, before they used AI |

Modern web text (Wikipedia, blogs, news, anything scraped) does **not** qualify
and makes results measurably worse. Never improvise an anchor from your own
output.

## How to run it

Call `humanize_text`. It handles anchor selection, the rewrite, and verification.

```
humanize_text(text="<the passage>", user_anchor="<optional 150 words>")
```

**Call it WITHOUT `user_anchor` first.** If this student has given a sample
before, it is loaded automatically and asking again is a wasted turn — the
anchor is saved per student, not per project, so it carries across their
theses.

**When it returns `error: "no_anchor"`** — nothing is installed for this
language and nothing is saved for this student yet. Ask for their own writing:

> "Để viết lại cho tự nhiên, mình cần khoảng 150 chữ do chính bạn viết —
> một bài luận cũ, một báo cáo, bất cứ thứ gì viết trước khi dùng AI. Càng
> đúng giọng bạn thì kết quả càng giống bạn. Mình chỉ hỏi một lần thôi —
> lần sau sẽ tự nhớ."

Then call again with that text as `user_anchor`. It is remembered on success,
so you should never have to ask a second time. Do not proceed without one and
do not substitute your own prose.

**When it returns `error: "frozen_violation"`** — the rewrite altered a number
or a citation, so the original was kept. Say so plainly. Never report the
passage as humanized.

**Work section by section**, not on the whole thesis at once. A results chapter
and a literature review need different voices, and a shorter passage holds its
numbers better.

## What the student should expect

Say this before running it, once:

- This changes the writing, not the research. The numbers, the tables and the
  sources stay exactly as they are.
- It is not a guarantee against a detector. Registers that are saturated in
  modern web text — argumentative essays, formal memos, generic tutorials —
  hold their AI signal even after a good rewrite. Vietnamese quantitative
  results chapters are the strong case; that's the register this is tuned for.
- The supervisor's objection is usually about voice and specificity, not
  detection. Offer the follow-up: ask which paragraphs they flagged, and add the
  student's own reasoning to those, in their words. That fixes the underlying
  complaint; the rewrite fixes the surface.

## Exporting a humanized version

`export_docx(humanize=True)` runs the pass over every chapter before rendering,
so the student gets a DOCX/PDF they can hand over — useful when someone wants
the old and new versions side by side.

It reports per-chapter results. Chapters that failed verification are exported
**unchanged**; name them when you confirm, don't round up to "done".

## Never

- Never run the pass without an anchor, and never write the anchor yourself.
- Never claim a passage was humanized when the tool returned `ok: false`.
- Never let the rewrite touch a table produced by `render_verified_sections` —
  those tables are rendered from verified analysis state. Humanize the prose
  around them.
- Never promise a detector score. You have no detector in the loop and cannot
  see one.
