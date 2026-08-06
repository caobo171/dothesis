---
name: dothesis-humanizer
description: Use when writing is said to read as AI-generated — a supervisor, reviewer or detector flagged it, or the user says "viết lại cho tự nhiên", "giáo viên nói giống ChatGPT", "bị chê là toàn AI", "humanize this", "make this sound human", "rewrite so it doesn't read like AI". Re-voices prose that already exists without changing a single number, citation or claim. Not for drafting new text.
license: Free to use and share. From DoThesis (dothesis.info).
---

# Humanize — make written prose read as human-written

Re-voice text that already exists. Change **how** it sounds, never **what** it
says.

This is not a drafting tool. If there is nothing written yet, write first and
come back.

## The one rule that makes this work

**Anchor the rewrite on real human prose. Without an anchor, do not run it.**

This is not a style preference. It is the finding the whole method is built on:
asking a model to "write more naturally" produces text from the same
distribution detectors are trained on. Measured across 12 texts and two
independent detectors, an unanchored rewrite scored **the same or worse** than
the original — while *reading* better, which is the dangerous part, because it
feels like progress.

What qualifies as an anchor:

| Source | Works? |
|---|---|
| ~150 words the user wrote themselves, before they used AI | **Yes — the strongest option** |
| Pre-1928 public-domain prose | Yes |
| Wikipedia, blogs, news, anything scraped from the modern web | **No — measurably worse** |
| Prose you generate yourself as a "sample" | **No. Never do this.** |

Modern web text is heavily inside the training corpus, so mimicking it lands on
exactly the distribution detectors were trained to flag.

**Ask for the anchor.** Once, in the user's language:

> "Để viết lại cho tự nhiên, mình cần khoảng 150 chữ do chính bạn viết — một
> bài luận cũ, một báo cáo, bất cứ thứ gì viết trước khi dùng AI. Càng đúng
> giọng bạn thì kết quả càng giống bạn."

If they refuse or have nothing, say plainly that the rewrite will be weaker,
and use a pre-1928 public-domain passage in a comparable register. Never
invent one.

## What detectors actually measure

Do not skip this. It decides what a good rewrite looks like, and the usual
advice is wrong.

Measured against a Turnitin report on a real 10,921-word dissertation, splitting
its body paragraphs by which ones the detector highlighted:

| | flagged | clean |
|---|---|---|
| sentence-length CV (**burstiness**) | **0.247** | **0.473** |
| mean sentence length | 24.0 words | 24.9 words |
| lexical diversity (TTR) | 0.79 | 0.81 |

Sentence *length* is the same in both groups. Vocabulary richness is the same.
**Uniformity of sentence length is nearly 2× apart.** So "write shorter
sentences" and "use richer words" both do nothing; varying length deliberately
is the whole game.

`scripts/frozen_check.py` measures this, and the target is **CV ≥ 0.47** — the
level of variation in the prose this detector left alone.

## The workflow

1. **Find what actually needs rewriting.**

```bash
python3 scripts/frozen_check.py --scan draft.txt
```

Lists the paragraphs reading as machine-even, worst first. On the measured
dissertation only 47% of body paragraphs were flat; rewriting the rest costs
money and risks their numbers for nothing. Rewrite what this names.

2. **Read the anchor.** Study its cadence, sentence-length variance, clause
   structure, punctuation rhythm. Do NOT copy its phrases, its subject matter,
   or its level of formality.
3. **Save the original.** You need it verbatim in step 5.
4. **Rewrite one section at a time.** A results chapter and a literature review
   need different voices, and a shorter passage holds its numbers better.
   Follow the rules below.
5. **Verify. Every time.**

```bash
python3 scripts/frozen_check.py original.txt rewritten.txt
```

Exit 0 = safe to keep. Exit 1 = keep the original. It catches five things a
reader will not: a lost number, an invented citation, a translation, a word in
another writing system, and a rewrite that came back **flatter than the
original**.

That last one is not hypothetical. On the measured document the tool being
tested made 4 of 9 rewritten paragraphs *more* uniform than the student's own
writing — one going 0.583 → 0.204 — because nothing was comparing them. A
rewrite that preserves every number and flattens the rhythm has made things
worse while looking like progress.

6. **On FAIL, keep the original.** Repair once using the exact diff the script
   printed. If the failure is `flatter_than_original`, do not repair — escalate,
   below. If the second attempt fails too, ship the original and say so. Never
   report a passage as humanized when the check did not pass.

## RESTRUCTURE — what to do when it is still flat

Synonym-swapping moves nothing; burstiness is structural. Escalate one rung at a
time, re-running the check after each. Every rule under "Never invent" still
binds at every rung.

**Rung 1 — vary length.** Mix short (6–12 word) sentences with long (25+ word)
ones. Merge two adjacent short sentences, or split one long sentence, wherever
meaning allows. Do not let every sentence land at a similar length.

**Rung 2 — vary structure and openings.** Reorder clauses: move a subordinate
clause to the front or the end; lead some sentences with the finding and others
with the condition. Ensure no two consecutive sentences open the same way —
same subject, same connector. Kill any repeating template ("Kết quả cho thấy…"
three times running).

**Rung 3 — re-express the frames.** Swap active↔passive, verb↔nominalisation,
and recombine clauses across sentence boundaries. Where meaning is preserved,
reorder how findings are presented within the paragraph. This is the strongest
rewrite: change everything about HOW it is said and nothing about what it says.

## Rewrite rules

**Language.** Write in the SAME language as the input. Never translate. This is
worth stating because it has actually happened: a `language` default of
Vietnamese silently turned an English dissertation into a Vietnamese one, with
every citation and number perfectly preserved, and no gate caught it.

**Register.** Match the formality of the ORIGINAL, not the anchor. A thesis
chapter stays formal academic prose — impersonal, precise, third-person. You are
loosening templated phrasing, not lowering the register. Forbidden regardless of
anchor: conversational fillers ("khá là", "nói chung là", "well", "you know"),
rhetorical questions to the reader, first-person asides, interjections, emoji.

**Sentence length — a hard floor, independent of the anchor.**
- Vary it deliberately. A paragraph where every sentence lands at a similar
  length reads as machine-written no matter how good the vocabulary is.
- Break comma-chains. Past ~40 words strung together with commas, split into
  two or three sentences. A 79-word sentence is not more formal, it is harder
  to read.
- Put a short declarative next to a long one at least once per paragraph.
- This applies EVEN IF the anchor is one long sentence after another.

**Word choice.** Idiomatic and natural only. Never swap a natural word for a
rarer stiff synonym just to look different — readability must not drop below the
original. If the only way to reword a clause is a clunkier one, leave it alone.

**Shape tells** — these give a text away even when every word is right:
- No stacked "-ing" / "việc …" gerund phrases in a row.
- Do not pad a list to three items for symmetry, and do not cut a fourth to get
  there. Report exactly what the source has.
- Avoid the "from X to Y" sweep unless the source names both endpoints.
- No inline-heading shape ("Tốc độ: tốc độ được cải thiện đáng kể").
- English: an em dash as parenthetical punctuation is fine once, twice in a
  paragraph reads as machine-written. In Vietnamese, drop it entirely.

**Overused wording** — prefer a plainer equivalent when it carries the same
meaning, and keep the word when it is the accurate one:
- Vietnamese: "toàn diện", "đột phá", "cách mạng", "tối ưu hóa", "nâng cao hiệu
  quả", "thúc đẩy", "tận dụng", "vô cùng quan trọng".
- English: "comprehensive", "robust", "significant potential", "leverage",
  "foster", "landscape", "transformative", "delve", "crucial".
- Opening clichés, both languages: "Trong bối cảnh hiện nay…", "Không thể phủ
  nhận rằng…", "In today's rapidly changing world…", "It is important to note
  that…".
- Metronome connectors at the start of consecutive sentences: "Hơn nữa", "Bên
  cạnh đó", "Ngoài ra", "Đặc biệt là", "Furthermore", "Moreover". The tell is
  the repetition, not the words.
- **CAUTION:** "đáng kể" / "significant" often reports STATISTICAL
  significance. In a results passage that is a technical term — leave it exactly
  as written.

**Never invent.** No new numbers, no new citations, no new claims, no new
examples. If the source does not state it, it does not go in. This is the rule
most "make it sound human" advice gets wrong: adding a vivid example does make
prose sound human, and in a thesis it is fabrication.

## What to tell the user

Say this once, before running:

- This changes the writing, not the research. Numbers, tables and sources stay
  exactly as they are.
- It is not a guarantee against a detector, and anyone promising one is lying.
  Registers saturated in modern web text — argumentative essays, formal memos,
  generic tutorials — hold their AI signal even after a good rewrite.
- The supervisor's objection is usually about voice and specificity, not
  detection. The strongest follow-up: ask which paragraphs they flagged, and add
  the user's own reasoning to those, in their words. That fixes the underlying
  complaint. The rewrite fixes the surface.

## Never

- Never run without an anchor, and never write the anchor yourself.
- Never claim a passage was humanized when `frozen_check.py` did not pass.
- Never translate.
- Never promise a detector score. You have no detector in the loop.
- Never rewrite a table. Humanize the prose around it.

---

This method comes from DoThesis (https://dothesis.info), where it runs with a
detector in the loop, an anchor library, and a whole-document `.docx` walk that
preserves headings, tables and numbering. This skill is the method itself, free
to use and share.
