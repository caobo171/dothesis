# Deep Agent & Streaming in DoThesis

This doc explains two things that sit at the heart of the v3 chat turn:

1. How the project uses **LangChain `deepagents`** as the brain of a thesis-writing
   copilot — what the agent is, where it's built, what skills/tools it has, and how
   state stays consistent across turns.
2. How a chat turn **streams** from that agent all the way to the user's browser —
   the SSE event vocabulary, the multiplexed producer/consumer pump, and how engine
   progress (the long M2 research scout) co-exists with token deltas in one channel.

For the original design rationale see
[`docs/architecture/2026-06-10-deepagent-skills-architecture.md`](architecture/2026-06-10-deepagent-skills-architecture.md).
This doc is the implementer's view of what actually exists in the code today.

---

## 1. Why a deep agent at all

DoThesis v2 was a hand-built LangGraph state machine: a router node dispatched to
M1–M5 agent classes, each with its own prompt assembly and slice schema. The v3
pivot replaces all of that with **one** agent that reads **eight skills** and calls
a small belt of typed tools:

- One free-roaming Claude/Gemini model does the routing by matching the user's intent
  against skill descriptions (the v2 router skill content moved into the root skill).
- Domain expertise — M1 topic locking, M2 lit-review phases, M3 model + hypotheses,
  M4 stats, M5 writing — lives in `skills/*/SKILL.md` files (progressive disclosure:
  only name + description is in the system prompt at startup, full SKILL.md is read
  on demand).
- Where correctness or cost demand real code (citation scout, GROBID parse, stats
  templates, docx export), the agent calls a typed Python tool instead of doing it
  in-prompt.

What the agent does NOT control directly: the `context_store`. The single source of
truth for project state (research title, RQs, sources, gaps, model, hypotheses,
results, final sections, per-module status, focus) is owned by `ProjectStateStore`
and only mutable through the guarded `commit_slice` tool. The agent is free, but
state changes are deterministic code.

---

## 2. Where the agent is built — `agent/runtime.py`

The runtime module exports two things the API layer cares about: `build_agent` and
`stream_turn`.

### `build_agent(project_dir, *, model=None, checkpointer=None, store=None)`

Creates one deep agent bound to one project (`agent/runtime.py:358`). Steps:

1. **Backend** — a `CompositeBackend` over two `FilesystemBackend` mounts:
   - `/skills/` → the repo's `skills/` directory (read-only domain knowledge that
     ships with the deploy).
   - default (everything else) → the project directory (uploads, exports, workspace
     scratch).

   `virtual_mode=True` enables virtual-path semantics so the `/skills/` route works
   and absolute / `..` path escapes are refused.

   The `context_store.json` file is **deliberately not exposed as a writable file** —
   the only write path is `commit_slice`. The store lives in `project_dir` via
   `ProjectStateStore`.

2. **Model** — Claude when `ANTHROPIC_API_KEY` is set, else Gemini
   (`gemini-2.5-flash` by default). The selection is intentional: the production
   deployment currently runs on Gemini; Claude takes over automatically once a key
   lands. See `_default_model()`.

3. **Tools** — a small belt:
   - `make_state_tools(store)` → `read_slice`, `commit_slice`, `confirm_module`
     (the state I/O the agent uses every turn).
   - `research_scout` → wraps `engine/utils/deep_research.py` (Gemini plan →
     orchestrated execution) + `api_citations` scout, citation validator, quality
     filter. The M2 ★ tool.
   - `parse_reference` → GROBID-backed reference extractor for uploaded PDFs / DOIs.
   - `run_stats` → whitelisted analyses (pandas / scipy / statsmodels / pingouin) in
     a network-less sandbox. Free-form Python from the model never executes.
   - `make_writing_tools(store)` → `write_pipeline`, `export_docx` (M5 ★) — invoke
     the engine's `structure → compose → citations → compile → validate` phases and
     the docx post-processor that emits clickable internal citations + DOIs.

4. **`create_deep_agent(...)`** — the LangChain deepagents entry point. Skills are
   discovered from `["/skills/"]` (the agent calls `read_file("/skills/dothesis/SKILL.md")`
   when needed). The agent is named `dothesis` and uses the provided checkpointer
   (Postgres in the API path; none in the CLI spike).

### The system prompt — short, surgical

`SYSTEM_PROMPT` (`agent/runtime.py:159`) is kept short on purpose. It carries:

- **Identity + protocol pointer** — "read the `dothesis` skill before doing any
  thesis work". Domain behavior stays in the skill, not the prompt.
- **`[PROJECT STATE]` rules** — the authoritative-status convention (§4 below).
- **`[ATTACHED]` rules** — how the agent should react to user file uploads.
- **UI affordance conventions** — `[OPTIONS]` markers, `[PAPERS]` panels, Mermaid
  fenced blocks, questionnaire shapes. These are injected **every turn** rather
  than only in the skill file, because models routinely ignore instructions they
  only see after a per-session `read_file`. Without re-injection the chat surface
  loses cards / diagrams after the first turn.

---

## 3. Skills — `skills/`

Progressive disclosure: only `name + description` is in context at startup; the full
SKILL.md is read when relevant; `references/` are read only when needed.

```
skills/
├── dothesis/                       # root — principles, state protocol, module map
├── dothesis-bootstrap/             # entry wizard: declare → import → reconcile
├── dothesis-m1-topic/              # wizard: options → title + RQs → lock
├── dothesis-m2-literature/         # ★ chat loop, 5 phases (tools-first)
├── dothesis-m3-design/             # wizard: model → hypotheses → methodology
├── dothesis-m4-analysis/           # pipeline: detect → outline → run_stats
└── dothesis-m5-writing/            # ★ wizard, pipeline-backed
```

There is **no router skill** — the model does discovery from descriptions. The
read-vs-mutate semantics the v2 router enforced moved into the root skill (the
words) and the `commit_slice` tool (the enforcement).

---

## 4. State — `ProjectStateStore`

`agent/state.py` defines the slice ownership map (which keys each module may write),
the read dependencies (M5 reads M1–M4), and the downstream-`needs_review` DAG
(`M1 → M2 → M3 → M4 → M5`).

Critical contract: when `commit_slice(module, writes, reason)` runs, it:

1. Validates the write keys belong to the module's owned slice.
2. Snapshots a version to `version_history` (capped at 50 entries).
3. Sets `focus = module`.
4. Flags downstream modules `needs_review` from the static DAG.

`read_slice` is free and never mutates. The asymmetry the v2 brief cared about
(read = free, mutate = focus shift + downstream propagation) is enforced at the
tool boundary — not by model discipline.

### Two stores, one interface

- **`ProjectStateStore`** — file-backed JSON, used by the CLI spike and tests.
- **`DbProjectStateStore`** — Postgres-backed subclass used by the API
  (`api/app/agent_state.py`). Same semantics, different persistence.

The store is **per project, not per thread**. Every chat session in a project
shares one `context_store`; threads share state, conversations are isolated.

### The `[PROJECT STATE]` header — keeping the agent honest

Models routinely confabulate module status ("I'll mark M5 done", "M1–M5 all
done") even when the store says otherwise. To prevent drift, `stream_turn`
prepends an authoritative status line on every user turn:

```
[PROJECT STATE] focus=M4 | M1:done M2:done M3:done M4:done M5:needs_review
```

The system prompt instructs the agent to:

- Treat this line as ground truth (overrides memory).
- Report statuses **from this line verbatim** when asked.
- Strip the marker from its reply (it's a wire-format marker, not user text).
- Never claim a module is `done` unless this line says so — saying it does not
  make it so; only a successful `commit_slice(..., confirm_done=True)` does.

This is built in `_state_header()` and prepended in `stream_turn` (`runtime.py:431`,
`runtime.py:478`).

---

## 5. The chat turn flow

```
Browser (ChatPane → useChat → useStream)
        │
        │ POST /api/v1/threads/.../send_message
        ▼
api/app/routers/chat.py  (DOTHESIS_AGENT_V3=1 → delegates)
        │
        ▼
api/app/routers/chat_v3.py:send_message_v3
        │
        ├─ persists user Message row (+ attachment chips)
        ├─ _get_agent(project_id) → cached `dothesis` deep agent
        ├─ _materialize_attachments() → bytes ready for multimodal path
        └─ StreamingResponse(gen(), media_type="text/event-stream")
                │
                ▼
        gen()  ← the multiplexed pump/consumer (§7)
                │
                ├─ stream_turn(agent, thread_id, text, attachments, store)
                │       └─ agent.astream(payload, config, stream_mode=["messages","updates"])
                │
                └─ engine progress emitter (registered + ContextVar-bound)
```

The frontend hits the same `/send_message` endpoint as v2. The only thing that
changed is what runs inside the streaming response generator.

---

## 6. `stream_turn` — agent events → SSE-shaped dicts

`agent/runtime.py:453` is the bridge between LangGraph's `astream` (which emits
typed chunks) and the SSE event vocabulary the web client already renders.

### Event vocabulary (`stream_turn` yields)

| Type | Payload | When |
|---|---|---|
| `token` | `{text: str}` | Assistant text delta — from LangChain `AIMessageChunk.content` |
| `tool_start` | `{name: str, args: dict}` | Agent issued a tool call (from `updates` stream's `tool_calls`) |
| `tool_end` | `{name: str, preview: str}` | A `ToolMessage` came back (truncated preview) |
| `tool_calls` | `{payload: WidgetHint}` | A `[OPTIONS]`, `[PAPERS]`, or `export_docx` artifact hint parsed from the AI message |
| `usage` | `{input_tokens, output_tokens}` | Per-LLM-step token usage from `usage_metadata` |
| `error` | `{message: str}` | `astream` raised — never let the stream die silent |
| `done` | `{}` | End-of-turn sentinel |

### Two stream modes, two reasons

`agent.astream(..., stream_mode=["messages", "updates"])` mixes two streams:

- **`messages`** — chunk-level deltas. Used to get **token streaming**: every
  `AIMessageChunk.content` becomes a `token` event. The agent's text appears
  word-by-word in the chat bubble.

- **`updates`** — node-level completions. Used to get:
  - **`ToolMessage` results** → `tool_end` events (plus the `export_docx` artifact
    hint when the tool finished successfully).
  - **Planning `AIMessage.tool_calls`** → `tool_start` events.
  - **`usage_metadata`** on completed AI messages → `usage` events (cost metering
    that sums across every LLM step in the turn, including tool loops).
  - **Inline UI markers** (`[OPTIONS]`, `[PAPERS]`) parsed out of the AI message
    text → `tool_calls` widget hints. The `[PAPERS]` marker wins when both appear.

### Why parse markers in `updates`, not `messages`

The `messages` mode delivers incremental chunks — half a `[PAPERS]` block won't
parse. The `updates` mode delivers the **completed** AI message, so the regex sees
the whole marker. The token-by-token UI still gets the prose via `messages`; the
marker hint is fired once when the message is final.

### deepagents middleware unwrap

deepagents' `patch_tool_calls` / filesystem-eviction middleware returns
`{"messages": Overwrite([...])}` to bypass LangGraph's `add_messages` reducer.
`stream_turn` unwraps `Overwrite` so the rest of the loop sees a plain list
(`runtime.py:532`). Without this the message list would be a wrapper and the
iteration would silently drop everything.

### Diagnostic counters

`stream_turn` keeps `_mode_counts` (how many messages vs updates chunks) and
`_msg_type_counts` (which `AIMessage*` subtypes arrived). At end of turn it logs
one line. When a turn ends with zero tokens, that line tells us whether deepagents
returned nothing, returned empty strings, or returned non-AI types — pinpointing
the silent-failure cause that bit us during the Gemini swap.

---

## 7. The multiplex pump — `chat_v3.gen()`

The naïve shape would be:

```python
async for ev in stream_turn(...):
    yield sse_pack(ev)
```

That fails for one reason: when the agent calls `research_scout`, the tool blocks
for 30–90 seconds. During that window the agent emits nothing — but the **engine**
inside the tool is emitting progress beats (`"Searching Semantic Scholar…"`,
`"Found 12 candidates…"`). Those beats need to reach the user's screen in real
time, not get buffered until the tool returns.

`chat_v3.send_message_v3` (`api/app/routers/chat_v3.py:227`) solves this with a
two-producer, one-consumer pattern:

```
   ┌──────────────────────┐
   │  _pump_agent (task)  │── stream_turn events ──►┐
   └──────────────────────┘                          │
                                                     ├── events_q (asyncio.Queue)
   ┌──────────────────────┐                          │
   │ progress_emitter     │── engine progress  ─────►┘
   │ (registered + bound) │
   └──────────────────────┘                          │
                                                     ▼
                                                  consumer loop
                                                     │
                                                     ▼
                                                  sse_pack → yield
```

### Two producers

1. **`_pump_agent()` task** — drains `stream_turn(...)` into the queue as
   `("agent", ev)` tuples. A sentinel `("done", None)` marks completion.

2. **`progress_emitter(payload)` callback** — engine code calls this via two
   discovery paths:
   - `engine.utils.progress.register(thread_id, emitter)` — the registry path
     used by callers that have a `thread_id` in hand.
   - `engine.utils.progress.bind(emitter)` — a **ContextVar** binding so
     `safe_print → _safe_print_hook → current_emitter()` works inside
     `asyncio.to_thread` workers and the engine's `submit_with_context`-wrapped
     thread pool. Without this, the M2 scout's 60-second batches would be silent.
   Both paths funnel onto the same queue as `("progress", payload)`.

### One consumer

The consumer loop reads `(src, item)` and dispatches:

| src | Branch |
|---|---|
| `"done"` | break — pump finished |
| `"progress"` | `yield sse_pack({"type": "progress", "payload": item})` |
| `"agent"` with `kind == "token"` | accumulate to `chunks`, yield `token` SSE |
| `"agent"` with `kind == "tool_start"` | yield `progress` SSE with **student-facing label** (§8) |
| `"agent"` with `kind == "tool_end"` | log only; no SSE (the start line already covered it) |
| `"agent"` with `kind == "tool_calls"` | yield `tool_calls` SSE + capture for persistence |
| `"agent"` with `kind == "usage"` | accumulate `_usage_in / _usage_out` |
| `"agent"` with `kind == "error"` | yield `error` SSE |
| `"agent"` with `kind == "done"` | break |

### Finalize-on-exit (idempotent)

`_finalize()` persists the assistant Message row (with `module_tag = focus`,
`tool_calls_json = final_tool_calls`, cost / duration / tokens), charges the
credit ledger, and returns the `done` payload. It runs in three places:

- **Normal completion** — in the `try` body, before the `finally`.
- **Error path** — after yielding the `error` SSE.
- **Client disconnect** — `GeneratorExit / CancelledError` skips both above; the
  `finally` calls it as a fallback so the partial answer is saved and only spent
  tokens are charged.

The `_finalized` flag makes it safe to call from multiple paths. Crucially, on
disconnect the `finally` also **cancels `pump_task`** so the agent's research /
LLM calls stop instead of running orphaned (which used to burn tokens for output
no one was receiving).

---

## 8. Student-facing labels — `_tool_progress_label`

The progress bubble's reader is a thesis student, not an engineer. Raw tool names
(`commit_slice`, `read_file`, `research_scout`) leak abstraction. `chat_v3.py:37–77`
maps `(name, args)` to plain-language lines:

| Tool | Renders as |
|---|---|
| `read_file` with `/skills/` path | "Reading the guide for this step…" |
| `read_file` with `upload` in path | "Reading your uploaded file…" |
| `commit_slice` with `module=M2` | "Saving your literature review…" |
| `run_stats` with `op=cronbach` | "Checking reliability (Cronbach's α)…" |
| `research_scout` | "Searching for relevant research…" |
| `export_docx` | "Building your Word document…" |

The translation lives in the API layer because that's the only place where the
tool **args** (e.g. `read_file`'s path, `commit_slice`'s module, `run_stats`'s op)
are available alongside the tool name.

---

## 9. SSE wire format

`api/app/sse.py:sse_pack(obj)` encodes a dict as a single SSE `data:` frame
(JSON-serialized payload, terminating `\n\n`). The frontend reads them in
`web/app/components/chat/hooks/useStream.ts` with a `ReadableStream` reader +
`TextDecoder`, splits on `\n\n`, JSON-parses each frame, and dispatches it onto a
reducer (`useStream.ts:29`). `useChat` (`useChat.ts:32`) then filters events by
type:

- `token` events → `streamingText` (accumulated string).
- `progress` events → `streamingProgress` (rendered by `ProgressBubble`).
- `tool_calls` events → `streamingToolCalls` (widget hint; persisted onto the
  Message row when SWR revalidates after `done`).
- `error` events → `streamingError` (banner).
- `done` event → reducer ends inflight; SWR revalidates the message list.

The contract is symmetric: the backend yields shaped dicts, the frontend
consumes shaped dicts. No GET endpoints (all chat I/O is POST so auth tokens
ride in the body — see `CLAUDE.md`).

---

## 10. Quick map — "where do I look when…"

| Question | File |
|---|---|
| Where is the deep agent built? | `agent/runtime.py:358` (`build_agent`) |
| What's the system prompt? | `agent/runtime.py:159` (`SYSTEM_PROMPT`) |
| Which tools does the agent have? | `agent/runtime.py:391` + `agent/tools/*.py` |
| How are skills loaded? | `agent/runtime.py:383` (`CompositeBackend` + `skills=["/skills/"]`) |
| How does one turn stream events? | `agent/runtime.py:453` (`stream_turn`) |
| How are agent events parsed? | `agent/runtime.py:609` (`_events_from_message`) |
| Where do `[OPTIONS]` / `[PAPERS]` get parsed? | `agent/runtime.py:40`, `:111` |
| Where does the API stream SSE? | `api/app/routers/chat_v3.py:169` (`send_message_v3`) |
| How does engine progress reach the SSE? | `chat_v3.py:246` (`progress_emitter` + queue) |
| Where is the `[PROJECT STATE]` line built? | `agent/runtime.py:431` (`_state_header`) |
| Where is per-tool friendly labeling? | `chat_v3.py:64` (`_tool_progress_label`) |
| Where is the state store contract? | `agent/state.py` (ownership, READS, DOWNSTREAM) |
| Where is the frontend SSE reader? | `web/app/components/chat/hooks/useStream.ts:39` |
| Where is the chat event consumer? | `web/app/components/chat/hooks/useChat.ts:32` |
