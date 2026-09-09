# Questionnaire quality checklist (before you field)

Vet the instrument BEFORE collecting a single response. A bad item cannot be
fixed after the fact — it silently corrupts the dataset. The `audit_instrument`
tool automates the mechanical parts of this list; use this reference to fix what
it flags and to catch what a linter can't.

## Item-level checklist

- **Double-barreled** — one item, one idea. "The app is fast *and* reliable"
  forces two judgments into one answer. Split it. (The lint flags EN `and/or`
  and VI `và/hoặc`.)
- **Leading / loaded** — don't presuppose the answer ("How much do you love the
  new design?"). Keep the stem neutral.
- **Ambiguous / jargon** — every respondent should read the item the same way.
  Avoid double negatives and undefined acronyms.
- **Anchor consistency** — keep one response scale per block (e.g. 1=Strongly
  disagree … 5=Strongly agree). Don't mix 5-point and 7-point scales without a
  reason; label both endpoints.
- **Reverse-coded coverage** — include at least one reverse-worded item per
  construct so careless / straight-line responding is detectable.
- **Attention checks** — at least one instructed-response item ("Select
  'Strongly agree' to show you're reading") to screen inattentive respondents.
- **Back-translation for adapted scales** — if you translated or adapted a
  published scale (e.g. EN → VI), back-translate and reconcile before fielding.
- **Screening** — put eligibility questions first so ineligible respondents are
  excluded before they consume the survey.

## Structural defects (check these first — they are fatal, not cosmetic)

Item wording above is what a linter catches. These are defects in how the instrument is
*assembled*, and they are the ones that actually appear in student questionnaires. All
six are visible before a single response exists; none can be repaired afterwards. Lead
with the consequence when you raise one — the student needs to see what it costs them,
not a rule number.

- **Screening question not isolated.** Eligibility questions sitting in the same section
  as the Likert blocks means ineligible respondents still fill in the whole model, and
  the student has to hand-filter them out later. Put screening in its own section, with
  branching that ends the survey for a disqualifying answer.
- **Mixed response formats inside one construct.** Every observed item of a construct
  must share one response scale. A construct measured by one multi-select question, one
  single-choice question and one Likert item cannot be aggregated into a construct score
  at all — and therefore cannot enter a correlation, a regression, or a measurement
  model. If the student wants those questions, they belong in descriptive statistics,
  not in the model.
- **Fewer than three observed items per construct.** Three is the working minimum for
  reliability estimation and for the construct to be identified in a measurement model.
  Two items give an α that is not meaningfully interpretable; one item is not a latent
  construct.
- **A model construct missing from the questionnaire.** Cross-check the instrument
  against `conceptual_model.nodes` every time either changes. A construct in the diagram
  with no items in the form is discovered at analysis time, when re-fielding is
  impossible.
- **A second-order construct given its own observed items.** A higher-order construct is
  measured *through* its first-order dimensions; it does not get a separate item block.
  Writing one both double-counts the construct and breaks the two-stage estimation.
- **Naming drift between model and questionnaire.** The construct codes in the diagram,
  the item prefixes in the form, and the column names in the exported dataset must be the
  same tokens. Drift here is the single most common cause of an analysis that cannot be
  run without manual re-mapping.

Also confirm before fielding: **reverse-worded items are recorded as such**, so they are
recoded before any construct score is computed. An un-flagged reverse item silently
depresses α and can invert a path.

## Scale-provenance table

For every construct, record where the scale came from. An empty row is a
red flag: an un-sourced measure is hard to defend in the viva.

| Construct | Source (author, year) | Adapted from | Back-translated? |
|-----------|-----------------------|--------------|------------------|
| PE        | Venkatesh et al. 2003 | UTAUT PE     | Yes              |
| …         |                       |              |                  |

`audit_instrument` returns this table pre-seeded with one empty row per
construct — fill each row before you field.

## Advisory, not a gate

These findings never block fielding. They are guidance: fix what you can, note
what you can't, and field with your eyes open.
