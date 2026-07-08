# Master Execution Roadmap — Vertical Agent Upgrade (8 features)

**Date:** 2026-07-08
**Status:** Program plan — sequences the eight specced features into one ordered build.
**Scope:** This does not restate the per-task steps — it orders the plans by their real
dependencies, defines shippable milestones, and marks what can run in parallel. Each feature
keeps its own plan file (the source of truth for its tasks).

## The eight features

Core five (the vertical-agent foundation):

| # | Feature | Spec | Plan | Tasks |
|---|---|---|---|---|
| F1 | Unify headless generation | `specs/…unify-headless-generation-design.md` | `plans/…unify-headless-generation.md` | 7 |
| F2 | Proactive coaching layer | `specs/…proactive-coaching-layer-design.md` | `plans/…proactive-coaching-layer.md` | 7 |
| F3 | Quality evaluation | `specs/…quality-evaluation-design.md` | `plans/…quality-evaluation.md` | 6 |
| F4 | Cross-session memory + advisor loop | `specs/…cross-session-memory-design.md` | `plans/…cross-session-memory.md` | 5 |
| F5 | Observability / agent-quality evals | `specs/…observability-agent-quality-design.md` | `plans/…observability-agent-quality.md` | 4 |

Best-in-class extensions (make it best-in-class at guiding quant theses):

| # | Feature | Spec | Plan | Tasks |
|---|---|---|---|---|
| F6 | Mock Committee (Hội đồng ảo) | `specs/…mock-committee-design.md` | `plans/…mock-committee.md` | 4 |
| F7 | Field-It survey pipeline (Questionnaire Doctor + survify) | `specs/…field-it-survey-pipeline-design.md` | `plans/…field-it-survey-pipeline.md` | 4 |
| F8 | Quantitative correctness content pack | `specs/…quant-correctness-content-pack-design.md` | `plans/…quant-correctness-content-pack.md` | 4 |

**41 tasks total.**

## Dependency graph

```
F1 (unify headless) ─────────────┐
   produces: chapter-scoped        │ gate consumed by
   assess_export_readiness         ▼
F2 (coaching) ──► roadmap spine, flag_blocker, [NEXT] ──►  F3 (quality-evals)
   │  produces roadmap_tasks path + flag_blocker           reads advisor_feedback +
   │                                                         institution_profile (empty default)
   └──────────────► F4 (memory + advisor loop) ─────────────┘
                     writes advisor_feedback + institution_profile,
                     turns directives into flag_blocker

F3 + F4 + F2 emit events ──►  F5 (observability)  [instruments; built last]
```

Hard dependencies (must precede):
- **F3 needs F1** (structure dimension calls the chapter-scoped gate) **and F2** (M5 `review`
  roadmap step + `flag_blocker`).
- **F4 needs F2** (`flag_blocker`/`resolve_blocker` + the `roadmap_tasks` dedicated write path).
- **F5 needs F2, F3, F4** (it instruments their events).
- **F3 ↔ F4 are decoupled by contract:** F3 reads `advisor_feedback`/`institution_profile`
  with empty defaults, so F3 does NOT block on F4 and F4 does NOT block on F3.
- **F1 is independent** — no dependency on F2–F5.

## Recommended execution order

Weighted by your stated priority — **the advisor-feedback loop (F4) is the most important
feature** — while respecting the dependency graph:

1. **F2 — Proactive coaching layer** (7 tasks).
   *Why first:* it's the foundation the flagship needs (`flag_blocker`, `roadmap_tasks` path,
   `[NEXT]`), and it's independently valuable (the agent starts leading). No upstream deps.
2. **F4 — Cross-session memory + advisor loop** (5 tasks).
   *Why second:* the most-important feature, and F2 unblocks it. Ships the full
   ingest → directive → blocker → adjust → track loop end-to-end.
3. **F1 — Unify headless generation** (7 tasks).
   *Why third:* independent foundation cleanup; produces the single M4 gate F3 needs. Can
   also be pulled earlier or run in parallel (see below) since it shares no code with F2/F4.
4. **F3 — Quality evaluation** (6 tasks).
   *Why fourth:* needs F1 (gate) + F2 (review step); lands after F4 so its advisor dimension
   lights up with real data instead of empty defaults.
5. **F5 — Observability** (4 tasks).
   *Why last:* instruments the events F2–F4 emit; inert until PostHog is provisioned.

### Parallelization (if more than one implementer/agent)

- **Track A:** F2 → F4 → (F3 review step) — the coaching/memory/quality line.
- **Track B:** F1 in parallel with Track A (zero shared files — F1 touches
  `partner_report_service.py` / `compose_export.py`; Track A touches `agent/roadmap.py`,
  `state.py`, `state_tools.py`).
- **Join:** F3 starts once BOTH F1 (gate) and F2 (review step) are merged.
- **F5 last**, after F2/F3/F4 land.

Single-implementer: just follow 1→5 above.

### Where the extensions (F6–F8) slot in

- **F8 (correctness content pack)** — mostly skill content + two thin checks; **no hard deps**.
  Its content tasks (Design→Test Matrix, Two-Register) are the cheapest, highest-leverage work
  in the whole program — **do them early, even before F1**, in parallel with F2. Its `preflight`
  rubric criterion waits for F3.
- **F7 (Field-It / Questionnaire Doctor)** — depends only on existing tools; shares
  `agent/sampling.py` with F8. Slot it after F8's content lands (Questionnaire Doctor pairs with
  the correctness content) and around F3 (adds `instrument_quality`). Its survify handoff is the
  commercial flywheel — prioritize if monetization is the near-term goal.
- **F6 (Mock Committee)** — depends on **F2** (post-M5 offer) and is best **right after F3**
  (rubric findings feed the questions). It's the referral moment — do it once F3 ships.

**Revised full order (single track), advisor-loop + quick-wins weighted:**
F8-content (matrix + two-register) → F2 → F4 → F1 → F3 → F8-rest → F7 → F6 → F5.

## Milestones (shippable increments)

- **M-A — "The agent leads."** After F2. Roadmap + `[NEXT]` + ContextPanel Next card. Demoable
  on its own.
- **M-B — "Closes the professor loop."** After F4. Paste feedback → tracked directives →
  roadmap blockers → adjust → mark addressed. The flagship; demo to users.
- **M-C — "One clean headless path."** After F1. Partner optional-inputs + budgeted M2 +
  single gate; auto/partner share the back half. Internal quality win.
- **M-D — "Committee-readiness grading."** After F3. Student review score + fixes; CI
  regression gate on model swaps.
- **M-E — "We can see it in prod."** After F5. The agent-quality dashboard.

## Cross-cutting invariants (apply to every task, every feature)

Copied so no task drops them:
- **POST-only** endpoints (`/health` excepted).
- **No headless coupling:** chat features never gate/break auto-mode or partner API; new
  chat-only slices unread/unwritten by headless paths (`project_headless_surfaces` memory).
- **Never narrate state:** position/status are derived or earned, not model-declared. Ephemeral
  coaching data (`roadmap_tasks`, `advisor_feedback`, `institution_profile`) uses dedicated
  write paths, never `commit_slice`.
- **`agent/` must not import `app/`** — use the `agent.analytics` no-op hook the app wires
  (F5).
- **Best-effort side signals:** LLM judges, research, analytics all degrade gracefully, never
  crash a turn.
- **TDD + frequent commits** per each plan; run api tests via `./run.sh` (arm64).
- **Comment the decision behind each change.**

## Execution checklist (feature-level gates)

Work each feature through its own plan; check it off here when its plan's Final Verification
passes and it's merged.

- [ ] **F2 — Proactive coaching layer** → `plans/2026-07-08-proactive-coaching-layer.md`
- [ ] **F4 — Cross-session memory + advisor loop** → `plans/2026-07-08-cross-session-memory.md`
- [ ] **F1 — Unify headless generation** → `plans/2026-07-08-unify-headless-generation.md`
- [ ] **F3 — Quality evaluation** → `plans/2026-07-08-quality-evaluation.md`
- [ ] **F5 — Observability** → `plans/2026-07-08-observability-agent-quality.md`
- [ ] **F8 — Quant correctness content pack** → `plans/2026-07-08-quant-correctness-content-pack.md`
- [ ] **F7 — Field-It survey pipeline** → `plans/2026-07-08-field-it-survey-pipeline.md`
- [ ] **F6 — Mock Committee** → `plans/2026-07-08-mock-committee.md`

## Suggested branch/PR strategy

One branch + PR per feature (F2, F4, F1, F3, F5), each merged when its Final Verification is
green — so review stays feature-sized and a milestone can ship without waiting for the rest.
F1 can be its own branch off `master` in parallel; the others chain in the order above.

## Deferred (not in these five)

- A real PLS-SEM/stats engine — explicitly rejected (students use their own software,
  `project_agent_gaps` memory).
- Deadline/timeline planning in the roadmap — YAGNI for now.
