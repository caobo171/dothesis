> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# Guided Agent Architecture — enter-anywhere, guide-the-rest, lowest-effort

> **Status:** Proposed (design) · **Author:** drafted with Claude · **Date:** 2026-05-30
> **Scope:** the LangGraph **orchestrator** (`/orchestrator`), not the legacy `/engine` pipeline documented in [`../ARCHITECTURE.md`](../ARCHITECTURE.md).

This doc proposes how to evolve DoThesis from a **linear M1→M5 pipeline** into a **guided process over an artifact dependency graph**, so a student can arrive *stuck at any step*, have their existing work assessed, and be driven to a finished thesis with the lowest possible effort.

It is grounded in an external research pass (Anthropic *Building Effective Agents*; LangGraph 1.x docs; VeriMAP/EACL 2026; SagaLLM/PVLDB; *Levels of Autonomy for AI Agents*). Citations are inline; the **weak/uncited** parts are flagged explicitly — read [§9](#9-risks--what-the-research-does-not-cover).

---

## 1. Goal & non-goals

**Goal.** A student says *"I'm stuck on my methodology / I have a rough Chapter 2 / I have SPSS output but no write-up"* and the agent:
1. **Assesses** what they already have,
2. **Places** them in the thesis process,
3. **Backfills** any missing prerequisites that later steps depend on,
4. **Drives** the remaining work to done, asking for the minimum number of decisions.

**Non-goals (for this iteration).**
- Replacing LangGraph (the research found no capability gap that forces it — [§7](#7-framework-decision-keep-langgraph)).
- Adding a durable-execution engine (Temporal/DBOS) — deferred until a concrete failure mode justifies it ([§7](#7-framework-decision-keep-langgraph)).
- Autonomous multi-agent orchestration — wrong tool for a known, human-gated process ([§6](#6-research-backing-condensed)).

---

## 2. Current architecture (orchestrator)

```
Next.js (chat + M1–M5 sidebar + zero-typing card/list widgets)
   │ SSE
FastAPI (/api/v1: projects, threads, messages, uploads)   api/app/routers/chat.py
   │ graph.astream()
LangGraph   START → _seed → supervisor → {M1│M2│M3│M4│M5│END}     orchestrator/graph.py
   │              each module ──(_module_paused?)──→ supervisor│END
Postgres   projects · threads · messages · context_store(JSONB) · paper_uploads
   + LangGraph checkpoints (per langgraph_thread_id)
```

**Deliverables today** (`orchestrator/schemas/`):

| Node | Owns (`context_store` slice) | Key fields |
|------|------------------------------|------------|
| M1 Topic | `m1_topic` | `research_title`, `field`, `research_type`, `target_population`, `scope`, `objectives[]`, `research_questions[]` |
| M2 Literature | `m2_literature` | `research_state_summary`, `research_gaps[]`, `theoretical_framework`, `hypotheses[]`/`propositions[]`, `literature_review_doc`, `citation_list[]` |
| M3 Design | `m3_design` | `paradigm` + (`conceptual_model`,`scale_items`,`hypotheses`) \| (`themes`,`interview_guide`,`purposive_criteria`), `sampling_strategy`, `target_sample_size` |
| M4 Analysis | `m4_analysis` | `data_type_detected`, `analysis_outline`, `results{step→StepResult}`, `qual_codes[]`, `qual_themes[]`, `interpretations` |
| M5 Writing | `m5_writing` | `chapters{intro,lit_review,methodology,results,discussion,conclusion}`, `bibliography`, `export_artifacts[]` |

**Routing.** `supervisor` calls `next_unconfirmed_module()` (`orchestrator/state.py`): walk M1→M5, return the first slice without a `confirmed_at`. A module is "done" iff its slice has `confirmed_at`.

**Modes.** `interactive` (chat, pauses via `_module_paused`) vs `auto` (`_auto_fill()` fills everything silently).

### Why this doesn't serve the goal

| Need | Today | Gap |
|------|-------|-----|
| Enter at step N | `next_unconfirmed_module` always returns the *first* gap | No way to target a step |
| Assess existing work | Project always starts at M1; no intake | Missing |
| Backfill prerequisites | No dependency model | Missing — **the hard part** |
| Know when a step is *truly* done | `confirmed_at` flag only | No content validation (a confirmed-but-empty slice passes) |
| Safe rewind/edit | Editing M1 leaves M3–M5 silently inconsistent | No invalidation |
| Lowest effort | `auto` is all-or-nothing | No per-step autonomy |

The structure is a **pipeline wearing an agent costume**. The fix is in the *modeling layer*, not the runtime.

---

## 3. Target architecture

Five additions on the **existing** LangGraph graph. Nothing below requires a rewrite — they are new nodes + new state + metadata on existing modules.

```
                         ┌─────────────── PLANNER / ROUTER ───────────────┐
START → _seed → INTAKE → │  compute done/ready/blocked over artifact DAG; │ → {worker node} → PLANNER → …
                         │  pick next-best action; emit ONE low-effort    │            │
                         │  decision via interrupt()                      │            └→ END (await user)
                         └────────────────────────────────────────────────┘
   INTAKE: assess uploaded/pasted work → seed artifact slices → mark which are done/partial
   workers: M1..M5 (+ finer chapter nodes), each = generator + INDEPENDENT validator
```

### 3.1 Artifact dependency DAG + definition-of-done validators

Replace the implicit M1→M5 line with an explicit graph of deliverables. Each node declares **dependencies** and a **definition-of-done (DoD)** validator that is *separate from the generator* (research: LLM self-validation is unreliable — SagaLLM, PVLDB).

```python
# orchestrator/artifacts.py  (new)
@dataclass(frozen=True)
class Artifact:
    key: str                       # "topic", "framework", "design", "ch_methodology", ...
    slice: str                     # context_store field it reads/writes (or a sub-key)
    depends_on: tuple[str, ...]    # prerequisite artifact keys
    dod: Callable[[dict], "DoD"]   # deterministic + optional LLM-judge → done? + gaps

ARTIFACTS = [
    Artifact("topic",          "m1_topic",      (),                          dod_topic),
    Artifact("framework",      "m2_literature", ("topic",),                  dod_framework),
    Artifact("gaps",           "m2_literature", ("topic",),                  dod_gaps),
    Artifact("design",         "m3_design",     ("topic","framework"),       dod_design),
    Artifact("analysis",       "m4_analysis",   ("design",),                 dod_analysis),
    Artifact("ch_methodology", "m5_writing",    ("design",),                 dod_chapter),
    Artifact("ch_results",     "m5_writing",    ("analysis",),               dod_chapter),
    Artifact("ch_discussion",  "m5_writing",    ("ch_results","topic"),      dod_chapter),
    # ... intro, lit_review, conclusion
]
```

**Why finer than M5.** A student stuck on the *discussion* needs `results` + `RQs`, **not** a perfect M3. Modeling chapters as nodes makes entry precise. (Validated pattern: VeriMAP models subtasks as a DAG with per-node verification functions — EACL 2026.)

**DoD returns `done | gaps`**, not just a boolean — the gap list is what the planner uses to drive work and what intake uses to assess uploads.

### 3.2 Intake / triage node (the "I'm stuck" front door)

A subgraph that runs when a project is new *or* the user drops in existing work. It:
1. Asks (cards) *"Where are you / what do you have?"*, or ingests an upload/paste.
2. An **assessment agent** maps artifacts into the DAG — e.g. "complete topic, partial methodology, no analysis" — and **seeds the matching `context_store` slices** from the existing work instead of regenerating.
3. Hands off to the planner with the graph pre-populated.

This is the **highest-leverage missing piece**: today every project starts at M1.

### 3.3 Planner / router node (replaces `next_unconfirmed_module`)

Given current artifact state, compute — **deterministically** (topo-sort), LLM only for ambiguity:
- `done / ready / blocked` for every artifact,
- the **next-best action**: if the user wants `ch_discussion` but `analysis` is missing → *backfill `analysis` first* (with a one-line "why"),
- surface it as **one** low-effort decision via LangGraph `interrupt()`.

Keep it rule-based; the live logs showed the current LLM nav-classifier mis-routing "I'll use a quantitative survey" → M3. Determinism here is more debuggable.

### 3.4 Progressive autonomy ("lowest effort")

Generalize `interactive`/`auto` into a **per-artifact autonomy level** (research: *Levels of Autonomy*, arXiv 2506.12469 — autonomy is a design choice independent of capability):

- **Draft-first, confirm-light.** Every step generates a *complete* candidate, then asks only accept/nudge — never field-by-field interrogation. The card/list widgets are the surface.
- For *minimum* effort, lean toward **L3 Consultant / L4 Approver** (agent plans+executes, user approves) — note the paper's L2 "Collaborator" (draft-then-edit) is actually *more* hands-on.
- Each worker exposes `auto_fill()` **and** `propose_then_confirm()`; the planner picks based on the autonomy level + whether the field is user-specific (their data, a judgment call → must ask).

### 3.5 Downstream invalidation

When an upstream artifact changes, mark dependents **stale** (don't silently leave them inconsistent). A `stale` flag + "N downstream steps may need review" nudge. Borrow saga-style **compensation** (SagaLLM): each artifact has a way to roll back / mark-for-regen the minimal affected set. This is what makes "go back and change RQs" safe.

### 3.6 Conversation resilience — staying on flow (the "out of nowhere" problem)

It's a chat box, so users digress: random questions, anxiety, meta-questions, "actually let's change my topic." A guided agent must handle **any** message like a human and steer back — **without feeling like a phone tree**.

**Principle: two layers; the task is *parked*, not *lost*.** Separate the **conversation layer** (handles any message) from the **task layer** (artifact DAG + planner). The current step and the exact pending question sit parked in the LangGraph `interrupt()` checkpoint, so a digression never destroys them — returning is just resurfacing the parked question.

```
user message → DISPATCHER (every turn): on-task? digression? navigation? meta? frustration?
   on-task ───────► worker (resume the interrupt)
   digression/meta► concierge: answer briefly + re-surface the parked question (as a card)
   navigation ────► planner re-plans (mark downstream stale)
   frustration ───► offer to lower effort ("want me to just draft it?") + anchor
   off-scope ─────► politely decline + redirect
```

**The human move — "Answer, then anchor."** Never ignore, never just re-ask. Three beats in one message: (1) acknowledge/answer the digression briefly, (2) bridge back, (3) re-surface the pending question as a **one-click card** so returning costs zero effort. Because the card persists in the UI, "where was I?" never happens — the user can ignore the prose and just click.

```
User:  wait, does APA 7 need a DOI for every source?
Agent: Good catch — APA 7 wants a DOI when one exists, else the URL. I'll handle that
       automatically at the references step, so don't worry about it. 🙂
       Back to your design though — roughly how many people can you survey?
       [ ~100 ]  [ ~200 ]  [ 300+ ]  [ Not sure — you pick ]
```

**Per-turn dispatcher (extends the existing `_classify_user_intent`):**

| User does | Intent | Behavior |
|-----------|--------|----------|
| Answers the question | `on-task` | Feed to current worker, advance |
| Random factual Q | `digression` | Answer in 1 sentence → anchor |
| "How many steps left? what are you doing?" | `meta` | Show progress from the DAG (done/ready/blocked) → anchor |
| Vents / anxious | `frustration` | Empathize → **offer to lower effort** ("I can draft it, you review") → anchor |
| "Actually, change my topic" | `navigation` | *Real* redirect — route to planner, mark downstream stale, **don't** force back |
| "Write my cover letter" | `off-scope` | Politely decline + redirect to what we can do |
| "idk / you choose" | `delegation` | Pick a sensible default, state it, move on (already supported) |

**Two guardrails against the phone-tree feel:**
- **Don't over-steer.** Tell *digression* (park-and-return) apart from *intent to redirect* (re-plan). Forcing "back to step 3!" when the user wants something else is the robotic failure mode.
- **The next action is always visible** — the step's card persists, so the user is never lost.

> **Today's gap:** `base.py` handles `off_topic` by *ignoring the reply and re-asking* (`off_topic: ignore the reply`). That's the cold part. Change it to **answer-then-anchor**, and add `meta` + `frustration` branches. It lives architecturally as a **dispatcher node wrapping the planner**; the "park" is the same `interrupt()` checkpoint that powers enter-at-any-step — no new plumbing.

### 3.7 Context routing — windowed history to the conversation, authoritative state to the task

To not feel robotic, the **conversation layer must see recent messages, not just the current one** — otherwise "yes", "the second one", "like I said" are meaningless and it can't tell a digression from a continuation. But **more context ≠ better**: three context types must not be conflated.

| Context | Source | Who consumes it |
|---------|--------|-----------------|
| **Recent chat** (last N turns / window) | `messages`, sliced | Dispatcher + concierge — references, tone, digression detection |
| **Task state** (current artifact, pending question, DoD gaps) | structured `context_store` slices | Workers — **authoritative; never re-guessed from chat** |
| **Project memory** (topic, field, prior decisions, style) | project memory store | Concierge + workers — personalization |

**The rule:** chat history is for *understanding the human*; structured state is the *source of truth for the task*. Don't let a worker re-derive "what step are we on / what's filled" from scrollback.

> **Cautionary tale (a real bug in this repo):** M2's phase 1 read "the latest user message" and consumed the **"yes"** that was actually M1's *confirmation* → it skipped its own question and the conversation wedged. Fix was to gate on structured state (`is_resume`), not "grab the last message." Lesson, two-sided: give the **conversation layer more** (a window, so it's human); give the **task layer the precise answer + authoritative state** (so it doesn't misfire).

**Two practical rules:** (1) **Window, don't dump** — pass the last few exchanges, not the whole thread (cost, drift, stale-instruction pickup); the `add_messages` reducer keeps the full list, you slice before each LLM call. (2) **Summarize as threads grow** — a running "story so far" + the last few literal turns (thesis threads get long).

---

## 4. Data-model changes

Additive; no destructive migration.

- **`context_store` slices** gain internal markers (underscore-prefixed, like the existing `_phase_state`): `_status` (`empty|partial|done|stale`), `_dod_gaps[]`, `_source` (`generated|imported|assessed`), `_autonomy`.
- **New `artifact_state` view/table** (optional) materializing done/ready/blocked per project for the sidebar — or compute on the fly from slices.
- **New endpoints:**
  - `POST /projects/{id}/import` — seed `context_store` from a JSON blob or uploaded artifact (intake).
  - `POST /threads/start-at/{artifact}` — open a thread targeting an artifact; planner backfills deps.
  - `GET /projects/{id}/artifacts` — done/ready/blocked map for the UI.

---

## 5. The hard part: prerequisite backfill (flagged risky)

> ⚠️ **This is the one piece no source de-risks.** LangGraph time-travel *re-runs existing* checkpoints; saga compensation *undoes committed* work. **Neither generates an upstream artifact the student skipped entirely.** Backfilling a never-started `design` from a student's existing analysis is **bespoke logic we must design and validate ourselves.**

Proposed approach (to prototype first, before committing the rest):
1. Planner detects `target.depends_on` includes an artifact with `_status=empty`.
2. For each missing prerequisite, run its worker in a **reconstruct** mode seeded with whatever downstream evidence exists (e.g. infer the `design`/paradigm from the student's pasted analysis + topic), producing a *candidate* marked `_source=assessed`.
3. **Gate it:** the prerequisite's DoD validator + a single user confirm ("we inferred your design was a quantitative survey — correct?"). Never silently fabricate prerequisites.
4. Only then unblock the target.

Build this as the **first vertical slice** ([§8](#8-migration-plan)) because if reconstruction quality is poor, the whole "enter anywhere" promise is at risk.

---

## 6. Research backing (condensed)

| Claim | Confidence | Source |
|-------|-----------|--------|
| Workflow/state-machine skeleton > autonomous multi-agent for a known, gated process | high | Anthropic, *Building Effective Agents*; arXiv 2508.02694 |
| LangGraph `interrupt()`/`Command(resume=...)` + durable checkpointer = native human-gates & resume-anywhere | high | LangGraph docs (interrupts) |
| Time-travel replay + `update_state` fork enable reconstruction/branching at any checkpoint | high | LangGraph docs (persistence, time-travel) |
| Model deliverables as a DAG with per-node DoD verification functions; replan/retry on fail | high | VeriMAP, EACL 2026 (arXiv 2510.17109) |
| Validators must be **independent** of generators; saga compensation for rollback | high | SagaLLM, PVLDB (arXiv 2503.11951) |
| Autonomy is a design choice independent of capability; draft-first then approve | high | *Levels of Autonomy*, arXiv 2506.12469 |
| Durable engines (Temporal/DBOS/Restate) **complement**, not replace; layer only if needed | high | Pydantic-AI durable-execution docs; Temporal blog |

**Refuted (do not cite as support):** that Anthropic's orchestrator-workers maps cleanly onto the current supervisor+modules (ours is fixed-sequential, not dynamically decomposed); that coding-agent automation empirically lowers user effort; that comprehension (not capability) is the adoption limiter.

---

## 7. Framework decision: keep LangGraph

No documented capability gap forces a migration, and "add complexity only when it demonstrably improves outcomes" (Anthropic) argues against one.

| Option | Verdict |
|--------|---------|
| **LangGraph** (current) | **Keep.** Native dynamic `interrupt`, durable thread checkpointing, time-travel/fork — exactly the primitives for enter-anywhere + backfill. *Adopt native `interrupt()` to replace the hand-rolled `_module_paused`.* |
| Durable execution (Temporal/DBOS/Restate) | **Defer.** Complements, not replaces. Postgres checkpointing already gives durability; add only when a concrete weeks-long failure mode demands infra-grade recovery (and note: it covers infra crashes, **not** code bugs). |
| OpenAI Agents SDK / Pydantic-AI / CrewAI / AutoGen / LlamaIndex Workflows | **Not better here.** Built for open-ended autonomy; we want determinism + auditability + human gates. Borrow *patterns* (VeriMAP DAG/DoD, SagaLLM independent-validators) onto LangGraph, not the frameworks. |

---

## 8. Migration plan (each step shippable)

0. **Adopt native `interrupt()`** for human gates (replace `_module_paused`). Low-risk cleanup that pays off everywhere below.
1. **Add artifact metadata** — `depends_on` + `dod()` per module/chapter (`orchestrator/artifacts.py`). Pipeline still works; nothing routes on it yet.
2. **Import + start-at endpoints** — unlocks "drop in your half-finished thesis." *(Fastest path to the core pitch.)*
3. **🔬 Backfill vertical slice** — prototype prerequisite reconstruction ([§5](#5-the-hard-part-prerequisite-backfill-flagged-risky)) for ONE realistic case (e.g. enter at `analysis`, reconstruct `design`). **De-risk before going wide.**
4. **Intake/triage subgraph** — the assessment front door.
5. **Planner replaces `next_unconfirmed_module`** — topo-sort over the DAG; LLM only for ambiguity.
6. **Dispatcher + conversation resilience** ([§3.6](#36-conversation-resilience--staying-on-flow-the-out-of-nowhere-problem)) — answer-then-anchor; `meta`/`frustration` branches; windowed history to the dispatcher ([§3.7](#37-context-routing--windowed-history-to-the-conversation-authoritative-state-to-the-task)).
7. **Stale flags + autonomy slider + project memory.**

Steps 2–3 alone deliver "enter anywhere," and step 3 is where the real uncertainty lives.

---

## 9. Risks & what the research does NOT cover

1. **Prerequisite backfill is uncited & novel** ([§5](#5-the-hard-part-prerequisite-backfill-flagged-risky)). Reconstruction quality is the make-or-break unknown. Prototype first.
2. **Keep-vs-migrate is a reasoned inference, not a benchmark.** No source measured this exact composite vs a full migration.
3. **Validator reliability is itself unmeasured.** DoD validators can be wrong; decide deterministic-Python vs LLM-judge vs both, and how to gate the gater.
4. **LangGraph 1.x moves fast.** `interrupt()`/`Command(resume=...)` is current; `NodeInterrupt`/static breakpoints are deprecated — verify against live docs at build time.
5. **"Lowest effort" level is contested.** L3/L4 (approve) minimizes effort more than L2 (edit); validate with real students.

---

## 10. Open decisions (need product input)

| # | Decision | Recommended default |
|---|----------|---------------------|
| D1 | How to reconstruct skipped prerequisites? | Worker "reconstruct mode" seeded with downstream evidence + a single confirm gate ([§5](#5-the-hard-part-prerequisite-backfill-flagged-risky)) |
| D2 | Autonomy level for new projects | L3/L4 draft-first (generate full candidate → approve/nudge); per-step slider later |
| D3 | DoD validators: Python vs LLM-judge | Both per artifact — deterministic checks first, LLM-judge for prose quality; keep independent of generator |
| D4 | Add a durable-execution engine? | No, until a concrete weeks-long failure mode is identified |
| D5 | Artifact granularity | Finer than M5 — chapters as nodes; keep M1–M4 as-is initially |
| D6 | History window passed to the dispatcher | Last ~3–5 exchanges + running summary for long threads; never the whole thread ([§3.7](#37-context-routing--windowed-history-to-the-conversation-authoritative-state-to-the-task)) |

---

*Companion: current-state map lives in this conversation's analysis; legacy engine in [`../ARCHITECTURE.md`](../ARCHITECTURE.md). Full cited research report archived with the deep-research run.*
