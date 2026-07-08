# Unify Headless Generation (Auto-mode + Partner API)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Sequence:** Spec 1 of 2. Spec 2 (Proactive Coaching Layer) follows and depends on the
single M4 readiness gate this spec produces.

## Problem

DoThesis has three generation surfaces:

1. **Interactive chat** — the v3 deep agent (`agent/runtime.py`). Out of scope here.
2. **Auto-mode** — the Auto-draft button → `get_auto_graph()` run as a subprocess
   (`api/app/job_runner.py`, `orchestrator/__main__.py`), with a real project,
   PostgresSaver checkpoint, and credit ledger. Result backfilled into `context_store`.
3. **Partner API** — service-to-service report generation for other products
   ("Powered by DoThesis"), `api/app/partner_report_service.py`. Takes an uploaded
   analysis PDF, infers framing, composes chapters, exports. No project/thread/ledger.

Auto-mode and Partner **already share the M5 compose+export engine** (`compose_chapter`,
`run_export`, `_references_section_body`, `_chapter_titles` from
`orchestrator/tools/m5_writing.py`) but **do not share orchestration**, and they have
**two different M4 readiness gates**:

| | Auto-mode | Partner API |
|---|---|---|
| Fills `context_store` by | graph *generates* every module | infers M1/M2/M3 from the PDF, M4 = raw text |
| M4 readiness gate | `assess_export_readiness` | `_has_sufficient_m4_data` (hand-rolled) |
| Chapter compose | engine M5 `compose_*` | partner's `_compose_chapters` (a near-clone) |
| References | graph's M2 | `_literature_search` (light ~8-source Crossref) |
| Export | `run_export` | same `run_export` |

The divergence causes drift risk (two definitions of "M4 is complete", two compose loops)
and blocks a requirement: Spec 2's coaching layer wants **one** definition of per-module
completeness to read.

## Goals

- **One shared back half.** Extract `compose_and_export(context_store, ...)` that owns the
  M4 readiness gate, the chapter compose loop, prose sanitation, references append, and
  `run_export`. Both auto-mode and partner call it.
- **One M4 readiness gate** replacing both `assess_export_readiness` and
  `_has_sufficient_m4_data`.
- **Partner input contract:** M1/M2/M3 become **optional inputs**; each missing one is
  **generated**; a missing M2 runs **real, time-bounded literature research** (not a token
  fetch). M4 (uploaded analysis) is always required. Provided modules are used as-is and
  never overwritten.

## Non-goals

- **Do not merge the two front halves.** How each surface fills `context_store`
  (graph-generates-everything vs. infer-from-one-PDF) are genuinely different jobs and
  stay separate.
- **Do not touch the interactive chat path** (see `project_headless_surfaces` memory).
  No new gates, no required state on any surface.
- Not changing auto-mode's subprocess/checkpoint/ledger machinery.

## Design

### Shared back half — `compose_and_export`

New module (proposed: `orchestrator/tools/compose_export.py`, next to the M5 engine it
wraps; final location decided in the plan):

```python
def compose_and_export(
    context_store: dict,
    *,
    chapters: list[str],       # subset of M5_CHAPTER_ORDER, canonical order enforced
    language: str,
    references: list[dict] | None = None,
    progress: ProgressSink | None = None,   # unifies partner's _set_progress + auto's event stream
) -> list[Artifact]:
    ...
```

It owns, moved out of `partner_report_service.py` and de-duplicated against the engine:

- **The single M4 readiness gate** (see below).
- The per-chapter compose loop (today's `_compose_chapters`), including canonical-order
  enforcement and the Discussion+Conclusion merge.
- Prose sanitation: `_sanitize_prose`, `_drop_placeholder_tables`, `_reflow_inline_bullets`
  (auto-mode output benefits from the same cleanup partner already does).
- The deterministic References section append.
- `run_export`.

`progress` is a small sink interface so partner's in-memory `_PROGRESS` token updates and
auto-mode's JSON-lines event stream both plug in without the back half knowing which.

### Single M4 readiness gate

`assess_export_readiness` (structured: reads `context_store["m4_analysis"]`) is the
canonical form. Partner's `_has_sufficient_m4_data` (text-heuristic on raw PDF text) moves
**earlier**, into partner's front half, as an *ingest validation* ("does this PDF even
contain statistics?") — a different question from "is M4 complete in the store?". So:

- **Front half (partner only):** `pdf_looks_like_analysis(text)` — fail fast before any LLM
  spend if the upload has no statistics (keeps the small-validation-fee behavior).
- **Back half (shared):** `assess_export_readiness(context_store)` — the one gate both
  surfaces hit; returns `{ok}` or `{error: "needs_data", missing: [...]}`.

### Partner front half — input contract

New `build_partner_context_store(...)` in `partner_report_service.py`:

```python
def build_partner_context_store(
    analysis_bytes, *, filename, notes, language,
    m1=None, m2=None, m3=None,   # optional caller-provided modules
) -> dict:  # returns context_store
```

Rules:

- **M4** — always from the uploaded analysis (required). `pdf_looks_like_analysis` gate.
- **M1** — `m1` if provided, else `_infer_topic(text + notes)`.
- **M3** — `m3` if provided, else `_infer_model` (+ diagram in methodology chapter).
- **M2** — `m2` if provided, else **budgeted real research** (see below).
- Provided modules are copied verbatim into the store; generation only fills holes.

The router (`api/app/routers/partner_report.py`) accepts the optional `m1`/`m2`/`m3` in the
request body (POST-only, per project convention) and passes them through.

### M2 research — budgeted scout (approved)

The full `research_scout` is too slow for a per-report budget (100+ sources / minutes).
Missing-M2 research uses a **budgeted scout**: reuse the real engine research path capped
at `≤ N queries / ≤ M seconds` (values fixed in the plan). On budget-exhaustion or error,
**fall back to the current Crossref `_literature_search`**. Result: genuine research when
it fits the budget, never a hang, never zero references.

## Data flow

```
Partner:  PDF (+ optional m1/m2/m3, notes)
            → build_partner_context_store  (front half: gate PDF, fill holes, budgeted M2)
            → compose_and_export(context_store)   ← shared
            → presign S3 → {pdf_url, docx_url, keys}

Auto-mode: graph fills context_store (subprocess, unchanged)
            → compose_and_export(context_store)   ← shared
            → run_export artifacts → exports table
```

## Error handling

- `compose_and_export` raises the existing `ReportError(code)` taxonomy
  (`no_extractable_text`, `insufficient_m4_data`→`needs_data`, `bad_chapters`,
  `compose_failed`) so the partner router keeps its stable 4xx/5xx mapping. Auto-mode
  wraps the same errors into its job-event stream.
- Budgeted-scout failure is swallowed → Crossref fallback → `[]`-safe (citations are never
  a hard blocker), matching today's partner behavior.
- Provided-but-malformed `m1/m2/m3` → validated at the router; a bad shape is a `4xx`, not
  a silent overwrite.

## Testing

- **Golden back-half test:** one `context_store` fixture → `compose_and_export` → assert
  sections, chapter order, Discussion/Conclusion merge, references section present. Run for
  both a full-thesis and analysis-report chapter set.
- **M4 gate parity:** feed the store shape auto-mode produces and the one partner produces
  through the single gate; assert identical verdicts (regression against the old two gates).
- **Partner input contract:** matrix of provided/missing across m1/m2/m3 → assert provided
  modules pass through verbatim and only missing ones are generated.
- **Budgeted scout:** stub the scout to (a) return within budget → real sources used;
  (b) exceed budget → Crossref fallback; (c) throw → `[]`, compose still succeeds.
- Existing `api/tests/test_partner_report.py` must stay green (run via `./run.sh`, arm64).

## Migration / rollout

1. Add `compose_and_export` + single gate; unit-test in isolation.
2. Point partner at it (delete partner's `_compose_chapters`, `_has_sufficient_m4_data`
   duplication; keep front-half helpers).
3. Point auto-mode's post-graph export at it.
4. Add partner optional-inputs + budgeted M2 last (largest new surface).

Each step is independently shippable and leaves both surfaces working.

## Out of scope — becomes Spec 2

**Proactive Coaching Layer** (`project_agent_gaps` memory, Approach A): the derived
sub-step roadmap + next-action engine + chat-only `roadmap_tasks` slice + roadmap UI. It
**reuses the single M4 readiness gate** this spec creates as one input to its per-module
completeness derivation. Separate spec, built after this one lands.
