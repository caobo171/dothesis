# Agent-Quality Events (F5 Observability)

Source-of-truth for the best-effort agent-quality events DoThesis emits to
PostHog, and the HogQL behind the "DoThesis — Agent Quality" dashboard.

All events are emitted through the best-effort `emit()` layer
(`api/app/analytics.py`): fire-and-forget, a no-op when `POSTHOG_API_KEY` is
unset, and it swallows every error so analytics can never block or break a turn.
The agent and quality layers emit through `agent.analytics.emit` (a no-op hook
the app rebinds to `app.analytics.emit` in `create_app`) so they never import
`app/`.

`distinct_id` is the `user_id` when the emit site knows it; otherwise `None`
(captured as PostHog's `"anonymous"`). No new PII — only ids already in the
system travel as properties.

## Event table

| Event | Emitted from | `distinct_id` | Properties | Meaning |
|-------|--------------|---------------|------------|---------|
| `module_status_changed` | `DbProjectStateStore.commit_slice` (`api/app/agent_state.py`) | user_id or None | `module`, `from`, `to`, `project_id` | A module's status transitioned (locked → in_progress → done, or → needs_review). The completion-funnel spine. |
| `done_rejected_empty` | `DbProjectStateStore.commit_slice` (empty-done gate) | user_id or None | `module`, `project_id` | The strict done-gate refused a `confirm_done` because the module's slice was empty (hallucinated completion caught). |
| `needs_review_propagated` | `DbProjectStateStore.commit_slice` | user_id or None | `module`, `downstream` (list), `project_id` | A commit knocked started downstream modules back to `needs_review` (a late upstream edit invalidated finished work). |
| `quality_reviewed` | `review_thesis` tool (`agent/tools/writing.py`) | None | `overall` (0..1), `method`, `blocking_count` | The committee-readiness rubric scored the thesis. The quality-trend metric. |
| `citation_rejected` | citation dimension of `quality/rubric.py` | None | `kind` (`"uncited"`), `citation` | An uncited `(Author, Year)` — a source not in the reference pool, i.e. a likely fabrication caught. One event per rejected citation. |
| `next_action_surfaced` | roadmap endpoint (`api/app/routers/roadmap.py`) | user_id or None | `module`, `substep`, `project_id` | The coaching "single next thing" changed. Deduped per poll (see note) so it fires on change, not on every poll. |
| `advisor_feedback_ingested` | `ingest_advisor_feedback` tool (`agent/tools/state_tools.py`) | None | `count` | N professor directives were extracted + tracked this turn. |
| `advisor_feedback_addressed` | `mark_feedback_addressed` tool (`agent/tools/state_tools.py`) | None | — | One advisor directive was marked addressed. |
| `export_completed` | chat: `export_docx` tool (`agent/tools/writing.py`); auto: `DbProjectStateStore._auto_export_m5`; partner: `POST /partner/report` (`api/app/routers/partner_report.py`) | user_id or None | `scope` (`"full"` / `"M1,M3"` / depth), `surface` (`"chat"` / `"auto"` / `"partner"`), `project_id` (chat/auto) | A DOCX/PDF export finished on one of the three generation surfaces. |

### Note on `next_action_surfaced` dedup

The roadmap endpoint is polled, so emitting on every call would flood PostHog.
The router keeps a per-process in-memory map `project_id → (module, substep)` and
emits only when the surfaced action changes. This is deliberately **not** durable:
the only cost of a process restart (or a second web worker) is at most one
duplicate emit per project, which is acceptable for a coaching signal and avoids
adding a DB column or a coaching-key round-trip purely for dedup. Design the
"advisor loop" / "next action" insights to tolerate the occasional duplicate
(e.g. count distinct sessions, not raw events, if exactness ever matters).

## Dashboard: "DoThesis — Agent Quality"

Five insights. HogQL below (PostHog properties are accessed as
`properties.<name>`; JSON string props compare as strings).

> **Manual follow-up:** these insights + the dashboard are created **out of
> band** via the PostHog MCP or UI — that's an external side effect a human
> triggers, not part of this change. Fill in the URLs once created.

### 1. Completion funnel (M1 → M5 done)

Funnel over `module_status_changed` where `to = 'done'`, one step per module.
Build as a PostHog Funnel insight (5 steps), each step:
`module_status_changed` filtered by `properties.to = 'done'` and
`properties.module = 'M1' … 'M5'`, sequential.

HogQL equivalent (per-module done counts as the funnel backbone):

```sql
SELECT properties.module AS module, count() AS reached_done
FROM events
WHERE event = 'module_status_changed' AND properties.to = 'done'
GROUP BY module
ORDER BY module
```

### 2. Gate pass rate (per module)

Rejections vs. successful dones — how often the empty-done gate fires.

```sql
SELECT
  properties.module AS module,
  countIf(event = 'done_rejected_empty') AS rejected,
  countIf(event = 'module_status_changed' AND properties.to = 'done') AS accepted,
  countIf(event = 'module_status_changed' AND properties.to = 'done')
    / (countIf(event = 'module_status_changed' AND properties.to = 'done')
       + countIf(event = 'done_rejected_empty')) AS pass_rate
FROM events
WHERE event IN ('done_rejected_empty', 'module_status_changed')
GROUP BY module
ORDER BY module
```

### 3. Hallucination catches (citations rejected)

Trend of `citation_rejected` count, breakdown by `properties.kind`.

```sql
SELECT
  toStartOfDay(timestamp) AS day,
  properties.kind AS kind,
  count() AS rejected
FROM events
WHERE event = 'citation_rejected'
GROUP BY day, kind
ORDER BY day
```

### 4. Quality trend

`avg(properties.overall)` of `quality_reviewed` over time, breakdown by
`properties.method`.

```sql
SELECT
  toStartOfWeek(timestamp) AS week,
  properties.method AS method,
  avg(toFloat(properties.overall)) AS avg_overall,
  avg(toFloat(properties.blocking_count)) AS avg_blocking
FROM events
WHERE event = 'quality_reviewed'
GROUP BY week, method
ORDER BY week
```

### 5. Advisor loop (ingested vs. addressed)

Did professor feedback get closed out?

```sql
SELECT
  toStartOfWeek(timestamp) AS week,
  sumIf(toInt(properties.count), event = 'advisor_feedback_ingested') AS ingested,
  countIf(event = 'advisor_feedback_addressed') AS addressed
FROM events
WHERE event IN ('advisor_feedback_ingested', 'advisor_feedback_addressed')
GROUP BY week
ORDER BY week
```

## Dashboard URLs

Fill in after creating the insights via MCP/UI:

- Dashboard: TODO
- Completion funnel: TODO
- Gate pass rate: TODO
- Hallucination catches: TODO
- Quality trend: TODO
- Advisor loop: TODO
