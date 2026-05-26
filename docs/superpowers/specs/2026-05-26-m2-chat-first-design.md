# M2 Literature Review — chat-first redesign (sub-project 2 of 7)

**Date:** 2026-05-26
**Status:** Draft — pending user review
**Depends on:** Sub-project 1 (orchestration foundation) — shipped 2026-05-26

## Context

Sub-project 1 landed M2 as a thin `ModuleAgent` subclass using the shared clarification loop — the same generic "ask for missing field one at a time" pattern used by every module. PRD §6.2.3 calls for something fundamentally different: a **5-phase chat-first conversation** where the agent presents synthesis material, the user accepts or asks for unlimited regenerations with new constraints, and only then advances. Sub-project 2 replaces M2's generic loop with a dedicated LangGraph sub-graph that encodes the 5 phases as self-looping nodes.

## Goal

Replace the generic M2 agent with a 5-phase sub-graph (Familiarization → Research_State → Gap_Analysis → Reference_Confirm → Output_Gen). The outer graph from sub-project 1 is **unchanged** — it still sees M2 as a single node. Internally, M2 is now a compiled LangGraph sub-graph with its own state model, its own intent classifier loop per phase, and its own thread_id namespace under PostgresSaver.

## Non-goals

- Quick-reply button rendering (sub-project 7 frontend; backend tags messages with affordances but doesn't render UI)
- Frontend drag-and-drop upload widget (sub-project 7 — but the backend upload endpoint ships here)
- Dedicated `citations` DB table (stays in `context_store.m2_literature` JSONB)
- Real engine `CitationDatabase` integration (continues using sub-project 1's minimal wrapper)
- Cross-thread citation deduplication
- Semantic Scholar live API (PRD Phase 4 roadmap)
- M3-M5 sub-graph redesigns (each gets its own sub-project)
- OCR for scanned PDFs (text-extraction only; if PDF has no extractable text, mark unverified)

## Decisions (locked from brainstorming)

- **Architecture:** M2 is a compiled LangGraph sub-graph with 5 phase nodes + self-loops for regeneration. Outer graph keeps its single `M2` node; the wrapper invokes the sub-graph internally.
- **PDF upload scope:** **IN scope for sub-project 2.** Backend endpoint `POST /api/v1/projects/{pid}/uploads` accepts multipart PDF/text, stores in S3, indexes a `paper_uploads` DB row. M2 sub-graph reads these on Phase 1 entry. Sub-project 7 still owns the frontend drag-and-drop widget but the backend is here.
- **Regeneration loop:** each phase node self-loops on user "redo / change X / focus on Y" requests until user confirms or a 5-iteration cap is hit (soft warning at iteration 3; configurable via `M2_REGEN_CAP` env).
- **Tool binding:** all 5 M2 tools (`scout_citations`, `summarize_paper`, `find_research_gaps`, `compile_citations`, `verify_page_numbers`) are bound to every phase node. Per-phase differentiation lives in the system prompts, not in tool gating.
- **State model:** new `M2SubGraphState` TypedDict separate from outer `OrchestratorState`. The wrapper translates outer ↔ sub-graph state at entry and exit.
- **Citation persistence:** continues to live in `context_store.m2_literature.citation_list` JSONB. No new DB table.
- **Bilingual:** agent detects vi/en from the user's latest message and responds in kind; falls back to project's `language` field.
- **PDF text extraction:** uses `pdfminer.six` (already vendored by sub-project 1's `summarize_paper`). If a PDF has no extractable text (image-only scan), `paper_uploads.text_extracted_at` stays NULL and Phase 1 surfaces a warning. No OCR.
- **Phase 4 walk-vs-batch:** walk one page reference at a time (matches PRD §6.2); `skip_all` quick-reply available.
- **Phase 5 regeneration:** single-shot. If user dislikes the Ch.2 draft, they jump back to Phase 2 or 3 to fix the underlying inputs.

---

## Architecture

The outer graph from sub-project 1 is unchanged. The `M2` node in `orchestrator/graph.py` still wraps a `ModuleAgent` subclass — only that subclass's `step()` implementation changes. Internally, M2 now invokes a compiled LangGraph sub-graph:

```
outer graph (sub-project 1, unchanged):
    START → supervisor → [M1, M2, M3, M4, M5] → supervisor → END

when supervisor routes to M2, it invokes this sub-graph:

┌─ START_M2 ──────────────────────────────────────────────┐
│   ▼                                                      │
│   m2_familiarize ─── advance ─────►                      │
│                                m2_research_state ◀──┐    │
│                                 │ "regenerate"      │    │
│                                 ├───────────────────┘    │
│                                 │ "confirm"               │
│                                 ▼                         │
│                            m2_gap_analysis ◀────┐         │
│                                 │ "regenerate"  │         │
│                                 ├───────────────┘         │
│                                 │ "select gaps"           │
│                                 ▼                         │
│                            m2_reference_confirm ◀──┐      │
│                                 │ "verify next"    │      │
│                                 ├──────────────────┘      │
│                                 │ "all done / skip_all"   │
│                                 ▼                         │
│                            m2_output_gen                  │
│                                 │                         │
│                                 ▼                         │
│                              END_M2 ─→ outer supervisor   │
│                                                           │
│   Cross-phase jumps ("go back to research state")        │
│   handled by the shared intent classifier — emits a       │
│   conditional edge to the target phase's node.            │
└──────────────────────────────────────────────────────────┘
```

**Compilation:** the M2 sub-graph compiles lazily on first call to `get_m2_graph(interactive)`. The compiled graph is cached (per interactive/auto mode) via `functools.lru_cache`.

**Interrupts:** in interactive mode, every phase node has `interrupt_before` set so it can present output and wait for the user's next turn. In auto mode, the sub-graph compiles with `interrupt_before=[]` — each phase runs once and advances.

**Auto-mode behavior:** Phase 1 assumes no PDFs. Phase 2 generates a one-shot synthesis. Phase 3 auto-selects all candidate gaps. Phase 4 marks all references as `verified=False`. Phase 5 writes the Ch.2 draft. The sub-graph completes in a single `invoke()`.

---

## Sub-graph state model

`orchestrator/agents/m2/state.py`:

```python
class M2SubGraphState(TypedDict, total=False):
    # --- Inputs from outer state (set on entry) ---
    project_id: UUID
    thread_id: UUID
    research_title: str                  # copied from context_store.m1_topic
    research_type: Literal["quantitative", "qualitative", "mixed"]
    language: Literal["vi", "en", "bilingual"]
    paper_uris: list[str]                # interface ready; populated by SP7 later
    messages: Annotated[list[BaseMessage], add_messages]
    mode: Literal["interactive", "auto"]

    # --- Phase pointer ---
    current_phase: Literal[
        "familiarize", "research_state", "gap_analysis",
        "reference_confirm", "output_gen", "DONE"
    ]
    regeneration_count: dict[str, int]   # per-phase iteration counter, capped at 5

    # --- Phase 1: Familiarize ---
    has_uploaded_papers: bool | None

    # --- Phase 2: Research_State ---
    research_state_draft: str | None
    research_state_refinements: list[str]    # user pushback log
    research_state_confirmed: bool
    research_state_citations: list[dict]     # raw scout output, reused across regens

    # --- Phase 3: Gap_Analysis ---
    candidate_gaps: list[dict] | None        # CitedGap-shaped dicts presented to user
    gap_refinements: list[str]
    selected_gap_ids: list[str] | None       # user's picks

    # --- Phase 4: Reference_Confirm ---
    pending_page_checks: list[dict]          # PaperReference-shaped queue
    verified_refs: list[dict]
    page_check_cursor: int

    # --- Phase 5: Output_Gen ---
    ch2_draft: str | None
    citation_list: list[dict]
```

The `M2SubGraphState` is **never persisted directly** — only LangGraph's PostgresSaver checkpoints hold it. The user-visible truth lives in `context_store.m2_literature` (which the outer chat UI reads).

**Why separate from `OrchestratorState`:**
- Sub-graph evolves independently — adding `page_check_cursor` doesn't bloat the outer state.
- LangGraph 1.x optimizes field read/write tracking better with focused TypedDicts.
- Future M3/M4/M5 sub-graphs follow the same pattern.

**Thread_id convention:** the sub-graph runs under thread_id `"{outer_thread_id}::m2"`. Future M3 sub-graph uses `"::m3"`, etc. Predictable, no collisions, easy to grep for.

---

## The wrapper (`orchestrator/agents/m2/agent.py`)

Public surface stays the same — it's still a `ModuleAgent` subclass so the outer graph doesn't change. The difference is `step()` invokes the sub-graph instead of running the generic clarification loop.

```python
class M2Agent(ModuleAgent):
    schema = M2Output
    module_key = "M2"
    system_prompt = _PROMPT
    tools = [scout_citations, summarize_paper, find_research_gaps,
             compile_citations, verify_page_numbers]

    def step(self, state: OrchestratorState) -> ModuleStepResult:
        sub_state = _seed_from_outer(state)
        sub_graph = get_m2_graph(interactive=state["mode"] == "interactive")
        config = {"configurable": {"thread_id": f"{state['thread_id']}::m2"}}
        final = sub_graph.invoke(sub_state, config=config)

        if final.get("current_phase") == "DONE":
            return ModuleStepResult(
                assistant_message=f"M2 complete — {len(final.get('citation_list',[]))} citations.",
                context_patch=_flatten_to_m2_output(final),
                transition=True,
            )

        latest_msg = final["messages"][-1].content if final.get("messages") else ""
        return ModuleStepResult(
            assistant_message=latest_msg,
            context_patch=_flatten_to_m2_output(final),  # partial — no confirmed_at
            transition=False,
            needs_user_reply=True,
        )
```

`_seed_from_outer(state)` reads `state["context_store"].m1_topic.{research_title, research_type, language}` plus any existing partial work in `state["context_store"].m2_literature`. Returns a fresh `M2SubGraphState`.

`_flatten_to_m2_output(sub_state)` takes the sub-graph's final state, packs it into a `M2Output`-shape dict ready to write to `context_store.m2_literature`. Sets `confirmed_at=now` only if `current_phase == "DONE"`.

These two pure functions are the only places that know about *both* state shapes — everywhere else either reads outer state or sub-state but never both.

---

## PDF upload subsystem

Project-scoped uploads (shared across all threads of a project). Phase 1 (Familiarize) reads this list on entry; later phases use the extracted text via `summarize_paper` (Phase 2) and `verify_page_numbers` (Phase 4).

### DB schema — new Alembic migration

```python
# api/migrations/versions/20260527_add_paper_uploads.py
def upgrade():
    op.create_table(
        "paper_uploads",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("s3_uri", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("mime_type", sa.String(64), nullable=False),
        sa.Column("text_extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("text_extract_uri", sa.Text, nullable=True),   # S3 location of cached .txt
        sa.Column("page_count", sa.Integer, nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
```

### SQLAlchemy model

Append to `api/app/models.py`:

```python
class PaperUpload(Base):
    __tablename__ = "paper_uploads"
    id: Mapped[uuid.UUID] = _uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(Text, nullable=False)
    s3_uri: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    text_extract_uri: Mapped[str | None] = mapped_column(Text)
    page_count: Mapped[int | None] = mapped_column(Integer)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

### HTTP endpoints

New file `api/app/routers/uploads.py`, mounted alongside `chat.py` when `ORCHESTRATOR_ENABLED`:

```
POST   /api/v1/projects/{project_id}/uploads        multipart/form-data → 200 {upload_id, filename, size_bytes, page_count}
GET    /api/v1/projects/{project_id}/uploads        → list of {id, filename, size_bytes, mime_type, page_count, uploaded_at}
DELETE /api/v1/uploads/{upload_id}                  → 204 no content (cascades nothing; M2 sub-graph re-reads on next phase)
GET    /api/v1/uploads/{upload_id}/text             → plain text of extracted body (cached) — for debugging only
```

### Server behavior

`POST /projects/{pid}/uploads`:
1. Verify caller owns the project (existing `_owned_project` helper from `chat.py`).
2. Validate `content-type` — must be `application/pdf` or `text/plain`. Reject otherwise (415).
3. Validate size — reject if `> 50MB` (config: `M2_UPLOAD_MAX_BYTES`, default `50 * 1024 * 1024`).
4. Generate `upload_id = uuid4()`. Upload to S3 at `s3://{bucket}/users/{user_id}/projects/{project_id}/uploads/{upload_id}/{filename}` using existing `engine/s3_for_jobs.s3_from_env()`.
5. Insert `paper_uploads` row.
6. **Synchronously extract text** (small files, <50MB, expected sub-second on modern hardware). Cache extracted text at `s3://.../{upload_id}/extracted.txt`. Update row's `text_extracted_at`, `text_extract_uri`, `page_count`. If extraction fails, leave NULL — Phase 1 surfaces the warning later.
7. Return the response payload.

Synchronous extraction is acceptable for sub-project 2's scope (academic papers are typically <10MB; pdfminer extracts in <2s). If a project hits the throughput ceiling later, a background worker is a follow-up — but **not** sub-project 2's concern.

### `paper_uris` field plumbing

The wrapper's `_seed_from_outer(state)` now queries `paper_uploads` for the project and populates `M2SubGraphState["paper_uris"]` with the list of S3 URIs. Phase 1 reads this list to decide:
- Empty list → behave as "no papers, fall back to scout" (the previous deferred behavior).
- Non-empty list → fetch extracted text via existing `summarize_paper` tool; ask user *"I see you've uploaded N papers. Want me to use them as primary sources?"*

### Tests

- `api/tests/test_uploads_router.py`:
  - `test_upload_pdf_returns_id_and_extracted_text`
  - `test_upload_rejects_oversized_file`
  - `test_upload_rejects_disallowed_mime_type`
  - `test_list_uploads_returns_project_scoped`
  - `test_delete_upload_removes_row_and_s3_object`
  - `test_upload_text_endpoint_returns_extracted_body`
  - `test_pdf_with_no_extractable_text_leaves_text_extracted_at_null`
- `orchestrator/tests/test_seed_with_paper_uris.py`: asserts `_seed_from_outer` populates `paper_uris` from `paper_uploads`.

S3 mocked via `moto[s3]` (already a test dependency from sub-project 1's `api/pyproject.toml`).

---

## The 5 phase nodes

All 5 phase nodes live under `orchestrator/agents/m2/phases/`. Each has the same shape:

```python
def run(state: M2SubGraphState) -> dict:
    """Returns a state patch that LangGraph merges into the sub-graph state."""
```

The shared intent classifier (`orchestrator/agents/m2/intent.py`, extracted from sub-project 1's `supervisor.py`) is reused across phases.

### Phase 1 — `m2_familiarize`

The wrapper has already populated `paper_uris` from the `paper_uploads` table before this node runs.

- **Prompt** (`prompts/m2/1_familiarize.md`): brief greeting + acknowledges uploaded papers if any.
- **Interactive flow:**
  - **If `paper_uris` is non-empty:** post *"I see N papers uploaded: {filenames}. Use them as the primary citation source? (yes / let me upload more / use AI search instead)"*, interrupt.
  - **If `paper_uris` is empty:** post *"Do you have papers to upload? You can drag-and-drop PDFs into the chat. (upload / skip — use AI search)"*, interrupt.
  - On resume, classify user reply:
    - `confirm_use_uploaded` → set `has_uploaded_papers = True`, advance.
    - `upload_more` (only valid in interactive UI when SP7 ships) → post a hint, interrupt again. **In SP2 backend: treat as `skip` and proceed; the user uploaded outside the chat turn via the upload endpoint.**
    - `skip` → set `has_uploaded_papers = False`, advance.
- **Auto flow:** if `paper_uris` non-empty, set `has_uploaded_papers = True`; otherwise `False`. Advance.
- **Edges out:** unconditional → `m2_research_state`.

### Phase 1.5 — handling user uploads mid-conversation

If the user uploads a PDF via the upload endpoint between two chat turns, on the *next* message the wrapper re-queries `paper_uploads` before invoking the sub-graph. Phase 1 doesn't re-run automatically (we've already moved past it) — but Phase 2's first call sees the refreshed `paper_uris` and the agent's prompt acknowledges them. The user can also explicitly say *"I just uploaded more papers"* and the intent classifier routes the sub-graph back to Phase 1 for re-familiarization.

### Phase 2 — `m2_research_state`

The PRD's centerpiece. Generates a literature synthesis with in-text citations; user can ask for unlimited regenerations (capped at 5).

- **Prompt** (`prompts/m2/2_research_state.md`): *"Synthesize the current state of research on `{research_title}`. Cite specific authors and page numbers where possible. Tone: academic but readable. Constraints from user (if any): `{refinements_joined}`."*
- **Interactive flow:**
  - **First call:** invokes `scout_citations(topic, min_n=20)` → stores result in `research_state_citations` → LLM synthesizes into `research_state_draft` → posts to chat → interrupts.
  - **Resume:** classifies user reply.
    - `confirm` → set `research_state_confirmed = True`, advance.
    - `refine` → append the constraint to `research_state_refinements`, increment counter, re-invoke LLM with the cached citations + new constraint. Loop.
    - `cap_hit` (counter == 5) → assistant posts *"we've regenerated 5 times — let's lock this in or move on"*; only accepts confirm/skip.
    - `navigate` (user wants to jump back/forward) → emit a transition event the outer wrapper catches.
- **Auto flow:** one-shot generation, set `confirmed = True`, advance.
- **Edges out:** `confirm` → `m2_gap_analysis`; self-loop on `refine`; navigate-back → END_M2 with reason `user_requested_navigate`.

### Phase 3 — `m2_gap_analysis`

- **Prompt** (`prompts/m2/3_gap_analysis.md`): *"Given the synthesis below, identify 3-4 research gaps WITH supporting page-level citations. Synthesis: `{research_state_draft}`. User constraints: `{gap_refinements_joined}`."*
- **Interactive flow:**
  - First call: `find_research_gaps(citations_from_phase2)` → store as `candidate_gaps` → present numbered list in chat → interrupt.
  - Resume: classifies reply.
    - `select [1, 2, 3]` → write `selected_gap_ids`, advance.
    - `refine` (e.g. *"make them more methodological"*) → loop with refinement appended.
    - `add_custom_gap` → append user's free-text gap as a manually-confirmed `CitedGap`, then ask for re-selection.
- **Auto flow:** auto-select all candidates, advance.
- **Edges out:** `select` → `m2_reference_confirm`; self-loop on `refine` (5-cap).

### Phase 4 — `m2_reference_confirm`

Walks every page reference in `selected_gap_ids`' supporting_papers one at a time, with cursor-based queue. When uploaded PDFs are available, attempts auto-verification first; only falls back to asking the user when no source exists or the auto-check is inconclusive.

- **Prompt per page** (when auto-verify inconclusive): *"Gap N cites `{author}, {year}, page {page}`. I couldn't find this in the uploaded sources — can you verify?"*
- **Auto-verification path:** on first call, for each pending reference where a matching `paper_upload` exists (matched by author + year heuristic, then fuzzy title), call `verify_page_numbers(claim={author, year, page, quote, pdf_path=text_extract_uri})`. If result is `verified`, mark and skip user interaction. If `unverified` or `not_found`, queue for user prompting.
- **Interactive flow** (for queued unverified references):
  - First call: populates `pending_page_checks` from selected gaps; runs auto-verify on all; presents the FIRST still-unverified reference, interrupts.
  - Resume: classifies reply.
    - `confirm` → mark `verified=True`, advance cursor.
    - `correct_page <n>` → update page, mark `verified=True`, advance cursor.
    - `skip` → leave `[page?]` placeholder, advance cursor.
    - `skip_all` → mark all remaining as unverified, exit phase.
  - When cursor exhausts the queue → advance to Phase 5.
- **Auto flow:** run auto-verify; mark anything still unverified as `verified=False` (don't ask user), advance.
- **Edges out:** queue empty → `m2_output_gen`; self-loop until cursor done.

### Phase 5 — `m2_output_gen`

Single-shot — no regeneration loop here.

- **Prompt** (`prompts/m2/5_output_gen.md`): *"Write Chapter 2 (Literature Review) using the synthesis from Phase 2, the confirmed gaps from Phase 3, and the page references from Phase 4. Mark unverified pages as `[page?]`. Structure: 2.1 Theoretical Foundation, 2.2 Empirical Studies, 2.3 Research Gaps, 2.4 Theoretical Framework."*
- **Output:** writes `ch2_draft` and final `citation_list`. Sets `current_phase = "DONE"`.
- **Edges out:** END_M2.

---

## File layout

```
orchestrator/agents/m2/
├── __init__.py              # exposes M2Agent (the wrapper)
├── agent.py                 # M2Agent — wraps the sub-graph for the outer graph
├── graph.py                 # build_m2_subgraph(), get_m2_graph()
├── state.py                 # M2SubGraphState TypedDict
├── intent.py                # shared intent classifier (extracted from supervisor.py)
└── phases/
    ├── __init__.py
    ├── phase1_familiarize.py
    ├── phase2_research_state.py
    ├── phase3_gap_analysis.py
    ├── phase4_reference_confirm.py
    └── phase5_output_gen.py

orchestrator/prompts/m2/
├── _style.md                # tone + voice guidelines shared by all phases
├── 1_familiarize.md
├── 2_research_state.md
├── 3_gap_analysis.md
├── 4_reference_confirm.md
└── 5_output_gen.md

orchestrator/tests/agents/m2/
├── test_intent_classifier.py
├── test_state_translation.py
├── test_phase1_familiarize.py
├── test_phase2_research_state.py    # heaviest — regen loop, 5-cap
├── test_phase3_gap_analysis.py
├── test_phase4_reference_confirm.py # cursor walk + auto-verify
├── test_phase5_output_gen.py
├── test_m2_subgraph.py              # full sub-graph e2e
└── test_m2_agent_wrapper.py         # outer-state-in → context_store-out

api/app/routers/uploads.py           # NEW — PDF upload endpoints
api/tests/test_uploads_router.py     # NEW
api/migrations/versions/
└── 20260527_add_paper_uploads.py    # NEW — paper_uploads table

orchestrator/tests/test_seed_with_paper_uris.py   # NEW — wrapper reads uploads
```

### Deletions

- `orchestrator/agents/m2_literature.py` — its responsibility moves to `orchestrator/agents/m2/agent.py`.
- `orchestrator/prompts/m2.md` — replaced by the 5 per-phase prompts under `orchestrator/prompts/m2/`. (The `_PROMPT` constant inside the new `agent.py` keeps a high-level wrapper-level prompt for the outer graph; not the same content.)

### Imports updated

- `orchestrator/graph.py`:
  ```diff
  - from orchestrator.agents.m2_literature import M2Agent
  + from orchestrator.agents.m2 import M2Agent
  ```
- Any test that imports the old path gets updated; the public `M2Agent` name is preserved.

---

## Testing

### Per-phase unit tests (the bulk of new coverage)

Every phase node has a test file covering:
- First-call behavior (synthesis + scout, interrupt)
- Refine path (append refinement, regenerate, do not advance)
- Confirm path (advance to next phase)
- Auto mode (one-shot, advance)
- 5-cap behavior (Phase 2 & 3 only)
- Phase-specific edge cases (Phase 4 cursor; Phase 3 custom gap)

All tests use `MagicMock`-based fake LLMs + monkeypatching at module-local names — no network.

### Sub-graph end-to-end tests (`test_m2_subgraph.py`)

- `test_subgraph_walks_all_5_phases_in_auto_mode`: drives sub-graph from start to END_M2 with all phases auto-filled; asserts final state has `current_phase = "DONE"`, `ch2_draft`, non-empty `citation_list`.
- `test_subgraph_phase_2_refines_then_confirms`: interactive; sends two refine messages then a confirm; asserts `regeneration_count["research_state"] == 2` and final advances to gap_analysis.
- `test_subgraph_phase_2_cap_blocks_6th_regen`: pre-seeds counter at 5; sends another refine; asserts no regeneration happens, assistant message says lock-in.
- `test_subgraph_phase_4_walk_then_skip_all`: confirms 2 of 5 references, then `skip_all`; asserts remaining 3 are marked unverified.
- `test_subgraph_navigate_back_returns_to_outer`: mid-phase-3, user says *"go back to research state"*; asserts sub-graph emits END with `reason="user_requested_navigate"` and `current_phase` is left at `gap_analysis` (so the wrapper can re-enter at the right place).

### Wrapper integration test (`test_m2_agent_wrapper.py`)

- `test_m2_agent_completes_module_in_auto_mode`: drives the full wrapper end-to-end (sub-graph stubbed); asserts `result.transition is True` and the flattened context_patch matches `M2Output` schema.
- `test_seed_and_flatten_roundtrip`: property-style — `_flatten_to_m2_output(_seed_from_outer(s))` does not lose data for several realistic outer-state fixtures.

### Regression guards (must pass unchanged)

- `orchestrator/tests/test_agents_m2.py` (from sub-project 1) — uses the public `M2Agent` interface; should still pass.
- `orchestrator/tests/test_graph.py::test_graph_routes_to_correct_first_unconfirmed` — exercises the full M1-M5 path; M2 portion goes through the new sub-graph but produces the same shape of context_store output.
- `orchestrator/tests/integration/test_full_interactive.py` and `test_full_auto.py` — full graph integration.

### Coverage targets

- Each phase node: **80%+**
- Sub-graph e2e: **90%+**
- Wrapper: **100%**

### Multi-language

- `test_phase2_research_state_vi_output`: seeds `language="vi"`; asserts assistant message contains Vietnamese tokens.

---

## Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Nested checkpointers (outer + sub) interact badly | Medium | Distinct `thread_id`s (`"<outer>::m2"`); integration test for outer → M2 sub → outer transitions |
| 5-iteration cap arbitrary; users hit it on hard topics | Medium | Configurable via `M2_REGEN_CAP` env. Soft warning at iteration 3. `/force-continue` lifts for the next turn only. |
| Per-phase prompts drift in tone/structure | Low | `prompts/m2/_style.md` style guide; each phase prompt references it |
| `_seed_from_outer` / `_flatten_to_m2_output` drift from M2Output schema | Medium | Unit test asserts `M2Output.model_validate(_flatten_to_m2_output(complete_sub_state))` passes — fails CI if schema diverges |
| Sub-graph compile heavy at startup | Low | M2 sub-graph compiles lazily on first call; FastAPI startup only warms the outer graph |
| Phase 4 "walk every reference" feels tedious | Medium | `skip_all` quick-reply; field experience after SP7 ships tells us whether to redesign |
| State translation has subtle data loss | High | Round-trip property test for `_seed_from_outer` ↔ `_flatten_to_m2_output` |
| `scout_citations` called multiple times across regens wastes tokens | Medium | Phase 2 caches the first scout result in `research_state_citations`; regens reuse it. Only fresh scouts on `add_custom_gap` paths. |
| PDF text extraction blocks the upload request for large/complex PDFs | Medium | Cap upload at 50MB. pdfminer.six on academic papers (typically <10MB) runs in <2s. If extraction fails or times out, row is created with `text_extracted_at = NULL` and the user is told. Background extraction is a follow-up. |
| Image-only / scanned PDFs have no extractable text | High | Detect zero-bytes extraction; mark `text_extracted_at = NULL`; Phase 1 warns the user *"PDF N has no extractable text — page-reference verification won't work for it. Add OCR'd version or proceed without verification."* |
| Author/year heuristic matching upload to citation is fragile | Medium | First version uses simple fuzzy match (`rapidfuzz` against `filename`, then against extracted-text first page). Misses surface as `auto-verify inconclusive → ask user`. Improving the matcher is a follow-up. |
| Cross-thread uploads — uploads are project-scoped but two threads might compete | Low | `paper_uploads.project_id` FK with CASCADE; no per-thread isolation. Both threads see the same papers. Acceptable for SP2. |

---

## Success criteria

Sub-project 2 is done when ALL hold:

1. **Outer-graph compatibility:** every test from sub-project 1's M2 surface still passes without modification.
2. **Phase coverage:** each of the 5 phase nodes has its own test file with the unit tests outlined above; coverage targets met.
3. **Auto-mode end-to-end:** `python -m orchestrator --auto-draft …` on a fresh topic produces a `context_store.m2_literature` with `research_state_summary`, ≥1 confirmed `CitedGap`, `literature_review_doc`, and a `citation_list` — same shape as sub-project 1's auto run but generated through the 5-phase sub-graph.
4. **Interactive end-to-end:** scripted integration test drives the sub-graph through all 5 phases (with at least one regeneration in Phase 2 and one selection in Phase 3) and reaches `current_phase = "DONE"`.
5. **Regen cap works:** integration test confirms iteration 6 in Phase 2 is rejected without `/force-continue`.
6. **Navigation works:** integration test confirms mid-phase "go back to research state" returns sub-graph control to the outer wrapper with `current_module` still `M2`; subsequent invocation resumes at Phase 2.
7. **No engine regressions:** existing `engine/` tests still pass.
8. **Bilingual smoke:** one integration test with `language="vi"` asserts the assistant's chat output is Vietnamese.
9. **Upload end-to-end:** integration test uploads a real PDF fixture (with extractable text) via `POST /projects/{id}/uploads`, then runs M2 auto-mode; asserts that Phase 1 surfaces the upload, Phase 4 auto-verifies at least one reference against the extracted text, and the M2 output's `citation_list` includes the uploaded paper.
10. **Upload error handling:** integration tests confirm 415 (bad mime), 413 (oversized), 404 (not owner) responses are returned and don't create rows.

## Explicit non-commitments

- **Agent prose quality:** the phase prompts are first drafts. Tuning them is a follow-on concern.
- **Tool call efficiency:** M2 might call `scout_citations` more than needed across regens. SP2 caches the first call but doesn't deduplicate across regen iterations or threads.
- **Frontend chat UI:** still doesn't exist (SP7's job). SP2 ships an API that the existing wizard frontend won't use; exercise via `curl` + SSE stream.
- **Background PDF extraction:** synchronous on upload. If you upload 100 papers at once, that's 100 sequential extractions. Acceptable for the typical thesis workflow (5-30 papers); a job queue is a follow-up if usage demands.
- **OCR for scanned PDFs:** out of scope. Image-only PDFs work for upload but yield empty extracted text; page-reference verification falls back to asking the user.
- **PDF/A or password-protected PDFs:** not specially handled. pdfminer.six will surface a runtime error; the upload returns 422 with the error message.
