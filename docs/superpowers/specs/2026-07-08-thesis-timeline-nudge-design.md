# Thesis Timeline + Weekly Nudge Design (F11)

**Date:** 2026-07-08
**Status:** Design — approved, pending spec review
**Motivation:** Make the tagline *"an agent that goes with your thesis journey"* literally true.
The 10 prior features make DoThesis present and proactive *within a session*; F11 adds the
**temporal accompaniment** — a realistic backwards timeline from the defense date and one weekly
nudge — so the agent walks with the student across the *months* a thesis takes.

## Problem

A thesis runs for months, but DoThesis is silent between sessions. It never says "your data
collection is 2 weeks behind" or "your defense is in 3 weeks — let's prep." Without a timeline
and a gentle recurring touch, it's a smart tool the student *visits*, not a companion that
*accompanies*. There is also no in-app scheduler today (jobs are request-triggered).

## Goals

- **Backwards timeline:** from the defense/submission date + method + target sample size, generate
  a milestone plan (M1→M5 + data collection + defense prep) with **realistic buffers** (data
  collection is 3–4 weeks, not 3 days).
- **Progress vs plan:** compare the student's actual roadmap position (F2) against the planned
  dates → on-track / N weeks behind / next milestone.
- **One weekly nudge:** a single email per week — "this week: finish your questionnaire; you're 2
  weeks behind on data collection" — opt-in, idempotent, via existing `mail.py`.
- **Surface in the roadmap UI:** a timeline card ("you are here vs plan").

## Non-goals

- **No gamification/streaks/badges** — thesis students need a calendar and a gentle nag, not a
  game (`project_best_in_class_backlog` memory).
- **No in-app scheduler build** — the weekly runner is a standalone module the deploy's cron
  invokes; we don't add Celery/APScheduler.
- Not a hard deadline enforcer — advisory, encouraging.

## Design

### Timeline generator

`agent/timeline.py` (pure):
```python
build_timeline(defense_date, method, target_n, today) -> dict
# → {"milestones": [{"module","label","start","end","weeks"}],
#    "data_collection_weeks": int, "total_weeks": int, "feasible": bool}
```
Backwards-plans from `defense_date`: reserve defense prep (F6) → writing (M5) → data collection
(sized from `target_n`, shared with F7's `sampling_plan`) → analysis (M4) → design (M3) →
literature (M2) → topic (M1), each with a buffer. `feasible=False` if the plan would need to start
before `today` (flag an aggressive timeline).

### Progress vs plan

`timeline_status(context_store, today) -> dict`:
```
{"expected_phase": "M4", "actual_phase": "M3", "weeks_behind": 2,
 "this_week": "Finish data collection", "next_milestone": {...}, "on_track": False}
```
`actual_phase` from the F2 roadmap (`focus` + `derive_substep`); `expected_phase` from where
`today` falls in the milestones. Pure and null-safe (no timeline ⇒ `{}`).

### Storage + capture

- `thesis_timeline` key in the context store, written via a dedicated `set_thesis_timeline` path
  (mirrors F4's `set_institution_profile` — never touches module status/focus).
- Captured via a `set_defense_date(date)` agent tool (or M1/bootstrap prompt): builds + stores the
  timeline and surfaces it. The M1 skill asks for a target defense date early.

### Weekly nudge runner (no scheduler)

`api/app/jobs/weekly_nudge.py`, runnable as `python -m app.jobs.weekly_nudge` (the deploy cron
runs it weekly):
- Query active projects that have a `thesis_timeline`, whose owner is **opted-in**, and that were
  **not nudged in the last 6 days** (idempotent via `last_nudge_at`).
- For each: compute `timeline_status`, render a short email (this week's focus + behind-status +
  one CTA link back into the chat) via `mail.send_template`, set `last_nudge_at`.
- Best-effort per project — one failure never aborts the batch.

### Opt-in

- `nudge_opt_in` (default `True`) added to `USER_MEMORY_KEYS` (F4); the email includes an
  unsubscribe link that flips it. Respected by the runner.

### UI

- A **timeline card** in `ContextPanel` (F2's roadmap surface): the milestone bar with "you are
  here", weeks-ahead/behind, and this-week's focus. Fed by the roadmap endpoint (extended with
  `timeline_status`) — no new endpoint.

## Data flow

```
M1: set_defense_date → build_timeline (buffers, target_n sizing) → set_thesis_timeline
roadmap endpoint: + timeline_status → UI timeline card ("you are here vs plan")
weekly (cron): app.jobs.weekly_nudge → per opted-in project → timeline_status
   → mail.send_template("this week / N weeks behind") → last_nudge_at
```

## Error handling

- `build_timeline` / `timeline_status` pure + null-safe (no date/timeline ⇒ `{}`; infeasible ⇒
  `feasible=False`, still returned).
- The runner is best-effort per project; a mail failure logs and continues.
- Idempotency (`last_nudge_at` + 6-day window) prevents double-sends if cron double-fires.
- Opt-out is honored immediately (checked at send time).

## Testing

- **build_timeline:** a defense date 6 months out ⇒ ordered milestones ending before it, with a
  3–4 week data-collection block; a date 2 weeks out ⇒ `feasible=False`.
- **timeline_status:** actual behind expected ⇒ `weeks_behind > 0`, correct `this_week`;
  on-track ⇒ `on_track=True`; no timeline ⇒ `{}`.
- **nudge runner:** two projects (one opted-in + due, one nudged yesterday) ⇒ exactly one email
  sent; opted-out ⇒ none; `last_nudge_at` updated. Mail + query stubbed (no real send).
- **opt-in key:** `nudge_opt_in` in `USER_MEMORY_KEYS`; unsubscribe flips it.
- **UI:** timeline card renders "you are here" + behind badge (component test).
- api tests via `./run.sh`; no real emails in tests.

## Migration / rollout

1. `agent/timeline.py` `build_timeline` (pure).
2. `timeline_status` (pure; reads F2 roadmap position).
3. `set_thesis_timeline` store path + `set_defense_date` tool + M1 capture.
4. `app.jobs.weekly_nudge` runner + `nudge_opt_in` pref + idempotency + email template.
5. Roadmap endpoint + ContextPanel timeline card.

Steps 1–3 give the in-app timeline; step 4 adds the between-session accompaniment; step 5 the UI.

## Dependencies

- **F2** (roadmap) — `derive_substep`/status for `actual_phase`; the ContextPanel surface.
- **F7** (`sampling_plan`/`target_n`) — sizes the data-collection block; shared helper.
- **F4** (`USER_MEMORY_KEYS`, dedicated store-path pattern) — opt-in pref + storage pattern.
- **F6** (defense) — the timeline's final "defense prep" block.
- Existing `api/app/mail.py`; the deploy's external cron to run the weekly module.
