# Anchor sourcing prompt — English path

Paste everything from "## Task" down into a fresh Claude Code session in this
repo. Companion to `anchor-sourcing-prompt-vi.md`; the criteria differ enough
that they are separate documents.

The English anchor directory is currently **empty** — `load_anchors('en')`
returns `[]`. Every English document therefore runs with no anchor at all, which
is the configuration measured as harmful below.

---

## Task

Find and install English style anchors for the DoThesis humanize pass, into
`skills/dothesis-humanize/references/anchors/`.

Read these first — they carry the binding constraints:
- `skills/dothesis-humanize/references/anchors/README.md`
- `skills/dothesis-humanize/references/anchors/PROVENANCE.md`
- `docs/anchor-sourcing-prompt-vi.md` (the 3-step index test applies here too)

## Why this is the highest-value work in the product right now

Measured on a real submission, 2026-08-06/07. A UK business dissertation written
in English by a Vietnamese student was scored by Turnitin before and after the
humanize pass:

| | Turnitin AI score |
|---|---|
| Original | **23%** |
| After humanize | **30%** |

Paired analysis on the *same* paragraphs, using Turnitin's own highlight spans:

| Group | Before | After | Change |
|---|---|---|---|
| Paragraphs the pass rewrote (n=40) | 16.4% flagged | **36.6%** | **+20.2 pts** |
| Control — byte-identical paragraphs (n=226) | 20.8% | 20.9% | +0.1 pts |

The rewrite **more than doubled** the flag rate on the text it touched. The
control moving 0.1 points confirms the measurement, not noise.

This is independently corroborated. Zhao (2025, UC Davis, real Turnitin access)
ran human-written work through an LLM for *grammar polish only*: case studies and
personal writing stayed at 0%, but lab reports and essays jumped from roughly 25%
to 50%+. Same mechanism, same direction.

### The cause, and what it demands of an anchor

Look at what the pass actually did:

```
OLD  To test the mediating role of job satisfaction between each leadership style…
NEW  To test whether job satisfaction mediates the relationship between…

OLD  …across age groups and levels of length of service.
NEW  …across age groups and different lengths of service.

OLD  RQ4: How much of the effect of each leadership style is transmitted through…
NEW  RQ4: To what extent is the effect of each leadership style transmitted through…
```

The originals are slightly awkward — *"levels of length of service"*, *"How much
of the effect"*. That is a real non-native writer's English, and it is the human
fingerprint. The rewrite sanded it off into canonical native-academic phrasing:
*"mediates the relationship between"*, *"To what extent"*. Those are precisely
the collocations a language model emits.

**So the operative rule for English anchors, and it is counterintuitive:**

> The anchor must NOT be polished native-speaker academic English.

Polished native English is the model's default output register. An anchor written
in it teaches the rewrite to move *toward* the thing being detected. The students
are Vietnamese researchers writing English; the anchor should sound like a
competent non-native academic writer — correct and professional, but with the
slightly unidiomatic collocations, uneven rhythm and occasional over-formality
that real L2 academic English carries.

Keep every imperfection. Do not tidy the anchor.

### One English-specific risk

Turnitin shipped **AI-bypasser detection on 27 Aug 2025**, trained on the
signatures of named humanizer tools, and it is **English-only**. The report now
carries a distinct "modified by a bypasser tool" label. No credible published
measurement of humanizer effectiveness against Turnitin exists after that date —
every peer-reviewed evasion study predates the feature. Assume the English path
is the exposed one and that any vendor claiming a 2026 bypass rate is fabricating.

## The "off-distribution" criterion in English

In Vietnamese, "not in the training corpus" is roughly achievable. In English it
is not — English academic text is the most heavily crawled material there is.
Do not chase literal absence; chase these three, in order:

1. **Real human authorship.** Never generated, never a model's rewrite.
2. **Register distance from the model's default output** for this task.
3. **Rhythm match to the actual student** — L2 academic English, not native.

This is why the archived bake-off found pre-1928 prose works despite Project
Gutenberg being squarely inside every training corpus: what matters is that the
cadence is far from what the model produces by default, not that the text is
unseen.

## Source tiers — work down, do not skip to tier 3

### Tier 1 (best) — English-language articles by Vietnamese / regional authors, pre-2022

This is the strongest fit and where most effort should go. It matches register,
matches the student's own L2 English, and is far less indexed than Western
journals.

Search these (all publish English or bilingual, most pre-2022 archives are open):
- Journal of International Economics and Management (Foreign Trade University)
- VNU Journal of Science: Economics and Business
- Journal of Economics and Development (National Economics University)
- Can Tho University Journal of Science
- Ho Chi Minh City Open University Journal of Science
- Dalat University Journal of Science
- Hue University Journal of Science: Economics and Development
- Danang University journals
- Regional peers pre-2022: Philippine, Indonesian, Thai and Malaysian management
  and hospitality journals

Prefer quantitative business / management / hospitality / HR papers reporting
survey work — that is the register we actually rewrite.

### Tier 2 — scanned or print-only English dissertations, pre-2022

Institutional repositories where the PDF is an image scan with no text layer are
the highest-value rows: very likely absent from text corpora. Verify the year
from the title page, not from the file date.

### Tier 3 (fallback only) — pre-1928 public domain prose

Russell, Mill, James, Strunk. Licence-clean and validated by the archived
bake-off, but **register-mismatched for a thesis** — never route a results
chapter to one. Acceptable only for general expository passages, and only if
tiers 1 and 2 come up empty. Record clearly in the manifest `desc` that it is a
fallback.

### Never

Wikipedia, blogs, news, SEO content, textbook prose, anything post-2022 without
known provenance, anything on 123doc / tailieu.vn / scribd / academia.edu /
ResearchGate / studocu, and anything with signs of AI drafting or machine
translation. Modern CC-licensed web text is the configuration measured as
*worse than doing nothing*.

## Mandatory index test — 3 steps per source, no exceptions

The Vietnamese round rated five sources "not indexed"; re-testing found two
outright wrong and one unusable. **The first test sentence passed in both false
cases.** One sentence is not enough.

1. Quote-search a distinctive sentence (12–20 words, numbers or proper nouns
   help).
2. Quote-search a **second sentence from a different section**. Mandatory.
3. Search **title + author names** — this is what catches ResearchGate,
   academia.edu and aggregator mirrors.

Then: search the author names plus the topic, to catch a near-duplicate paper by
the same authors that *is* indexed. If one exists, reject — the voice is in the
corpus regardless.

Accept only when all four come back clean. Record every result.

## Slots to fill

Match the structure of the documents we actually process (UK-style quantitative
business dissertation). One anchor per slot, **each from a different paper**.

| Priority | id | Register |
|---|---|---|
| 1 | `en_results_sem` | Results — reliability, validity, path coefficients, hypothesis verdicts (PLS-SEM / CFA / regression) |
| 2 | `en_methodology_survey` | Methodology — instrument adaptation, sampling, administration, analysis plan |
| 3 | `en_discussion` | Discussion — interpreting findings against prior studies |
| 4 | `en_litreview` | Literature review — study-by-study prior research |
| 5 | `en_intro_problem` | Introduction — problem statement, gap, contribution |

250–400 words each. Prose only.

## Extraction rules

Two-column justified journal PDFs corrupt silently in two ways: `pdftotext`
interleaves the columns into single lines, and `-x/-W` cropping clips the last
glyph of any line reaching the gutter. Use pdfminer layout analysis, assigning
each text box to a column by which side of the page midpoint its centre falls on.

Then strip running heads, page numbers, table captions and "Source:" notes;
re-flow paragraphs (a short line ending in a full stop ends a paragraph); rejoin
words hyphenated across a line break; and truncate at the last full stop so the
anchor never ends mid-sentence.

**Read the passage back before saving.** A clipped word teaches broken English.

Exclude: equations, regression formulae such as `Y = 0.338*X1 + …`, tables,
bulleted lists. Asterisks in an anchor can induce markdown in the output — a bug
already fixed once, do not reintroduce it via anchor content.

## Install

1. Save `<id>.txt`, UTF-8, prose only, no front matter.
2. Add to `manifest.json` with `"language": "en"`. Write `desc` as instructions
   to a picker — `"PICK FOR: … NOT FOR: …"` — describing the content type, not
   the source.
3. Update `PROVENANCE.md`: full citation, URL, all 4 test results, and the
   copyright/licence line **quoted verbatim** from the page. Never infer a
   licence; if none is stated, write "not stated".
4. Record rejected sources and why, so nobody re-imports them.
5. Verify loading:

```bash
./api/run.sh python -c "from orchestrator.tools.humanize import load_anchors; \
print([(a['id'], len(a['text'].split())) for a in load_anchors('en')])"
```

6. Confirm the Vietnamese path is untouched — it must still return 4:

```bash
./api/run.sh python -c "from orchestrator.tools.humanize import load_anchors; \
print(len(load_anchors('vi')))"
```

7. Run the suite:

```bash
cd api && ./run.sh python -m pytest ../tests/test_humanize.py -q
```

`test_humanize.py` has **2 pre-existing failures** unrelated to anchors
(`test_a_translated_rewrite_is_rejected_and_the_original_kept`,
`test_content_expansion_is_rejected`). Do not fix them. Confirm only that no
*new* failures appear.

## Do not

- Do not write an anchor yourself or have a model produce one. Model output as an
  anchor for model output is a closed loop.
- Do not correct grammar, smooth phrasing, or summarise a chosen passage. The
  irregularities are the entire value.
- Do not take more than one anchor from a single paper.
- Do not use a famous author's recent work.
- Do not bypass paywalls or logins, mass-download, or contact anyone.
- Do not guess a licence.

## Report

1. Sources accepted: citation, URL, year, all 4 test results.
2. Sources rejected, with reasons.
3. Anchors installed, word counts, slots filled.
4. Output of both load checks and the test run.
5. Say plainly if most of what you found was indexed, or if only tier 3 was
   reachable. Do not lower the bar to fill slots — an anchor that fails the
   criteria is measurably worse than no anchor, and no anchor is the current
   state.
