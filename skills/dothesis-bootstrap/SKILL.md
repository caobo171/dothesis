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

### Drop-first intake (no labeled sections)

The drop-first `/new` page sends `/bootstrap` with **no labeled sections** —
instead the user has attached/uploaded files (a draft, papers, a proposal) and
maybe a free-text note. When the `/bootstrap` message has no `Topic:` /
`References:` / … labels, do this instead of parsing labels:

1. **Read every attached/uploaded file.** Each upload is project-scoped and
   mirrored to the workspace at `uploads/<filename>` — list that directory and
   `read_file` each one (or use the attachment the message carries). Don't
   guess from the filename; open the content.
2. **Classify what you find into module slices.** Map each file's content to
   the module(s) it covers using the same declare → seed table below — judge
   it yourself rather than asking the user to label:
   - title / research questions / objectives → **M1 topic**
   - a reference list, cited papers, a lit-review section → **M2 literature**
   - identified gaps → **M2 research_gaps**
   - a conceptual model / hypotheses / framework → **M3 design**
   - a questionnaire / survey instrument → **M3 instrument**
   - a dataset or statistical results section (SPSS/SmartPLS) → **M4 analysis**
   - drafted chapters / prose → **M5 writing**
   A single file (e.g. a full draft) usually covers several modules — split it.
3. Fold in the free-text note (if any, under `My own notes:`) the same way.
4. Then proceed to Step 2 (Import) → Step 3 (Reconcile) → Step 4 (Focus) →
   Step 5 (Commit + show the status list). The status list IS what the page's
   analysis screen renders, so be accurate about each module's status.

If a `/bootstrap` message has neither labeled sections nor any files (only a
note, or nothing), classify the note as above; if there's truly nothing,
treat it as "none of these" (Step 5).

If the user did NOT come through the wizard (no `/bootstrap` prefix on
the first message), ask them the question instead — same list:

> "Before we begin — which of these do you already have for your thesis? Pick any that apply:
> - **topic** — title or research questions
> - **references** — PDFs / DOI list of papers you've read
> - **gaps** — already-identified research gaps
> - **model** — conceptual model / hypotheses / framework diagram
> - **instrument** — questionnaire / survey instrument
> - **data** — collected survey data (SPSS `.sav`, `.csv`) for SmartPLS / SPSS
> - **draft** — partial Word/PDF draft of any chapter
> - **none of these** — start from scratch"

Wait for the answer. Then for each declared item, ask the user to paste content or
upload a file.

## Step 1b — Triage (two questions, before any module work)

The declare list tells you what the student *has*. It does not tell you what they
**need**, and those diverge constantly. Resolve both before handing off — one
`[OPTIONS]` row each, so it costs two clicks.

**Q1 — does this thesis need inferential statistics at all?**

> "Bài của bạn chỉ cần thống kê mô tả (tần suất, tỷ lệ, trung bình), hay có mô hình
> nghiên cứu cần chạy kiểm định?"
>
> `[OPTIONS:needs_inferential] Có mô hình, cần chạy kiểm định | Chỉ thống kê mô tả | Chưa rõ, tư vấn giúp mình`

If the answer is descriptive-only, say so plainly and do **not** build a conceptual
model or push toward SEM — frequencies and means are a complete answer for some
assignments, and saying that early saves the student weeks. Seed M1 and skip the M3
model work. If "chưa rõ", ask what the supervisor/outline requires and decide from that.

**Q2 — where are they stuck?** (only for the model case)

> `[OPTIONS:research_stage] Đã chốt mô hình, đang/sắp thu khảo sát | Đang xây đề tài, chưa chốt mô hình | Đã có data nhưng chạy ra kết quả xấu`

| Answer | Entry focus | First thing you do |
|---|---|---|
| Đã chốt mô hình | M3 | QA the instrument before a single response is collected (`audit_instrument` + the structural defects in `dothesis-m3-design/references/questionnaire-quality.md`) |
| Đang xây đề tài | M1 or M2 | Normal M1 → M2 → M3 sequence |
| Data xấu | M4 | `run_stats(op="screening")` first — careless responders and un-recoded reverse items explain most "ugly" datasets |

This answer **overrides Step 4's computed focus** when the two disagree: a student who
says their data is failing opens at M4 even if M2 is technically incomplete. Position is
a recommendation, not a wall.

Also note anything they say about their supervisor here — an approved model, a required
software, a pending approval. That constraint outranks your own recommendations for the
rest of the project (see the `dothesis` skill, *Supervisor precedence*).

## Step 2 — Import (seed into context_store)

Use this declare → seed map. Import via the **module's own tools** — don't invent a
second pipeline.

| Declared | Module | Seeds | Import with | Resulting status |
|---|---|---|---|---|
| topic | M1 | `research_title`, `research_questions` | paste / type | `done` |
| references | M2 | `literature_sources` | `parse_reference(file or DOI)` per source | `in_progress` *(gaps not derived yet)* |
| gaps | M2 | `research_gaps` (with `supporting_papers` + page refs if cited) | paste | `done` |
| model | M3 | `conceptual_model` (nodes + edges), `hypotheses` | paste / describe | `done` |
| instrument | M3 | `instrument` (questionnaire / survey) | upload | `done` |
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
