---
name: dothesis-bootstrap
description: Use when starting a new thesis project, when no project state exists yet, or when the user has existing materials (topic, references, gaps, model, data, draft) to import.
---

# DoThesis Bootstrap (Entry Wizard)

## Role

You run ONCE per project, before any module work. Your job: seed the project state and
pick the entry focus. This is **not a parallel flow** — it's a one-time seed, then
normal routing (the `dothesis` skill) takes over.

## The flow

```
1. Ask: "What do you already have?"
2. Import each declared item into the right module's slice
3. Reconcile dependency holes
4. Compute entry focus (first module that needs attention)
5. Commit the seed, show the status list, hand off
```

## Step 1 — Declare

The web client's entry wizard collects what the user already has BEFORE
dropping into chat, and sends a structured first message:

```
/bootstrap

Topic: <text>
References:
<paste>
Gaps:
<paste>
Model:
<paste>
Instrument:
<paste>
Data:
<paste>
Draft:
<paste>
```

When you see a message starting with `/bootstrap`, SKIP the question.
Parse each labeled section from the message body and proceed to Step 2
(Import) directly. The labels (`Topic:`, `References:`, etc.) map 1-to-1
to the declared-item ids in the table below.

If the user did NOT come through the wizard (no `/bootstrap` prefix on
the first message), ask them the question instead — same list:

> "Before we begin — which of these do you already have for your thesis? Pick any that apply:
> - **topic** — title or research questions
> - **references** — PDFs / DOI list of papers you've read
> - **gaps** — already-identified research gaps
> - **model** — conceptual model / hypotheses / framework diagram
> - **instrument** — questionnaire or interview guide
> - **data** — collected results (`.sav`, `.csv`, transcripts)
> - **draft** — partial Word/PDF draft of any chapter
> - **none of these** — start from scratch"

Wait for the answer. Then for each declared item, ask the user to paste content or
upload a file.

## Step 2 — Import (seed into context_store)

Use this declare → seed map. Import via the **module's own tools** — don't invent a
second pipeline.

| Declared | Module | Seeds | Import with | Resulting status |
|---|---|---|---|---|
| topic | M1 | `research_title`, `research_questions` | paste / type | `done` |
| references | M2 | `literature_sources` | `parse_reference(file or DOI)` per source | `in_progress` *(gaps not derived yet)* |
| gaps | M2 | `research_gaps` (with `supporting_papers` + page refs if cited) | paste | `done` |
| model | M3 | `conceptual_model` (nodes + edges), `hypotheses` | paste / describe | `done` |
| instrument | M3 | `instrument` (questionnaire / interview guide) | upload | `done` |
| data | M4 | raw file reference + detected schema | `run_stats(op="detect", file=…)` | `in_progress` |
| draft | M5 | `final_sections` (split by heading) | upload | `in_progress` |

Store compact schemas, not full datasets. For PDFs always go through
`parse_reference` — it returns validated metadata (title, authors, year, DOI,
abstract); do not transcribe citations from memory.

## Step 3 — Reconcile dependency holes

**Same propagation logic as a mutate, applied at intake.** After all imports:

| Condition | Action |
|---|---|
| `conceptual_model` present **and** `research_gaps` absent | `M2 = needs_review` — *"H1/H2 not yet grounded in a gap."* |
| data present **and** `conceptual_model` absent | `M3 = needs_review` — *"data without a model — what are you testing?"* |
| `final_sections` present **and** any of M1–M4 `locked` | that module `= needs_review` — *"draft references decisions not in the project state."* |
| `literature_sources` present **and** `research_gaps` absent | M2 stays `in_progress` (not a hole — gaps just not derived yet) |

## Step 4 — Compute entry focus

Iterate M1 → M5, pick the first module that needs attention:

1. First `needs_review` module (a dependency hole — most urgent)
2. Else first `in_progress`
3. Else first `locked`
4. Else M5 (everything done — go write)

## Step 5 — Commit and hand off

One `commit_slice` per imported module (reason: "bootstrap"), statuses as computed.
Then show the status list plainly:

> "I've seeded your project:
> - M1 ✅ done — title + RQs locked in
> - M2 ⚠ needs review — you have a model but no gaps backing H1/H2
> - M3 ✅ done — model + hypotheses imported
> - M4 🔒 locked — no data yet
> - M5 🔒 locked
>
> **Opening at M2** — let's build the literature so your hypotheses are grounded.
> Skip ahead if you'd rather (it's a recommendation, not a wall)."

If the user declared "none of these": just commit `M1 = in_progress`, focus M1, and
start the M1 wizard — no ceremony.

## Critical invariants

1. **Soft entry, not forced.** Entry focus is a recommendation; obey the user.
2. **Dependency holes are caught here, not later.**
3. **Reuse the module slice shapes** — no parallel data structures.
4. **`needs_review` ≠ `locked`.** Hole modules are open for work, just flagged.

## What you do NOT do

- ❌ Do not do module work yourself (no generating gaps, no drafting sections).
  You're the seed function.
- ❌ Do not skip reconciliation — holes MUST be flagged before handoff.
- ❌ Do not run more than once per project.
