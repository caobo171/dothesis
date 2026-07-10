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
