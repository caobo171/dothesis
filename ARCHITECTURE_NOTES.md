# DoThesis — Architecture Notes: Two-Runtime Design & the "One Agent" Question

> Status: **discussion notes for the owner to decide later.** Nothing here is implemented.
> Written 2026-07-15. Author: engineering assistant, from reading the current code.
> Scope: why DoThesis has two LLM "brains", how they connect, the model routing, and
> an honest analysis of the recurring "shouldn't this just be one agent?" question.

---

## TL;DR

DoThesis runs **two separate LLM runtimes**, not one:

1. **Chat agent** (`agent/`) — the interactive tutor. Talks to the student, decides which
   tool to call. Runtime: `create_deep_agent` (deep-agent / ReAct style). Model knob:
   `DOTHESIS_MODEL_ROUTE` + `DOTHESIS_AGENT_MODEL` (currently unset → **native Gemini**).
2. **Report orchestrator** (`orchestrator/`) — the thesis-building pipeline. A LangGraph
   pipeline of per-module worker "agents" (M1→M5) that produces the 30-page deliverable.
   Model knob: `ORCHESTRATOR_LLM_ROUTE` + `ORCHESTRATOR_LLM_MODEL` (currently
   **`bailian/qwen-plus` via Ofox**).

They are **separate on purpose** (mainly: the report engine must run **headless** for the
B2B/partner flow). They coordinate through **shared state**, not direct calls.

The word **"agent" is overloaded** in the repo — this is the main source of confusion:
- `agent/` = the chat tutor.
- `orchestrator/agents/` = the per-chapter workers of the report pipeline.

---

## 1. The two runtimes

### 1a. Chat agent — `agent/`
- Entry: `agent/runtime.py` → `create_deep_agent(model=..., tools=..., system_prompt=..., skills=["/skills/"])`.
- Model built by `agent/model_factory.py` (`make_model()` / `spec_from_env()`):
  - `route = DOTHESIS_MODEL_ROUTE` (default `native`), `model = DOTHESIS_AGENT_MODEL`
    (default `gemini-3.5-flash`, or `claude-sonnet-4-6` if `ANTHROPIC_API_KEY` is set on native).
  - Routes: `native` (provider SDK — Google/Anthropic), `openrouter`, `ofox`.
- Tools (all lightweight, store-bound): state tools, preflight, `sampling_plan`,
  writing tools (incl. `export_docx`), `backfill_upstream_modules`, defense (mock committee),
  questionnaire audit, research brief.
- Tool-calling regime: **free choice** (`tool_choice` auto, multi-turn) — decides *if* and
  *which* tool. Harder regime than the orchestrator's forced choice.
- Handles **student image uploads** (SPSS/SmartPLS screenshots) — vision matters here.

### 1b. Report orchestrator — `orchestrator/`
- Per-module workers: `orchestrator/agents/{m1_topic, m2, m3_design, m4_analysis, m5_writing}.py`.
- Router: `orchestrator/agents/router_agent.py:168` →
  `llm = _router_llm().bind_tools(ALL_TOOLS, tool_choice="any")` — **binds many tools and
  FORCES a tool call every turn** (easy tool-calling regime).
- Model built by `orchestrator/llm.py` (`get_orchestrator_llm()`): routes `native` (Gemini)
  and `ofox` (ChatOpenAI → `https://api.ofox.ai/v1`). Vision handled separately via
  `get_vision_llm()` (on `ofox`, uses a Google client pointed at Ofox's `/gemini` endpoint;
  `DOTHESIS_VISION_MODEL`, default `gemini-2.5-flash`, because qwen is text-only).
- Runs **headless** for the partner/B2B flow — see §2.

---

## 2. How the two connect

Two connection points — **no direct object calls between the runtimes**:

### 2a. Shared state — `ProjectStateStore` (the glue)
- Defined in `agent/state.py`; **per-project** contextStore.
- Both runtimes read/write the SAME store: orchestrator uses it in `intake`, `planner`,
  `graph`, `backfill`, `artifacts`, `loader`; every chat-agent tool is store-bound.
- Example: chat agent's `backfill_upstream_modules` writes reconstructed M1/M2/M3 slices →
  the orchestrator reads them on the next run. They "talk through the whiteboard".

### 2b. Direct bridge — `export_docx` (chat → orchestrator)
- `agent/tools/writing.py` → `export_docx()` imports `run_export` + compose from
  `orchestrator.tools.m5_writing`. When the student asks to export/download, the chat agent
  calls this tool, which: `store.load()` → compose missing chapters (M1–M4) **on the
  orchestrator LLM (qwen)** → `run_export()` renders DOCX/PDF (LibreOffice) → commits
  artifacts to the store.

### 2c. Headless path (no chat agent at all)
- `api/app/partner_report_service.py` (fillform/partner) builds the whole report via
  `build_partner_context_store` + `compose_sections` (orchestrator) — **it does not import
  `agent/`**. Press a button → server emits a full thesis PDF, no conversation.
- **This is the load-bearing reason the two are separate**: the report engine has to run
  server-side with no human in the loop; a conversational agent is the wrong tool for that.

```
Student chat → Chat agent (Gemini) ─┐ read/write
                                     ▼
                          ProjectStateStore  ← one shared store per project
                                     ▲ read/write
   export_docx (agent) ─────────────┘→ orchestrator compose+export (QWEN) → DOCX/PDF → store
   Partner/auto API ────────────────────→ orchestrator (QWEN) → report   (NO chat agent)
```

**Division of labour:** Gemini agent = *coordinator* (understands the student, decides to call
`export_docx`/`backfill`/preflight). qwen orchestrator = *writer* (the actual chapter prose,
even when the button was pressed from chat). So "who writes the thesis" = **qwen**, always.

---

## 3. Current model routing (and why)

| Knob | Controls | Current value | Reason |
|---|---|---|---|
| `ORCHESTRATOR_LLM_ROUTE` / `_MODEL` | Report pipeline (M1–M5) | `ofox` / `bailian/qwen-plus` | Owner's benchmark: qwen-plus wins report-writing quality **and** is cheapest. Verified it drives the tool-heavy pipeline end-to-end (~215s full report, real tables/TOC/citations). |
| `DOTHESIS_MODEL_ROUTE` / `DOTHESIS_AGENT_MODEL` | Chat agent | *(unset)* → native Gemini | Vision (student images) works only on the native path today (see §4c). Also prompt-caching on the big system prompt. |
| `DOTHESIS_VISION_MODEL` | Orchestrator vision turns | `gemini-2.5-flash` | qwen is text-only; image turns go to Gemini via Ofox's `/gemini` endpoint. |

`.env` is gitignored; never committed. Owner does **not** treat "Chinese model (Alibaba/qwen)
writes thesis content" as a dealbreaker.

---

## 4. Corrections / debunked assumptions (recorded so we don't repeat them)

During the 2026-07-15 discussion, three plausible-sounding claims turned out to be **wrong**
on inspection. Kept here as a caution:

- **4a. "qwen is weak at tool-calling" → FALSE.** The orchestrator binds `ALL_TOOLS` with
  `tool_choice="any"` on qwen (`router_agent.py:168`) and runs full reports fine. The chat
  agent's "didn't call backfill" incident was on **Gemini** and caused by a tool-schema 400
  bug (`audit_instrument` had bare `list` params — since fixed), not by qwen.
- **4b. "Ofox loses prompt-caching, only native keeps it" → FALSE.** Owner confirmed **Ofox
  supports prompt caching**. The `agent/model_factory.py` comment implying native-only caching
  is not authoritative for the Ofox gateway.
- **4c. "gemini-2.5-flash via Ofox keeps chat vision" → FALSE (verified).**
  `agent/multimodal.py:225 detect_provider()` returns only `"anthropic"` (if `ANTHROPIC_API_KEY`)
  or `"gemini"` — **it ignores `DOTHESIS_MODEL_ROUTE`**. So on `route=ofox` the code builds
  **Gemini-native `{"type":"media"}` blocks** but sends them through a **ChatOpenAI** client →
  images are mishandled/dropped. **Consequence: moving the chat agent to `route=ofox` (ANY
  model) breaks student image uploads until the code is fixed.** Only native Gemini currently
  keeps chat vision working.

**Net:** the current config (report=qwen/Ofox, agent=native Gemini) is the correct, working
setup. There is no env-only change that improves it; moving the agent to Ofox needs a code fix
first (§4c) and should be verified with a real image, not assumed.

---

## 5. The "should it be ONE agent?" analysis

The recurring instinct — "it should just be one agent" — is reasonable and matches where modern
agent SDKs (Claude Agent SDK, deep-agents: one capable agent + subagents + skills) are heading.
Honest weighing:

### Arguments FOR collapsing to one agent
- Simpler mental model; one model knob; kills the "agent" naming overload.
- A single strong agent (with subagents per chapter + skills for formatting) *can* do both the
  conversation and the long-form generation.
- Less duplication (two LLM factories, two config prefixes).

### Arguments FOR keeping two runtimes (the current design)
1. **Headless B2B flow (strongest).** The partner path emits a 30-page PDF server-side with no
   chat. That wants a **deterministic pipeline** (M1→M5 with gates/validators/resumability/
   progress), not a conversational agent. Collapse to one agent and you must rebuild that
   determinism inside the agent anyway.
2. **Structured, controllable generation.** LangGraph gives per-module execution, per-step
   retry, checkpointing, progress tracking, and reliable tables/TOC/citations. A free-form
   ReAct agent is harder to make reproducible/reliable on a fixed 30-page deliverable.
3. **Cost.** The pipeline can use a cheap prose model (qwen) for the heavy writing while chat
   uses another model. One unified *premium* agent (e.g. Fable 5 at $10/$50 per 1M tokens)
   doing everything gets very expensive on long output.
4. **Separation of concerns.** Chat = interactive coaching (latency-sensitive, cheap, vision).
   Pipeline = artifact production (throughput, determinism, prose quality). Different profiles.

### Honest conclusion
The pain the owner feels is **DX (confusing env names + overloaded "agent" word)**, not a broken
architecture. The two-runtime split is a defensible, common **orchestrator-worker / planner+
pipeline** pattern, justified primarily by the headless report flow. Merging into one agent is a
**large rewrite** that trades a proven deterministic pipeline for agent autonomy (less
predictable) and pushes toward premium models — worth it only as a deliberate rebuild, not as
cleanup.

### If a rebuild is ever pursued
- Single agent (Claude Agent SDK / deep-agents) with: subagents per chapter, skills for
  DOCX/PDF/citation formatting, a headless "batch" entry for the B2B flow, and a shared store.
- Budget for a premium model or accept quality tradeoffs; re-validate determinism (gates,
  resumability) that the pipeline currently gives for free.

---

## 6. Known DX pain + deferred cleanup (NOT done — owner to decide)

- **Inconsistent env prefixes:** `ORCHESTRATOR_LLM_*` (report) vs `DOTHESIS_*` (agent).
  Proposed (deferred) rename to `DOTHESIS_REPORT_*` / `DOTHESIS_AGENT_*` for symmetry — touches
  `orchestrator/llm.py`, `agent/model_factory.py`, `.env`, `scripts/deploy.sh`. Low value, some
  risk; owner said **don't rename now**.
- **Overloaded "agent":** consider renaming `orchestrator/agents/` → `orchestrator/modules/` (or
  `workers/`) in a future cleanup to disambiguate from the chat `agent/`.

---

## 7. Open decisions for the owner

1. **Unify chat agent onto Ofox (one bill)?** Requires the §4c code fix first
   (`detect_provider()` must honor `route=ofox` → use the OpenAI image path → verify Ofox
   forwards images to a vision model), tested with a real image. Otherwise keep native Gemini.
2. **Rename env vars for consistency?** Deferred; low value, small deploy risk.
3. **Rebuild to a single agent?** Big project; only if the flexibility is worth losing the
   deterministic pipeline + accepting premium model cost. Headless B2B flow is the main
   constraint to design around.

*No action taken from these notes. Current running config unchanged: report = qwen-plus (Ofox),
chat agent = native Gemini.*
