# Field-It Survey Pipeline Design (F7)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Relationship:** The commercial flywheel — DoThesis designs the instrument, the user's own
survey tools (fillform.info VN / survify.net intl, `project_sibling_products` memory) collect
the data, structured data returns and feeds M4. Builds on the existing `make_google_form_script`
tool and M3's `instrument` slice.

## Problem

M4 is unfixable if the instrument or the collected data is bad, and data collection is the
longest, riskiest phase of a quantitative thesis. Today DoThesis can emit a Google Form script
but does nothing to (a) vet questionnaire quality before fielding, (b) compute a defensible
sampling plan, or (c) route collection through the team's own survey rails where quality
metadata comes back structured.

## Goals

1. **Questionnaire Doctor** — an M3 instrument audit before fielding: double-barreled/leading
   items, back-translation check for adapted scales, reverse-coded coverage per construct,
   Likert-anchor consistency, attention checks, and a **scale-provenance table** (every adapted
   scale cites its source). Advisory + a rubric criterion.
2. **Sampling plan** — from the study's model complexity + target method, compute a defensible
   target n (10× rule + inverse-square-root; CB-SEM minimums) plus quota/screening logic and a
   realistic collection timeline.
3. **Field-It handoff** — once the instrument passes, generate the survey structure and hand off
   to fillform/survify with the sampling plan, returning a collection link. Structured responses
   + quality metadata (completion time, straight-lining, attention-check pass) come back and
   feed M4's Output Sanity Layer (F8).

## Non-goals

- Not building a survey platform — fillform/survify already exist; this integrates.
- Not forcing survify — the Google Form path (existing tool) stays as a free fallback.
- No PII handling beyond what the survey tools already do.

## Design

### Questionnaire Doctor

- `audit_instrument(instrument, hypotheses, constructs) -> dict` in `agent/tools/instrument.py`:
  deterministic lint (double-barreled via conjunction heuristics, missing reverse-coded per
  construct, anchor inconsistency, attention-check presence) + returns a structured findings list
  and a scale-provenance skeleton the student fills. Content playbook in
  `skills/dothesis-m3-design/references/questionnaire-quality.md`.
- Feeds F3 rubric as an `instrument_quality` criterion.

### Sampling plan

- `sampling_plan(context_store) -> dict` in `agent/tools/sampling.py` (pure): reads M3
  method + model size (paths/indicators) → `{target_n, rationale, method_rule, screening,
  timeline_weeks}`. Encodes the same power logic as F8's Methods Pre-Flight (share the helper).

### Field-It handoff

- `create_survey_handoff(instrument, sampling_plan, provider) -> dict` — a POST tool/route
  (`api/app/routers/field_it.py`, POST-only) that builds the survey payload and returns a
  deep link / prefilled draft for fillform (VN) or survify (intl), plus a `collection_id`.
- A return webhook/poll (`POST /field-it/results`) ingests structured responses + quality
  metadata into `m4_analysis.analysis_results` (or a raw dataset the student then analyzes),
  tagged with quality flags for the Output Sanity Layer.
- Provider selection defaults from language/region (VN → fillform, else survify).

## Data flow

```
M3: instrument drafted → audit_instrument (Questionnaire Doctor) → fix findings
   → sampling_plan(store) → target n + timeline
   → create_survey_handoff → fillform/survify link  (cross-sell)
collect (weeks) → POST /field-it/results → structured data + quality metadata → M4
M4: Output Sanity Layer (F8) uses the quality metadata to flag bad responses
```

## Error handling

- `audit_instrument` / `sampling_plan` pure and total; advisory (never blocks fielding).
- Handoff is best-effort: a provider API failure returns the Google Form fallback script
  (existing tool) so the student is never stuck.
- Results ingestion validates shape; malformed payloads are rejected (4xx) without corrupting M4.

## Testing

- `audit_instrument`: a double-barreled item ⇒ flagged; a construct with no reverse-coded item ⇒
  flagged; a clean instrument ⇒ no findings.
- `sampling_plan`: PLS-SEM with k paths ⇒ target_n follows the rule; CB-SEM ⇒ minimum applied.
- `create_survey_handoff`: VN language ⇒ fillform provider; returns a link + collection_id;
  provider failure ⇒ Google Form fallback.
- `POST /field-it/results`: valid payload ⇒ writes M4 data + quality flags; bad payload ⇒ 4xx.
- POST-only routes; api tests via `./run.sh`.

## Migration / rollout

1. `questionnaire-quality.md` content + `audit_instrument` tool + F3 rubric criterion.
2. `sampling_plan` tool (shares power helper with F8 Methods Pre-Flight).
3. `create_survey_handoff` tool/route + provider selection + Google Form fallback.
4. `POST /field-it/results` ingestion + quality-flag tagging for F8.

## Dependencies

- Existing `make_google_form_script` (`agent/tools/forms.py`), M3 `instrument` slice.
- **F8** — shares the power/sample-size helper; F8's Output Sanity Layer consumes the returned
  quality metadata.
- **F3** — gains `instrument_quality` criterion.
- fillform/survify APIs (`project_sibling_products` memory).
