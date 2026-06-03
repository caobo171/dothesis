# ResearchFlow — Architecture & Context-Memory Brief

> Handoff spec for Claude Code. Target: an AI thesis-assistant SaaS with 5 modules, delivered as a **single chat interface** where the student can move between steps freely. This document captures the design decisions; build against the principles in §1 first — everything else follows from them.

---

## 0. What we are building (read this first)

A chat-first web app that guides a student through the academic research lifecycle in 5 modules (M1 Topic Discovery → M2 Literature Review → M3 Research Design → M4 Data Analysis → M5 Writing). The student talks to one assistant in one thread. They can resume at any module, and — critically — **ask about or edit any module from anywhere**, even while working in another.

This is **not** a free-roaming autonomous agent. It is a **persistent, resumable state machine** with a thin routing layer on top and a shared, versioned state document underneath.

---

## 1. Core design principles (NON-NEGOTIABLE)

These are the decisions that everything else depends on. Do not violate them for convenience.

1. **State machine, not a free agent.** Each module is a handler with a defined job, prompt, and output schema. The assistant is *guided, not dictated* — it proposes, the user decides. Do not implement an open-ended ReAct loop that plans arbitrary multi-step tool sequences across the whole app.

2. **`context_store` is the single source of truth.** All durable project state (decisions, gaps, methodology, results) lives in one versioned document per project. Everything reads from it and writes to it.

3. **Resume = load durable state. The DB is the checkpoint.** "Stay in any step" is not an agent-runtime feature; it falls out of persisting `context_store` + per-module status. Do not reach for a checkpoint framework (LangGraph etc.) to get resume.

4. **Conversation focus ≠ workflow state.** Two separate concepts:
   - *Workflow state*: which modules are `done | in_progress | locked | needs_review`. Bookkeeping.
   - *Conversation focus*: what we're talking about **right now**. Fluid, decided per message.
   The current module is a **default context, never a lock.** Being "in M4" must never stop the user from asking about M2.

5. **Reads are free; mutates shift focus.**
   - A **read** (the user asks about another module) → answer from that module's state slice, **change nothing**, focus stays put.
   - A **mutate** (the user edits another module) → apply the edit, shift focus to it, and **flag downstream modules `needs_review` (⚠)**. This is context propagation.

6. **"Reads all previous messages" is a UX promise, NOT "load the whole transcript every turn."** Maintain the feeling of total recall via layered memory (§5), not by stuffing the full transcript into every prompt. This is the single most misunderstood part of the design — see §5 in full.

7. **Three interaction shapes — don't treat all modules as "an agent" (§3).**

8. **Token metering wraps the actual LLM call.** Estimate → reserve → reconcile on real usage. Bounded context (§5) is what keeps real cost aligned with the per-action pricing table.

---

## 2. State model: `context_store` as the spine

One aggregate root per project. Store in **Postgres `JSONB`** (better partial-update + querying than MySQL JSON for this shape). Keep `version_history` as append-only snapshots.

```ts
type ModuleId = 'M1' | 'M2' | 'M3' | 'M4' | 'M5';
type ModuleStatus = 'locked' | 'in_progress' | 'done' | 'needs_review';

interface Project {
  id: string;
  status: Record<ModuleId, ModuleStatus>;   // workflow state (principle #4)
  focus: ModuleId | null;                    // conversation focus (default, not a lock)
  contextStore: ContextStore;                // the spine (principle #2)
  tokenLedger: TokenLedger;
  versionHistory: Snapshot[];
}

interface ContextStore {
  research_title?: string;
  research_questions?: string[];
  research_gaps?: CitedGap[];        // each with supporting_papers + page refs
  hypotheses?: string[];
  methodology?: MethodologyConfig;   // paradigm, design, tool
  analysis_outline?: AnalysisOutline;
  analysis_results?: AnalysisResult[];
  final_sections?: DocumentSection[];
  // per-module rolling conversation summaries (see §5)
  module_summaries?: Partial<Record<ModuleId, string>>;
}
```

The structured store holds **decisions**. The conversation transcript (separate table, §5) holds **nuance and asides**. Keep them distinct.

---

## 3. The three interaction shapes

The 5 modules are not uniform. Build them with the right mechanism:

| Modules | Shape | Mechanism |
|---|---|---|
| M1, M3, M5 | Guided click-first wizard | Structured LLM call (`generateObject` + Zod schema) → write a validated slice to `context_store`. Not a chat loop. |
| M2 | Free chat loop with phases | Streaming chat (`streamText`) + a small phase machine: `familiarization → research_state → gap_analysis → reference_confirm → output_gen`. Regeneration-on-rejection = append to turn log + re-prompt; preserve history. |
| M4 | Pipeline with real computation | Detect data type → propose outline → user confirms → execute step-by-step. **M4 requires actually running statistics on raw uploaded data** (t-test, Sobel mediation, scatter) — a sandboxed Python service, not just LLM interpretation. See §8 and §9. |

---

## 4. The router (the piece that makes chat-first + jump-anywhere work)

A thin layer in front of the module handlers. On **every** user message:

1. **Classify** `(intent, target)` — a cheap call (Haiku) or rules + tool-calling. Output is structured JSON.
2. **Assemble context** scoped to the target (§5).
3. **Dispatch** to the target module's handler.
4. On `mutate`, **propagate**: write changes, set `focus = target`, mark downstream modules `needs_review`.

```ts
type Intent = 'continue' | 'read' | 'mutate';

interface RouteDecision {
  intent: Intent;
  target: ModuleId;        // which module this message concerns
  changesFocus: boolean;   // true only for a mutate to a non-focus module
}
```

Router classification prompt (sketch — return JSON only, no prose):

```
You route messages in a thesis assistant with modules:
  M1 Topic, M2 Literature/gaps, M3 Method/design, M4 Data analysis, M5 Writing.
Current focus: {focus}. Recent turns: {recent}. Project state keys present: {state_keys}.

Classify the user's message:
- intent: "continue" (works within current focus),
           "read" (asks ABOUT another module, no change requested),
           "mutate" (asks to CHANGE/ADD/REDO something in a module).
- target: the module the message concerns (default = current focus).
Return ONLY: {"intent": "...", "target": "M_", "changesFocus": bool}
```

Worked example (this is the behaviour to verify):
- User in M4 asks *"remind me what gap 2 was"* → `{read, M2}` → answer from `research_gaps`, **focus stays M4**, nothing flagged.
- User in M4 asks *"add a gap about remote work"* → `{mutate, M2, changesFocus:true}` → edit gaps, `focus = M2`, mark **M3, M4, M5 = needs_review ⚠**.

---

## 5. Memory & context assembly (THE key resolution)

### The problem
A chat UI makes users assume the assistant "can read everything we've ever said." A naive read of §1.6 ("use state slices") seems to break that. It does not — because **"reads all previous messages" (UX promise) and "loads the entire transcript into the prompt every turn" (implementation) are different things.**

For a thesis spanning weeks and hundreds/thousands of messages you **cannot** keep it all in-window anyway: you hit the context limit, per-message cost explodes (and breaks the per-action pricing table), and recall *degrades* when the model attends over a huge context. So bounded context + retrieval is not a compromise — it is the only thing that scales chat to that length while *preserving* the recall illusion.

### The model: assemble each prompt from three sources + a mode switch

```
Sources, in priority order:
  1. Structured state   — decisions from context_store (focus slice + target slice). Small. ALWAYS in.
  2. Recent turns       — last ~N turns verbatim. ALWAYS in. (guarantees "remembers what I just said")
  3. Retrieved turns    — semantic search over the FULL transcript, on demand. (covers old references / asides)
  + Rolling summaries   — per-module summaries of compacted older segments. Cheap, included when relevant.

The full transcript lives in the DB (unbounded). It is SEARCHED, not RESIDENT.
```

### Mode switch + budget logic

```ts
const WINDOW            = 200_000; // model context window
const TARGET            = 40_000;  // aim to keep the prompt ~this size: sharper attention, predictable cost
const FULL_MODE_CEILING = 90_000;  // if everything fits under this, skip ALL tiering machinery

function assembleContext(msg, route, store, transcript): AssembledContext {
  const handlerPrompt = handlers[route.target].systemPrompt(store);
  const state         = sliceFor(store, route);   // focus slice + target slice (cross-module read/mutate)
  const fixed         = tk(systemPrompt) + tk(handlerPrompt) + tk(state);

  // --- FULL MODE: short projects. Perfect recall, zero machinery. Build this first. ---
  if (tk(transcript) + fixed < FULL_MODE_CEILING) {
    return { systemPrompt, handlerPrompt, state, turns: transcript };
  }

  // --- TIERED MODE: long projects. Add this ONLY when the threshold is crossed. ---
  let budget = TARGET - fixed;

  const recent = takeRecentTurns(transcript, reserve = 0.45 * budget); // always-present verbatim tail
  budget -= tk(recent);

  const retrieved = referencesOutside(msg, recent, state)              // cheap heuristic/classifier
    ? searchTranscript(msg, { scope: route.target, topK, maxTokens: 0.40 * budget })
    : [];
  budget -= tk(retrieved);

  const summaries = rollingSummaries(store, route.target, { maxTokens: budget });

  return { systemPrompt, handlerPrompt, state, turns: recent, retrieved, summaries };
}
```

Compaction (async, after each committed turn, tiered mode only):

```ts
onTurnCommitted(turn) {
  embedAndStore(turn);                 // EVERY turn is searchable, always — regardless of mode
  if (recentWindowExceedsReserve()) {
    const evicted = turnsAgingOut();
    foldIntoSummary(evicted, evicted.module);  // cheap Haiku summarization → context_store.module_summaries
  }
}
```

### What lives where (decide this per piece of info)
- **Decisions** (title, gaps, methodology, results) → `context_store`. Answers the common case (e.g. "what was gap 2") cheaply, no transcript needed. This is why cross-module **reads** are cheap.
- **Nuance / asides / reasoning** ("you suggested firm size as a control, why?"; "my advisor is strict about APA") → transcript. Never distilled into state, so **retrieved on demand**.
- **Aged-out detail** → rolling per-module summaries.

### Build guidance
Ship **FULL MODE first** — just send the whole transcript while it fits. Perfect recall, no retrieval, no embeddings. Add the tiered path (recent window + retrieval + summaries) only when real projects start crossing `FULL_MODE_CEILING`. Build the *threshold check* early; build the *memory manager* late.

---

## 6. Module handler interface

Every module implements the same contract. The router dispatches to one of these.

```ts
interface HandlerInput {
  message: string;
  route: RouteDecision;
  ctx: AssembledContext;     // from §5
  store: ContextStore;       // read-only view
}

interface HandlerResult {
  message: RenderableMessage;          // assistant reply (may include quick-reply chips)
  writes?: Partial<ContextStore>;      // state mutations to persist (mutate only)
  invalidates?: ModuleId[];            // downstream modules to flag needs_review (mutate only)
  statusChange?: Partial<Record<ModuleId, ModuleStatus>>;
  tokenCost: number;                   // actual, for the meter (§1.8)
}

interface ModuleHandler {
  id: ModuleId;
  systemPrompt(store: ContextStore): string;   // module persona + instructions
  slice(store: ContextStore): object;          // what this module owns/reads
  tools?: Tool[];                               // e.g. M4: stats execution tool (sandboxed)
  handle(input: HandlerInput): Promise<HandlerResult>;
}
```

Mutation + propagation flow (the only place state changes):

```ts
async function onMessage(project, message) {
  const route  = await router.classify(message, project);
  const ctx    = assembleContext(message, route, project.contextStore, transcript);
  const result = await handlers[route.target].handle({ message, route, ctx, store: project.contextStore });

  if (route.intent === 'mutate') {
    applyWrites(project.contextStore, result.writes);
    project.focus = route.target;                              // mutate shifts focus
    for (const m of result.invalidates ?? []) project.status[m] = 'needs_review'; // ⚠ downstream
    snapshotVersion(project);                                  // version_history
  }
  meter.reconcile(project, result.tokenCost);                  // real usage
  persist(project); appendTranscript(message, result.message);
}
```

---

## 7. Recommended stack

- **App**: Next.js (App Router) + Vercel AI SDK — `generateObject` for wizards (M1/M3/M5), `streamText` for chat (M2/M4). Provider = Claude (Opus/Sonnet for writing & gap analysis; Haiku for routing, initial coding, summaries).
- **State**: Postgres `JSONB` (`context_store` + append-only `version_history`). Separate `transcript` table (one row per turn) + embeddings (pgvector) for retrieval.
- **Async**: Redis + BullMQ for file parsing, batch paper analysis, long generations, compaction. Do not run these inline in request handlers.
- **Polyglot worker (required)**: Python (FastAPI) sidecar in Docker for:
  - **GROBID** — academic PDF → structured references (don't hand-roll citation extraction).
  - **pyreadstat** — `.sav` / `.spv` parsing.
  - **Stats sandbox** — `pandas` / `scipy` / `statsmodels` / `pingouin` to actually run M4's ad-hoc tests.
- **Frontend**: TipTap (ProseMirror) for M2/M5 document preview/editing; React Flow for the M3 conceptual-model canvas.
- **Export**: `docx` (docx-js) + citeproc-js (CSL) for citations; existing Puppeteer/LaTeX path for PDF.

---

## 8. Risks / must-get-right

1. **Stats execution is a security surface, not a feature.** "Run a Sobel test on my data" is one prompt-injection away from arbitrary code if the LLM emits free-form Python. Constrain to a whitelisted analysis DSL / pre-built functions, run in an isolated sandbox (gVisor/Firecracker or a locked-down, network-less container with hard resource limits).
2. **Token metering must wrap the call.** The pricing table is per-action but real cost is per-token and varies with paper length and history. Meter at the AI SDK boundary; bounded context (§5) keeps this honest.
3. **Resume granularity.** M2's phase machine implies resuming *mid-chat*, so persist phase pointer + turn history to Postgres, not just Redis. Redis sessions don't survive.
4. **Soft locks, not walls.** `locked` modules are *recommendations*. A user can wander into M4 before M2 has gaps — the handler answers gracefully ("no gaps defined yet, want to do that first?") rather than blocking.

---

## 9. Entry wizard / flexible onboarding (project bootstrap)

Students don't always start at zero. The entry wizard is a **one-time bootstrap that seeds `context_store` + statuses + `focus`, then hands off to the same chat + router** — it is NOT a parallel flow. It produces the same `{ writes, statusChange, focus }` shape a handler returns (§6); it just runs before the first message.

Flow: declare what you already have → import each via the module's **own** adapter → seed slices → reconcile dependency holes → compute entry focus → drop into chat there.

```ts
type Have = 'topic' | 'references' | 'gaps' | 'model' | 'instrument' | 'data' | 'draft';

interface ImportAdapter {
  module: ModuleId;
  import(input: ImportInput): Promise<{ writes: Partial<ContextStore>; status: ModuleStatus }>;
}

async function bootstrapProject(have: Have[], inputs): Promise<Project> {
  const store: ContextStore = {};
  const status = allLocked();
  for (const item of have) {
    const { writes, status: st } = await adapters[item].import(inputs[item]); // reuse module parsers
    Object.assign(store, writes);
    status[adapters[item].module] = st;       // usually 'done'; 'in_progress' if partial
  }
  reconcileDependencies(status, store);        // SAME propagation rule as §4, applied at intake
  const focus = computeEntryFocus(status);     // first non-'done' module in M1→M5 order needing attention
  return { contextStore: store, status, focus, /* ... */ };
}
```

### Declare → seed mapping

| User declares | Module | Seeds into `context_store` | Import method | Resulting status |
|---|---|---|---|---|
| Topic / title | M1 | `research_title`, `research_questions` | type · paste · file | `done` |
| References | M2 | `literature_sources` | PDF (GROBID) · DOI · list | `in_progress` (gaps not derived) |
| Gaps | M2 | `research_gaps` | paste · derive from refs | `done` |
| Model | M3 | `conceptual_model`, `constructs`, `hypotheses` | describe · build · upload | `done` |
| Questionnaire / guide | M3 | `questionnaire` / `interview_guide` | Word · PDF | `done` |
| Data / results | M4 | `analysis_results` (or raw for re-run) | `.sav` · SmartPLS · transcript | `in_progress` |
| Draft | M5 | `final_sections` | Word | `in_progress` |

### Key rules
- **Reuse the module parsers.** Importing references = the same GROBID pipeline M2 uses; importing `.sav` = the same M4 detector. Not a second import stack.
- **References ≠ literature review.** References → M2 `in_progress` (indexed, gaps not yet derived). Gaps → M2 `done`.
- **A model can back-fill hypotheses** into `context_store` even when M2 is empty — which creates a *dependency hole*.
- **Dependency holes are caught at intake** by the same propagation rule as a mutate (§4): model present + gaps absent → `status.M2 = needs_review` ("H1/H2 not yet grounded in a gap"); data present + model absent → `status.M3 = needs_review`.
- **Soft entry, not forced.** `computeEntryFocus` lands the user on the first hole/incomplete step *as a recommendation*. They can skip.

### Worked example — "I have a topic and a model"
- M1 `done` (title, RQs) · M3 `done` (model + hypotheses back-filled) · **M2 `needs_review`** (hole) · M4/M5 `locked`.
- Entry focus = **M2**, opened softly: *"You've got a topic and a model, but no literature review backing H1/H2 yet — build that now so they're grounded, or skip ahead to data analysis?"* Nothing is walled off.

---

## 10. Suggested build order

1. Project + `context_store` schema (Postgres JSONB) + version snapshots.
2. Single chat thread, **FULL transcript mode** (no router) — get **one** module working end-to-end.
3. `ModuleHandler` interface + the 5 handlers (wizard / chat / pipeline shapes per §3).
4. **Entry wizard** (declare/text path): `bootstrapProject` seeds `context_store` + statuses + `focus`, then hands off to chat (§9). File-import variants arrive with step 9.
5. Router: `(intent, target)` classification.
6. Read vs mutate + downstream `needs_review` propagation (§4, §6).
7. Token meter wrapping LLM calls.
8. **Tiered memory** (recent window + pgvector retrieval + rolling summaries) + the `FULL_MODE_CEILING` switch — only when projects outgrow full mode (§5).
9. File pipeline + Python sidecar (GROBID, pyreadstat, stats sandbox).

---

## Appendix — emphasis recap (the four things that are easy to get wrong)

- **Focus is a default, not a lock.** One chat thread; the user talks about any module anytime.
- **Read = free + no focus change. Mutate = focus shift + downstream ⚠.**
- **Total recall is maintained by layered memory, not by re-sending the transcript.** Full mode until it doesn't fit, then tiered (state + recent + retrieved + summaries).
- **It's a state machine over a shared state document, not an autonomous agent.** The DB is the checkpoint.
- **Flexible entry is a bootstrap, not a parallel flow.** The wizard seeds `context_store` + statuses, then it's the same chat. Imported state can have dependency holes (e.g. model without gaps) — caught by the same propagation rule that handles a mutate.
