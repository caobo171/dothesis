> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# Chat-based orchestration foundation (sub-project 1 of 7)

**Date:** 2026-05-25
**Status:** Draft — pending user review

## Context

PRD v1.1 (`new_prd/Copy of thesis_saas_PRD_v3.md`) pivots dothesis from a synchronous "submit topic → wait → get thesis" wizard into a chat-based research copilot with 5 modules (Topic Discovery, Literature Review, Research Design, Data Analysis, Writing). The user wants a LangGraph-driven architecture modeled on `langchain-ai/open_deep_research`: each module is a node with its own specialized agent and tool set; existing engine code is preserved and exposed as tools.

The pivot is too large for a single spec — it crosses 6+ independently buildable subsystems. We decomposed into 7 sub-projects, each with its own design → plan → implementation cycle:

| # | Sub-project |
|---|---|
| **1** | **Orchestration foundation (this spec)** |
| 2 | Module 2 (Literature Review) chat-first redesign |
| 3 | Module 1 (Topic Discovery) card-grid UX |
| 4 | Module 3 (Research Design) multi-method branches |
| 5 | Module 4 (Adaptive Analysis) data-type detection + parsers |
| 6 | Module 5 (Writing) auto-fill + new editor |
| 7 | New Next.js chat UI |

This spec covers **sub-project 1 only**: the LangGraph backbone, persistence, two entrypoints (interactive + auto-mode), generic agent contract, and the tool layer wrapping existing `engine/*` code. Module-specific UX and per-module agent quality are explicitly deferred.

## Goal

Land a working end-to-end orchestrator where:

1. A user can have a chat thread that walks through all 5 modules with a supervisor routing between dedicated module agents.
2. Auto-mode produces a complete thesis artifact (docx + pdf) via the same graph, no human in the loop.
3. The existing wizard + `python -m engine` path remains fully operational in parallel during rollout.

## Non-goals

- Module-specific UX (chat-first M2 phases, M1 card-grid, M3 model builder, M4 outline/parsers, M5 editor) — own sub-projects.
- New Next.js chat UI — sub-project 7.
- Per-module agent prompt quality. Sub-project 1 uses a shared clarification loop with a generic prompt.
- Multi-provider model routing. Sub-project 1 stays on Gemini via `ChatGoogleGenerativeAI`.
- Forking threads via LangGraph time-travel — deferred.
- "Pause auto-mode and switch to interactive" mid-run — deferred.
- Frontend wizard deprecation — separate decision after sub-project 7 stabilizes.
- New pricing rules — reuses `api/app/pricing.py` as-is.

## Decisions (locked from brainstorming)

- **Node completion criterion:** hybrid schema-driven. Each module declares a Pydantic output schema; agent loops until required fields filled + user confirms (interactive) or auto-fills + auto-confirms (auto-mode).
- **Auto-mode behavior:** fully silent. Zero user prompts between start and final artifact.
- **Runtime split:** interactive turns run in-process inside `api/` FastAPI (SSE streaming); auto-mode runs as a subprocess (reuses today's `api/app/job_runner.py` pattern).
- **Code location:** new top-level `orchestrator/` package, parallel to `engine/`, `api/`, `web/`.
- **Graph topology:** supervisor-routed. Supervisor sits between every module transition; module agents return to supervisor on completion. Matches `open_deep_research`'s pattern.
- **Agent-per-module:** 5 dedicated agents, each with its own system prompt + Pydantic schema + tool set. Shared `ModuleAgent` base class implements the clarification loop.
- **Per-project threads:** N threads per project. `context_store` (the confirmed module outputs) is shared across all threads in a project.
- **Concurrency conflict policy:** first-confirm-wins + alert. When thread B tries to confirm a module already confirmed by thread A, the user sees a "this was confirmed in thread A 3 minutes ago — discard / replace / merge" prompt.
- **Stop & resume auto-mode:** SIGTERM the subprocess; LangGraph's per-node checkpoint preserves progress; resume re-spawns and graph picks up at the next-node boundary.

---

## Architecture overview

```
                Browser (Next.js)
                       │
                       ▼ HTTPS + SSE
       ┌───────────────┴───────────────────────────┐
       │                                           │
       ▼ in-process                                ▼ subprocess
  api/ FastAPI                          python -m orchestrator
       │                                           │  --auto-draft
       ▼ imports                                   ▼ imports
       ┌──────────── orchestrator/ ────────────────┐
       │                                           │
       │   ┌─ Supervisor agent ─┐                  │
       │   │                    │                  │
       │   ▼                    ▲                  │
       │   M1 → M2 → M3 → M4 → M5 (5 agents,       │
       │   each calling its own tool set)          │
       │   │                                       │
       │   ▼ tools wrap                            │
       │   engine/utils/*  +  engine/phases/*      │
       └───────────────────────────────────────────┘
                       │
                       ▼
           PostgreSQL (Alembic-managed)
   ┌──────────┬──────────┬──────────┬──────────┬─────────────┐
   │ projects │ threads  │ messages │ context_ │ langgraph_  │
   │          │          │          │ store    │ checkpoints │
   └──────────┴──────────┴──────────┴──────────┴─────────────┘
```

**One graph, two runtimes.** Interactive chat imports the orchestrator in-process and streams via SSE. Auto-draft runs as a subprocess (existing `job_runner.py` pattern), writes to `events.jsonl`, and the existing SSE bridge in `api/app/routers/jobs.py` tails it.

**Supervisor in the middle.** Every module-to-module transition goes through the supervisor — it owns "what's next" based on `context_store` + user intent.

**Tools = thin wrappers over `engine/utils/*` and `engine/phases/*`.** Nothing in `engine/` gets rewritten; it's exposed as callable LangChain tools. Existing `python -m engine` path stays alive untouched.

---

## State model

Three layers, kept separate:

### 1. LangGraph in-memory state (per-turn, ephemeral)

`orchestrator/state.py`:

```python
class OrchestratorState(TypedDict):
    project_id: UUID
    thread_id: UUID
    messages: list[BaseMessage]       # LangChain message history (this turn)
    current_module: Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
    context_store: ContextStore        # the 5 module schemas (see below)
    mode: Literal["interactive", "auto"]
    user_intent: str | None
    pending_confirmations: list[str]
```

### 2. LangGraph checkpoints (durable, internal)

LangGraph's `PostgresSaver` writes to its own tables (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`). Provides: crash resume, time-travel, branching. We don't design these — LangGraph owns them. We call `PostgresSaver.setup()` once at app startup.

### 3. Application-owned tables (durable, queryable, user-facing)

```sql
projects                  -- one row per research project
  id                      UUID PK
  user_id                 UUID FK → users.id
  name                    TEXT
  field                   VARCHAR(64)
  language                VARCHAR(16)
  citation_style          VARCHAR(16)
  research_approach       VARCHAR(16)
  status                  VARCHAR(16)
  current_module          VARCHAR(8)       -- supervisor pointer
  created_at, updated_at  TIMESTAMPTZ

threads                   -- N per project (no UNIQUE on project_id)
  id                      UUID PK
  project_id              UUID FK → projects.id
  name                    TEXT             -- "Main", "Alt methodology", ...
  langgraph_thread_id     TEXT UNIQUE      -- scopes PostgresSaver state
  parent_thread_id        UUID NULL        -- (deferred fork feature)
  forked_at_message_id    BIGINT NULL      -- (deferred fork feature)
  status                  VARCHAR(16)      -- active / archived
  created_at, last_active_at  TIMESTAMPTZ

messages                  -- chat UI scrollback, per thread
  id                      BIGSERIAL PK
  thread_id               UUID FK → threads.id
  role                    VARCHAR(16)      -- user / assistant / system / tool
  content                 TEXT
  module_tag              VARCHAR(8)
  tool_calls_json         JSONB
  created_at              TIMESTAMPTZ

context_store             -- shared across threads of a project
  project_id              UUID PK FK → projects.id
  m1_topic                JSONB
  m2_literature           JSONB
  m3_design               JSONB
  m4_analysis             JSONB
  m5_writing              JSONB
  updated_at              TIMESTAMPTZ

runs                      -- one per auto-draft subprocess invocation.
                          -- Implementation: the DB table stays named `jobs` (no rename),
                          -- but the SQLAlchemy model is aliased to `Run` and HTTP routes
                          -- expose `/runs/*` paths for naming clarity. New columns are
                          -- added via Alembic; old `jobs` rows from the engine path
                          -- continue to function unchanged.
  id                      UUID PK
  project_id              UUID FK NULL     -- new; old engine jobs have paper_id only
  thread_id               UUID FK NULL     -- new; nullable
  mode                    VARCHAR(16)      -- new; "auto" for orchestrator, "engine" for legacy
  status                  VARCHAR(16)      -- queued/running/paused/done/failed/canceled (adds "paused")
  pid, workdir, started_at, finished_at, error_text       -- existing
  langgraph_thread_id     TEXT NULL        -- new; null for legacy engine rows
```

**Why three layers and not one:**

| Layer | Cost of reading | Use case |
|---|---|---|
| LangGraph state | free (in-memory) | within a graph invocation |
| Checkpoints | medium (deserialize blob) | resume, time-travel, debugging |
| App tables | cheap (SQL) | chat UI, "what gaps does this project have", admin, billing |

`context_store` lives in app tables (not in LangGraph checkpoints) so the chat UI and progress tracker can query it cheaply without deserializing graph state.

### Concurrency on `context_store`

When two threads both reach M2-complete on the same project:

- DB-level `SELECT … FOR UPDATE` on `context_store(project_id)` row.
- First write commits. The losing thread's commit fails the row check and triggers the alert flow:
  - Agent posts a chat message: "M2 was confirmed in thread '{other_thread_name}' 3 minutes ago. Options: discard your version, replace theirs with yours, or merge."
  - User picks via quick-reply; backend acts accordingly.
- Implementation goes in a dedicated `orchestrator/concurrency.py` helper called from the `ModuleAgent.commit_to_context_store()` step.

---

## Module agent contract

### Pydantic schemas (one per module)

Each module declares its required outputs. Derived from PRD §6.1.3 / §6.2.4 / §6.3.6 / §6.4.7 / §6.5. Lives in `orchestrator/schemas/`.

Example shape (M1):

```python
# orchestrator/schemas/m1.py
class M1Output(BaseModel):
    """Topic Discovery — confirmed when all required fields filled & user OK'd."""
    research_title: str = Field(..., description="Final research title")
    field: AcademicField
    research_type: ResearchType                            # quant/qual/mixed
    target_population: str
    scope: str
    objectives: list[str] = Field(..., min_length=1)
    research_questions: list[str] = Field(..., min_length=1)
    confirmed_at: datetime | None = None
```

M2..M5 follow the same pattern. M2 includes `research_gaps: list[CitedGap]`, `theoretical_framework`, `hypotheses`/`propositions`, `literature_review_doc`, `citation_list`. M5 includes the section drafts and export artifact URIs. All schemas live under `orchestrator/schemas/`.

### Shared `ModuleAgent` base class

`orchestrator/agents/base.py`:

```python
class ModuleAgent(ABC):
    schema: type[BaseModel]              # subclass: M1Output, M2Output, ...
    system_prompt: str                   # subclass provides
    tools: list[BaseTool]                # subclass provides — its skill set
    module_key: str                      # "M1" .. "M5"

    def step(self, state: OrchestratorState) -> ModuleStepResult:
        """
        1. Read partial schema from state.context_store[module_key].
        2. If complete + confirmed → emit transition signal to supervisor.
        3. Else, interactive: ask user a targeted question for the next missing field.
              auto: call tools + LLM to auto-fill the next missing field.
        4. Validate response against the field's Pydantic type → update partial schema.
        5. If just filled the last required field → ask user to confirm (interactive)
           or auto-confirm (auto). On confirm: commit to context_store (with concurrency check).
        """
```

Subclasses (`m1_topic.py` through `m5_writing.py`) only override `system_prompt`, `tools`, `schema`, and `module_key`. The loop itself is shared. This lets sub-projects 2-6 specialize individual modules without touching the others.

### Per-module tool sets

Tools live in `orchestrator/tools/` and are LangChain `@tool`-decorated thin wrappers around existing `engine/*` functions. Each module's agent is bound to its own subset.

| Module | Tools | Wraps existing |
|---|---|---|
| **M1** Topic | `suggest_topics(field)`, `refine_title(seed)` | New light LLM helpers |
| **M2** Literature | `scout_citations(topic, min_n)`, `summarize_paper(pdf_path)`, `find_research_gaps(citations)`, `compile_citations(items, style)`, `verify_page_numbers(claim)` | `engine/utils/agent_runner.research_citations_via_api`, `engine/utils/deep_research`, `engine/utils/citation_compiler`, `engine/utils/api_citations/*` |
| **M3** Design | `recommend_methodology(rq, paradigm)`, `build_conceptual_model(constructs)`, `suggest_scale_items(construct)`, `estimate_sample_size(model)` | New LLM helpers + prompt fragments from `engine/prompts/02_structure/` |
| **M4** Analysis | `detect_data_type(file_path)`, `generate_analysis_outline(data_type, methodology)`, `run_analysis_step(step_name, data)`, `interpret_result(result, lang)` | Sub-project 1 stubs return plain-text outline + interpretation; real parsing in later sub-project |
| **M5** Writing | `compose_section(section_name, context_store)`, `validate_draft(text)`, `compile_pdf(sections)`, `export_docx(sections)`, `format_citations(style)` | `engine/phases/compose.run_compose_phase`, `engine/phases/validate.run_validate_phase`, `engine/phases/compile.run_compile_and_export`, `engine/utils/docx_post_processor`, `engine/utils/export_professional` |

M5's `compose_section` and `export_docx` are what guarantee auto-mode produces a thesis identical to today's — same `engine/phases/compose.py` and same `engine/utils/docx_post_processor`, just invoked by the LangGraph instead of by `draft_generator.py`.

### Interactive vs auto-mode at the agent level

Same `step()` function; behavior branches on `state.mode`:

| Situation | Interactive | Auto |
|---|---|---|
| Missing required field | Ask user a targeted question | Call LLM with tools → auto-fill |
| Multiple plausible answers | Show options, user picks | Highest-confidence pick |
| All required filled | Show summary, await user confirm | Set `confirmed_at = now`, transition |
| User pushback | Re-run with new constraint | n/a |

---

## Supervisor & routing

`orchestrator/agents/supervisor.py`. The supervisor is the only node where module-to-module transitions happen.

**Hybrid decision logic** — pure rules for the happy path, LLM classifier only when the user signals a deviation:

```python
def supervisor_step(state) -> RouteDecision:
    # 1. Rule-based default
    decision = rule_based_route(state.context_store)   # walks M1..M5 in order

    # 2. LLM override only in interactive mode AND only when user message
    #    contains navigation keywords ("go back", "skip", "redo", "I already have").
    if state.mode == "interactive" and looks_like_navigation(state.messages[-1]):
        intent = classify_intent(state.messages[-1])   # IntentClassification schema
        if intent.wants_navigation and intent.confidence > 0.7:
            decision = RouteDecision(next_module=intent.target_module,
                                     reason=f"user requested {intent.target_module}",
                                     needs_user_acknowledgement=True)
    return decision
```

Auto-mode never calls the LLM classifier — supervisor is deterministic and cheap.

**Graph topology** (`orchestrator/graph.py`):

```python
def build_graph(interactive: bool) -> CompiledStateGraph:
    builder = StateGraph(OrchestratorState)
    builder.add_node("supervisor", supervisor_node)
    for m in ["M1", "M2", "M3", "M4", "M5"]:
        builder.add_node(m, agent_for(m).step)

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"M1": "M1", "M2": "M2", "M3": "M3", "M4": "M4", "M5": "M5", "DONE": END},
    )
    for m in ["M1", "M2", "M3", "M4", "M5"]:
        builder.add_edge(m, "supervisor")

    return builder.compile(
        checkpointer=PostgresSaver(...),
        interrupt_before=["supervisor"] if interactive else [],
    )
```

`interrupt_before=["supervisor"]` is the key flag for interactive mode: graph halts before each supervisor decision so the API can stream the last agent's output, accept the user's reply, then resume. Auto-mode runs end-to-end without interrupts.

**Mid-module navigation requests** (interactive only): each module agent has a lightweight intent classifier on entry. If the user message is a navigation request, the module returns control to supervisor without filling its schema.

---

## Two entrypoints

### Interactive (in-process FastAPI)

New router `api/app/routers/chat.py`. Routes:

```
POST   /api/v1/projects                          → create project + default thread
GET    /api/v1/projects/{id}                     → project + context_store snapshot
GET    /api/v1/projects/{id}/threads             → list threads
POST   /api/v1/projects/{id}/threads             → create new thread (inherits context_store)
GET    /api/v1/threads/{tid}                     → thread metadata
POST   /api/v1/threads/{tid}/messages            → send user message; streams agent reply via SSE
GET    /api/v1/threads/{tid}/messages            → paginated history (cheap; reads `messages` table)
GET    /api/v1/threads/{tid}/state               → SSE stream of context_store + module transitions
                                                   (emits "remote_update" when another thread writes)

POST   /api/v1/projects/{id}/runs                → spawn auto-mode subprocess (body: {mode:"auto",topic:"..."}); returns run_id
                                                   (mirrors existing POST /papers/{id}/jobs pattern)
POST   /api/v1/runs/{rid}/pause                  → SIGTERM the subprocess
POST   /api/v1/runs/{rid}/resume                 → re-spawn with --resume-run-id
GET    /api/v1/runs/{rid}                        → status + last module + events tail URL
GET    /api/v1/runs/{rid}/events                 → SSE tail of events.jsonl (reuses existing handler)
```

Send-message handler:

```python
@router.post("/threads/{thread_id}/messages")
async def send_message(thread_id: UUID, body: SendMessageBody, ...):
    # 1. Persist user message → messages table
    # 2. Resume LangGraph at thread's langgraph_thread_id
    # 3. Stream tokens as they arrive
    from orchestrator.graph import get_interactive_graph
    graph = get_interactive_graph()              # cached singleton, compiled at app startup
    config = {"configurable": {"thread_id": thread.langgraph_thread_id}}

    async def stream():
        async for event in graph.astream(
            {"messages": [HumanMessage(body.text)], "mode": "interactive"},
            config=config,
            stream_mode="messages",
        ):
            yield sse_pack(event)

    return StreamingResponse(stream(), media_type="text/event-stream")
```

The graph is compiled once at app startup. Per-request cost is just `astream()`.

### Auto-mode (subprocess)

`orchestrator/__main__.py`:

```
python -m orchestrator --auto-draft \
    --project-id <uuid> \
    --user-id <uuid> \
    --workdir <path> \
    --brief-json <path>          # initial topic + any seed input

# or to resume:
python -m orchestrator --resume-run-id <uuid> --workdir <path>
```

Spawned by `api/app/job_runner.py` — identical Popen pattern to today's `python -m engine`. Single change in `job_runner.py`: choose between `engine` and `orchestrator` based on the run's mode field.

Auto-mode invocation:

```python
def main():
    args = parse_args()
    appender = JsonlAppender(workdir / "events.jsonl")    # reuse existing
    tracker = JobTracker(appender)

    # SIGTERM handler for pause:
    signal.signal(signal.SIGTERM, lambda *_: _graceful_stop(appender))

    from orchestrator.graph import get_auto_graph
    graph = get_auto_graph()                              # interrupts disabled
    config = {"configurable": {"thread_id": str(uuid4())}}

    if args.resume_run_id:
        # Empty input means LangGraph picks up at last checkpoint
        graph.invoke({}, config=config)
    else:
        brief = json.loads(Path(args.brief_json).read_text())
        graph.invoke({
            "project_id": args.project_id,
            "messages": [HumanMessage(brief["topic"])],
            "mode": "auto",
            "context_store": ContextStore(),
        }, config=config)

    # M5's export_docx/compile_pdf tools have written artifacts to workdir.
    # Upload using existing s3_for_jobs.py.
    upload_artifacts(s3_from_env(), workdir, ...)
```

**Stop & resume:**

- Stop: `POST /runs/{rid}/pause` → API sends SIGTERM via existing `job_runner.cancel_job(db, run)` pathway. Inside the subprocess, the signal handler lets the current node finish, commits the LangGraph checkpoint, writes `{"type":"paused","module":"M3"}` to `events.jsonl`, and exits cleanly. The API's `_monitor` task in `job_runner.py` (which already tails `events.jsonl` and updates `jobs.status`) sees the `paused` event and updates `runs.status = "paused"` in the DB. **The subprocess never writes to the DB directly** — it owns only `events.jsonl`.
- Resume: `POST /runs/{rid}/resume` → re-spawn with `--resume-run-id`. LangGraph picks up at the next-node boundary. UI re-tails the same `events.jsonl` over the existing SSE route.

**Event shape** (extends today's JSONL with a `module` field):

```jsonl
{"type":"activity","module":"M1","agent":"M1 Topic","text":"Selecting field..."}
{"type":"module_complete","module":"M1","context_keys":["research_title","objectives"]}
{"type":"activity","module":"M2","agent":"Scout","text":"Found 42 citations"}
{"type":"tool_call","module":"M2","tool":"scout_citations","duration_ms":12000}
{"type":"paused","module":"M3","reason":"user_stop"}
{"type":"job_done","exports":{"docx":"s3://...","pdf":"s3://..."}}
```

**Streaming model:**

| Mode | Stream type | Reason |
|---|---|---|
| Interactive | LangGraph token stream | Chat needs typewriter effect |
| Auto | JSONL semantic events | Progress UI shows phase chips, identical to today's engine UX |

---

## Migrations & coexistence

### One Alembic migration (`api/migrations/versions/20260525_add_orchestrator_tables.py`)

```python
def upgrade():
    op.create_table("projects", ...)
    op.execute("""
        INSERT INTO projects (id, user_id, name, field, language, citation_style,
                              status, current_module, created_at, updated_at)
        SELECT id, user_id, topic, NULL, language, citation_style,
               status, 'DONE', created_at, updated_at
        FROM papers
    """)
    op.create_table("threads", ...)
    op.execute("""
        INSERT INTO threads (id, project_id, name, langgraph_thread_id, status, created_at)
        SELECT gen_random_uuid(), id, 'Main', id::text, 'archived', created_at
        FROM papers
    """)
    op.create_table("messages", ...)
    op.create_table("context_store", ...)
    op.execute("""
        INSERT INTO context_store (project_id, m5_writing, updated_at)
        SELECT id, jsonb_build_object('confirmed_at', updated_at), NOW()
        FROM papers
    """)
    # Extend existing `jobs` table for the runs API: add nullable columns so
    # legacy engine jobs keep working (mode IS NULL → engine; "auto" → orchestrator).
    op.add_column("jobs", sa.Column("project_id", UUID, nullable=True))
    op.add_column("jobs", sa.Column("thread_id",  UUID, nullable=True))
    op.add_column("jobs", sa.Column("mode",       sa.String(16), nullable=True))
    op.add_column("jobs", sa.Column("langgraph_thread_id", sa.Text, nullable=True))
    # papers table is otherwise untouched — backfill only INSERTs into projects.
    # LangGraph creates its own checkpoint tables via PostgresSaver.setup()
    # at app startup — not in this migration.

def downgrade():
    op.drop_column("jobs", "langgraph_thread_id")
    op.drop_column("jobs", "mode")
    op.drop_column("jobs", "thread_id")
    op.drop_column("jobs", "project_id")
    op.drop_table("context_store")
    op.drop_table("messages")
    op.drop_table("threads")
    op.drop_table("projects")
```

### Coexistence with existing engine

| Path | Today | After sub-project 1 |
|---|---|---|
| `web/(inapp)/wizard` | Creates Paper + Job, runs `python -m engine` subprocess | **Unchanged** |
| `web/(inapp)/papers/[id]` | Tails events.jsonl from engine | **Unchanged** |
| New chat API (no UI yet) | n/a | Creates Project + Thread, calls new chat endpoints; can trigger auto-draft via `orchestrator` subprocess |

**Sub-project 1 does not delete or modify any existing code path.** Old wizard + `python -m engine` runs side-by-side with the new orchestrator. Deprecation happens after sub-project 7 (new chat UI) ships and stabilizes.

### Feature flag

`ORCHESTRATOR_ENABLED` env var (default `false`):

- false: new routes return 404, orchestrator code isn't imported at app startup.
- true: routes mount, graph compiles at startup, `PostgresSaver.setup()` runs.

Lets us ship the migration + code without exposing the feature; flip in staging → validate → enable in prod.

### Billing

- Interactive turns: deduct per-turn from `credit_ledger` inside the chat router before invoking the graph, using existing `pricing.py` rules.
- Auto-mode runs: identical to today's engine flow — lock estimated cost on submit, true up on completion.

No new pricing logic.

### Repo layout

```
dothesis/
├── api/                    -- existing, +chat router + small job_runner.py edits
├── engine/                 -- existing, UNCHANGED. Imported as library by orchestrator/tools/.
├── orchestrator/           -- NEW
│   ├── __init__.py
│   ├── __main__.py         -- subprocess entrypoint (auto-mode + resume)
│   ├── graph.py            -- build_graph(), get_interactive_graph(), get_auto_graph()
│   ├── state.py            -- OrchestratorState, ContextStore Pydantic
│   ├── concurrency.py      -- context_store commit with first-write-wins
│   ├── schemas/            -- M1..M5 Pydantic schemas
│   │   └── m1.py ... m5.py
│   ├── agents/
│   │   ├── base.py         -- ModuleAgent base + clarification loop
│   │   ├── supervisor.py
│   │   └── m1_topic.py ... m5_writing.py
│   ├── tools/              -- LangChain @tool wrappers over engine/utils/*
│   │   ├── m1_topic.py
│   │   ├── m2_literature.py
│   │   ├── m3_design.py
│   │   ├── m4_analysis.py
│   │   └── m5_writing.py
│   ├── prompts/            -- system prompts per agent (Markdown)
│   └── tests/
├── web/                    -- existing, UNCHANGED in sub-project 1
└── api/migrations/versions/
    └── 20260525_add_orchestrator_tables.py
```

---

## Testing

### Test categories

| Layer | What's tested | Tools |
|---|---|---|
| Unit — agent step | Given a partial state, agent returns expected schema/transition | `pytest` + LangChain fake LLMs |
| Unit — tool wrappers | Each tool's input/output contract | `pytest`; real engine functions where fast, mocked external APIs |
| Unit — supervisor routing | RouteDecision correct for every combination of context_store state + user intent | `pytest` parametrized |
| Integration — single module e2e | Module loops to completion, schema filled, context_store written | `pytest` + LangGraph `MemorySaver` + `vcrpy` cassettes |
| Integration — full graph auto | Topic in → 5 modules run → exports artifact | `pytest` slow-marked, nightly CI, real LLM |
| Integration — full graph interactive | Scripted user-turn sequence drives graph to END | `pytest` + `FakeUser` helper with fixture-driven responses |
| Integration — concurrency | Two threads, same project, both confirm M2 → second gets alert | `pytest` two concurrent invocations |
| Migration | Alembic up/down/up on fresh DB + on DB with existing papers | `pytest` against ephemeral Postgres |

### Coverage targets

- Tools layer: 90%+ (wrappers; easy to cover; foundation for everything else)
- Agents: 70%+
- Graph topology + supervisor: 100% of routing combinations

### Observability

- **Structured logs** — reuse `engine/utils/structured_logger.StructuredLogger`. Every agent step logs `{thread_id, module, agent, tool_calls, latency_ms, token_in, token_out}`.
- **Sentry** — reuse `engine/sentry_config.py`. Tool/agent failures escalate with module context.
- **Token tracking** — reuse `engine/utils/token_tracker.py` as a LangChain callback. Surfaces as SSE events (interactive) or `job_events` rows (auto).
- **LangSmith** — optional, gated by `LANGSMITH_API_KEY`. Off by default.

### Debugging tools

- `python -m orchestrator.replay --thread-id <uuid>` — re-runs from a chosen checkpoint via `get_state_history()`.
- `python -m orchestrator.inspect --project-id <uuid>` — pretty-prints current `context_store`.

---

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| LangGraph PostgresSaver schema conflicts with Alembic | Medium | Call `PostgresSaver.setup()` at app startup, not in Alembic; pin LangGraph version; CI test runs both |
| Existing engine functions don't expose clean tool entry points (deep coupling) | Medium-high | First implementation milestone: enumerate every `engine/utils/*` function we need; write façades where needed. Long pole of the project. |
| Auto-mode with empty messages confuses agents | Medium | Each `ModuleAgent.step()` branches on `state.mode == "auto"` first; no-prompt code path |
| Interactive turn latency too high (supervisor → module → supervisor every turn) | Medium | Supervisor only runs at transitions; mid-module turns skip it. Profile early. |
| Token costs balloon (every agent sees full context) | High | Each agent gets only its module's context slice + last N messages. Enforced in `state.py` access helpers. |
| Two threads race on context_store | Low | DB row-level `SELECT … FOR UPDATE`; conflict triggers alert flow |
| Streaming SSE backpressure | Low | Existing `api/app/sse.py` handles this; orchestrator inherits |
| LangGraph pre-1.0 version churn | High | Pin exact version in `requirements.txt`; isolate LangGraph imports behind `orchestrator/graph.py` so upgrades are one-file scope |

---

## Success criteria

Sub-project 1 is "done" when **all** of these hold:

1. **End-to-end interactive run** — From an empty project, a user can drive the chat API to END with all 5 modules confirmed. Final state writes to `context_store` and an export artifact (docx + pdf) to S3.
2. **End-to-end auto-mode run** — From a one-line topic, `python -m orchestrator --auto-draft` produces the same artifact set as today's `python -m engine` (qualitatively equivalent on a fixed test topic).
3. **Stop & resume auto-mode** — User can pause an auto-draft; status → `paused`; resume picks up at the next-node boundary.
4. **Multi-thread within one project** — Two threads on the same project share `context_store`; first to confirm M2 writes; second gets the alert (option B).
5. **Coexistence** — Existing wizard + `python -m engine` path unchanged; engine tests still pass.
6. **Tests green** — All categories above passing in CI; coverage targets met.
7. **Migration safe** — Alembic up/down/up clean on fresh DB and on DB with existing papers.

## Explicit non-commitments

- Agent prose quality. Sub-project 1 is plumbing.
- Performance targets. Measured but not optimized.
- Finished frontend. API only; new UI is sub-project 7.
