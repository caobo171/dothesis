# Humanizer pattern library — design

**Date:** 2026-09-05
**Status:** approved, ready for implementation

## Why

`skills-public/dothesis-humanizer` and `skills/dothesis-humanize` both tell the
agent *how* to rewrite (anchor it, vary rhythm, freeze the numbers) and *when to
stop*. Neither tells it **what specifically is wrong with a passage**. The shape
tells that do exist live inside `orchestrator/tools/humanize.py`'s
`_REWRITE_PROMPT` — about ten of them, unnumbered, mostly without examples, and
invisible to anyone reading a skill file.

`blader/humanizer` (MIT, v2.11.2) solves exactly that half: 35 numbered patterns
from Wikipedia's *Signs of AI writing*, each with watch-words and a before/after
pair, plus a false-positive section listing what must **not** be flagged. It has
no anchor, no verification, no measurement — the half DoThesis already owns.

So: import the taxonomy, keep our method.

## Scope

In:
- A new `references/ai-patterns.md`, written for a quantitative-thesis register,
  bilingual VI/EN.
- Both skill files gain a pointer to it.
- Packaging so the downloaded zip installs three ways, not one.
- Tests that keep the two copies and the shipped zip from drifting.

Out (deliberate):
- `orchestrator/tools/humanize.py` is **not** touched. That prompt produced a
  measured Turnitin regression once (16.4% → 36.6% on rewritten paragraphs); it
  does not get edited without an eval run behind the change. Folding the
  taxonomy into it is a separate, later decision.
- No standalone public GitHub repo. `npx skills add dothesis/...` by name would
  need one; the sync cost is not worth it yet.

## The pattern library

**File:** `skills-public/dothesis-humanizer/references/ai-patterns.md`

Each entry carries:

| Field | Purpose |
|---|---|
| Number + name | So a review can say "this paragraph trips 7 and 23" |
| Watch-words, VI and EN | The actual lexical trigger, in both languages |
| Why it is a tell | One line; no padding |
| Before → After | In academic register, not blog register |
| `Do not touch when` | The guard that stops the fix becoming a defect |

### What carries over from the 35

Inflated importance; shallow `-ing` / `việc …` analysis; vague sources;
formulaic challenges-and-outlook; overused AI vocabulary; avoiding *is/are*;
not-X-but-Y; forced groups of three; false from-X-to-Y ranges; too much bold;
bold mini-heading lists; emojis; chatbot residue; knowledge-cutoff disclaimers
and speculative gap-fill; filler phrases; stacked qualifiers; generic positive
endings; fake deeper truths; announcing the next point; a heading repeated in
the sentence below it; forced punchlines; formulaic sayings; fake-candid
openings; answering unraised objections; rejecting fake alternatives.

### What is dropped, and why

- **Active voice (blader §13).** A methods section uses passive legitimately
  ("dữ liệu được thu thập"). Pushing active is a register error.
- **Title case in headings (§17).** The university template decides heading
  case, not a style guide.
- **Name-dropping (§2) and sales language (§4) as written.** Their prescribed
  fix is deleting the claim. `frozen_check.py` fails any rewrite that drops a
  citation or a number, so these become *flag it for the writer*, never *cut it*.

### What is inverted

blader §11 says stop renaming the same subject. In a thesis the opposite holds:
a construct must keep exactly one name, and synonym-cycling `Chất lượng dịch vụ`
into `yếu tố chất lượng` breaks the variable. It becomes a never-touch rule, and
the file says so explicitly, because the instinct it overrides is a common one.

### What is added

Numbered and exampled for the first time, lifted from `_REWRITE_PROMPT` where
they already live as prose: gerund stacking, the inline-heading shape, metronome
connectors, comma-chains past ~40 words, repeated `Kết quả cho thấy` templates,
and the `đáng kể` / *significant* statistical-term caution.

### What not to flag

A first-class section, and the largest gap in what we ship today. The skill
already argues that the safest rewrite is often no rewrite; it gives the agent
no list of things to leave alone. Academic edition: technical terms that read as
inflated, passive voice in methods, mandated template phrasing, a Vietnamese
author's correct-but-unidiomatic English (protected in `_NATURALNESS_EN`, stated
in no skill file), a single em dash, deliberate repetition, and any token the
frozen check owns.

Patterns are numbered contiguously from 1. The count fell out of the writing at
32. One test asserts contiguity; a second pins 32, because the number is quoted
in both `SKILL.md` files and in the web download card, and a tripwire is cheaper
than four silent drifts.

## Where it lives

Source of truth is the public copy. `scripts/build_public_skill.py` gains a sync
step that writes `skills/dothesis-humanize/references/ai-patterns.md` from it,
and a test asserts the two are byte-identical.

A symlink would be the obvious alternative and is wrong here: the file has to
survive `zipfile` and a stranger's unzip, and blader's own validator forbids a
symlinked skill file after they shipped that bug.

Both `SKILL.md` files gain one short pointer — read the reference when a passage
still reads flat, or when you need to name what is wrong with it. Progressive
disclosure keeps both prompts near their current length.

Free and paid copies are byte-identical on purpose. That matches the stance the
public skill already takes ("the real thing, not a teaser"); the product
differentiator is anchors, document-wide state and memory, which a chat window
cannot reach.

## Packaging

Inside `skills-public/dothesis-humanizer/`:

- `.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json`, so the
  extracted folder installs as a Claude Code plugin.
- `agents/openai.yaml` — display name and default prompt for non-Claude loaders.
- `INSTALL.md`, VI and EN: Desktop upload, `~/.claude/skills/` copy, plugin add.

**Verification gate:** the manifests ship only if `claude plugin validate` passes
on the extracted directory. If a local-path marketplace does not validate, the
manifests come out and `INSTALL.md` documents only the two paths that are proven.

## Tests

`tests/test_public_skill.py` gains:

1. `ai-patterns.md` exists in the public skill and is referenced by `SKILL.md`.
2. Pattern headings are numbered contiguously from 1.
3. The internal copy is byte-identical to the public one.
4. The shipped `web/public/skills/dothesis-humanizer.zip` matches its sources —
   today it can go stale with no signal.
5. The archive contains no `__pycache__` or `.pyc`. One is sitting in
   `skills-public/` right now; `build_public_skill.py` skips it, and nothing
   proves that.

## Web surface

`HumanizeTool.tsx` keeps its download button and gains the three install paths
beneath it, through new `tools.skill.*` keys in `web/app/lib/i18n/messages/vi.ts`
and `en.ts`.

## Attribution

Patterns are written in our own words from Wikipedia's *Signs of AI writing*
(CC BY-SA 4.0), crediting that page and `blader/humanizer` (MIT) as the prior art
that organized it. No paragraphs are copied, which keeps the paid prompt
unencumbered by share-alike.
