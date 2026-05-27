# SP6.5 — M5 Editor Surface Design Spec

**Date:** 2026-05-27
**Owner:** Cao Nguyen
**Parent roadmap:** `docs/superpowers/2026-05-26-platform-pivot-roadmap.md` (Sub-project 6.5 — listed under SP6 "Out of scope (deferred)")
**Depends on:** SP1 (orchestration), SP6 (M5 chapter compose + S3 export), SP7 (chat UI shell), SP2 (M2 reference pool — citation source-of-truth)
**Status:** 🟡 (designed; awaiting plan)

---

## Goal

Add a dedicated editor surface at `/chat/projects/[pid]/editor` where the user directly edits the six chapters M5 produced. The editor ships with three inline AI tools — **paraphrase**, **translate**, **cite** — that operate on text selections and present their output as **pending edits** the user accepts or rejects inline. Chat-side NL rewrites (`"rewrite chapter 3 less formal"`) route through the same pending-edit machinery instead of overwriting prose immediately.

**Explicit non-goal for SP6.5:** Citation Manager UI (style switching, Zotero/Mendeley), LaTeX / Google Docs export, real-time collaboration, slash-commands. Each lands later. Live web-search for citations is post-pivot.

---

## Locked decisions (from brainstorming)

| # | Question | Answer |
|---|---|---|
| Q1 | Scope | **C.** Full SP6.5 — editor + paraphrase + translate + cite. |
| Q2 | Surface location | **C.** Dedicated route `/chat/projects/[pid]/editor` with outline rail + sources rail. |
| Q3 | Editor library | **A.** TipTap (ProseMirror-based). |
| Q4 | Save + re-export model | **A.** Autosave-debounced (~1s) PATCH + explicit "Re-export" button. |
| Q5 | AI-edit accept/reject UX | **B.** Inline diff (strike old + highlight new) + floating ✓/✗ ribbon. Multiple pending edits stack per chapter. |
| Q6 | Cite tool UX | **A.** Popover typeahead on selection — same shape as paraphrase/translate. Corpus = M2 reference pool only. |
| Q7 | Document structure | **B.** Per-chapter TipTap doc, switched via outline rail. Six independent editor instances. |
| Q8 | Chat ↔ editor conflict policy | **C.** Chat NL-rewrites land as pending edits in editor (unified accept/reject for all four sources: paraphrase, translate, cite, chat_rewrite). |

---

## Architecture

A new editor surface lives at `/chat/projects/[pid]/editor`. It mounts six per-chapter TipTap instances backed by `context_store.m5_writing.chapters[i].prose`, switched via an outline rail. A floating selection toolbar exposes paraphrase / translate / cite — each produces a **PendingEdit** the user accepts or rejects inline. Chat-side NL rewrites route through the same machinery: instead of overwriting `prose` immediately, the rewrite is stored as a *pending diff* on the chapter and appears in the editor when the user opens it.

**Key load-bearing primitives:**

1. **`PendingEdit`** — backend schema attached to each chapter. Stores `from_offset`/`to_offset` (into chapter prose), `old_text`, `new_text`, `source` (one of `paraphrase | translate | cite | chat_rewrite`), `pending_at` timestamp, and a `metadata` dict (e.g. `{"target_lang": "vi"}` for translate). Multiple stack per chapter.

2. **TipTap custom mark `AiPending`** — visual layer for pending edits: strike-through old text + highlighted new text + floating ✓/✗ ribbon via NodeView portal. Same mark whether the source was a toolbar click or a chat rewrite.

3. **Autosave PATCH** — `PATCH /api/v1/projects/{pid}/m5/chapters/{i}` debounced ~1s; body is `{prose}`. Bibliography re-validation (regex citation check + uncited flags) runs server-side on this PATCH.

4. **Re-export button** — top of editor, shows "Last export: 2m ago · 3 edits since." Click → `POST /api/v1/projects/{pid}/m5/export` runs `compile_pdf` + `export_docx` to S3 + returns fresh signed URLs.

5. **`/editor` route gating** — route exists from project creation. Empty state ("M5 hasn't drafted yet — open chat to start") shows when `m5_writing.chapters` is empty.

The chat surface, the M5 agent's existing chapter-compose path, and the export endpoint all stay. The only behavior change to chat: `_handle_rewrite` writes to `chapters[i].pending_edits` instead of `chapters[i].prose`, and the chat bubble says "Rewrite ready — review in editor" with a link.

---

## File map

### NEW backend files

```
orchestrator/schemas/m5_editor.py                      # PendingEdit
orchestrator/tools/m5_inline.py                        # paraphrase_selection, translate_selection, validate_citation_insert
orchestrator/prompts/m5_inline/paraphrase.md           # selection-scoped LLM prompts
orchestrator/prompts/m5_inline/translate.md
orchestrator/tests/schemas/test_pending_edit.py
orchestrator/tests/tools/test_m5_inline.py
orchestrator/tests/agents/test_m5_pending_edits.py     # _handle_rewrite writes pending_edits

api/app/routers/m5_editor.py                           # PATCH /chapters/{i}, POST /pending/{eid}/accept|reject, POST /export, etc.
api/tests/test_m5_editor_router.py
api/tests/test_m5_editor_concurrency.py
api/tests/test_m5_editor_auth.py
```

### NEW frontend files

```
web/app/(chat)/chat/projects/[pid]/editor/page.tsx
web/app/(chat)/chat/projects/[pid]/editor/layout.tsx
web/app/components/editor/ThesisEditor.tsx
web/app/components/editor/ChapterEditor.tsx
web/app/components/editor/OutlineRail.tsx
web/app/components/editor/ReExportBar.tsx
web/app/components/editor/SelectionToolbar.tsx
web/app/components/editor/CitePopover.tsx
web/app/components/editor/TranslateMenu.tsx
web/app/components/editor/PendingEditRibbon.tsx
web/app/components/editor/SourcesRail.tsx
web/app/components/editor/EmptyState.tsx
web/app/components/editor/extensions/AiPending.ts      # TipTap custom mark
web/app/components/editor/extensions/CitationMark.ts   # TipTap mark for (Author, Year)
web/app/components/editor/hooks/useChapterAutosave.ts
web/app/components/editor/hooks/usePendingEdits.ts

web/app/components/editor/__tests__/
  ChapterEditor.test.tsx
  SelectionToolbar.test.tsx
  CitePopover.test.tsx
  PendingEditRibbon.test.tsx
  ReExportBar.test.tsx
  useChapterAutosave.test.ts
  editor-flow.integration.test.tsx
```

### MODIFIED backend files

```
orchestrator/schemas/m5.py                             # ChapterDraft.pending_edits: List[PendingEdit] (additive)
orchestrator/agents/m5_writing.py                      # _handle_rewrite writes pending_edits, not prose; chat bubble links to /editor
orchestrator/tools/m5_writing.py                       # validate_citations exposed as standalone for autosave re-run
api/app/routers/__init__.py                            # mount m5_editor router
```

### MODIFIED frontend files

```
web/app/components/chat/MessageBubble.tsx              # render "Open in editor" link for rewrite-result bubbles
web/app/components/chat/ChatHeader.tsx                 # "Open editor" button (visible after M5 has chapters)
```

---

## Data model

### `PendingEdit` (orchestrator-side, persisted inside ChapterDraft)

```python
class PendingEdit(BaseModel):
    id: str                                       # uuid4
    chapter_index: int                            # 0..5 (intro..conclusion)
    from_offset: int                              # char offset into chapter.prose at creation time
    to_offset: int
    old_text: str                                 # what's being replaced — must equal prose[from:to] at accept time
    new_text: str
    source: Literal["paraphrase", "translate", "cite", "chat_rewrite"]
    pending_at: datetime
    metadata: dict = {}                           # e.g. {"target_lang": "vi"} for translate
```

### Modified `ChapterDraft`

```python
class ChapterDraft(BaseModel):
    name: str
    prose: str
    citations_used: List[str] = []
    uncited_warnings: List[str] = []
    pending_edits: List[PendingEdit] = []         # NEW; defaults empty (backward-compat)
```

`pending_edits` is purely additive — existing M5Output validators and S3 export code stay untouched (pending edits never appear in exported artifacts).

---

## REST API (all under `/api/v1/projects/{pid}/m5`)

```
GET    /chapters                              → List[ChapterDraft]
GET    /chapters/{i}                          → ChapterDraft
PATCH  /chapters/{i}                          body: {prose: str}
                                              re-runs validate_citations server-side
GET    /references                            → List[ReferenceRecord]   (M2 reference pool)

POST   /chapters/{i}/paraphrase               body: {from_offset, to_offset, style?: str}
                                              → PendingEdit
                                              style is free-form (e.g. "more formal", "concise", "simpler")
POST   /chapters/{i}/translate                body: {from_offset, to_offset, target_lang: str}
                                              → PendingEdit
POST   /chapters/{i}/cite                     body: {at_offset, reference_id: str}
                                              → PendingEdit (degenerate range: from==to==at_offset,
                                              old_text="", new_text=" (Author, Year)")

POST   /chapters/{i}/pending/{eid}/accept     → ChapterDraft     (splice new_text into prose; drop edit; revalidate)
POST   /chapters/{i}/pending/{eid}/reject     → ChapterDraft     (drop edit; prose unchanged)

POST   /export                                → {pdf: ExportArtifact, docx: ExportArtifact}
                                              re-runs compile_pdf + export_docx; replaces s3_keys; fresh signed URLs
```

### Authentication + ownership

Reuse SP6's pattern: every endpoint checks `project.user_id == current_user.id`. Pending-edit endpoints additionally verify `chapter_index` matches the edit's stored `chapter_index`.

### Concurrency model

- **Autosave PATCH** is last-writer-wins. No optimistic-lock token — single-user assumption within a session.
- **Accept** is server-authoritative: validates `old_text == prose[from:to]` and returns 409 with conflict body if stale. Client renders the ribbon as "Stale — discard?"
- **Chat rewrite + editor edit** never block each other. Chat append a PendingEdit; editor saves prose. The next editor render reads both.
- **Two-tab same user** is documented as last-writer-wins for autosave; not formally synchronized.

---

## Frontend architecture

### Component tree

```
/editor/page.tsx
└── ThesisEditor
    ├── ReExportBar         (header: title, last-export status, Re-export button)
    ├── OutlineRail         (left: 6 chapter list)
    ├── ChapterEditor       (center: ONE TipTap instance for active chapter)
    │   ├── EditorContent
    │   ├── BubbleMenu → SelectionToolbar (Paraphrase · Translate · Cite)
    │   ├── CitePopover     (mounted by Cite button)
    │   ├── TranslateMenu   (mounted by Translate button)
    │   └── PendingEditRibbon[] (one per AiPending mark, via NodeView)
    └── SourcesRail         (right: read-only M2 reference list)
```

### State + API per component

| Component | Server data | Mutates server via |
|---|---|---|
| ThesisEditor | `GET /chapters` | — |
| ReExportBar | derived from `GET /chapters` (timestamps) | `POST /m5/export` |
| ChapterEditor | `GET /chapters/{i}` | `PATCH /chapters/{i}` (via hook) |
| CitePopover | `GET /references` (cached) | `POST /chapters/{i}/cite` |
| TranslateMenu | — | `POST /chapters/{i}/translate` |
| PendingEditRibbon | from AiPending mark attrs | `POST .../accept` and `.../reject` |
| SourcesRail | `GET /references` | — |
| SelectionToolbar | reads `editor.state.selection` | `POST .../paraphrase` (via parent) |

### Two custom hooks

**`useChapterAutosave(chapterIndex, prose)`** — debounces editor onChange (1000ms), PATCHes `/chapters/{i}`, exposes `{ saving, lastSavedAt, error }`.

**`usePendingEdits(chapterIndex)`** — SWR-backed; provides `acceptEdit(eid)` and `rejectEdit(eid)` that hit accept/reject endpoints and revalidate `/chapters/{i}`. ChapterEditor watches this and reconciles AiPending marks against the list.

### TipTap extensions

**`AiPending` mark** — attrs `{id, source, oldText, newText}`. Renders as `<span data-pending-id="..." class="ai-pending">{newText}</span>` with `data-old-text` for strike-through display via CSS. NodeView companion mounts `PendingEditRibbon` portal next to the marked range.

**`CitationMark` mark** — represents an inserted `(Author, Year)`. Attrs `{referenceId}`. Renders as `<span class="citation" data-ref="...">`. Hover shows tooltip with full reference; click jumps to that ref in SourcesRail.

### Inline-tool flow (end-to-end)

1. User selects text in ChapterEditor → BubbleMenu auto-appears.
2. User clicks **Paraphrase**: SelectionToolbar reads `editor.state.selection.{from, to}` → POSTs `/chapters/{i}/paraphrase` → server runs LLM → returns PendingEdit.
3. `usePendingEdits` revalidates → ChapterEditor adds `AiPending` mark with new edit's attrs → PendingEditRibbon portal mounts.
4. User clicks ✓ → `acceptEdit(eid)` → POST `/accept` → server splices `new_text` into `prose`, drops edit → hook revalidates → ChapterEditor reloads content with server prose.
5. User clicks ✗ → POST `/reject` → edit dropped, mark removed, prose untouched.

### Empty state

If `chapters` is empty when `/editor` loads → render `EmptyState` ("M5 hasn't drafted yet" + CTA to `/chat/projects/[pid]`).

---

## Edge cases + error handling

| Scenario | Behavior |
|---|---|
| Offset conflict on accept (`old_text != prose[from:to]`) | Server 409. UI shows ribbon as "Stale — this pending edit no longer matches. [Discard]" Recovery path is re-select + re-run the tool; no automatic resync. |
| Autosave + accept race | Server serialized. Accept rewrites `prose`; if debounced autosave arrives ms later with stale prose, last-writer-wins overwrites. Acceptable in single-tab/single-user. |
| Paraphrase/translate LLM failure | Toast "Paraphrase failed — try again." No partial state. |
| Network failure mid-autosave | Hook retries with exponential backoff (3 attempts, 250ms / 1s / 4s). After 3 failures: persistent banner "Failed to save — changes are local." |
| Re-export while another in flight | Re-export button disabled with "Exporting…" spinner. |
| Pending edit list grows large | "Reject all" / "Accept all" buttons appear in ChapterEditor header when `pending_edits.length >= 3`. |
| Empty M2 reference pool when Cite clicked | CitePopover shows "No references yet — go to M2 to add. [Open chat]" |
| Translate target language unset | Default `context_store.m1_topic.language`. Remember last-used in `localStorage["m5editor.targetLang"]`. |
| User navigates away with unsaved edits | `beforeunload` warning if `dirtyMap` has entries. |
| Editor opened mid-chat-draft (partial chapters) | Render what's drafted; "Drafting in progress — open chat to monitor" banner. Re-export disabled until all 6 chapters present. |
| Re-export to S3 fails | ReExportBar red status: "Export failed — last successful 12 min ago." Stale URLs still resolve. |
| Concurrent editors (2 tabs same user) | Last-writer-wins on PATCH. Documented constraint; not formally synced. |
| 401/403 on any API call | Existing auth middleware → login redirect. |
| `confirmed_at` interaction | Confirmed gates the editor's "enabled" state (alongside chapters being present). Editing after confirm is allowed; just means re-export is needed. No lock. |

---

## Testing

### Backend (pytest)

```
orchestrator/tests/schemas/test_pending_edit.py
orchestrator/tests/tools/test_m5_inline.py
orchestrator/tests/agents/test_m5_pending_edits.py
api/tests/test_m5_editor_router.py
api/tests/test_m5_editor_concurrency.py
api/tests/test_m5_editor_auth.py
```

Coverage target: 90%+ on new files (matches SP6 baseline).

### Frontend (Vitest + RTL)

```
ChapterEditor.test.tsx
SelectionToolbar.test.tsx
CitePopover.test.tsx
PendingEditRibbon.test.tsx
useChapterAutosave.test.ts
ReExportBar.test.tsx
editor-flow.integration.test.tsx          # select → Paraphrase → ribbon → accept → mark cleared
                                          # chat NL-rewrite fixture → editor opens → AiPending visible
                                          # outline switch fires autosave
```

Coverage target: 85%+ on new files.

### Not in SP6.5
- Playwright / e2e — RTL integration covers the user paths.
- Load testing of the LLM inline-tool endpoints — performance work is post-pivot.

---

## Decisions worth remembering for post-SP6.5 work

- **PendingEdit is reusable.** Any future "AI suggests, user confirms" feature (grammar fixer, expand, condense, summarize) becomes a new entry in the `source` enum + an extra endpoint. No new UI machinery needed.
- **TipTap is the editor framework going forward.** Custom marks > custom nodes > custom commands is the layered extensibility path.
- **Autosave + explicit re-export is the right split** for any artifact-producing editor: edits are cheap, exports are not.
- **Chat-as-coordinator + editor-as-canvas** is the durable separation. As more module-specific editors land (M2 reference editor, M4 outline editor, etc.), they should follow this pattern.

---

## Out of scope (deferred to later sub-projects)

- **Citation Manager UI** — style switching (APA/MLA/Chicago), Zotero/Mendeley import → SP6.6 or post-pivot
- **LaTeX / Google Docs export** → post-pivot
- **Slash commands** (`/cite`, `/translate`, `/explain`) → post-pivot
- **Real-time multi-user collaboration** → post-pivot (PRD Phase 4-ish)
- **Live web-search for new citations** → post-pivot
- **AI-assisted style consistency check** (cross-chapter tone audit) → post-pivot
- **Editor-side undo/redo history beyond TipTap's built-in** (long-form revision history with named checkpoints) → post-pivot
- **Mobile responsive editor** — desktop-first for SP6.5; mobile is post-pivot

---

## Status log entry (to add when SP6.5 ships)

`| 2026-MM-DD | 6.5 | ⬜ → ✅ | M5 editor surface shipped — TipTap WYSIWYG + 3 inline AI tools + unified pending-edit accept/reject |`
