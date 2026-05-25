# Platform pivot — master roadmap

> This is the **north-star document** for the chat-based / LangGraph platform pivot. The pivot is decomposed into 7 sub-projects; each sub-project has its own spec + plan + implementation cycle. **When in doubt about scope, status, or "what comes next" — read this first.**

**Date opened:** 2026-05-26
**Owner:** Cao Nguyen
**Driver:** `new_prd/Copy of thesis_saas_PRD_v3.md` (PRD v1.1)
**Status legend:** ⬜ not started · 🟡 in design · 🔵 in implementation · ✅ shipped

---

## The vision

`dothesis` becomes a chat-based research copilot built on LangGraph, modeled on `langchain-ai/open_deep_research`. Each project has:

- One shared `context_store` of confirmed module outputs
- **Many threads** (the user can fork to try alternative directions)
- 5 specialized module agents (Topic Discovery → Literature Review → Research Design → Data Analysis → Writing) each with its own tool set
- A supervisor that routes between modules based on `context_store` state and user intent
- Two operating modes: **interactive** (in-process chat, SSE streaming) and **auto** (subprocess, silent end-to-end draft, identical artifact to today's `python -m engine`)

The existing `engine/` pipeline does not get rewritten. It gets wrapped as LangChain tools that agents call.

The existing wizard (`web/(inapp)/wizard`) stays alive in parallel until the new chat UI is stable.

---

## Sub-project map

```
                    ┌───────────────────────────────────┐
                    │  1. Orchestration foundation      │   ⬅ unblocks everything
                    │     (LangGraph + DB + auto+chat)  │
                    └───────────────────────────────────┘
                                    │
        ┌───────────────────────────┼──────────────────────────────┬─────────────┐
        │            │              │              │               │             │
        ▼            ▼              ▼              ▼               ▼             ▼
    2. M2 chat   3. M1 topic   4. M3 design   5. M4 analysis  6. M5 writing  7. New chat UI
       (Lit       (card-grid    (multi-method  (data-type      (auto-fill      (Next.js)
        Review)    UX)          branches)       detection +    + editor)
                                                 parsers)
        │            │              │              │               │             │
        └────────────┴──────────────┴──────────────┴───────────────┘             │
                                    │                                            │
                                    └────────────────────────────────────────────┘
                                          (each module ships behind the chat UI)
```

Sub-projects 2–6 are mostly independent and can be parallelized once #1 lands. #7 partly depends on #2–6's UX details but can begin as soon as #1 exposes the API.

---

## Sub-project 1 — Orchestration foundation 🔵

**Status:** In implementation (spec + plan complete 2026-05-26)
**Spec:** `docs/superpowers/specs/2026-05-25-orchestration-foundation-design.md`
**Plan:** `docs/superpowers/plans/2026-05-26-orchestration-foundation-plan.md` (+ 4 phase files)
**Estimated effort:** ~32 TDD tasks, ≈ 2–4 weeks

**Delivers:**
- New `orchestrator/` Python package (sibling to `engine/`, `api/`, `web/`)
- LangGraph supervisor + 5 module agents, all with shared `ModuleAgent` base class
- 4 new DB tables (`projects`, `threads`, `messages`, `context_store`) + nullable columns on `jobs`
- HTTP API: `POST /projects`, `POST /threads/{id}/messages` (SSE), `POST /projects/{id}/runs`, `POST /runs/{id}/pause|resume`
- Subprocess CLI: `python -m orchestrator --auto-draft` and `--resume-run-id`
- Multi-thread per project with shared `context_store` + first-confirm-wins concurrency
- Stop/resume auto-mode via SIGTERM + LangGraph checkpoints
- Feature flag `ORCHESTRATOR_ENABLED` (off by default) — existing wizard untouched

**Out of scope (deferred to later sub-projects):**
- Module-specific UX (M2 chat-first, M1 card-grid, M3 model builder, M4 outline/parsers, M5 editor)
- New Next.js chat UI
- Per-module agent prompt quality (uses generic clarification loop)
- Multi-provider model routing (stays on Gemini)
- Forking threads via LangGraph time-travel
- "Pause auto-mode and switch to interactive" mid-run

---

## Sub-project 2 — M2 Literature Review chat-first redesign ⬜

**Status:** Not started · brainstorm when sub-project 1 is shipped

**Why this one second:** Most chat-native module in the PRD (PRD §6.2). Existing `engine/utils/agent_runner.research_citations_via_api` + `engine/utils/api_citations/*` + `engine/utils/citation_compiler` are already used as tools in sub-project 1, so the upgrade is purely about M2 agent specialization — not new tools.

**Anticipated scope:**
- Replace generic clarification loop in `orchestrator/agents/m2_literature.py` with the **5-phase chat machinery** from PRD §6.2.3:
  1. Familiarization (optional paper upload)
  2. Research_State presentation (with citations)
  3. Gap_Analysis presentation (with page references)
  4. Reference_Confirm loop (verify pages)
  5. Output_Gen (Chapter 2 draft)
- Each phase is a sub-node within an M2 sub-graph
- Citation verification layer: when user has uploaded PDFs, verify `[author, year, page]` claims against extracted text
- Replace cosine-similarity gap detection with the existing Signal agent's prompt approach

**Key technical decisions to make in brainstorming:**
- Is M2 itself a LangGraph sub-graph, or one node with internal state machine?
- How aggressively do we verify page references? (Per-PDF cost can be high.)
- Quick-reply buttons in chat — frontend feature flag or backend annotation in `tool_calls_json`?

**Out of scope for this sub-project:** Semantic Scholar live search (Phase 4 of PRD roadmap), Zotero/Mendeley integration.

---

## Sub-project 3 — M1 Topic Discovery card-grid UX ⬜

**Status:** Not started

**Why this one next (after M2):** Smallest module-specific UX, validates the "agent + custom frontend widget" pattern that M3 and M4 also need.

**Anticipated scope:**
- Card-grid field selector (PRD §6.1.2 Step 1.1)
- 3-column topic explorer: Topic Clusters / Suggested Topics / Topic Detail
- Topic specification with 3 AI-suggested directions (PRD §6.1.2 Step 1.3)
- Frontend component: `web/app/(inapp)/project/[id]/m1-topic-discovery/` (or whatever the chat UI router from sub-project 7 settles on)
- Agent emits structured "render-card-grid" instructions (likely via `tool_calls_json` with a typed schema) that the frontend interprets

**Key brainstorming questions:**
- How does the agent signal "show a card grid here" to the chat UI? Via tool-call shape, via a special message role, or via a separate "ui_hints" SSE event?
- Does click-to-select bypass the agent's clarification loop, or does it just synthesize a user message?
- Trending-topics data source — Gemini search grounding, Semantic Scholar API, or a curated static list?

---

## Sub-project 4 — M3 Research Design multi-method branches ⬜

**Status:** Not started

**Why important:** This is where the user's paradigm choice (quant vs qual vs mixed) cascades into very different tool sets and downstream M4 outline. Without this redesign, sub-project 1's generic M3 agent will produce shallow research designs.

**Anticipated scope:**
- Branch the M3 agent into three sub-paths (quantitative / qualitative / mixed) with distinct tool sets:
  - **Quant branch:** drag-and-drop conceptual model builder (PRD §6.3.3 Step 3.2A-i), scale builder pulling from canonical scales (PRD §6.3.3 Step 3.2A-ii), Cohen / Hair sample size calculator
  - **Qual branch:** thematic framework builder, interview guide composer (PRD §6.3.4 Step 3.2B-ii), purposive sampling strategy
  - **Mixed branch:** sequential design selector (explanatory vs exploratory), both sub-flows
- New tools: `validate_likert_scale`, `compose_interview_guide`, `compute_sample_size_pls_sem`
- M3 schema bifurcates: `M3Quant`, `M3Qual`, `M3Mixed` (or one schema with discriminated union)

**Key questions:**
- Is the model builder a true drag-and-drop frontend (canvas) or chat-driven ("add a path from A to B")?
- How do we represent the conceptual model in `context_store.m3_design` so M4 can consume it programmatically?

---

## Sub-project 5 — M4 Adaptive Analysis ⬜

**Status:** Not started

**Why hardest:** This is the highest-effort sub-project by far. Sub-project 1 ships M4 as stubs (`run_analysis_step` returns a placeholder). This sub-project replaces those stubs with real parsers for SPSS / SmartPLS / CB-SEM (AMOS / R lavaan) / NVivo / Atlas.ti / manual transcripts, plus the chat-triggered ad-hoc analysis (PRD §6.4.6).

**Anticipated scope:**
- File format parsers:
  - SPSS `.spv` (XML), `.sav` (read via `pyreadstat`), copy-paste of SPSS output (regex over text)
  - SmartPLS HTML reports (BeautifulSoup-based)
  - R lavaan console output (regex over fit indices)
  - NVivo / Atlas.ti exports (XLSX/DOCX)
  - Raw transcript files (TXT/DOCX) → coding pipeline
- Outline templates from PRD §6.4.3 (outlines A–E) become Pydantic schemas with editable steps
- Chat-triggered ad-hoc analysis: `/run-extra <step>` command flow + tool calls
- Initial coding pipeline for qualitative data (line-by-line code suggestion + theme clustering)

**Out of scope:** NVivo/Atlas.ti file format support beyond Excel/Word exports; live SPSS execution (we read existing output, don't run SPSS ourselves).

**Risks:** Parser fragility against vendor format updates. May need a `parser_version` field per data type and version-gated parsing logic.

---

## Sub-project 6 — M5 Writing & Finalization (auto-fill + new editor) ⬜

**Status:** Not started

**Why later:** Sub-project 1 already wires M5 to existing `engine/phases/compose.py` + `engine/utils/docx_post_processor` so the auto-mode draft works end-to-end. This sub-project upgrades the **interactive** experience — section-by-section editing, paraphrase tools, citation manager.

**Anticipated scope:**
- WYSIWYG section editor (in the new chat UI) showing the composed draft + inline edit, paraphrase, translate, cite-insert affordances
- New tools: `paraphrase_text(passage, style)`, `translate_passage(text, from, to)`, `insert_inline_citation(passage, ref)`
- Citation manager UI: dedupe, format-switch (APA7 ↔ Vancouver ↔ Chicago), import from Zotero/Mendeley (Phase 3 of PRD roadmap)
- Auto-fill engine: when M1-M4 are confirmed, M5 pre-fills every chapter (PRD §6.5.2 — adapts structure by `research_approach`)

**Key questions:**
- Editor library? (TipTap / Lexical / Slate — drives the rest of the frontend stack)
- Do we keep `engine/utils/docx_post_processor` for export, or migrate to a Web-app-side renderer?

---

## Sub-project 7 — New Next.js chat UI ⬜

**Status:** Not started · could begin in parallel with #2 once #1's API stabilizes

**Why last to fully finish:** Each module's UX (sub-projects 2-6) lands real frontend components into this app. Sub-project 7 owns the chat-shell scaffold: routing, message list, streaming token rendering, thread switcher, project sidebar, file-upload drop zone, token-cost UI.

**Anticipated scope:**
- New `web/app/(chat)/` route group: `/project/[id]`, `/project/[id]/thread/[tid]`
- Components: ChatPane, MessageBubble, StreamingResponse, ThreadList, ContextPanel (shows context_store state), ProgressTracker (M1-M5 progress chips)
- SSE client for `POST /threads/{tid}/messages` token stream
- Live state-stream subscription (`GET /threads/{tid}/state`) — updates progress tracker + alerts on remote `context_store` updates from sibling threads
- File upload → `POST /threads/{tid}/uploads` (new endpoint to add in this sub-project)
- Token-cost meter

**Coexistence:** While sub-project 7 is in flight, the existing wizard (`web/app/(inapp)/wizard`) stays the primary entrypoint. Once 7 is feature-complete and validated, we decide on a separate flag/sub-project to deprecate the wizard.

---

## Cross-cutting concerns (NOT separate sub-projects — handled within whichever sub-project touches them)

- **Pricing:** Each sub-project reuses `api/app/pricing.py` rules; no per-module pricing changes are planned in the pivot.
- **Auth:** No changes from the platform pivot.
- **Sentry / observability:** Sub-project 1 wires `engine/sentry_config.py` into the orchestrator; later sub-projects inherit it.
- **i18n (VI/EN):** Existing language pass-through (PRD §1.3). Each module agent gets the project's language from `context_store.m1_topic.language`. No new i18n machinery.

---

## Things explicitly NOT in the pivot

These get listed here so they don't get smuggled into a sub-project mid-flight:

- Magic-link or passwordless login
- Real-time multi-user collaboration on the same thread (suggested by PRD §7.3 Comment & Annotation, but pushed to a post-pivot epic)
- Mobile-native app (iOS / Android — PRD Phase 4 of roadmap)
- Similarity / anti-plagiarism detection (PRD Phase 4)
- Switching the LLM provider (Gemini → multi-provider) is a one-off model-config task, not a sub-project
- Replacing the existing PDF/DOCX rendering pipeline (`engine/utils/docx_post_processor`, `weasyprint`)
- Replacing the existing job-runner subprocess pattern with a queue (Celery/RQ/Temporal)

---

## Re-entry checklist

When a new session opens and needs to figure out what to do next:

1. **Read this file.** It's the canonical map.
2. **Check status icons above.** What's the lowest-numbered ⬜ that has all its dependencies ✅?
3. **Open that sub-project's spec** if 🟡 or 🔵, or **start a brainstorming session** if ⬜.
4. **Never start a sub-project before its dependency is shipped.** Sub-project 1 unblocks everything; sub-projects 2-6 each unblock a slice of sub-project 7.

If the answer to step 2 is "everything is ⬜", the answer is **sub-project 1**.

---

## Status log

A short, append-only log of state changes. Update this when a sub-project moves between status icons.

| Date | Sub-project | Change | Notes |
|---|---|---|---|
| 2026-05-25 | 1 | ⬜ → 🟡 | Brainstormed; spec at `specs/2026-05-25-orchestration-foundation-design.md` |
| 2026-05-26 | 1 | 🟡 → 🔵 | Plan at `plans/2026-05-26-orchestration-foundation-plan.md` |

---

## Open questions for later sub-projects

Things that came up during sub-project 1's brainstorming but were intentionally deferred. Capture them here so they don't get lost.

- **Pause-and-switch-to-interactive mid-auto-run** — discussed in sub-project 1; deferred. Should be revisited once sub-project 7 has the UI surface to expose the choice.
- **Forking threads with LangGraph time-travel** — discussed in sub-project 1; deferred. Decide once sub-project 7 has thread-management UX.
- **Per-thread or per-project rate limiting** — uses today's user-level limits; revisit when usage patterns are clearer.
- **Concurrency option C (explicit promote)** — sub-project 1 ships option B (first-confirm-wins + alert). If alert UX feels too coarse after sub-project 7 lands, evaluate moving to C.
- **Multi-provider model routing** — Gemini-only for the pivot. The wrapper `_get_llm()` in each agent and tool is the chokepoint that would change.

---

*This document is the source of truth for "what's the bigger picture." Specs and plans live in `docs/superpowers/specs/` and `docs/superpowers/plans/` respectively. When a sub-project ships, update its status icon here AND add a line to the Status log.*
