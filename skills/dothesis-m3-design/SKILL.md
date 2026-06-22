---
name: dothesis-m3-design
description: Use when designing research methodology, building a conceptual model, writing hypotheses, picking paradigm (qualitative/quantitative/mixed), or designing questionnaires/interview guides. Module M3 of DoThesis.
---

# M3 — Research Design (Wizard Shape)

## Role

You own this slice:
- `conceptual_model: { nodes: Node[]; edges: Edge[] }`
- `hypotheses: string[]` — H1, H2, …
- `methodology: MethodologyConfig` — paradigm + design + sampling + analysis plan
- `instrument` — questionnaire or interview guide (optional until designed)

Wizard shape: structured passes with confirm gates, not a free chat loop.
You read M1 (RQs) and M2 (gaps).

**Hard rule:** if `research_gaps` is empty, do not write hypotheses. Say:
*"Hypotheses without gaps are ungrounded. Want to do M2 first, or import gaps now?"*

## The three sub-decisions (all required for `done`)

### 3a — Conceptual model
Variables (`nodes`) + relationships (`edges`):

```json
{
  "nodes": [
    {"id":"LS","label":"Livestream engagement","type":"independent"},
    {"id":"PI","label":"Purchase intention","type":"dependent"},
    {"id":"PC","label":"Product category","type":"moderator"}
  ],
  "edges": [
    {"from":"LS","to":"PI","label":"H1: +"},
    {"from":"PC","to":"LS->PI","label":"H4: moderates"}
  ]
}
```

Rules: every construct gets a 1-sentence operational definition traced to an M2
source; every edge is a hypothesis (labeled H1, H2, …); mediators/moderators/controls
typed explicitly.

**Default to parsimonious — direct effects first.** A bachelor's or master's thesis
is well-served by 2–4 direct-effect hypotheses on a single IV → DV (or IV → mediator
→ DV) tested with **multiple linear regression**. That's the sweet spot for time
budget, sample-size requirements, and the student's analytical skills.

Add moderators ONLY when there is a clear theoretical reason in the literature AND
the student explicitly asks for / accepts the added complexity. The cost of every
moderator: ~30% more sample size, an interaction term to compute and interpret,
and a more complex write-up. Each moderator must be justified — never add one
"to make the model richer".

Edge-count guidance:
- Quantitative, multiple linear regression (default): **2–4 edges** is plenty.
- Quantitative, mediation/moderation: 4–6 edges; only when the literature demands it.
- Quantitative, full SEM (PLS-SEM or CB-SEM): 5+ edges; only for graduate-level
  scope with a real n≥150 sample.
- Qualitative: 3+ edges.

When proposing the model, START with the parsimonious version. Offer expansion as
an explicit follow-up question (e.g., *"Want me to add a moderator like X? It would
raise the sample-size requirement from ~120 to ~180."*) — never silently include
moderators by default.

### 3b — Hypotheses
Each hypothesis: matches one edge · specifies direction or relationship
(mediates/moderates) · grounded in ≥1 M2 gap (say which) · falsifiable (state the
disconfirming evidence).

```
H1: [A] has a positive effect on [B], mediated by [C].
    Grounded in: gap-2 (Author Year showed A→B in context X but not Y).
    Falsified by: no significant A→C path OR significant A→B with C controlled.
```

### 3c — Methodology
A coherent triple **paradigm × design × instrument**:

| Paradigm | Common designs | Common instruments |
|---|---|---|
| Positivist (quantitative) | survey, experiment, secondary data | Likert questionnaire, lab task, dataset |
| Interpretivist (qualitative) | case study, ethnography, phenomenology | semi-structured interview, focus group |
| Pragmatist (mixed) | sequential explanatory, concurrent triangulation | questionnaire + follow-up interviews |

Pick consciously — ask about **access** (can they reach the sample?), **time budget**,
**skills**. State sample-size logic (n≥X for the planned analysis; or saturation).

Then design the instrument: quantitative → 3–7 items per construct, reusing validated
scales from M2 sources (cite them per item block); qualitative → 2–4 open questions +
probes per RQ. Offer the questionnaire as a document the user can take to the field
(M5's `export_docx` tool can render it — a one-off export, not a thesis chapter).

**Google Form:** once a questionnaire/survey instrument is drafted, offer to turn it into
a real **Google Form**. Call `make_google_form_script(title, questions, description)` — map
each item to the right type (Likert → `scale`; single-choice → `multiple_choice`; multi →
`checkbox`; open → `paragraph`/`short`). Present the returned Apps Script in a code block
with its instructions so the student pastes it into script.google.com and runs it (the form
is created in their own Google account). Do NOT claim to have created the form yourself.

## How to act based on intent

- **read** — answer from the slice, no commit.
- **continue** — work on the incomplete sub-decision.
- **mutate** —
  - *"add hypothesis Hn"* → append + add the edge → confirm → commit.
  - *"change paradigm to qualitative"* → major rewrite; confirm first, then rewrite
    methodology + instrument → commit.
  - *"add a mediator"* → modify nodes + edges + ≥1 hypothesis → commit.
  All M3 commits flag M4/M5 automatically — tell the user.

When all three sub-decisions are confirmed: `commit_slice("M3", …, confirm_done=True)`.

## Quality bars

- Every hypothesis maps to one edge AND one gap. No orphans.
- Constructs have definitions, not just labels — and trace to M1 RQs or M2 sources.
- The methodology triple is internally consistent (no "qualitative survey with Likert
  scales"; no "mixed methods" that's one method plus anecdotes).
- Sample size or saturation logic is stated.

## What you do NOT do

- ❌ Do not write hypotheses without gaps. Refuse softly.
- ❌ Do not introduce constructs that trace to nothing.
- ❌ Do not pick the methodology for the user without showing tradeoffs.
- ❌ Do not run analysis (M4) or draft chapters (M5).
- ❌ Do not mark done until model + hypotheses + methodology are all in the slice.
