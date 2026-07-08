# Master Execution Roadmap — Vertical Agent Upgrade (8 features)

**Date:** 2026-07-08
**Status:** Program plan — sequences the specced features into one ordered build. **Audited by an
independent Fable-5 pass (2026-07-08); see F0 for the mandatory pre-build fixes.**

## ⚠ Read first: F0 is a hard prerequisite

An independent audit found a systemic defect: the coaching/memory features write new
`context_store` keys that **`DbProjectStateStore` silently drops in prod** (it round-trips only
`SLICE_OWNERSHIP` keys), plus contract/auth/packaging/test defects. **Do `F0 — Foundation Fixes &
Remediation` (`plans/2026-07-08-F0-foundation-and-remediation.md`) before F2/F4/F7/F11**, and apply
its Part B/C corrections while building each feature. See `project_db_store_persistence_gap` memory.
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

Prerequisite (audit-driven, do first):

| # | Feature | Plan | Tasks |
|---|---|---|---|
| F0 | Foundation fixes & remediation (DB persistence + contracts + errata) | `plans/…F0-foundation-and-remediation.md` | 3 + corrections |

Best-in-class extensions (make it best-in-class at guiding quant theses):

| # | Feature | Spec | Plan | Tasks |
|---|---|---|---|---|
| F6 | Mock Committee (Hội đồng ảo) | `specs/…mock-committee-design.md` | `plans/…mock-committee.md` | 4 |
| F7 | Field-It survey pipeline (Questionnaire Doctor + survify + ethics/consent) | `specs/…field-it-survey-pipeline-design.md` | `plans/…field-it-survey-pipeline.md` | 4 |
| F8 | Quantitative correctness content pack | `specs/…quant-correctness-content-pack-design.md` | `plans/…quant-correctness-content-pack.md` | 4 |
| F12 | Mid-journey state import (join a thesis in progress + activation) | `specs/…mid-journey-import-design.md` | `plans/…mid-journey-import.md` | 3 |
| F13 | Screenshot / export output ingest (feeds F8) | `specs/…screenshot-output-ingest-design.md` | `plans/…screenshot-output-ingest.md` | 3 |
| F9 | Model cost/quality eval ("shootout") | `specs/…model-cost-quality-eval-design.md` | `plans/…model-cost-quality-eval.md` | 5 |
| F10 | Provider routing + OpenRouter fallback | `specs/…provider-routing-fallback-design.md` | `plans/…provider-routing-fallback.md` | 4 |
| F11 | Thesis timeline + weekly nudge | `specs/…thesis-timeline-nudge-design.md` | `plans/…thesis-timeline-nudge.md` | 5 |

**55 tasks total.**

**F11 is the tagline capstone** — "an agent that goes with your thesis journey." F1–F10 make it
present and proactive *within* a session; F11 adds the *temporal* accompaniment (backwards
timeline from the defense date + one weekly nudge) so it walks with the student across the months.
Depends on F2 (roadmap position + UI) and F6 (the defense block closes the timeline).

## Audit-revised build order (2026-07-08)

The Fable-5 audit re-sequenced for correctness + value. Single track:

1. **F0** — foundation fixes (persistence + contracts). *Hard prerequisite.*
2. **F5 Task 1** — the `emit()` layer only (inert without a key), so everything ships instrumented.
3. **F8-content** — design→test matrix + two-register (cheapest, highest-leverage).
4. **F12** — mid-journey import (activation; uses partner inference; no F0 dep).
5. **F2** — coaching roadmap.
6. **F4** — advisor loop (needs F0 + F2). *The flagship.*
7. **F9 probe tier** — cost pressure-test (Gemini→Qwen/GPT).
8. **F1 steps 1–3** — gate unification (defer step 4 partner optional-inputs until a partner asks).
9. **F3** — quality rubric (needs F1 gate + F2; apply F0 read-API fix).
10. **F13** — screenshot/export ingest (needs F8).
11. **F7** — Questionnaire Doctor + survify + a folded consent/data-privacy generator (was F14 ethics).
12. **F6** — Mock Committee (ship heuristic early, enrich after F3).
13. **F11** — timeline + nudge.
14. **F10 Tasks 1–3** — provider factory + route (defer Task 4 cached-cost telemetry).
15. **F5 dashboards** — last.

**Deferred / not yet specced (proposed next):** integrity **methods audit trail + authorship
provenance**; **per-university DOCX templates** (invert the old F13 order — templates before Zotero,
since APA7 is hardcoded and `institution_profile.citation_style` is a dead field). Monetization
placement (free/paid boundary + paywall location) needs an owner. Nudge channel → Zalo/Messenger.
Defense slide-deck generator. "When the agent is wrong" confidence/escalation rule + advisor-
precedence rule. Mid-collection monitoring.

**F9 + F10 are the cost/reliability pair:** F9 tells you *which* model (quality × VN × true cost);
F10 lets you *switch and fall back* safely (one factory, OpenRouter cascade, caching-preserving
native escape hatch, route-independent billing). Do F10 right after/with F9 — both attack the
cost concern and neither blocks the coaching/quality line.

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

- **F9 (model cost/quality eval)** — the probe suite (Tasks 1–3, 5) is useful **immediately** and
  standalone; its compose-quality dimension (Task 4) needs F3. Given cost-vs-quality is a live
  concern (Gemini 3.5 Flash tripled in price), run F9's probe tier **early** to pressure-test a
  swap to Qwen3.6 Plus / GPT-5.4 mini, and complete Task 4 once F3 lands to make the swap fully
  data-gated.

**Revised full order (single track), advisor-loop + quick-wins + cost weighted:**
F8-content (matrix + two-register) → **F9 probe tier (Tasks 1–3,5)** → F2 → F4 → F1 → F3 →
**F9 Task 4 (compose-quality)** → F8-rest → F7 → F6 → F5.

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

- [ ] **F0 — Foundation fixes & remediation (DO FIRST)** → `plans/2026-07-08-F0-foundation-and-remediation.md`
- [ ] **F12 — Mid-journey state import** → `plans/2026-07-08-mid-journey-import.md`
- [ ] **F13 — Screenshot / export output ingest** → `plans/2026-07-08-screenshot-output-ingest.md`

- [ ] **F2 — Proactive coaching layer** → `plans/2026-07-08-proactive-coaching-layer.md`
- [ ] **F4 — Cross-session memory + advisor loop** → `plans/2026-07-08-cross-session-memory.md`
- [ ] **F1 — Unify headless generation** → `plans/2026-07-08-unify-headless-generation.md`
- [ ] **F3 — Quality evaluation** → `plans/2026-07-08-quality-evaluation.md`
- [ ] **F5 — Observability** → `plans/2026-07-08-observability-agent-quality.md`
- [ ] **F8 — Quant correctness content pack** → `plans/2026-07-08-quant-correctness-content-pack.md`
- [ ] **F7 — Field-It survey pipeline** → `plans/2026-07-08-field-it-survey-pipeline.md`
- [ ] **F6 — Mock Committee** → `plans/2026-07-08-mock-committee.md`
- [ ] **F9 — Model cost/quality eval** → `plans/2026-07-08-model-cost-quality-eval.md`
- [ ] **F10 — Provider routing + OpenRouter fallback** → `plans/2026-07-08-provider-routing-fallback.md`
- [ ] **F11 — Thesis timeline + weekly nudge** → `plans/2026-07-08-thesis-timeline-nudge.md`

## Suggested branch/PR strategy

One branch + PR per feature (F2, F4, F1, F3, F5), each merged when its Final Verification is
green — so review stays feature-sized and a milestone can ship without waiting for the rest.
F1 can be its own branch off `master` in parallel; the others chain in the order above.

## Deferred (not in these five)

- A real PLS-SEM/stats engine — explicitly rejected (students use their own software,
  `project_agent_gaps` memory).
- Deadline/timeline planning in the roadmap — YAGNI for now.
