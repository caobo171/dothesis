# Auto-save reconstructed modules

**Date:** 2026-08-06
**Status:** implemented

## Problem

A returning student drops their existing thesis work on `/new`. The import
classifies it (say it lands an M4 analysis), then `reconstruct_upstream` infers
the earlier steps behind it — M1 Topic, M2 Literature, M3 Design.

Those inferences were then shown as a stack of cards, each stamped
**"Suggested — not saved yet"**, each with a Confirm and a Skip button, each
with an editable form under it. Nothing counted until the student clicked
through all of them. Two problems with that:

1. **The gate is asking the wrong person for the wrong thing.** The
   reconstruction is inferred from work the student already did. Making them
   re-approve it is asking them to sign off on their own thesis.
2. **The form couldn't be reviewed anyway.** Structured fields —
   `conceptual_model` (a nodes/edges graph), `research_gaps` (objects with
   citations) — fell through to a read-only `<pre>{JSON.stringify(v)}</pre>`.
   Nobody reviews a JSON blob. A student reads it as the product breaking.

There was also a persistence hazard: the save lived in the card's click
handler, so the headless auto-mode and partner API surfaces — which run the
same backfill with no UI — never persisted anything at all.

## Decisions

| Question | Decision |
|---|---|
| Save automatically? | Yes. Reconstructing IS saving. |
| Module status | `done`, not `in_progress` — the student's own work is what was reconstructed FROM |
| Focus after saving | Advance to the first module that isn't done, **forwards only** |
| UI after saving | Read-only cards showing what landed; edits happen in chat |
| Structured fields | Render through the chat context panel's own renderers (mermaid for the model), never JSON |

The `done` decision was taken with the trade-off stated: content inferred by an
LLM is marked complete before anyone reads it, and downstream modules build on
it. Accepted deliberately — the alternative drags students backwards through
milestones they had already passed.

## Architecture

### One write path: `store.commit_reconstructed(module, slice_)`

`SLICE_OWNERSHIP` is deliberately narrower than the module schemas. M2 also
infers `research_state_summary` / `theoretical_framework`; M3 infers
`paradigm` / `design` / `tool` / `sampling_strategy` / `target_sample_size`.
`commit_slice` rejects those as unowned, and `load`/`_save` only round-trip
owned keys — so they only persist via a direct merge into the module's JSONB
column. That merge used to live in the `/confirm` route, which is why the chat
tool could not save without importing from the api layer.

It moved into the store:

- `ProjectStateStore.commit_reconstructed` (agent/state.py) — owned keys via
  `commit_slice(confirm_done=True)`, downstream statuses preserved, focus
  advanced. A slice too thin for the done-gate falls back to `in_progress`
  rather than failing.
- `DbProjectStateStore.commit_reconstructed` (api/app/agent_state.py) —
  overrides to merge the non-owned schema fields into the module column first,
  tagged `_source: "reconstructed"`, then delegates to the base.

Three call sites, no duplicated logic:

- `POST /mid-journey-import/reconstruct` — infers and commits in `MODULES`
  order, returns `{reconstructed, saved, focus}`.
- `backfill_upstream_modules` tool — commits as it infers, so chat, headless
  auto-mode and the partner API all persist.
- `POST /mid-journey-import/confirm` — kept, no longer a gate: it's the edit
  path for a client sending corrected fields.

### Focus: forwards only

`commit_slice` parks focus on whatever it just wrote, which for an upstream
backfill is wrong. But "first module not done" alone is wrong from the other
side: backfilling only M3 while M1 is empty would point the student at M1.

`_advance_focus(prev_focus)` takes the later of the two. Import M4, reconstruct
M1–M3 → focus lands on M4. Backfill M3 alone while at M4 → stays at M4.
`prev_focus` is captured before the commit, because the commit destroys it.

### Rendering

`ContextPanel.tsx` (1384 lines) held `M1Body` / `M2Body` / `M3Body` / `M5Body`
and their detail renderers — including `ConceptualModelDetail`, which already
builds a mermaid `flowchart LR` from nodes/edges. Those were extracted to
`ModuleSlices.tsx` and are now rendered by both the chat panel and the
reconstructed-modules card, via a `ModuleBody` switch. A backfilled M3 looks
exactly like an M3 built step by step.

M4 has no bespoke body, so `ModuleBody` falls back to `GenericSlice`:
shape-driven labeled rows (`target_sample_size` → `Target sample size`),
bullets for primitive lists, and a plain count for anything nested. It never
prints JSON.

## Tests

- `agent/tests/test_state_store.py` — done vs thin-fallback, meta/audit-key
  stripping, focus advances past finished steps, focus never regresses.
- `api/tests/test_import_route.py` — reconstruct saves every candidate in
  MODULES order, owned + non-owned fields round-trip the DB, downstream M4
  preserved, one failing module doesn't cost the others.
- `agent/tests/test_backfill_tool.py` — tool commits in MODULES order, reports
  the rest when one commit fails, widget hint carries `saved`.
- `web/…/ReconstructedModules.test.tsx` — no Confirm/Skip buttons exist,
  structured fields render as content, generic fallback prints no JSON.
