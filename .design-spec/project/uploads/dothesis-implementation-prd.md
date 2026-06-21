# DoThesis — Implementation PRD (for Claude Code)

> **How to use this doc.** Build **phase by phase** (§13). Each phase has acceptance criteria — treat them as the definition of done before moving on. **Do not over-build:** the expensive pieces (tiered memory, stats sandbox, qualitative analysis, collaboration) are deliberately deferred. When a phase says "trivial X for now," build the trivial version and move on.
>
> **Companion doc:** `dothesis-architecture-brief.md` holds the *rationale* for the core decisions. This PRD is the *buildable spec*. Where they overlap, the types in this PRD are authoritative.

---

## 1. Scope

A chat-first SaaS that guides a student through the academic research lifecycle across 5 modules — M1 Topic Discovery, M2 Literature Review, M3 Research Design, M4 Data Analysis, M5 Writing — in **one chat thread**, with flexible entry (start anywhere) and free movement (ask about / edit any module from anywhere). Primary users: Vietnamese university/grad students (UI + content default to Vietnamese). Pricing is token-metered.

**This is a state machine over a shared, versioned state document — not an autonomous agent.** See §2.

---

## 2. Architecture summary (non-negotiables)

1. **`context_store` is the single source of truth** (one versioned JSON doc per project).
2. **Resume = load durable state. The DB is the checkpoint.** No checkpoint framework.
3. **Conversation focus ≠ workflow state.** `focus` is a *default*, never a *lock*.
4. **Reads are free; mutates shift focus.** Read → answer from a state slice, change nothing. Mutate → write + `focus = target` + flag downstream modules `needs_review`.
5. **"Reads all previous messages" is a UX promise maintained by layered memory, not by re-sending the whole transcript.** Full-transcript mode until it outgrows the window, then tiered (§5.2).
6. **Three interaction shapes** (wizard / chat / pipeline) — see §7.
7. **Token metering wraps the real call.**
8. **Entry wizard is a bootstrap, not a parallel flow** (§6).

---

## 3. Tech stack

- **App:** Next.js (App Router, TypeScript) + Vercel AI SDK. `generateObject` (Zod) for wizard modules; `streamText` for chat.
- **Model:** Claude — Opus/Sonnet for writing & gap analysis; Haiku for routing, summaries, initial coding.
- **DB:** Postgres + `pgvector` (retrieval, phase 3). `JSONB` for `context_store`.
- **Async:** Redis + BullMQ (file parsing, analysis, compaction).
- **Sidecar:** Python (FastAPI) in Docker — GROBID, `pyreadstat`, stats sandbox (§8).
- **Frontend libs:** TipTap (doc preview/edit), React Flow (M3 model canvas).
- **Export:** `docx` (docx-js) + citeproc-js (CSL); Puppeteer/LaTeX for PDF.

## 4. Repo structure

```
/app                      Next.js routes + server actions
  /api/projects/...       REST endpoints (§9)
/src
  /runtime
    lifecycle.ts          onMessage() — the spine (§5)
    router.ts             intent/target classification (§5.1)
    assembler.ts          context assembly + mode switch (§5.2)
    meter.ts              token metering (§5.5)
    propagation.ts        needs_review cascade (§5.4)
  /modules
    types.ts              ModuleHandler, HandlerResult, ContextSlice
    m1-topic.ts ... m5-writing.ts
    registry.ts           handlers + import adapters
  /bootstrap
    wizard.ts             bootstrapProject() (§6)
    adapters.ts           ImportAdapter per module
  /db
    schema.sql            DDL (§4 below)
    repo.ts               typed queries
  /sidecar-client         HTTP client for the Python service
/sidecar                  Python FastAPI (GROBID, parsers, stats sandbox)
/components               React UI (§10)
```

---

## 5. Data model

### 5.1 Postgres DDL

```sql
create extension if not exists vector;

create table projects (
  id              uuid primary key default gen_random_uuid(),
  owner_id        uuid not null,
  name            text not null,
  field           text,
  language        text default 'vi',
  citation_style  text default 'apa7',
  research_approach text,                  -- quantitative | qualitative | mixed | null
  status          jsonb not null default '{}',  -- Record<ModuleId, ModuleStatus>
  focus           text,                          -- ModuleId | null
  context_store   jsonb not null default '{}',
  token_balance   int not null default 0,
  created_at      timestamptz default now(),
  updated_at      timestamptz default now()
);

create table transcript_turns (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  role        text not null,                 -- 'user' | 'assistant'
  module_id   text,                          -- focus at time of turn
  content     text not null,                 -- rendered markdown/JSON
  token_count int default 0,
  embedding   vector(1536),                  -- phase 3 (tiered retrieval); null until then
  created_at  timestamptz default now()
);
create index on transcript_turns (project_id, created_at);

create table version_snapshots (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  context_store jsonb not null,
  status        jsonb not null,
  reason        text,
  created_at    timestamptz default now()
);

create table token_ledger (
  id            uuid primary key default gen_random_uuid(),
  project_id    uuid not null references projects(id) on delete cascade,
  action        text not null,
  estimated     int, actual int, balance_after int,
  created_at    timestamptz default now()
);

create table jobs (
  id          uuid primary key default gen_random_uuid(),
  project_id  uuid not null references projects(id) on delete cascade,
  kind        text not null,   -- parse_pdf | parse_spss | parse_smartpls | analyze | compact
  status      text default 'queued', -- queued | running | done | failed
  payload     jsonb, result jsonb, error text,
  created_at  timestamptz default now()
);
```

### 5.2 Core TypeScript types

```ts
type ModuleId = 'M1' | 'M2' | 'M3' | 'M4' | 'M5';
type ModuleStatus = 'locked' | 'in_progress' | 'done' | 'needs_review';
type Intent = 'continue' | 'read' | 'mutate';

interface ContextStore {
  research_title?: string;
  research_questions?: string[];
  research_objectives?: string[];
  research_gaps?: CitedGap[];
  hypotheses?: string[];
  theoretical_framework?: string;
  literature_sources?: PaperRef[];
  literature_review_doc?: string;
  methodology?: MethodologyConfig;     // paradigm, design, tool, sampling
  conceptual_model?: ConceptualModel;  // nodes + edges + hypothesis labels
  constructs?: Construct[];
  questionnaire?: Questionnaire;
  interview_guide?: InterviewGuide;
  analysis_outline?: AnalysisOutline;
  analysis_results?: AnalysisResult[];
  final_sections?: DocumentSection[];
  module_summaries?: Partial<Record<ModuleId, string>>;  // rolling, phase 3
}

interface CitedGap {
  id: string; description: string;
  supporting_papers: { author: string; year: number; page?: number; verified: boolean }[];
  relevance: 'High' | 'Medium' | 'Low';
  confirmed: boolean;
}

interface MethodologyConfig {
  paradigm: 'quantitative' | 'qualitative' | 'mixed';
  design: string;                       // 'PLS-SEM' | 'Thematic' | 'Sequential Explanatory' | ...
  tool: string;                         // 'SmartPLS' | 'SPSS' | 'NVivo' | ...
  sampling?: { strategy: string; min_size?: number; target_size?: number };
}
```

---

## 6. The message lifecycle (the spine)

`runtime/lifecycle.ts` — runs on every user message. Build the data model and handler contract to support all of this from day one; phase in the smart parts.

```ts
async function onMessage(project: Project, message: string): Promise<HandlerResult> {
  const route  = await router.classify(message, project);                 // §6.1
  const ctx    = await assembler.assemble(message, route, project);        // §6.2
  const result = await registry.handlers[route.target].handle({ message, route, ctx, store: project.context_store });

  if (route.intent === 'mutate') {
    applyWrites(project.context_store, result.writes);
    project.focus = route.target;                                          // mutate shifts focus
    for (const m of result.invalidates ?? []) project.status[m] = 'needs_review';
    snapshotVersion(project, result.reason);
  }
  Object.assign(project.status, result.statusChange ?? {});
  await meter.reconcile(project, route.target, result.tokenCost);          // §6.5
  await persistTurn(project, message, result.message);
  return result;
}
```

### 6.1 Router (`runtime/router.ts`)
Classify `(intent, target)` per message. **Phase 1:** trivial router that always returns `{ intent: 'continue', target: project.focus }`. **Phase 2:** Haiku classification (prompt in the brief §4). Output `{ intent, target, changesFocus }`. **No schema change between phases.**

### 6.2 Context assembler (`runtime/assembler.ts`)
**Phase 1:** FULL mode only — return the whole transcript + relevant `context_store` slices. **Phase 3:** add tiered mode below the constants.

```ts
const TARGET = 40_000, FULL_MODE_CEILING = 90_000;  // tune to real window + pricing

async function assemble(msg, route, project) {
  const handlerPrompt = handlers[route.target].systemPrompt(project.context_store);
  const state = sliceFor(project.context_store, route);   // focus slice + target slice
  const transcript = await loadTranscript(project.id);
  const fixed = tk(handlerPrompt) + tk(state);

  if (tk(transcript) + fixed < FULL_MODE_CEILING)
    return { handlerPrompt, state, turns: transcript };   // FULL mode

  // TIERED mode (phase 3): recent window + pgvector retrieval + rolling summaries
  let budget = TARGET - fixed;
  const recent = takeRecent(transcript, 0.45 * budget); budget -= tk(recent);
  const retrieved = referencesOutside(msg, recent, state)
    ? await searchTranscript(project.id, msg, { scope: route.target, maxTokens: 0.40 * budget }) : [];
  budget -= tk(retrieved);
  const summaries = rollingSummaries(project.context_store, route.target, budget);
  return { handlerPrompt, state, turns: recent, retrieved, summaries };
}
```

### 6.3 Module handler contract (`modules/types.ts`)

```ts
interface HandlerInput { message: string; route: RouteDecision; ctx: AssembledContext; store: ContextStore; }

interface HandlerResult {
  message: RenderableMessage;                  // assistant reply (+ optional quickReplies)
  writes?: Partial<ContextStore>;              // mutate only
  invalidates?: ModuleId[];                    // downstream → needs_review (mutate only)
  statusChange?: Partial<Record<ModuleId, ModuleStatus>>;
  tokenCost: number;                           // ACTUAL usage, for the meter
}

interface RenderableMessage {
  blocks: Block[];                             // markdown | citation | gap-card | doc-preview | table | model-canvas
  quickReplies?: { label: string; payload: string }[];
}

interface ModuleHandler {
  id: ModuleId;
  systemPrompt(store: ContextStore): string;
  slice(store: ContextStore): object;
  tools?: Tool[];
  handle(input: HandlerInput): Promise<HandlerResult>;
}
```

### 6.4 Propagation (`runtime/propagation.ts`)
On mutate, mark downstream-dependent modules `needs_review`. Dependency order: M1→M2→M3→M4→M5. Editing M2 invalidates M3–M5; editing M3 invalidates M4–M5; etc. Same function reused by the entry wizard (§6).

### 6.5 Token meter (`runtime/meter.ts`)
`estimate(action) → reserve → reconcile(actual)`. Write a `token_ledger` row per action; update `projects.token_balance`. Block an action if `balance < estimate` and surface "nạp thêm".

---

## 7. Module specs

| Module | Shape | Reads | Writes | MVP (phase) |
|---|---|---|---|---|
| **M1 Topic** | Wizard (`generateObject`) | — | `research_title`, `research_questions`, `research_objectives` | P1 |
| **M2 Literature** | Chat loop + phase machine | title, RQs | `research_gaps`, `hypotheses`, `theoretical_framework`, `literature_review_doc` | P1 |
| **M3 Design** | Wizard + canvas | gaps, hypotheses | `methodology`, `conceptual_model`, `constructs`, `questionnaire`/`interview_guide` | P2 |
| **M4 Analysis** | Pipeline + execution | methodology, model | `analysis_outline`, `analysis_results` | P2 (quant) / P3 (qual + sandbox) |
| **M5 Writing** | Wizard + doc editor | everything | `final_sections` | P1 (auto-fill M1/M2) |

**M1 Topic Discovery.** Field → topic clusters → concretize (3 directions, quant/qual tagged) → scope/population → generate objectives + RQs. Output written as a structured slice. Click-first; chat overrides.

**M2 Literature Review (chat-first).** Phase machine: `familiarization → research_state → gap_analysis → reference_confirm → output_gen`. AI presents the state of the literature *with page-level citations*, then gaps *with citations*, then confirms page refs (user can correct / skip → `[page?]`), then writes the Chapter-2 draft. Regeneration on rejection preserves history. **Persist phase pointer + turns** (resume mid-chat).

**M3 Research Design (multi-method).** Explain quant/qual/mixed → recommend based on RQs → branch:
- *Quant:* latent? + sample size → recommend PLS-SEM / CB-SEM / Regression / ANOVA → conceptual model (React Flow canvas, seeded from M2 gaps) → scale builder → sample size calc.
- *Qual:* design (Thematic / Grounded / Phenomenological / Case) → thematic framework → interview guide builder → purposive sampling.
- *Mixed:* sequential explanatory / exploratory → tools for both phases.

**M4 Data Analysis (adaptive).** Upload → **detect data type** (file signature + content) → propose the matching outline (SPSS / PLS-SEM / CB-SEM / Thematic / Mixed) → user edits/confirms outline → execute step-by-step with academic interpretation + out-of-threshold warnings (e.g. Cronbach item < 0.3). **Ad-hoc analysis via chat** (t-test, Sobel, scatter) requires the **stats sandbox** (§8) — phase 3.

**M5 Writing.** Auto-fill chapter structure from `context_store` (adaptive: quant vs qual layout). Section editor (paraphrase, citation insert, academic style, translate). Citation manager (CSL). Export.

---

## 8. Python sidecar contract (`/sidecar`)

```
POST /parse/pdf        { fileUrl }            → { references: PaperRef[], fullText }     # GROBID
POST /parse/spss       { fileUrl }            → { variables, descriptives, rawHandle }   # pyreadstat
POST /parse/smartpls   { html }               → { outerLoadings, ave, cr, htmt, paths }
POST /analyze          { rawHandle, op, params } → { result }                            # SANDBOXED
```

**`/analyze` is the security surface, not a feature.** `op` is from a **whitelist** (`descriptive`, `reliability`, `efa`, `correlation`, `regression`, `t_test`, `anova`, `sobel`, `bootstrap_mediation`, `scatter`). **Never** accept or `exec` free-form Python from the model. Run in an isolated container: no network, hard CPU/memory/time limits, read-only except a scratch dir. The LLM may only *choose an op + params*; it never emits code.

---

## 9. API surface

```
POST   /api/projects                      create (optional bootstrap declaration → §6)
GET    /api/projects/:id                  project + status + context_store
POST   /api/projects/:id/messages         MAIN chat endpoint (streaming) — runs lifecycle (§6)
POST   /api/projects/:id/uploads          file → enqueue parse job → returns jobId
GET    /api/jobs/:jobId                    job status/result
POST   /api/projects/:id/focus            set focus (sidebar click; read-only switch)
GET    /api/projects/:id/tokens           ledger + balance
POST   /api/projects/:id/export           { format: docx|pdf } → file
GET    /api/projects/:id/versions         snapshots (phase 2)
```

---

## 10. Frontend (`/components`)

```
<AppShell>
  <Sidebar>
    <ProgressTracker/>      status dots (done/in_progress/locked/needs_review ⚠), clickable = set focus (read-only)
    <ContextStorePanel/>    live slices, fresh-write highlight
    <TokenMeter/>
  </Sidebar>
  <Main>
    <FocusBar/>             "Đang ở: M_ · name"
    <ChatThread>
      <RouterBadge/>        appears on cross-module read/mutate (green/amber)
      <MessageBubble/>      renders Block[]: markdown | CitationList | GapCard | DocPreview(TipTap) | OutlineChecklist | ResultsTable | ModelCanvas(React Flow)
    </ChatThread>
    <Composer/>             quick-reply chips + free text input (streams to /messages)
  </Main>
</AppShell>
<EntryWizard/>              shown on project create (declare → import → bootstrap → enter)
```

**No `localStorage`/`sessionStorage`.** Server is the source of truth; chat history persists via the DB. Auto-save every 30s; chat survives reload.

---

## 11. Non-functional

- PDF ≤ 50MB parsed < 30s (async job). Chat first-token < 2s. Section gen (500 words) < 15s.
- `context_store` + transcripts encrypted at rest. Uploads/transcripts **never** used for training. Full-delete option.
- Auto-save 30s; chat history persistent across reload. Uptime target 99.5%.
- Responsive down to tablet; chat mode full-support on tablet.

---

## 12. Phased build plan with acceptance criteria

**Phase 0 — Scaffolding.** Next.js + TS, Postgres + DDL (§5.1), AI SDK wired to Claude, one streaming `/messages` endpoint echoing a model reply, auth stub.
- ✅ A message round-trips and streams; a `projects` row persists and reloads.

**Phase 1 — MVP (core loop, no router).** Lifecycle in FULL mode with trivial router; M1, M2, M5; entry wizard (declare/text path); token meter; export docx.
- ✅ New project from scratch → M1 wizard writes `research_title` + `research_questions`; `status.M1='done'`.
- ✅ M2 chat produces `research_gaps` (≥1 with citations) and a `literature_review_doc`; phase pointer + turns persist across reload.
- ✅ M5 auto-fills Ch.1/Ch.2 from M1/M2 `context_store`; export to `.docx` downloads.
- ✅ Entry wizard: declaring "topic" seeds M1 `done` and drops focus on M2.
- ✅ Token ledger decrements per LLM action; balance shown.

**Phase 2 — Router + design + quant analysis.** Real Haiku router (intent/target); read vs mutate + propagation; M3 multi-method (incl. React Flow canvas); M4 SPSS + SmartPLS adaptive outline + interpretation; file pipeline + sidecar (parse only); version history; citation manager (APA7).
- ✅ While focused on M4, "what was gap 2?" answers from M2 slice **without** changing focus (RouterBadge=read).
- ✅ "Add a gap about X" edits M2, shifts focus, and flags M3–M5 `needs_review` (RouterBadge=mutate).
- ✅ Upload `.sav` → detected as SPSS → Outline A proposed → user removes a step → AI runs confirmed steps with interpretation + a threshold warning.
- ✅ Entry wizard "topic + model" → M2 = `needs_review` with the soft prompt.

**Phase 3 — Qualitative, sandbox, tiered memory.** Stats sandbox (ad-hoc t-test/Sobel/scatter); M4 thematic analysis (coding → themes → quotes); tiered memory (recent + pgvector retrieval + rolling summaries) + `FULL_MODE_CEILING` switch; Semantic Scholar live search.
- ✅ "Run a t-test of TL by gender" returns results from the sandbox; no model-authored code executed.
- ✅ A project past `FULL_MODE_CEILING` still answers an old-reference question via retrieval; per-message token count stays bounded.

**Phase 4 — Advanced.** Mixed-methods integration report; CB-SEM/AMOS, NVivo/Atlas.ti import; journal templates; collaboration (advisor comments, sharing); mobile app.

---

## 13. Explicit non-goals for v1
- No autonomous multi-step agent planning. The router only classifies `(intent, target)`.
- No model-authored code execution — sandbox ops are whitelisted (§8).
- No tiered memory before `FULL_MODE_CEILING` is a real problem (§6.2).
- No anti-plagiarism / Zotero / Mendeley / Google Form export in v1.
- Hard module locks are **never** built — `locked` is a recommendation (soft).
