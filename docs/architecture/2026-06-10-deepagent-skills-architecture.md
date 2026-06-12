# DoThesis v3 — Deep Agent + Skills Architecture

> High-level redesign. DoThesis becomes a **real agent** built on LangChain
> [deepagents](https://docs.langchain.com/oss/python/deepagents/skills), with the M1–M5
> domain expertise packaged as **skills** (progressive disclosure), instead of the
> LangGraph state-machine orchestrator (`orchestrator/graph_v2.py`).
>
> Reference experience: the Claude.ai `/dothesis` session (PDF, 2026-06-10) where a
> skill-driven Claude walked a student from "I have nothing" → locked topic → searched
> real papers → cited gap analysis → model + hypotheses → questionnaire DOCX → PLS-SEM
> interpretation → full APA-7 paper with clickable citations. **That is the product.**
> The app's job is to deliver that exact experience with server-side state, real research
> tooling, and metered billing.
>
> Prior art this supersedes: `docs/architecture/2026-06-03-researchflow-target-architecture.md`
> (the state-machine fix design) and `dothesis_v2/dothesis-architecture-brief.md` (the
> brief). Skills prototype: `dothesis_v2/skills/` (validated on Claude.ai — the PDF).

---

## 0. The pivot, stated honestly

The v2 brief's principle §1.1 was *"state machine, not a free agent — do not implement an
open-ended ReAct loop."* **We are deliberately reversing that principle.** The PDF session
proved the free-agent + skills shape produces a better experience: the agent reads module
playbooks on demand, manages its own todo/state files, runs code when it needs to
(questionnaire DOCX, OOXML hyperlink debugging), and stays coherent across M1→M5 without
a hand-built router graph.

What we are **not** reversing — the brief's principles that survive, re-homed:

| v2 principle | Where it lives in v3 |
|---|---|
| `context_store` is the single source of truth | Unchanged — but it's now a **file** (`/project/context_store.json`) the agent edits through a guarded tool, mirrored to Postgres JSONB |
| Read = free, mutate = focus shift + downstream `needs_review` | Deterministic code in the `commit_slice` tool — not prompt-trust |
| Soft locks, never walls | Skill instructions (the v2 skills already encode this) |
| Token metering wraps the actual LLM call | deepagents **middleware** around model calls — same `token_meter.py` logic |
| Three interaction shapes (wizard / chat-loop / pipeline) | Encoded *inside* each module skill's instructions, not as different runtime mechanisms |

The router, the per-module agent classes, the shapes registry, and the LangGraph node
wiring (`router_agent.py`, `agents/m*`, `shapes.py`, `graph_v2.py`) are **replaced by one
deep agent + 8 skills**. The model does the routing by reading skill descriptions — the
PDF shows this working ("Reading M1 topic module…", "Check docx skill before writing").

---

## 1. System at a glance

```
┌────────────────────────────────────────────────────────────────────────┐
│  Next.js web (unchanged surface: chat UI, widgets, SSE, dashboard)     │
└───────────────▲────────────────────────────────────────────────────────┘
                │ SSE / REST (same /api/v1 contract)
┌───────────────┴────────────────────────────────────────────────────────┐
│  FastAPI api  — auth, projects, threads, uploads, billing (unchanged)  │
│                                                                        │
│   chat turn ──► DeepAgent runtime (deepagents.create_deep_agent)       │
│                 │  model: claude-sonnet / opus (per-action tier)       │
│                 │  middleware: TokenMeter · SSEProgress · HITL         │
│                 │  checkpointer: Postgres (LangGraph) — resume = free  │
│                 │                                                      │
│                 ├─ SKILLS (read-only, progressive disclosure)          │
│                 │    /skills/dothesis            ← root: principles,   │
│                 │    /skills/dothesis-bootstrap     state file, status │
│                 │    /skills/dothesis-m1-topic      protocol, routing  │
│                 │    /skills/dothesis-m2-literature ★ tools-first      │
│                 │    /skills/dothesis-m3-design                        │
│                 │    /skills/dothesis-m4-analysis                      │
│                 │    /skills/dothesis-m5-writing   ★ pipeline-first    │
│                 │                                                      │
│                 ├─ TOOLS (the agent's hands — deterministic code)      │
│                 │    read_slice / commit_slice   ← guarded state I/O   │
│                 │    research_scout              ← ★ current M2 engine │
│                 │    parse_reference (GROBID)                          │
│                 │    run_stats (sandboxed)                             │
│                 │    write_pipeline / export_docx ← ★ current M5 engine│
│                 │                                                      │
│                 └─ BACKEND (CompositeBackend)                          │
│                      /skills/…   → read-only bundle (versioned, code) │
│                      /project/…  → per-project store (Postgres-backed)│
│                      /workspace/…→ sandbox scratch (scripts, exports) │
└───────────────┬────────────────────────────────────────────────────────┘
                │
   ┌────────────┴───────────────┐
   │ engine (kept as a library) │  deep_research planner · api_citations
   │                            │  scout · citation validator/quality
   │                            │  filter · phases: structure→compose→
   │                            │  citations→compile→validate · docx
   │                            │  post-processor (citeproc, TOC,
   │                            │  clickable refs — the PDF's M5 output) │
   └────────────────────────────┘
```

One agent. Eight skills. A short tool belt where correctness or cost demand real code.

---

## 2. Skills — the domain layer

Skills follow the deepagents layout (`SKILL.md` + `references/` + `scripts/`), seeded from
`dothesis_v2/skills/` (already validated in the PDF session). Three-layer progressive
disclosure keeps per-turn context small: only name+description at startup, full SKILL.md
when relevant, references on demand.

```
skills/
├── dothesis/                      # root skill — always activates first
│   ├── SKILL.md                   # principles, state protocol, status legend,
│   │                              #   "which module skill to read when"
│   └── references/
│       ├── context-store-schema.md
│       └── status-protocol.md     # read=free / mutate=propagate, soft locks
├── dothesis-bootstrap/            # entry wizard: declare→import→reconcile
├── dothesis-m1-topic/             # wizard shape: options → title+RQs → lock
├── dothesis-m2-literature/        # ★ chat loop, 5 phases — see §2.1
│   ├── SKILL.md
│   └── references/
│       ├── gap-quality-rubric.md
│       └── search-playbook.md     # when/how to call research_scout
├── dothesis-m3-design/            # wizard: model → hypotheses → methodology
├── dothesis-m4-analysis/          # pipeline: detect → outline → run_stats steps
│   └── scripts/                   #   whitelisted analysis templates
├── dothesis-m5-writing/           # ★ wizard, pipeline-backed — see §2.2
│   └── references/
│       └── section-lineage.md     # which slice feeds which chapter
└── dothesis-router/               # RETIRED as a skill — routing is the agent's
                                   #   own skill-matching; root skill keeps the
                                   #   read/mutate semantics it must enforce
```

Why no router skill: in deepagents the model already does discovery→activation from skill
descriptions. The v2 router skill's real content — intent semantics (`read` vs `mutate`
vs `continue`) and propagation — moves into the **root skill** (semantics) and the
**`commit_slice` tool** (enforcement). A second classifier pass would add latency and
fight the agent.

### 2.1 M2 — keeps the **current research strategy** (the ★ difference #1)

The v2 skill said "use Claude's native PDF reading, don't use external extractors" —
right for Claude.ai-web, wrong for our app. Here M2's *procedure* stays (5 phases:
familiarization → research_state → gap_analysis → reference_confirm → output_gen,
≥2 supporting papers per gap, page-cited claims) but its *muscle* is the engine:

- `research_scout(topic, rqs, seed_refs)` — wraps the existing
  `engine/utils/deep_research.py` planner (Gemini plan → orchestrated execution) +
  `api_citations` scout, citation validator, and quality filter. Streams progress events
  (the existing `safe_print` → emitter chain) so the web UI's ProgressBubble keeps working.
- `parse_reference(file|doi)` — the existing GROBID path for uploaded PDFs / DOI lookups.
- Verified citations carry `verified: true` + page refs into `literature_sources`;
  the skill's gap rubric then operates over *real, validated* sources instead of
  whatever the model remembers. This is exactly the PDF's "Searched the web → 6 papers
  table" beat, but backed by our pipeline instead of Claude.ai's generic web search.

SKILL.md instructs: *never* fabricate sources; if the slice has no papers, call
`research_scout` or ask for uploads — phase 3 (gaps) is gated on indexed sources.

### 2.2 M5 — keeps the **current writing pipeline** (the ★ difference #2)

The v2 skill had the agent write chapters in-context and export with ad-hoc
`python-docx` scripting — which is how the PDF session ended up hand-debugging OOXML
`r:id` hyperlinks for three turns. We already own that solution: the engine's
draft pipeline. M5's skill orchestrates; the pipeline executes:

- `write_pipeline(sections, style, language)` — invokes the engine's
  `structure → compose → citations → compile → validate` phases scoped to the project's
  `context_store` (M1 RQs, M2 sources/gaps, M3 model/methodology, M4 results as the
  grounding corpus). Used for "write the full paper" and per-chapter generation.
- `export_docx(draft_id)` — the engine's `docx_post_processor` + citeproc (CSL): APA-7
  references, auto TOC, **clickable internal citations and DOIs out of the box** — the
  exact features the PDF session had to retrofit by hand.
- The skill keeps the v2 quality bars (every number copied from `analysis_results`,
  hypotheses verbatim, lineage recorded per section) and the wizard UX (pick sections →
  outline → confirm → generate), but generation happens in the pipeline, streamed back
  as progress.

Inline edits after generation ("rewrite the discussion, more practical implications")
stay agent-side: read the section from the slice, revise, `commit_slice` — no full
pipeline re-run for a paragraph.

### 2.3 M4 — pipeline shape, sandboxed

Unchanged in spirit from v2/current: detect uploaded data (`pyreadstat` for `.sav`),
propose an outline, execute **whitelisted** analyses (`run_stats(op, params)` over
pandas/scipy/statsmodels/pingouin in the network-less sandbox). The skill's
`scripts/` hold the analysis templates; free-form Python from the model never executes
against user data (v2 brief risk §8.1 still applies — agent pivot does not soften it).

---

## 3. State — `context_store.json` as a file, Postgres as the truth

The PDF's one manual step ("download context_store.json, re-attach it to Project
Knowledge") disappears: the agent reads/writes `/project/context_store.json` through the
backend, and the backend is Postgres.

- **Backend**: `CompositeBackend`
  - `/skills/` → read-only `StoreBackend` (skills ship with the deploy, content-versioned;
    `FilesystemPermission` read-only in production).
  - `/project/` → a thin custom backend over the existing `projects.context_store`
    JSONB + `uploads` tables (one project = one root). The agent sees files; the DB sees
    rows. Version snapshots append to `version_history` (migration `20260603_version_history`
    already landed).
  - `/workspace/` → per-thread sandbox filesystem for scripts, generated questionnaires,
    draft exports.
- **Guarded writes**: the agent does *not* free-write the state file. It calls
  `commit_slice(module, writes, reason)`; the tool validates against the slice schema
  (`orchestrator/agents/shapes.py` survives as pure schemas), applies the write, snapshots
  a version, sets `focus = module`, and flags downstream modules `needs_review` from the
  static dependency DAG (M2→M3→M4→M5). Propagation is **code**, not model discipline.
  `read_slice(module)` is free and never mutates — the read/mutate asymmetry the brief
  cared about, enforced at the tool boundary.
- **Status map** (`locked | in_progress | done | needs_review`) lives next to the store,
  updated only by `commit_slice` / `confirm_module`. The web's module tracker, dashboard
  cards, and focus chip keep reading `projects.module_status` exactly as today.
- **Conversation memory**: LangGraph Postgres checkpointer (already in place) gives
  resume-mid-thread; the deepagents planning file (`/workspace/todos.md`) replaces the
  phase pointer. Transcript stays in `messages` (unchanged); tiered memory (recent window
  + retrieval) remains a later optimization exactly as the v2 brief sequenced it.

---

## 4. Runtime — middleware, streaming, HITL, billing

- **TokenMeterMiddleware** — wraps every model call (main agent and subagents): estimate
  → reserve → reconcile against the credit ledger (`20260603_token_ledger`). Per-action
  pricing maps to skill activations (an M2 scout turn bills differently than a chat read).
- **SSEProgressMiddleware** — bridges agent events (skill activation, tool start/finish,
  engine progress callbacks) onto the existing SSE event types the web already renders:
  `progress` → ProgressBubble, module tags → bubble chips, `error` → ErrorBubble. Skill
  activation events become the UI's "Reading M2 literature module →" affordance (the PDF
  shows how much trust this builds).
- **HITL / confirmations** — deepagents interrupt support backs the lock-gates ("Khóa M3
  lại nhé?") and the existing quick-reply widgets. Widget clicks keep synthesizing user
  messages (current `synthesize.ts` mechanism) — no protocol change for the web.
- **Subagents** — two places where context isolation pays:
  - `scout` subagent: runs the M2 deep-research execution (long, tool-noisy) and returns
    a compact sources digest, keeping the main thread lean.
  - `writer` subagent: drives `write_pipeline` for full-paper jobs (the current auto-draft
    runs path can converge here later).
  Subagents get only the skills they need (deepagents: skills are not inherited).

---

## 5. What is kept / replaced / deleted

| Area | Fate |
|---|---|
| `engine/` research stack (deep_research, api_citations, validators, GROBID) | **Kept** — becomes the `research_scout` / `parse_reference` tools (M2 ★) |
| `engine/` writing pipeline (phases, citation compiler, docx post-processor) | **Kept** — becomes `write_pipeline` / `export_docx` tools (M5 ★) |
| `api/` FastAPI (auth, projects, threads, uploads, credit, SSE) | **Kept** — only the chat turn's internals change |
| `web/` (chat UI, widgets, dashboard, module tracker) | **Kept** — same SSE/REST contract; gains "skill activation" affordance |
| Postgres schema (context_store JSONB, module_status, focus, token ledger, version history) | **Kept** — the new backend reads/writes the same rows |
| `orchestrator/agents/shapes.py` slice schemas | **Kept** as validation schemas for `commit_slice` |
| `orchestrator/token_meter.py` | **Kept** — re-homed as middleware |
| `orchestrator/graph_v2.py`, `router_agent.py`, `agents/m1…m5` classes, `loader.py`, `read_handler.py`, per-module prompt assembly | **Replaced** by the deep agent + skills |
| `dothesis_v2/skills/*` | **Promoted** into this repo (`skills/`), adapted per §2.1/§2.2 |
| M4 stats sandbox plan | **Unchanged** — whitelisted ops only |

---

## 6. Migration path (strangler, not rewrite)

1. **Spike (CLI)** — `create_deep_agent` + promoted skills + a filesystem backend against
   a throwaway project dir. Replay the PDF transcript as the acceptance script: bootstrap
   → M1 lock → M2 with `research_scout` → M3 → M4 on the sample `.sav` → M5 full paper
   DOCX with clickable citations. (`dothesis_v2/testcases` already sketches these.)
2. **Tool extraction** — wrap engine entry points as typed tools (`research_scout`,
   `write_pipeline`, `export_docx`, `run_stats`, `parse_reference`); build
   `read_slice`/`commit_slice` over the existing JSONB + version-history tables.
3. **Agent service behind a flag** — new turn handler in `api/routers/chat.py` dispatches
   to the deep agent for flagged projects; graph_v2 keeps serving the rest. Same SSE
   events, so the web needs no fork.
4. **Middleware parity** — token metering + progress + HITL wired; billing reconciliation
   verified against the ledger.
5. **Cutover & deletion** — flip default, migrate active projects (state shape is already
   compatible), delete the graph: router, module agent classes, shapes-as-runtime.
6. **Later** — converge auto-draft runs onto the `writer` subagent; tiered memory when
   projects outgrow full-context; Claude.ai skill bundle (`dothesis_v2`) stays as the
   zero-infra distribution of the same skills (one source tree, two targets).

---

## 7. Risks

1. **Routing regression** — model skill-matching replaces the deterministic router.
   Mitigation: root skill carries explicit dispatch rules; the v2 testcases become an
   eval suite (intent → expected skill + tool calls) run on every skill edit.
2. **State discipline** — a free agent could try to bypass `commit_slice` by editing the
   file directly. Mitigation: `/project/context_store.json` is **read-only through the
   file API**; the only write path is the tool. (Backend permission rules, not prompt.)
3. **Cost drift** — agent loops can burn tokens vs. the fixed graph. Mitigation: metering
   middleware with per-turn budget caps; subagents isolate the noisy phases; skill bodies
   stay under the 5k-token guidance.
4. **Sandbox surface** (unchanged from v2 §8.1) — stats and export scripts execute only
   whitelisted templates in a network-less sandbox; deepagents script execution stays
   disabled outside `/workspace/`.
5. **deepagents maturity** — pin versions; the backend and middleware seams are ours, so
   a framework change stays contained to the runtime layer.
```
