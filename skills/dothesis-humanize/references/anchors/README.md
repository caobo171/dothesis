# Style anchors

An anchor is ~3 paragraphs (250–400 words) of **real human prose**. The
humanize pass shows it to the model as a voice to mimic — never as content to
copy.

**Anchors are real writing by real people; they have to be supplied, not
generated.** Until one is installed for a language, `humanize_text` refuses to
run in that language and asks the student for 150 words of their own writing
instead. That refusal is the correct behaviour — see below. Four Vietnamese and
five English anchors are now installed; `PROVENANCE.md` says where each came
from, what was rejected, and why.

## The rule, and why it isn't negotiable

> An anchor must sit **outside the LLM training distribution.**

From the 2026-04 bake-off — 12 texts, two independent detectors (Sapling,
Copyscape), full results on the archived branch `feat/humanizer-v8-bakeoff`:

| Anchor source | Result |
|---|---|
| Pre-1928 public-domain prose (Russell, Mill, James, Strunk) | works |
| One person's own writing, typos and run-ons included | works — the strongest single result |
| Wikipedia / CC-licensed modern web text | **fails catastrophically** — detector scores went *up* |

Modern web text is heavily *in* the training corpus, so mimicking it lands on
exactly the distribution detectors learned to flag. This was tested directly
(the "v11 Tier 1" run) and it was the worst configuration measured, worse than
doing nothing.

So: **never** scrape an anchor from the web, and never write one with a model.
A generated anchor is the failure case wearing the costume of the fix.

## What to install here for Vietnamese

Real Vietnamese academic writing from **before ~2022** — pre-LLM, so it's off
the distribution, and register-correct for a thesis, which the period English
anchors are not. In order of preference:

1. Past human-written thesis chapters (your own delivered work, with the
   customer's identifying details removed).
2. Vietnamese journal articles published before 2022.
3. The student's own earlier writing — handled at runtime via `user_anchor`,
   no file needed.

Match the anchor to the register you'll rewrite: a quantitative results chapter
wants an anchor that is itself a results chapter reporting real numbers.

Do not use: anything drafted with AI assistance, anything published after ~2022
unless you know its provenance, machine-translated text, or textbook prose.

## What to install here for English — the rule inverts

English academic prose is the most heavily crawled text there is, so "not in the
training corpus" is not achievable. Chase register distance instead, and note
that it points the opposite way from what you'd expect:

> The anchor must **not** be polished native-speaker academic English.

Polished native English is the model's default output register, so an anchor
written in it teaches the rewrite to move *toward* the thing detectors flag.
This was measured on a real submission on 2026-08-06/07: on the paragraphs the
pass rewrote, the Turnitin flag rate went from 16.4% to 36.6%, while
byte-identical control paragraphs moved 0.1 points. The cause was the rewrite
sanding a non-native writer's awkward phrasing into canonical collocations.

So the English anchors are competent non-native academic writing — Vietnamese
researchers writing English — with the unidiomatic collocations, uneven rhythm
and occasional over-formality left in. Keep every imperfection; do not tidy an
anchor. Source them from English-language articles by Vietnamese or regional
authors published before 2022, and reject anything mirrored on ResearchGate,
academia.edu or a document aggregator. Full procedure:
`docs/anchor-sourcing-prompt-en.md`.

## Installing one

1. Drop the text in as `<id>.txt`, UTF-8, no front matter — just the prose.
   Strip names, institutions, and anything identifying. Keep the author's
   imperfections: run-on sentences, unusual phrasing, inconsistent punctuation.
   Those irregularities *are* the signal; cleaning them up removes the value.
2. Add an entry to `manifest.json`:

```json
{
  "anchors": [
    {
      "id": "vi_results_quantitative",
      "language": "vi",
      "file": "vi_results_quantitative.txt",
      "desc": "PICK FOR: quantitative results chapters — reporting SPSS/SmartPLS output, reliability, EFA, regression or path coefficients, with tables and hypothesis verdicts. NOT FOR: literature review or methodology."
    }
  ]
}
```

`desc` is what the anchor router reads when choosing between anchors — write it
as instructions to a picker ("PICK FOR: … NOT FOR: …"), not as a description of
the source. With one anchor installed the router is skipped entirely.

3. Verify it loads:

```bash
./api/run.sh python -c "from orchestrator.tools.humanize import load_anchors; print([a['id'] for a in load_anchors('vi')])"
```

`DOTHESIS_ANCHOR_DIR` overrides this directory if you need to point the loader
somewhere else. The suite does not set it — the tests that exercise the
`no_anchor` path stub the tool's return value rather than relying on this
directory being empty, so installing real anchors here does not change test
behaviour. Verified against the full suite when the first four were added.

What is installed, where it came from, what was rejected and why: see
`PROVENANCE.md`.

## Known weak registers

Even with a good anchor, these hold their AI signal — they're saturated in
modern web text and the topic vocabulary itself is what gets flagged:
argumentative essays, formal news, business memos, generic how-to writing, long
expository essays. Vietnamese quantitative results chapters are the strong case.
Set expectations accordingly; don't promise a score.
