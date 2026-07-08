# Cross-Session Memory Design

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Sequence:** Spec 4 of the follow-on set. Owns the read contracts (`advisor_feedback`,
`institution_profile`) that the quality-evals spec consumes, and drives the coaching layer
via `flag_blocker` (Spec 2). Implements the "most important" advisor-feedback loop
(`project_advisor_feedback_loop` memory).

## Problem

The agent forgets everything durable between sessions. Above all, it can't close the human
loop: a student takes a draft to their professor, gets feedback, and the agent neither
remembers those comments nor adjusts the work to them. It also re-asks for institution
requirements every project and never learns a student's recurring mistakes.

## Goals

- **Advisor-feedback loop (core):** ingest professor feedback → extract discrete directives →
  persist → surface open directives as coaching blockers → track addressed. The agent adjusts
  the work to the feedback.
- **Institution profile:** a per-project config (citation style, min refs, reporting standard,
  required sections) that seeds the quality rubric and stops re-asking, defaulting from a
  per-user institution default.
- **Cross-project learning:** summarize recurring advisor themes into per-user memory so a new
  project starts pre-warned.

## Non-goals

- Not a chat-history store (LangGraph checkpointer already does that).
- Does not grade — quality-evals owns the rubric; this spec only *populates* what it reads.
- No new headless coupling (`project_headless_surfaces` memory): per-project keys live in the
  context store and are chat-written; the partner/auto paths neither read nor write them.

## Design

### Two tiers

**Tier 1 — per-project (context store).** New keys written through a dedicated lightweight
path (same pattern as Spec 2's `roadmap_tasks`, NOT `commit_slice`):
- `advisor_feedback`: `[{id, source, chapter, section?, quote?, issue, required_change,
  status: "open"|"addressed", created_at, addressed_at?}]`
- `institution_profile`: `{citation_style, min_references, reporting_standard,
  required_sections, weight_overrides}` (any subset; generic default when absent).

**Tier 2 — per-user, cross-project (extend `api/app/user_memory.py`).** Add two allowlisted
keys to `USER_MEMORY_KEYS`:
- `institution_default`: seeds a new project's `institution_profile`.
- `recurring_advisor_themes`: short list of patterns distilled from feedback across projects
  (e.g. "advisor consistently requires reported effect sizes").

### The advisor-feedback loop

**1. Ingest** — a tool `ingest_advisor_feedback(text=None, attachment=None)`:
- Accepts pasted text OR an uploaded file (DOCX inline comments via python-docx, or a PDF/txt
  of the professor's notes — reuse `pdf_extract` / the docx path already in
  `partner_report_service._extract_text`).
- Neutralizes prompt injection on extracted file text (`agent/guardrails.py`, as
  `parse_reference` already does).

**2. Extract** — one LLM call turns raw feedback into structured directives
`{chapter, section?, quote?, issue, required_change}`; deduped against existing open items by
(chapter, issue) similarity. Best-effort: on failure, store the raw text as a single
directive so nothing is lost.

**3. Persist + surface** — append directives to `advisor_feedback` via the dedicated store
path, and for each new open directive call `flag_blocker(module, substep, title, why)`
(Spec 2) so it appears in the roadmap and drives `next_action`. This is what makes the agent
*lead the revision* — the open directive becomes the next action.

**4. Adjust** — because open directives are now blockers, the per-turn `[NEXT]` line
(Spec 2) points the agent at them; when the student revises a chapter, the agent reads
`advisor_feedback` and applies the `required_change`.

**5. Track** — a tool `mark_feedback_addressed(feedback_id)`: flips the directive to
`addressed` and resolves the linked blocker (`resolve_blocker`). The quality rubric's advisor
dimension then shows N-of-M addressed.

**6. Learn (cross-project)** — when directives are addressed (or on project completion), a
distillation step summarizes recurring themes into `user_memory.recurring_advisor_themes` via
`write_user_prefs` (with provenance + confidence, as that module already supports). A new
project seeds `institution_profile` from `institution_default` and warns from
`recurring_advisor_themes`.

### Institution profile

- Set via `set_institution_profile(**fields)` tool (or the onboarding wizard), defaulting each
  field from `user_memory.institution_default`.
- Read by quality-evals (Spec 3) and the export/citation paths that already honor a citation
  style.

## Data flow

```
student pastes professor feedback
  → ingest_advisor_feedback → extract directives → append advisor_feedback
       → flag_blocker per open directive  (Spec 2 roadmap)
  → [NEXT] now points at the top advisor directive → agent leads the revision
  → student revises → mark_feedback_addressed(id) → resolve_blocker + status=addressed
  → on completion → distill recurring_advisor_themes → user_memory (cross-project)
quality-evals: reads advisor_feedback + institution_profile (Spec 3)
```

## Error handling

- Ingest/extract are best-effort: a bad LLM parse stores the raw feedback as one directive
  (never silently drops a professor comment).
- The per-project write path (like `roadmap_tasks`) never touches module status/focus — a
  malformed directive can't corrupt thesis state.
- `write_user_prefs` already rejects non-allowlisted keys (`ForbiddenMemoryKey`) and skips
  blanks — cross-project learning inherits that safety.
- File ingest reuses the existing prompt-injection neutralization.

## Testing

- **Extract:** stub the LLM → assert directives parsed into the shape; malformed JSON → raw
  text stored as one directive.
- **Ingest wiring:** ingesting 2 directives creates 2 `advisor_feedback` entries + 2 blockers;
  a duplicate directive isn't double-added.
- **Track:** `mark_feedback_addressed` flips status AND resolves the linked blocker.
- **Institution profile:** `set_institution_profile` writes the key; a new project seeds from
  `institution_default`.
- **Cross-project learning:** distillation calls `write_user_prefs` with
  `recurring_advisor_themes` and provenance; forbidden keys rejected.
- **Loop integration:** after ingest, `next_action` (Spec 2) returns the top advisor directive
  as the next step.
- api tests via `./run.sh` (arm64).

## Migration / rollout

1. Per-project store path: `upsert_advisor_feedback` / `mark_advisor_feedback_addressed` +
   `set_institution_profile` on `ProjectStateStore` (mirrors `roadmap_tasks`).
2. `extract_directives` (LLM) — pure-ish, unit-tested with a stubbed LLM.
3. `ingest_advisor_feedback` tool: extract → persist → `flag_blocker` per directive.
4. `mark_feedback_addressed` tool: status + `resolve_blocker`.
5. `USER_MEMORY_KEYS` += `institution_default`, `recurring_advisor_themes`; seed on project
   create; distill on addressed/completion.
6. Root skill section documenting the loop.

## Dependencies

- **Spec 2** (roadmap): `flag_blocker` / `resolve_blocker` / `roadmap_tasks` write path.
- **Spec 3** (quality-evals): consumer of `advisor_feedback` + `institution_profile`.
- Existing `api/app/user_memory.py`, `agent/guardrails.py`, `pdf_extract` / docx extraction.
