# Architectural Review — DoThesis as a Vertical Agent with Persistent Structured Output

> Companion to [`DEEP_AGENT_AND_STREAMING.md`](DEEP_AGENT_AND_STREAMING.md).
> That doc *describes* what's implemented. This doc *judges* it against the
> goal the reader asked about:
>
> > "Build a project with persistent result (with clear structure), this
> > project run by a vertical (or a master and sub-agents) agent solving a
> > specific problem."
>
> DoThesis is the worked example. The question is: as a blueprint for the
> kind of project the reader wants to build, **what works, what doesn't, and
> what would you do differently if you were starting today?**

---

## TL;DR

| Dimension | DoThesis pattern | Verdict |
|---|---|---|
| **Vertical vs master/sub** | One free agent + 7 skills + small tool belt | **Right call** for chat-driven copilots; the wrong call would have been a tree of LLM orchestrators routing among themselves. |
| **Persistent structured result** | `context_store.json` (slice-owned, DAG-propagated) + final DOCX/PDF artifact | **Strong.** The slice ownership map + downstream `needs_review` DAG is the single best idea in the system and the part most worth copying. |
| **State enforcement** | `commit_slice` is the only write path; file API is read-only on the state | **Strong** as code; **weak** as a contract — the agent still has to *choose* to call it, and re-injecting `[PROJECT STATE]` every turn is the smell that it doesn't always want to. |
| **Domain knowledge** | Skills (progressive disclosure) | **Strong** in principle, **fragile** in practice — model skips skill reads after turn 1, which is why critical conventions migrated back into the system prompt. |
| **Long-running work** | Engine tools (`research_scout`, `export_docx`) wrap deterministic pipelines | **Strong.** Hand the agent *intent*, hand the pipeline the *execution*. |
| **Subagents** | Spec says yes; implementation is mostly one agent | Spec under-delivered; in practice the deterministic pipelines absorbed the work subagents would have done. **Probably fine.** |
| **Cost / latency control** | Token meter middleware, per-action billing | Adequate but reactive — no upfront budget caps. |

**Headline**: the architecture is a **good template** for what the reader described — *if* you internalize that the deep agent is the **conversational glue**, not the worker. The actual work (research, stats, writing) happens in deterministic Python pipelines the agent calls. Skills are domain prompts in a delivery system that conveniently looks like a filesystem. The `context_store` slice map is the load-bearing idea. Copy that pattern. Copy the marker-driven UI affordances. Don't copy the "model routes everything" optimism without the `[PROJECT STATE]` belt-and-braces.

---

## 1. The problem shape DoThesis is solving

Before judging the design, it helps to name what kind of problem we're looking at:

1. **One concrete deliverable.** A thesis. ~50–100 pages of structured text with
   citations and tables. The artifact has a clear shape: title → RQs → lit review
   → conceptual model → methodology → analysis → discussion → references.
2. **A long, branchy process.** The student doesn't know what they want at
   turn 1. They explore, change their mind, upload a paper, re-anchor.
3. **Heterogeneous compute needs.** Some turns are "rewrite this paragraph"
   (cheap, conversational). Others are "search the literature and validate
   citations" (60–120s, network-bound, real Python pipeline). Others are
   "run a Cronbach's α on this `.sav`" (sandboxed code execution).
4. **Stateful checkpoints.** Decisions made in M1 constrain M2; M3 depends on
   M2; M4 depends on M3; M5 reads everything. The DAG is real.
5. **Resumable.** A real thesis project spans weeks. State must survive.

This shape recurs in lots of "vertical AI" products: legal-brief drafting,
research reports, audits, design docs, marketing campaigns, RFP responses,
fundraising decks. **Anywhere the deliverable has a known structure and the
process to get there is long, branchy, and re-entrant — DoThesis's shape
fits.**

Where it doesn't fit: bursty single-shot tasks (one-prompt → one-answer),
realtime control loops, anything with a fixed pipeline and no human in the
loop (use a workflow engine, not an agent).

---

## 2. Vertical agent vs master/sub-agent — which is right?

The reader's question framed these as alternatives. They're not — they're a
spectrum, and the right point depends on **how much the work decomposes
into independent specialists**.

### Three reference points

**A. Pure vertical agent (one model, big prompt, fat tools).**
One model handles everything. Tools encapsulate complexity (search, code
execution, document rendering). The model decides what to call and when.

- **Wins**: simplest to debug, lowest latency, one stream of consciousness, no
  cross-agent context loss.
- **Loses**: prompt bloat as the domain grows; the model has to "be everyone"
  every turn.

**B. Master + specialist subagents.**
A planner LLM decomposes the task and dispatches to specialist LLMs (research
agent, writing agent, critique agent), aggregating their outputs.

- **Wins**: each specialist gets a focused prompt; you can run them in parallel;
  context windows stay small.
- **Loses**: orchestration overhead is real (every handoff is a serialization +
  re-loading of context); failure modes multiply (specialist returns junk, master
  doesn't notice); cost scales fast; debugging a 4-agent transcript is painful.

**C. Vertical agent + deterministic pipeline tools.**
One model, but the heavy lifting (research, analysis, rendering) is **Python**
that just happens to be wrapped as a tool. The "subagents" are not LLMs — they
are deterministic engines.

- **Wins**: cost predictability, testability, replayability. The expensive parts
  (citation scoring, statistical analysis, OOXML hyperlink rendering) are *coded*,
  so they don't drift run-to-run.
- **Loses**: when a step genuinely needs LLM judgment (re-ranking, summarization,
  consistency checking), you have to either upgrade the pipeline or kick back to
  the master.

**DoThesis is firmly C** — and that's the right answer for the problem shape.

### Why C wins for "vertical + persistent + structured"

- **Persistence wants determinism.** The `context_store` schema is a contract.
  An LLM subagent that hallucinates a key the master doesn't expect breaks the
  schema. A Python tool that validates against `SLICE_OWNERSHIP` doesn't.
- **Citations want reproducibility.** A research subagent might rank papers
  differently on rerun. The engine's `api_citations` orchestrator scores them
  the same way every time. For a thesis, "the same way every time" is the
  feature.
- **Long jobs want a progress channel.** A Python pipeline can `safe_print`
  every beat (this is exactly what `engine/utils/progress.py` does). An LLM
  subagent's only signal is its final message — you can't render a useful
  progress bubble off that.
- **Cost.** A pipeline that runs in 8 seconds at \$0 of LLM cost vs a
  subagent loop that runs 12 turns at \$0.40 is not a close call.

The spec did call out two subagent slots (`scout`, `writer`) — and in practice
those collapsed into the engine pipelines (`research_scout` tool wraps
`deep_research.py`; `export_docx` tool wraps the docx post-processor). The
implementation **was right to collapse them**.

### When to add a real LLM subagent

You only need one when:

1. The work needs **LLM judgment that can't be templated** (e.g., "is this
   citation actually relevant to RQ2?") AND
2. The work is **noisy enough that doing it in the main thread would blow
   the context window** AND
3. The work is **isolatable** — you can describe the input as a self-contained
   prompt and the output as a small JSON.

For DoThesis, the candidate that survives all three filters is **gap-quality
critique** (read 20 candidate gaps + 6 verified sources, return the 3 best
gaps with rationale and a refutability score). Even that one, today, lives
inline in M2 phase 3 — and it works fine because the engine pre-filters the
inputs hard.

**Rule of thumb**: every LLM subagent costs you debuggability. Earn it.

---

## 3. The `context_store` — the load-bearing idea

If you take one thing from DoThesis, take this.

```python
# agent/state.py
SLICE_OWNERSHIP = {
    "M1": ["research_title", "research_questions"],
    "M2": ["literature_sources", "research_gaps"],
    "M3": ["conceptual_model", "hypotheses", "methodology", "instrument"],
    "M4": ["analysis_outline", "analysis_results"],
    "M5": ["final_sections"],
}
READS      = {"M2": ["M1"], "M3": ["M1","M2"], "M4": ["M3"], "M5": ["M1","M2","M3","M4"], ...}
DOWNSTREAM = {"M1": ["M2","M3","M4","M5"], "M2": ["M3","M4","M5"], ...}
```

Three rules, enforced by code:

1. **Each module owns specific keys.** Nobody else writes them.
2. **Each module declares its reads.** That's the dependency graph.
3. **Writes propagate `needs_review` downstream.** Re-touching M1 doesn't
   silently invalidate the paper — it tells M2–M5 they need to re-validate.

This is the same idea as a **make/bazel build graph applied to LLM output**.
The agent is free, but the schema is not. When the agent writes via
`commit_slice(module, writes, reason)`:

- Keys validated against `SLICE_OWNERSHIP[module]` (rejects cross-write).
- Version snapshot appended (capped at 50 for cost).
- `focus = module` set.
- Downstream modules flagged `needs_review` from the DAG.

**Why this matters for the reader's project**: persistent structured output
without an ownership map is a mess waiting to happen. Two turns later the
agent will write the same key from two places and you'll have no idea which
is authoritative. The slice map *names the contract* between the agent and
the artifact.

### What's clever — and what's still fragile

- **Clever**: the contract is enforceable because **the file API does not
  expose the state file as writable**. Even if the agent tried to
  `write_file("/project/context_store.json", ...)` it can't — `commit_slice`
  is the only door. That's good belt-and-braces.

- **Fragile**: the agent still has to *choose* to call `commit_slice`. Nothing
  prevents it from saying "I'll mark M5 done" and then never committing. The
  `[PROJECT STATE]` header injection on every turn is a tell — it's a
  band-aid for the model confabulating status. It works, but the existence of
  the band-aid is evidence the contract isn't fully self-enforcing.

  **What would close the loop**: a "ghost-write detector" that, at end of
  turn, diffs what the agent *claimed* (parsed from its message) against what
  it *committed*. If it said "I'll save the gaps" and didn't, the next-turn
  header surfaces the discrepancy and the agent has to reconcile. Today this
  is handled informally — worth formalizing if you build a similar system.

### Generalize the pattern

For your own project, replace M1–M5 with whatever your deliverable's
sections are. For a legal brief: facts → issues → analysis → conclusion.
For an audit: scope → findings → evidence → recommendations. The shape is
identical:

```
{section: {owns: [keys...], reads: [sections...], invalidates: [sections...]}}
```

That table is the spine. Build it before you build the agent.

---

## 4. Skills as a delivery mechanism

The spec sells skills as "progressive disclosure": only the name + description
is in context at startup; the SKILL.md loads on demand; references load only
when needed. In theory this keeps each turn's prompt small.

**In practice, the reality is grittier:**

- The system prompt in `runtime.py:159` is *not* short. It carries the
  `[PROJECT STATE]` rules, the `[ATTACHED]` protocol, the `[OPTIONS]` /
  `[PAPERS]` / Mermaid markers, questionnaire shapes, markdown gotchas.
  All of this *should* live in the root skill. It lives in the prompt
  because **the model skips skill reads after the first turn**.

  Comment in the code is honest about it: *"models routinely ignore
  instructions they only see after a skill-read"*.

- So skills are actually doing two things:
  1. **Bulky domain content** that genuinely doesn't need to load every
     turn (M2 5-phase protocol, M4 analysis templates) — these *do*
     stay in skills.
  2. **Conventions that must hold every turn** (`[OPTIONS]`, state
     protocol) — these had to come *back* into the prompt because the
     model couldn't be trusted to re-read them.

**Skills are good for #1 and bad for #2.** Plan accordingly: when you build
your own system, the "must-hold-every-turn" stuff goes in the system prompt;
the "load when relevant" stuff goes in a skill-like progressive store. Don't
naively put everything in skills because the architecture doc says so.

---

## 5. Long-running work — pipelines, not subagents

DoThesis has two ★ long jobs: M2 research scout (30–90s) and M5 docx export
(8–20s). Both are **deterministic Python pipelines wrapped as tools** —
`research_scout` and `export_docx`. The agent calls them; they stream
progress beats; the agent gets back a compact JSON.

This is the **right pattern** for "vertical agent solving a specific
problem with persistent structured output":

- **Reproducible**: same inputs → same outputs, run after run. For a
  thesis, that's the difference between "shippable" and "novel each time".
- **Profileable**: latency is in known phases. You can optimize the slow
  one without retraining a prompt.
- **Restartable**: a pipeline can checkpoint internally; an LLM loop can't.
- **Stream-friendly**: the engine emits `{stage, message}` payloads via
  `engine/utils/progress.py`, which is bridged onto SSE via both a thread-id
  registry and a ContextVar — so even `asyncio.to_thread` workers inherit
  the emitter. (Detail covered in
  [`DEEP_AGENT_AND_STREAMING.md`](DEEP_AGENT_AND_STREAMING.md) §7.)

**Generalize**: anywhere your domain has a "this is deterministic and slow"
step, build the pipeline first and wrap it as a tool second. Don't try to
make the model do it just because the model technically can.

---

## 6. The chat surface — markers as a UI protocol

DoThesis uses **inline markers** (`[OPTIONS] a | b | c`, `[PAPERS] {...}
[/PAPERS]`, Mermaid fenced blocks) as a way for the agent to drive rich UI
without a separate tool-call channel. The frontend parses them out of the
streamed text and renders cards, papers panels, or SVG diagrams.

This is **pragmatic and underrated.** The alternative — making the agent
call a `display_papers_panel` tool — costs an extra LLM turn (the tool
call + result), doubles persistence (tool result *and* assistant message),
and breaks the streaming-text UX. Markers piggyback on the text stream the
agent is already producing.

**Caveats worth knowing if you copy the pattern:**

- The marker must be **parseable on the completed message**, not on a
  half-stream chunk. DoThesis parses on the `updates` LangGraph stream
  mode (after the message is complete), not the `messages` mode (chunk
  deltas). Otherwise a regex on a half-arrived `[PAPERS]` block would fail
  and the user would see raw marker text leaking into the chat.

- You need a **strip rule** on the frontend so the marker text doesn't show
  in the message bubble. DoThesis does this in `MessageBubble`.

- The marker grammar should be **conservative** (one marker per message
  preferred, well-defined precedence when two co-occur — `[PAPERS]` wins
  over `[OPTIONS]` in DoThesis). Don't let the model invent new markers
  in-prompt — it will.

---

## 7. Persistence — what the artifact actually is

For "persistent result with clear structure", DoThesis has **two** persistent
artifacts and they play different roles:

1. **`context_store` (Postgres JSONB row)** — the *living* artifact. The
   slice map says what's there. Versioned. Single-source-of-truth for any
   downstream consumer (the docx renderer, the Auto Thesis job, the dashboard).
2. **DOCX + PDF (S3 objects)** — the *frozen* artifact. Renderable at any
   time from the `context_store`. Disposable. Re-renderable on convention
   change (citation style, language).

This split is the right shape for any structured-deliverable system. Don't
conflate them. The `context_store` is your database; the DOCX is a view of
that database. If you let the DOCX become the source of truth, you'll spend
the rest of the project parsing it back to JSON.

**Other persistence layers in play** (also worth copying):

- **Conversation memory**: LangGraph's Postgres checkpointer keyed by
  `thread_id`. Resume mid-thread is free; multiple threads can run over the
  same project state.
- **Sandbox / scratch**: `/workspace/` per project — for generated
  questionnaires, scripts, intermediate exports. Not authoritative.
- **Version history**: bounded (50 commits) snapshot inside the
  `context_store`. Cheap insurance for "undo this change".

**Four persistence layers, each with a defined role**:
*conversation* (LangGraph checkpoint), *state* (context_store), *scratch*
(workspace), *frozen artifact* (S3 export). If you build something similar,
make this layering explicit before you write any tool code.

---

## 8. Honest weaknesses

Things that are *not* great about the current design — worth knowing before
you copy the template.

### 8.1 The model is the router (and routers are leaky)

The v2 brief's principle was "state machine, not free agent — do not
implement an open-ended ReAct loop." V3 deliberately reversed that. The
trade is real:

- **Won**: less code, more graceful handling of off-script user requests
  ("can we revisit M1?"), no rigid state walls.
- **Lost**: deterministic behavior. The model decides when to read a skill,
  when to call a tool, when to ask. On a noisy turn it can do none of those
  and just hallucinate.

The mitigations are good but not free:
- Eval suite of intent → expected skill + tool calls (the v2 testcases).
- `[PROJECT STATE]` re-injection every turn.
- The slice ownership map blocks the worst structural drift.

If your project's failure tolerance is **lower** than a thesis copilot's
(e.g., legal, medical, regulated finance), the free-agent shape is probably
the wrong starting point. Use a state machine and call LLMs from inside its
nodes. DoThesis's reversal is right for a *coaching* product where talking
the user through ambiguity is the value prop.

### 8.2 No upfront budget control

There's a token meter middleware (good) but it's reactive — it bills after
the call. For a turn that loops 6 tool calls deep and burns 40k output tokens
on a runaway Gemini regeneration, the user pays the bill. A **per-turn budget
cap** (kill the turn at N tokens, return a partial answer with apology) would
be cheap insurance. Wasn't on the implementation list at time of writing.

### 8.3 Multi-tenant agent caching is per-project, not per-user

`_agents: dict[uuid.UUID, object]` in `chat_v3.py` caches one agent per
*project id*. The checkpointer inside scopes conversations by `thread_id`.
This is fine for single-tenant or low-tenancy deployments. For high-fanout
(thousands of concurrent projects), the cache grows unbounded. Worth an LRU
if you go to scale.

### 8.4 Subagent story is under-specified

The spec talks about scout/writer subagents; the implementation collapsed
them into deterministic pipelines. That was right. But the docs still read
as if subagents exist, which will confuse the next implementer. **For your
own project: decide subagents-or-pipelines once and write only that path.**

### 8.5 Skills drift from prompt drift

Because critical conventions had to be moved back into the system prompt
(`[OPTIONS]`, `[PAPERS]`, state protocol), the skill files have a quiet
risk: they may *say* something the prompt overrides, or vice versa. Without
a lint, the two will drift. Worth a unit test: "every behavior in the root
skill that the agent must follow every turn is also in the system prompt."

### 8.6 No explicit "agent failure" UI

When the agent crashes mid-turn, `stream_turn` emits `{"type":"error",
"message":...}` and `_finalize` persists whatever streamed. That's the
right plumbing. But the user-facing experience of a partial answer + an
error banner is opaque ("what went wrong, can I retry?"). A retry flow with
*replayable* turns (LangGraph checkpoint already supports this) would make
it production-grade. Not there yet.

---

## 9. What would I copy, what would I change, what would I drop?

For a reader building "a vertical agent with persistent structured output":

### Copy
- **The slice ownership map + downstream DAG.** This is the most important
  idea. Build it before the agent.
- **`commit_slice` as the only write path.** Even if you have one schema,
  put it behind a tool. Don't let the agent free-write state.
- **`[PROJECT STATE]` re-injection.** A four-line band-aid that prevents
  hours of debugging "why does the agent think we're done."
- **Marker-driven UI protocol.** Cheap rich UI without an extra round-trip.
- **Deterministic pipelines as tools.** For any step that's slow,
  reproducible, or has a known-good algorithm.
- **Four-layer persistence.** Conversation / state / scratch / frozen
  artifact. Each with a clear role.
- **POST-only API** (DoThesis's `CLAUDE.md`). Boring choice, removes a
  whole class of auth-leakage bugs.

### Change
- **Make the schema-skill alignment a test, not a guideline.** Lint that
  the root skill and the system prompt don't contradict.
- **Add per-turn token caps.** Reactive billing is not enough.
- **Move the `[PROJECT STATE]` re-injection from "every turn" to "every
  turn that touches state."** Pure prose turns don't need it. Saves tokens.
- **Add a "claimed vs committed" diff at end of turn.** If the agent
  promised to save something and didn't, surface it.
- **Build replayable retries** on top of the LangGraph checkpoint.

### Drop
- **The mention of LLM subagents** unless you actually build them. The
  spec → implementation drift here is real and will confuse the next person.
- **Skills as the home for must-hold-every-turn conventions.** Put those
  in the system prompt and stop fighting the model.
- **Any code path that pretends `write_pipeline` still exists.** It was
  removed because stubbed tools produced confusing error messages — the
  scar in `agent/tools/writing.py` is a useful lesson: **don't ship stubs
  to a free agent. It will call them.**

---

## 10. A starter template for the reader's project

If you're building a vertical agent for some other domain — legal brief
drafting, audit reports, due-diligence memos, whatever — the order I'd
build in:

1. **Name the deliverable.** What is the frozen artifact? PDF, DOCX,
   spreadsheet, JSON export?
2. **Name the sections.** What modules does it have? (M1..M5 for thesis;
   yours will differ.)
3. **Write the slice map.** For each module: what keys does it *own*, what
   does it *read*, what does it *invalidate*?
4. **Write `read_slice` + `commit_slice`** with hard validation against the
   slice map. Snapshot history. Update focus + needs_review DAG.
5. **Build the pipelines for the slow / deterministic steps** (research,
   compute, render). Wrap each as a tool. Stream progress via a
   ContextVar-bound emitter.
6. **Write the system prompt with conventions** (`[OPTIONS]`, marker
   grammar, state protocol). Re-inject `[PROJECT STATE]` every turn.
7. **Add the skill files** for bulky domain content the agent reads on
   demand (per-module playbooks, references).
8. **Wire one LangGraph checkpointer** and one SSE bridge. Pump agent
   events and engine progress through one multiplexed queue.
9. **Add the eval suite** — intent → expected skill reads + tool calls.
   Run it on every prompt or skill change.
10. **Then, and only then**, consider whether a subagent (an LLM, not a
    pipeline) earns its keep for any step. Default answer: no.

That order works because each step **forces a decision** before the next
becomes hard. Skip step 3 and you'll be debugging schema drift in step 9.
Skip step 5 and your token bill will eat your margin. Skip step 6 and
you'll be re-injecting `[PROJECT STATE]` *and* `[ATTACHED]` *and* the
markers like DoThesis had to.

---

## 11. Final judgment

**DoThesis is a good template for the kind of project the reader described,
provided you internalize three claims:**

1. **The agent is glue, not the worker.** Real work happens in
   deterministic Python pipelines the agent calls. The model's job is to
   *choose* what to call and to *talk to the user* — that's it. Anywhere
   you find yourself asking the model to do a multi-step deterministic
   task, build a pipeline instead.

2. **State is a contract, not a vibe.** The slice ownership map, the
   read DAG, and the downstream invalidation rules are the spine. Build
   that table first. Without it you have a chatbot, not a deliverable
   system.

3. **The free-agent shape needs belt-and-braces.** `[PROJECT STATE]`,
   eval suites, schema-enforced commits, marker grammars. The framework
   gives you a loop; you give it the discipline.

If the reader's product needs **higher determinism** than that — pick a
state machine. If it needs **less structure** than that — pick a plain
chat copilot. DoThesis lives in the productive middle: deterministic
where it matters (state, pipelines), free where it pays (chat, routing,
domain reasoning). The architecture is, on balance, **a sound starting
point.**

The single thing I'd most strongly endorse copying is the `context_store`
slice map. The single thing I'd most strongly avoid is the optimism that
"the model will read the skill, it's right there." Belt and braces. Always.
