# Observability & Agent-Quality Evals in Prod Design

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Sequence:** Spec 5 (last of the follow-on set). Instruments the events the coaching layer
(Spec 2), quality-evals (Spec 3), and memory (Spec 4) already produce, so it lands cleanly
once those exist.

## Problem

PostHog exists at the org level, but the backend emits **no agent-quality signal**: no gate
pass/fail rates, no hallucination-catch counts, no module-completion funnel, no quality-score
trend, no advisor-loop metrics. There's no way to see whether a prompt/model change made the
agent worse in production, or where students drop off.

## Goals

- **A thin, best-effort server-side emit layer** (`emit(event, distinct_id, props)`) that
  captures agent-quality events to PostHog and never blocks or breaks a turn.
- **A defined event taxonomy** for the moments that matter: module transitions, gate firings,
  hallucination catches, next-action, quality reviews, advisor loop, export.
- **A dashboard** answering: completion funnel, gate pass rates, hallucination catches over
  time, quality-score trend, advisor-loop throughput.

## Non-goals

- Not client/product analytics (web already has its own). This is backend agent-quality only.
- No new blocking behavior anywhere; emit is fire-and-forget.
- No PII beyond the existing `distinct_id` (user id) + project id already in the system.
- Does not create dashboards *in code* — dashboards/insights are defined here as HogQL and
  created via the PostHog MCP/UI (a one-time setup, documented).

## Design

### Emit layer — `api/app/analytics.py`

```python
def emit(event: str, distinct_id: str | None, properties: dict | None = None) -> None:
    """Fire-and-forget PostHog capture. No-ops if unconfigured; swallows all errors."""
```

- Wraps the PostHog Python SDK `capture` (batches in a background thread — non-blocking).
- No-ops when `POSTHOG_API_KEY` is absent (tests, local, a fresh deploy) — added to
  `api/app/settings.py` (`posthog_api_key`, `posthog_host`).
- Every call is wrapped so an analytics failure can never surface into a turn.

### Event taxonomy

| Event | Properties | Emitted from |
|---|---|---|
| `module_status_changed` | `module, from, to` | `DbProjectStateStore.commit_slice` |
| `done_rejected_empty` | `module` | the empty-done gate (`ValueError` path) |
| `needs_review_propagated` | `module, downstream[]` | `commit_slice` |
| `citation_rejected` | `count, kind: uncited\|fabricated` | citation validators / rubric |
| `next_action_surfaced` | `module, substep, reason` | roadmap endpoint / `[NEXT]` build |
| `quality_reviewed` | `overall, method, blocking_count` | `review_thesis` |
| `advisor_feedback_ingested` | `count` | `ingest_advisor_feedback` |
| `advisor_feedback_addressed` | — | `mark_feedback_addressed` |
| `export_completed` | `scope, surface: chat\|auto\|partner` | export paths |

`distinct_id` = user id where known; `properties` always include `project_id`. Headless paths
(auto/partner) may emit `export_completed` with their surface but never gain blocking logic.

### Dashboard (defined as HogQL, created via MCP/UI)

- **Completion funnel:** `module_status_changed to=done` for M1→M2→M3→M4→M5 — where students
  drop off.
- **Gate pass rate:** ratio of `done_rejected_empty` to successful `module_status_changed
  to=done` per module (how often the agent tries to fake-complete).
- **Hallucination catches:** `citation_rejected` count over time, split by `kind`.
- **Quality trend:** average `quality_reviewed.overall` over time, split by `method` and by
  model (a property we tag from the active model) — catches a model-swap regression in prod.
- **Advisor loop:** `advisor_feedback_ingested` vs `advisor_feedback_addressed` throughput.

These live in `docs/observability/agent-quality-events.md` as the source-of-truth reference,
with the HogQL for each insight.

## Data flow

```
turn / gate / review / export
  → emit(event, user_id, {project_id, ...})   [fire-and-forget, best-effort]
  → PostHog  → insights/dashboard (funnel, gate rate, hallucination, quality, advisor)
```

## Error handling

- `emit` catches everything; a capture failure logs at debug and returns. No turn ever fails
  because of analytics.
- Unconfigured (`POSTHOG_API_KEY` empty) ⇒ `emit` is a no-op — safe in tests and local dev.
- No event carries content/PII beyond ids already present in the system.

## Testing

- **`emit` best-effort:** with the SDK stubbed to raise, `emit` returns without raising; with
  no key, `emit` no-ops (SDK never called).
- **Instrumentation:** monkeypatch `emit` and assert `module_status_changed` fires on a
  status change, `done_rejected_empty` on an empty-done reject, `quality_reviewed` on
  `review_thesis`, `advisor_feedback_ingested` on ingest.
- **Non-blocking:** a raising `emit` inside `commit_slice` doesn't break the commit (the emit
  is wrapped/after the state write).
- api tests via `./run.sh`.

## Migration / rollout

1. `api/app/analytics.py` + settings keys + the PostHog SDK dependency (best-effort/no-op).
2. Instrument state transitions (`DbProjectStateStore`): `module_status_changed`,
   `done_rejected_empty`, `needs_review_propagated`.
3. Instrument the quality/coaching/advisor/export points (Specs 2–4 + export).
4. `docs/observability/agent-quality-events.md` + create the dashboard via MCP/UI.

Each step is shippable; with no key, everything is inert (safe to land before PostHog is
provisioned for prod).

## Dependencies

- **Specs 2–4** produce most events; this spec instruments them. Order it last.
- PostHog Python SDK; the org/project already exists (token in the MCP context).
