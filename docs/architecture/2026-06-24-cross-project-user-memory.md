# Cross-Project User Memory — Implementation Plan

- **Date:** 2026-06-24
- **Status:** Phase 0 IMPLEMENTED (2026-06-25) — table `user_memory`, whitelist
  helper `api/app/user_memory.py`, capture on project create, `POST /me/prefs`
  endpoint, and `/new` form pre-fill (Field/Language/Citation). Migration
  `20260625_usermem01`. Phases 1–2 still proposed.
- **Author:** drafted with agent assistance for @caobo171
- **Scope:** Add a per-user memory layer so a returning user does not start every
  new thesis project from zero. Carries *preferences and meta-patterns* across
  that user's projects.

---

## 1. Goal & Non-Goals

### Goal
Give DoThesis a 4th memory tier, **per-user**, that sits above the existing
per-project `context_store`. When a user who already finished projects starts a
new one, the agent should already know their durable preferences (language,
citation style, research approach, discipline, presentation style) and pre-fill
the `/new` form + bias early guidance accordingly.

### Non-Goals (hard boundaries)
- **NOT** a place to store thesis *content* (literature sources, statistics,
  hypotheses, chapter text, findings). See §3.
- **NOT** semantic/RAG retrieval in v1 (deferred to Phase 2, likely unnecessary).
- **NOT** cross-*user* sharing. Strictly scoped to one `user_id`.

---

## 2. Current Memory Architecture (as-is)

DoThesis today has three memory tiers:

| Tier | Where | Scope | Key |
|---|---|---|---|
| Project | `context_store` table (5 JSONB slices m1–m5) | per project | `project_id` (PK, FK→projects) |
| Thread | `messages` table | per chat thread | `thread_id` |
| User | only `users.credit` exists | per user | `users.id` |

**There is no general per-user memory table today.** That is the gap.

Key files (verified):
- `api/app/models.py` — `User` (L25–37), `Project` (L188–218, `user_id` FK),
  `ContextStore` (L323–337), `VersionHistory` (L303–321).
- `orchestrator/state.py` — `ContextStore` pydantic model (L22–39),
  `get_module_slice()` (L129–137), `SLICE_OWNERSHIP` / `READS` whitelists.
- `orchestrator/loader.py` — `load_state(project_id, thread_id, *, db)` (L72–144):
  the single place a turn loads project state from DB.
- `agent/runtime.py` — `_state_header()` (L448–462) injects the `[PROJECT STATE]`
  line into the system prompt every turn; `stream_turn()` (L465+).
- `api/app/agent_state.py` — `DbProjectStateStore._save()` (L104–148): write path.
- `agent/state.py` — `commit_slice()` (L142–218): validates ownership, snapshots
  version history, marks status, persists. `confirm_done=True` = module finalized.

---

## 3. Critical Constraint — Anti-Fabrication

DoThesis has an anti-fabrication invariant: literature/sources/stats must come
from the toolchain, never from model memory. A naive cross-project memory would
let content from thesis A leak into thesis B → **fabrication**.

**Rule:** user memory stores **preferences + meta-patterns only**, enforced by a
hard whitelist (mirroring how `SLICE_OWNERSHIP` whitelists slice keys).

### Allowed keys (typed, whitelisted)
| Key | Type | Example | Source |
|---|---|---|---|
| `language` | enum | `"vi"` / `"en"` | project field |
| `citation_style` | enum | `"APA7"` | project field |
| `research_approach` | enum | `"quantitative"` | project field |
| `field` | string (short) | `"Marketing"` | project field |
| `education_level` | enum | `"undergrad"` / `"master"` | inferred (Phase 1) |
| `writing_formality` | enum | `"formal"` | inferred (Phase 1) |
| `option_presentation` | enum | `"concise"` / `"detailed"` | inferred (Phase 1) |
| `auto_approve_default` | bool | `true` | UI setting |

### Forbidden (never persisted to user memory)
`literature_sources`, `research_gaps`, `analysis_results`, `hypotheses`,
`conceptual_model`, `final_sections`, any chapter/finding text, any DOI/citation,
any numeric result. A write attempting a non-whitelisted key is **rejected**, not
silently dropped (raise + log), so regressions are loud.

---

## 4. Proposed Design — 4th Tier `user_memory`

### 4.1 Schema (new table)
```python
# api/app/models.py  (new model, after CreditTransaction ~L166)
class UserMemory(Base):
    __tablename__ = "user_memory"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,          # one row per user (1:1)
    )
    prefs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # prefs shape: { key: {value, source_project_id, confidence, updated_at} }
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
```
Each pref carries **provenance** (which project it came from + when + confidence)
so it is auditable and so Phase-1 inferred prefs can be distinguished from
deterministic ones.

### 4.2 Migration
`api/migrations/versions/2026MMDD_user_memory.py` — create `user_memory` table,
FK to `users` with CASCADE. No backfill needed (empty = no prefs yet).

### 4.3 Memory whitelist module
New `api/app/user_memory.py` (or `orchestrator/user_memory.py`):
```python
USER_MEMORY_KEYS = {
    "language", "citation_style", "research_approach", "field",
    "education_level", "writing_formality", "option_presentation",
    "auto_approve_default",
}

def load_user_prefs(user_id, *, db) -> dict: ...        # {} if no row
def write_user_prefs(user_id, updates: dict, *, source_project_id, db) -> None:
    # reject any key not in USER_MEMORY_KEYS (raise ValueError)
    # upsert row, merge per-key with provenance, bump updated_at
```

---

## 5. Integration Points

### 5.1 Read path
- `orchestrator/loader.load_state()` — load `user_memory` alongside `context_store`
  (one extra cheap SELECT by `user_id`, available from the project row).
- `agent/runtime.py` — add `_user_prefs_header()` sibling to `_state_header()`,
  injecting a clearly-labelled block:
  ```
  [USER PREFERENCES] (preferences, NOT facts — do not cite or treat as data)
  language=vi | citation=APA7 | approach=quantitative | field=Marketing
  ```
  Labelled explicitly so the model never mistakes prefs for evidence.

### 5.2 Write path
- **Deterministic (Phase 0):** when a project is created/updated with
  `field / language / citation_style / research_approach`, call
  `write_user_prefs(...)` with `source_project_id`. Hook in the project-create
  route (`api/app/routers/` project endpoint) and/or `commit_slice` M1 confirm.
- **Inferred (Phase 1):** a cheap LLM "preference extractor" runs **only on
  `confirm_done`** (module finalize) or project completion — never per turn — to
  distill soft prefs (formality, option style). Cost-bounded by trigger frequency.

### 5.3 `/new` form pre-fill
- API: expose `GET`-style (POST per convention) endpoint returning `load_user_prefs`.
- Web: `web/app/(inapp)/new/page.tsx` reads prefs and pre-fills
  field/language/citation_style/research_approach defaults (user can override).

---

## 6. Phased Rollout

### Phase 0 — Deterministic preferences (BUILD FIRST)
- New table + migration + `user_memory.py` whitelist module.
- Capture field/language/citation_style/research_approach on project create.
- Pre-fill `/new` form.
- **Value:** returning users stop re-entering the same setup. Zero fabrication
  risk, zero LLM cost.
- **Touch:** 1 model + 1 migration + 1 helper module + loader read + 1 route +
  `/new` page. ~Half a day.

### Phase 1 — LLM-distilled soft preferences
- Preference extractor (cheap model, e.g. haiku/flash) on `confirm_done`.
- Inject `[USER PREFERENCES]` header into runtime.
- Provenance + confidence per entry; audit log.

### Phase 2 — Semantic retrieval (only if needed)
- Likely unnecessary for a bounded preference set. Revisit if prefs grow
  open-ended.

---

## 7. Privacy, Safety, Testing

- **Whitelist test:** writing a forbidden key (e.g. `literature_sources`) must
  raise, not persist. Unit test this explicitly.
- **Isolation test:** user A's prefs never load for user B.
- **Fabrication regression:** a project whose user-prefs say `field=Marketing`
  must still NOT inject any Marketing citations into M2 — prefs bias *framing*,
  never supply *evidence*. Add an assertion in the M2 grounding test.
- **Cascade:** deleting a user cascades `user_memory` (FK ondelete=CASCADE).
- **Opt-out:** consider a `users` flag or account setting to disable memory.

---

## 8. File-by-file change list (Phase 0)

| File | Change |
|---|---|
| `api/app/models.py` | add `UserMemory` model |
| `api/migrations/versions/2026MMDD_user_memory.py` | create table |
| `api/app/user_memory.py` (new) | whitelist + load/write helpers |
| `orchestrator/loader.py` | load prefs in `load_state` |
| `api/app/routers/<projects>.py` | capture prefs on project create |
| `api/app/routers/<account or new>.py` | endpoint returning prefs for `/new` |
| `web/app/(inapp)/new/page.tsx` | pre-fill form from prefs |
| tests | whitelist-reject + isolation + fabrication-regression |

---

## 9. Open Questions
1. 1:1 (`user_id` PK) vs 1:many entries with history? → Start 1:1 JSONB; provenance
   lives inside each key. Revisit if we need full pref history.
2. Capture prefs on project *create* only, or also reconcile when user changes a
   project mid-way? → Phase 0: create only. Phase 1: also on M1 confirm.
3. Should `/new` pre-fill be silent or shown as "from your last project"? →
   Recommend a subtle "Restored from your preferences" hint with a reset link.
