# Five-chapter thesis: collapse Discussion + Conclusion into Chapter 5

Date: 2026-09-04
Status: approved, ready for implementation plan

## Problem

The product answers "how many chapters does a thesis have?" two different ways,
and which answer a student gets depends on which export path they happen to hit.

`orchestrator/tools/m5_writing.py:1854` declares a **six**-chapter thesis:

```python
M5_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]
M5_CHAPTER_TITLES = {..., "discussion": "Chapter 5 — Discussion",
                          "conclusion": "Chapter 6 — Conclusion"}
```

`orchestrator/tools/compose_export.py:42` then patches that back to five at
export time (`wants_merged_conclusion`), by **dropping the `conclusion` prose**
and relabelling `discussion` to "Chương 5 — Kết luận".

That patch runs on only two of the five export paths:

| Path | Merges? | Ships |
|---|---|---|
| `compose_export.compose_and_export` (interactive) | yes | 5 chapters |
| `api/app/partner_run.py:234` (partner API) | yes (always) | 5 chapters |
| `api/app/agent_state.py:479` (auto-export hook) | **no** | 6 chapters |
| `agent/tools/writing.py` (agent export tool) | **no** | 6 chapters |
| `api/app/routers/m5_editor.py:701` (editor export) | **no** | 6 chapters |

So auto-mode and the editor still hand a Vietnamese student a Chapter 6 their
supervisor never asked for. Per
`memory/project_headless_surfaces.md`, the three generation surfaces must not
diverge; this is exactly that divergence.

### Why five is correct

Vietnamese quantitative theses (business/economics, bachelor's and master's) use
five chapters: Introduction, Literature Review, Methodology, Results,
Conclusions and Recommendations. The discussion of findings is written *inside*
the final chapter, not as a chapter of its own. Confirmed against Vietnamese
university guidance (Cần Thơ, TDTU, HCMUTE templates) and against the reference
thesis the owner supplied, which ends at
`CHAPTER 5: CONCLUSIONS AND RECOMMENDATIONS`.

### The two composers are ~80% redundant

`prompts/m5/discussion.md` already emits the whole final-chapter structure:

| `discussion.md` | Reference thesis Ch5 |
|---|---|
| 5.1 Summary of findings | 5.1 Summary of Key Findings |
| 5.2 Discussion of findings | (inside 5.1/5.2) |
| 5.3 Theoretical contributions | 5.2 Theoretical Contributions |
| 5.4 Practical implications | 5.3 Practical Implications and Recommendations |
| 5.5 Limitations (`[[DT:limitations]]`) | 5.4 Limitations of the Study |
| 5.6 Suggestions for future research | 5.5 Directions for Future Research |
| — | 5.6 Concluding Remarks |

`prompts/m5/conclusion.md` emits 6.1 restatement of objectives, 6.2 key
conclusions per RQ, 6.3 significance, 6.4 closing remarks. 6.2 restates 5.1 and
6.3 restates 5.3. **Closing remarks is the only content Chapter 6 owns.**

Therefore concatenating both prose blocks as subsections would summarise the
findings twice and state the contributions twice. The merge that drops
`conclusion` is discarding redundancy, not substance — but it discards it at
export time, invisibly, on some paths only.

## Design

Delete the sixth chapter from the **canonical structure**, so no path can emit
it and no merge step is needed.

### 1. Canonical key is `conclusion`, not `discussion`

The final chapter's key becomes `conclusion` and `discussion` is retired.

This direction is forced by the import paths, which already write the student's
own final chapter under `conclusion`:

- `api/app/import_work.py:290` — `{"chapter_name": "conclusion", "source": "import", ...}`
- `agent/tools/backfill_tool.py` — same, with the comment *"'conclusion' rather
  than 'discussion': the heading this splits on is the thesis's FINAL chapter
  (KẾT LUẬN VÀ KHUYẾN NGHỊ)"*

An imported thesis and a composed thesis must land the same chapter in the same
slot. Today they do not, which is the root of the drift.

New constants:

```python
M5_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "conclusion"]
M5_CHAPTER_TITLES  = {..., "conclusion": "Chapter 5 — Conclusions and Recommendations"}
M5_CHAPTER_TITLES_VI = {..., "conclusion": "Chương 5 — Kết luận và Kiến nghị"}
MODULE_CHAPTERS = {..., "M5": ["conclusion"]}
```

Title wording follows the owner's reference thesis: *Recommendations* = *Kiến
nghị*. (*Hàm ý* = *Implications*, which belongs at subsection level — `5.3` —
not in the chapter title.)

### 2. The conclusion composer keeps the good structure

`prompts/m5/conclusion.md` is rewritten to carry `discussion.md`'s 5.1–5.6
structure plus a closing-remarks section, absorbing the only unique content the
old Chapter 6 had. `prompts/m5/discussion.md` is deleted. Word budget rises to
the discussion composer's 1200–2000 (the old conclusion's 500–800 is a chapter
appendix, not a chapter).

Sections: 5.1 Summary of findings · 5.2 Discussion of findings · 5.3
Theoretical contributions · 5.4 Practical implications and recommendations ·
5.5 Limitations (`[[DT:limitations]]`, preserved verbatim — it renders the real
flagged weaknesses from state) · 5.6 Future research · 5.7 Concluding remarks.

### 3. The merge machinery is deleted, not rewired

`wants_merged_conclusion()`, `merged_chapter_keys()` and the `merge_conclusion`
parameter of `compose_sections()` all go. With one final chapter in the
canonical order, every path emits five chapters by construction — the three
non-merging paths are fixed by deletion rather than by adding a fourth and fifth
call site that must remember to merge.

`api/app/partner_run.py:234` drops its `merge_conclusion=True` argument.
`ANALYSIS_CHAPTERS` (`partner_run.py:40`) loses `"discussion"`.

### 4. Legacy prose must survive

Projects composed before this change hold their final-chapter prose under
`discussion`. Reads alias `discussion` → `conclusion` so that prose still
surfaces; a project holding **both** keeps `conclusion` and drops the redundant
`discussion` (matching what the export already did).

The alias belongs in the functions that map stored state onto canonical
chapters, so every caller inherits it:

- `m5_writing.chapters_from_final_sections()`
- `m5_writing.sections_from_m5_slice()`
- `orchestrator/artifacts.py::_m5_chapter_prose()`

Per `memory/project_db_store_persistence_gap.md`, whatever the editor writes
back must round-trip through `DbProjectStateStore`; the change adds no new
context_store key, so no store work is expected — to be confirmed, not assumed.

### 5. Coherence checks follow the key

`agent/coherence.py` reads `chapters.get("discussion")` at lines 576, 630 and
731, and `_RESULT_CHAPTERS` (line 26) lists it. These are real quality checks
(e.g. `traceability.discussion_uncited` — every hypothesis discussed must cite
its literature). Left alone they would silently never fire again, which is the
failure mode this spec exists to remove. They switch to `conclusion`.

Same for `orchestrator/tools/results_render.py:684-695` (`_RENDERABLE_CHAPTERS`
and its keyword map, which routes "thảo luận"/"hạn chế" to a chapter key) and
`agent/feedback.py:18` (the chapter-classification prompt's allowed values).

### 6. Roadmap loses a step

`agent/roadmap.py:29` becomes `"M5": ["write_conclusion", "export"]`;
`write_discussion` disappears from `SUBSTEP_LABELS` and `SUBSTEP_ARTIFACT`
(`final_sections` now backs `write_conclusion`).

`orchestrator/artifacts.py` drops the `ch_discussion` artifact. `ch_conclusion`
inherits `ch_discussion`'s dependencies:

```python
Artifact("ch_discussion", …, ("ch_results", "topic"),       dod_chapter("discussion"))   # deleted
Artifact("ch_conclusion", …, ("ch_discussion", "analysis"), dod_chapter("conclusion"))   # was
Artifact("ch_conclusion", …, ("ch_results", "topic"),       dod_chapter("conclusion"))   # becomes
```

`"analysis"` is dropped from the explicit tuple deliberately, not by oversight:
`ch_results` already declares `("analysis",)` (line 284), so analysis stays
reachable transitively and listing it again would be redundant. The registry
test that validates `depends_on` against artifact keys is the guard.

`_M5_CLOSING_CHAPTERS` collapses to a single name, and `dod_writing`'s "no
discussion or conclusion chapter yet" gap message becomes "no conclusion chapter
yet".

### 7. Schemas and validation

`orchestrator/schemas/m5.py:10,46` and `orchestrator/schemas/m5_editor.py:21`
hardcode the six-name `Literal`. Both drop `"discussion"`.
`api/app/routers/m5_editor.py:72` holds a third copy as `_VALID_CHAPTER_NAMES`
(a `set`, used to validate the autosave PATCH route) — it drops `"discussion"`
too. Three hand-maintained copies of `M5_CHAPTER_ORDER` is how the six/five
split survived this long; a test asserting each copy equals the canonical order
is cheaper than a fourth copy and is added here.

`chapter_split.py` needs **no change**: its `_FINAL_CHAPTER_RE` already accepts
chapters 5–9 precisely so it can find the final chapter whatever its number, and
it maps to `conclusion` already.

## Out of scope

`engine/` runs an independent legacy pipeline that numbers Discussion and
Conclusion as *sections* (`## 2.4 Discussion`), not chapters, so it emits no
"Chapter 6" heading. Untouched here; worth a follow-up read to confirm its
assembled output does not contradict the five-chapter shape.

## Testing

TDD per repo convention. API tests run through `./run.sh`, never
`api/.venv/bin/*` directly (`memory/project_venv_arm64_wrapper.md` — the Claude
shell is x86_64, the venv is arm64).

Tests to update or add:

- `orchestrator/tests/test_module_chapters.py` — asserts `MODULE_CHAPTERS["M5"]
  == ["discussion", "conclusion"]`; becomes `["conclusion"]`.
- `orchestrator/tests/test_chapter_structure.py`, `test_schemas.py`,
  `test_artifacts.py`, `test_planner.py`.
- `api/tests/test_compose_export.py` — the merge tests it covers are being
  deleted; replace with a test that **every** export path emits exactly five
  chapters with no "Chapter 6"/"Chương 6" heading.
- `api/tests/test_auto_export_completeness.py`, `test_partner_run.py`,
  `test_partner_report.py`, `test_m5_editor_router.py`,
  `agent/tests/test_export_completeness.py`, `test_roadmap.py`,
  `test_coherence.py`.
- New: a legacy-alias test — a stored slice with prose only under `discussion`
  still exports a Chapter 5 with that prose.

Web vitest has ~30 pre-existing failures; baseline with a stash before
attributing any failure to this change
(`memory/project_web_vitest_broken.md`). Web surfaces to check:
`OutlineRail.tsx`, `ContextPanel.tsx`, `ModuleSlices.tsx`,
`QuickActionsMenu.tsx`, `ChatPane.tsx:112` (a comment naming the pair).

## Risks

1. **Silently dead checks.** The coherence and results-render keyword maps fail
   open — a stale `"discussion"` key means the check never fires and nothing
   logs. Grep for the literal string across `.py`/`.ts`/`.tsx`/`.md` at the end
   and account for every remaining hit.
2. **In-flight projects.** A student mid-M5 has prose under `discussion`.
   Covered by the §4 alias; the legacy-alias test is the guard.
3. **Prompt regression.** The rewritten `conclusion.md` must keep
   `[[DT:limitations]]` on its own line, or real flagged weaknesses stop being
   disclosed at export.
