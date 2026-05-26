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
                    │  1. Orchestration foundation  ✅  │   ⬅ shipped 2026-05-26
                    │     (LangGraph + DB + auto+chat)  │
                    └───────────────────────────────────┘
                                    │
        ┌───────────────────────────┼──────────────────────────────┬─────────────┐
        │            │              │              │               │             │
        ▼            ▼              ▼              ▼               ▼             ▼
    2. M2 chat✅ 3. M1 topic ✅ 4. M3 design ✅ 5. M4 analysis  6. M5 writing  7. New chat UI ✅
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

## Sub-project 1 — Orchestration foundation ✅

**Status:** Shipped 2026-05-26 (branch `feat/orchestrator-foundation`, 28 commits, 68 tests passing)
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

## Sub-project 2 — M2 Literature Review chat-first redesign ✅

**Status:** Shipped 2026-05-27 (branch `feat/m2-chat-first`; 5-phase sub-graph + PDF upload subsystem + all tests passing)

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

## Sub-project 3 — M1 Topic Discovery card-grid UX ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp3-m1-card-grid`; widget infra + FieldPicker + ResearchTypePicker)

**Spec:** `docs/superpowers/specs/2026-05-27-sp3-m1-card-grid-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp3-m1-card-grid-plan.md`

**Delivers:**
- Backend widget primitive — `orchestrator/agents/widgets.py` with `CardOption` + `CardGridHint` + discriminated `WidgetHint` union (ready for SP4-SP6 variants)
- `ModuleAgent.render_hint_for_field` override hook (None-by-default on base; M1 overrides for `field` + `research_type`)
- Graph wiring — `_agent_node_factory` threads `tool_calls_json` through `AIMessage.additional_kwargs`
- API streaming — chat router emits `tool_calls` SSE event + persists `messages.tool_calls_json` (already-existing JSONB column)
- Frontend widget primitive — `widgets/types.ts` + `synthesize.ts` + `CardGridWidget` + `WidgetRenderer` dispatch (forward-compatible: unknown `widget_type` renders null)
- ChatPane integration — click on a card synthesizes a natural-language sentence ("I'd like to study Marketing.") and submits through the existing send path; no new backend protocol
- Widget "spent" semantics: enabled only on the last assistant message AND when nothing is streaming
- Schema-drift guard test (TS fixture mirrors backend Pydantic shape)

**Decisions worth remembering for SP4-SP6:**
- New widget variants land as new `WidgetHint` discriminated-union arms — existing variants and consumers stay untouched
- The "synthesize text and reuse the existing send path" approach keeps the protocol simple; click → text is one direction only
- M1 uses the shared `ModuleAgent` clarification loop (no sub-graph). M2's sub-graph pattern is reserved for modules with phase-distinct conversational shapes

---

## Sub-project 4 — M3 Research Design multi-method branches ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp4-m3-multi-method`; paradigm-aware agent + list_editor widget + 3 new qual tools)

**Spec:** `docs/superpowers/specs/2026-05-27-sp4-m3-multi-method-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp4-m3-multi-method-plan.md`

**Delivers:**
- Single `M3Agent` with paradigm-aware `_next_missing_field` walking `_FIELDS_BY_PARADIGM[paradigm]`; mixed flow composes quant + qual branches in order (no mixed-only code path)
- Improved flat `M3Output` schema with paradigm-specific optionals + `@model_validator` that fires only when `confirmed_at` is set (in-progress partials remain valid)
- Three new qualitative-flow tools: `suggest_themes`, `compose_interview_guide`, `suggest_purposive_criteria`
- Four static option JSON files (`_options_tool_quant.json`, `_options_tool_qual.json`, `_options_design_qual.json`, `_options_mixed_design_type.json`)
- New widget variant `ListEditorHint` joins the SP3 `WidgetHint` discriminated union; `ListEditorWidget` React component with local state + batch synthesize on Confirm (per-edit operations never hit the backend)
- `summarizeList` helper builds per-field bulleted final-state messages routed through the existing send path (themes/scale_items/purposive_criteria/interview_guide/conceptual_model formatters)
- 5 round-trip tests verify synthesized messages → `_extract_answer` produces expected structured values

**Decisions worth remembering for SP5-SP6:**
- Paradigm-aware field walks can live entirely in a single ModuleAgent override (`_next_missing_field`) — no sub-graph needed when branches differ only in *fields asked*, not in *conversational phases*
- New widget variants extend the WidgetHint discriminated union; existing variants and the `WidgetRenderer` default-null forward-compat stay untouched
- List_editor batch-confirm + per-field synthesizer keeps the LLM extraction unambiguous and the chat noise low
- M3 stashes paradigm context on a class-level cache that the parameter-less `render_hint_for_field` hook reads; this avoids changing the base-class signature while still allowing per-paradigm widget logic

**Out of scope (deferred):**
- Drag-and-drop conceptual-model canvas (separate post-pivot sub-project)
- Curated canonical scale library (Cronbach alpha + citations) — `suggest_scale_items` LLM tool covers V1
- Live Cohen / Hair / G*Power sample-size calculator widget — existing `estimate_sample_size` heuristic suffices

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

## Sub-project 7 — New Next.js chat UI ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp7-chat-ui-shell`; 3-pane shell + useStream + auto-draft drawer; 60+ tests passing)

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

**Note on actual ship order:** The original map implied 1 → 2 → 3 → 4 → 5 → 6 → 7, but the actual ship order was 1 → 2 → 7 (chat shell landed before the module-specific widgets). Sub-projects 3–6 will now plug their widgets directly into the SP7 shell.

---

## Status log

A short, append-only log of state changes. Update this when a sub-project moves between status icons.

| Date | Sub-project | Change | Notes |
|---|---|---|---|
| 2026-05-25 | 1 | ⬜ → 🟡 | Brainstormed; spec at `specs/2026-05-25-orchestration-foundation-design.md` |
| 2026-05-26 | 1 | 🟡 → 🔵 | Plan at `plans/2026-05-26-orchestration-foundation-plan.md` |
| 2026-05-26 | 1 | 🔵 → ✅ | All 32 tasks shipped on `feat/orchestrator-foundation`; 68 tests passing |
| 2026-05-27 | 2 | ⬜ → ✅ | M2 chat-first redesign + PDF upload shipped on feat/m2-chat-first; 207 tests passing |
| 2026-05-27 | 7 | ⬜ → ✅ | Chat UI shell shipped (no module-specific widgets yet); SP3-SP6 will plug widgets into this shell |
| 2026-05-27 | 3 | ⬜ → ✅ | M1 card-grid widgets shipped — widget infra + FieldPicker + ResearchTypePicker; pattern ready for SP4-SP6 |
| 2026-05-27 | 4 | ⬜ → ✅ | M3 multi-method shipped — paradigm-aware agent + list_editor widget + 3 new qual tools |

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
