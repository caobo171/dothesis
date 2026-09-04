# Five-Chapter Thesis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the sixth chapter from the thesis structure so every export path emits exactly five chapters, ending at "Chương 5 — Kết luận và Kiến nghị".

**Architecture:** The canonical chapter list (`M5_CHAPTER_ORDER`) currently declares six chapters, and `compose_export.wants_merged_conclusion()` patches it back to five at export time — on only 2 of the 5 export paths. We remove `discussion` from the canonical order entirely and make `conclusion` the single final chapter, then delete the merge machinery. Five chapters then hold by construction, not by every caller remembering to merge.

**Tech Stack:** Python 3 (FastAPI, Pydantic, pytest), TypeScript/React (Next.js, vitest).

**Spec:** `docs/superpowers/specs/2026-09-04-five-chapter-thesis-design.md`

## Global Constraints

- Canonical final-chapter key is **`conclusion`**. `discussion` is retired as a canonical name. Both import paths already write the student's final chapter under `conclusion` (`api/app/import_work.py:290`, `agent/tools/backfill_tool.py`), so this direction is forced.
- Chapter 5 titles, exact strings: EN `"Chapter 5 — Conclusions and Recommendations"`, VI `"Chương 5 — Kết luận và Kiến nghị"`. The dash is an em-dash `—`, matching every other title in the map.
- Reads must alias legacy `discussion` prose onto `conclusion` so in-flight projects do not lose written chapters. When a slice has **both**, `conclusion` wins.
- `[[DT:limitations]]` must stay on its own line in the conclusion prompt — it renders real flagged weaknesses from state. Losing it silently stops limitation disclosure.
- Python tests run from `api/` via the arm64 wrapper: `cd api && ./run.sh pytest <path> -q`. Never call `api/.venv/bin/pytest` directly (the Claude shell is x86_64; the venv is arm64).
- Web vitest has ~30 pre-existing failures. Baseline with `git stash` before attributing any failure to this change.
- Per repo convention (`CLAUDE.md`): all new endpoints are POST. This plan adds no endpoints.
- Comment the reasoning behind each change, not just the what — this repo's existing comments explain *why* a line exists, and the new ones must match that density.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `orchestrator/tools/m5_writing.py` | canonical order, titles, module ownership, slice→section mapping | Modify (~1854-1996) |
| `orchestrator/tools/compose_export.py` | subset compose + export hand-off | Modify — delete merge machinery |
| `orchestrator/prompts/m5/conclusion.md` | final-chapter composer prompt | Rewrite |
| `orchestrator/prompts/m5/discussion.md` | old Ch5 composer prompt | Delete |
| `orchestrator/prompts/m5.md` | M5 skill chapter list | Modify |
| `orchestrator/artifacts.py` | artifact DAG + DoD gates | Modify |
| `orchestrator/schemas/m5.py`, `m5_editor.py` | chapter-name Literals | Modify |
| `agent/roadmap.py` | M5 coaching spine | Modify |
| `agent/coherence.py` | quality checks keyed on chapter | Modify |
| `agent/feedback.py` | chapter-classification prompt | Modify |
| `agent/tools/writing.py` | agent export tool | Modify |
| `orchestrator/tools/results_render.py` | title→chapter keyword map | Modify |
| `api/app/partner_run.py` | partner chapter scope | Modify |
| `api/app/routers/m5_editor.py` | autosave validation + export | Modify |
| `web/app/components/editor/OutlineRail.tsx` + siblings | chapter rail UI | Modify |

---

### Task 1: Canonical constants collapse to five chapters

**Files:**
- Modify: `orchestrator/tools/m5_writing.py:1850-1906` (constants), `:1913-1952` (`chapters_from_final_sections`), `:1955-1996` (`sections_from_m5_slice`)
- Test: `orchestrator/tests/test_module_chapters.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `M5_CHAPTER_ORDER == ["intro","lit_review","methodology","results","conclusion"]`; `M5_CHAPTER_TITLES["conclusion"] == "Chapter 5 — Conclusions and Recommendations"`; `M5_CHAPTER_TITLES_VI["conclusion"] == "Chương 5 — Kết luận và Kiến nghị"`; `MODULE_CHAPTERS["M5"] == ["conclusion"]`; `LEGACY_CHAPTER_ALIASES == {"discussion": "conclusion"}`. Every later task depends on these exact names.

- [ ] **Step 1: Write the failing tests**

Replace `test_m5_owns_discussion_and_conclusion` and `test_module_for_chapter_reverse_lookup` in `orchestrator/tests/test_module_chapters.py`, and add the alias tests:

```python
def test_m5_owns_the_single_conclusion_chapter():
    # Vietnamese quantitative theses end at Chapter 5; the discussion of
    # findings is written INSIDE that chapter, not as a chapter of its own.
    assert M.MODULE_CHAPTERS["M5"] == ["conclusion"]
    assert M.chapters_for_module("M1") == ["intro"]
    assert M.chapters_for_module("m4") == ["results"]  # case-insensitive
    assert M.chapters_for_module("nope") == []


def test_canonical_order_has_five_chapters_ending_at_conclusion():
    assert M.M5_CHAPTER_ORDER == [
        "intro", "lit_review", "methodology", "results", "conclusion"]
    assert "discussion" not in M.M5_CHAPTER_ORDER


def test_chapter_five_titles_say_conclusions_and_recommendations():
    assert M.M5_CHAPTER_TITLES["conclusion"] == "Chapter 5 — Conclusions and Recommendations"
    assert M.M5_CHAPTER_TITLES_VI["conclusion"] == "Chương 5 — Kết luận và Kiến nghị"
    # No title anywhere may still say "6".
    for mapping in (M.M5_CHAPTER_TITLES, M.M5_CHAPTER_TITLES_VI):
        assert not any("6" in t for t in mapping.values())


def test_module_for_chapter_reverse_lookup():
    assert M.module_for_chapter("intro") == "M1"
    assert M.module_for_chapter("conclusion") == "M5"
    assert M.module_for_chapter("unknown") is None


def test_legacy_discussion_prose_is_read_as_the_conclusion_chapter():
    # A project composed before the five-chapter collapse holds its final
    # chapter under `discussion`. Dropping it would delete written work.
    out = M.chapters_from_final_sections(
        [{"chapter_name": "discussion", "prose": "Legacy final chapter."}])
    assert out["conclusion"]["prose"] == "Legacy final chapter."
    assert "discussion" not in out


def test_conclusion_wins_when_a_slice_carries_both():
    out = M.chapters_from_final_sections([
        {"chapter_name": "discussion", "prose": "Old discussion."},
        {"chapter_name": "conclusion", "prose": "Real conclusion."},
    ])
    assert out["conclusion"]["prose"] == "Real conclusion."


def test_sections_from_m5_slice_aliases_legacy_discussion():
    out = M.sections_from_m5_slice(
        {"chapters": {"discussion": {"prose": "Legacy final chapter."}}})
    assert [s["chapter_name"] for s in out] == ["conclusion"]
    assert out[0]["title"] == "Chapter 5 — Conclusions and Recommendations"
```

Also update `test_compose_module_chapters_shapes_and_filters` — M5 now owns one chapter:

```python
def test_compose_module_chapters_shapes_and_filters(monkeypatch):
    # Stub composition: M5 owns [conclusion]; compose_all_sections returns it
    # plus a References section that must be filtered out.
    def fake_compose(cs, chapters=None):
        assert chapters == ["conclusion"]
        return [
            {"chapter_name": "conclusion", "title": "Ch5", "prose": "Conclusion prose."},
            {"title": "References", "prose": "[1] Smith 2024"},  # no chapter_name
        ]
    monkeypatch.setattr(M, "compose_all_sections", fake_compose)

    out = M.compose_module_chapters({"m1_topic": {}}, "M5")
    assert set(out) == {"conclusion"}
    assert out["conclusion"] == {"name": "conclusion", "prose": "Conclusion prose."}
    assert "References" not in out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_module_chapters.py -q`
Expected: FAIL — `MODULE_CHAPTERS["M5"]` is still `["discussion", "conclusion"]`, and `chapters_from_final_sections` has no alias.

- [ ] **Step 3: Collapse the constants**

In `orchestrator/tools/m5_writing.py`, replace lines 1850-1893:

```python
# Canonical 5-chapter order + display titles, shared by every caller that
# turns an m5_writing slice into exporter sections (the auto-export hook in
# api/app/agent_state.py, the /m5/export route, and the agent's export tool).
# One source of truth so the paths can't drift.
#
# FIVE, not six. A Vietnamese quantitative thesis ends at "Chương 5 — Kết luận
# và Kiến nghị" and writes the discussion of findings INSIDE it (5.1 summary,
# 5.2 discussion, 5.3 contributions, ...). The order used to declare a separate
# `discussion` chapter and compose_export patched it back to five at export
# time — but only on 2 of the 5 export paths, so auto-mode and the editor
# shipped a Chapter 6 no supervisor asked for. Removing the chapter from the
# canonical order is what makes five hold everywhere by construction.
M5_CHAPTER_ORDER = ["intro", "lit_review", "methodology", "results", "conclusion"]
M5_CHAPTER_TITLES = {
    "intro":       "Chapter 1 — Introduction",
    "lit_review":  "Chapter 2 — Literature Review",
    "methodology": "Chapter 3 — Methodology",
    "results":     "Chapter 4 — Results",
    "conclusion":  "Chapter 5 — Conclusions and Recommendations",
}
# Vietnamese chapter titles — the document language must be consistent, so the
# headings match the (Vietnamese) chapter prose instead of staying English.
# "Kiến nghị" (Recommendations), not "Hàm ý" (Implications): implications sit at
# subsection level (5.3), not in the chapter title.
M5_CHAPTER_TITLES_VI = {
    "intro":       "Chương 1 — Giới thiệu",
    "lit_review":  "Chương 2 — Tổng quan tài liệu",
    "methodology": "Chương 3 — Phương pháp nghiên cứu",
    "results":     "Chương 4 — Kết quả",
    "conclusion":  "Chương 5 — Kết luận và Kiến nghị",
}
# Chapter names that no longer exist canonically, mapped to the one that
# replaced them. Projects composed before the five-chapter collapse hold their
# final chapter under `discussion`; reads alias it forward so a student
# mid-thesis does not lose a written chapter. Writes only ever use canonical
# names, so this never grows a second direction.
LEGACY_CHAPTER_ALIASES = {"discussion": "conclusion"}
_REFERENCES_TITLE = {"vi": "Tài liệu tham khảo", "en": "References"}


def _chapter_titles(language: str) -> dict:
    """Chapter-title map matching the prose language (vi → Vietnamese)."""
    return M5_CHAPTER_TITLES_VI if str(language).lower().startswith("vi") else M5_CHAPTER_TITLES


def canonical_chapter(name: str | None) -> str | None:
    """Canonical chapter key for `name`, resolving retired aliases.

    Returns None for anything that is not a chapter, so callers can use it as
    the single "is this a chapter, and which one" test instead of each
    re-implementing the alias rule.
    """
    if not name:
        return None
    key = str(name).strip()
    key = LEGACY_CHAPTER_ALIASES.get(key, key)
    return key if key in M5_CHAPTER_ORDER else None


# Which canonical chapters each module OWNS. This is the pivot from "M5 writes
# the whole thesis" to "every module composes its own chapter as it completes":
# M1–M4 map 1:1 to Chapters 1–4, and M5 owns the closing chapter. Single source
# of truth for per-module composition and the module→chapter mapping the
# export/UI share. Keep consistent with M5_CHAPTER_ORDER — every chapter must be
# owned by exactly one module.
MODULE_CHAPTERS = {
    "M1": ["intro"],
    "M2": ["lit_review"],
    "M3": ["methodology"],
    "M4": ["results"],
    "M5": ["conclusion"],
}
```

Delete the now-duplicated `_REFERENCES_TITLE` / `_chapter_titles` definitions that followed the old block (lines 1873-1878), since they are reproduced above.

- [ ] **Step 4: Alias legacy prose in the two read paths**

In `chapters_from_final_sections` (~line 1936), replace the canonical-name resolution:

```python
        name = canonical_chapter(sec.get("chapter_name"))
        if name is None:
            title = (sec.get("title") or sec.get("name") or "").strip().lower()
            name = canonical_chapter(title_to_name.get(title))
        if name is None:
            continue
```

and make `conclusion` win over an aliased `discussion` when both are present — insert before `out[name] = ...`:

```python
        # A slice carrying BOTH a legacy `discussion` and a real `conclusion`
        # must keep the conclusion: the alias exists to rescue old prose, not
        # to overwrite new. Order in final_sections is not guaranteed, so this
        # cannot rely on the loop reaching them in a particular sequence.
        if name in out and sec.get("chapter_name") != name:
            continue
```

In `sections_from_m5_slice` (~line 1965), resolve stored keys through the alias:

```python
    chapters = (m5_slice or {}).get("chapters") or {}
    if chapters:
        # Resolve stored keys through the alias FIRST so a legacy `discussion`
        # entry lands in the `conclusion` slot; a real `conclusion` already in
        # the dict wins (setdefault would let the alias overwrite it).
        resolved: dict = {}
        for stored_name, ch in chapters.items():
            name = canonical_chapter(stored_name)
            if name is None:
                continue
            if name in resolved and stored_name != name:
                continue
            resolved[name] = ch
        out = []
        for name in M5_CHAPTER_ORDER:
            ch = resolved.get(name)
```

Leave the rest of the loop body unchanged.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_module_chapters.py -q`
Expected: PASS (9 tests)

- [ ] **Step 6: Commit**

```bash
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_module_chapters.py
git commit -m "feat(m5): collapse the canonical chapter order to five

The final chapter is `conclusion`, titled 'Chương 5 — Kết luận và Kiến
nghị'. `discussion` is retired; reads alias it forward so projects
composed before this keep their written final chapter."
```

---

### Task 2: Delete the merge machinery

**Files:**
- Modify: `orchestrator/tools/compose_export.py:42-124` (delete `wants_merged_conclusion`, `merged_chapter_keys`, the `merge_conclusion` param and its branch), `:231-238`
- Modify: `api/app/partner_run.py:40`, `:231-234`
- Test: `api/tests/test_compose_export.py`, `api/tests/test_partner_run.py`

**Interfaces:**
- Consumes: `M5_CHAPTER_ORDER` from Task 1
- Produces: `compose_sections(context_store, chapters, language, references=None, progress=None, title_overrides=None)` — no `merge_conclusion` parameter. `compose_and_export` signature unchanged.

- [ ] **Step 1: Write the failing test**

The merge tests in `api/tests/test_compose_export.py` are being deleted with the feature. First read the file to find every test naming `merge_conclusion`, `wants_merged_conclusion` or `merged_chapter_keys`:

Run: `grep -n "merge\|wants_merged\|merged_chapter" api/tests/test_compose_export.py`

Delete those tests, then add the replacement that states the new invariant:

```python
def test_compose_sections_emits_five_chapters_with_no_chapter_six(monkeypatch):
    # The whole point of the collapse: no caller has to remember to merge,
    # because there is no sixth chapter to merge away.
    from orchestrator.tools import compose_export as CE
    monkeypatch.setattr(
        CE.compose_chapter, "invoke",
        lambda payload: {"prose": f"Prose for {payload['chapter_name']}."})

    out = CE.compose_sections({}, list(CE.M5_CHAPTER_ORDER), "vi")

    assert len(out) == 5
    titles = [s["title"] for s in out]
    assert titles[-1] == "Chương 5 — Kết luận và Kiến nghị"
    assert not any("6" in t for t in titles)


def test_compose_sections_has_no_merge_parameter():
    # Guards against the merge being reintroduced as an argument some callers
    # pass and others forget — the exact bug this change removes.
    import inspect
    from orchestrator.tools import compose_export as CE
    assert "merge_conclusion" not in inspect.signature(CE.compose_sections).parameters
    assert not hasattr(CE, "wants_merged_conclusion")
    assert not hasattr(CE, "merged_chapter_keys")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py -q`
Expected: FAIL — `merge_conclusion` is still a parameter and the helpers still exist.

- [ ] **Step 3: Delete the merge code**

In `orchestrator/tools/compose_export.py`, delete `wants_merged_conclusion` (lines 42-82) and `merged_chapter_keys` (lines 85-101) outright. In `compose_sections`, drop the `merge_conclusion: bool = False` parameter and delete its branch (lines 114-124).

In `compose_and_export`, drop the `merge_conclusion=` argument (lines 234-237) so the call reads:

```python
    sections = compose_sections(
        context_store, chapters, language,
        references=references, progress=progress, title_overrides=title_overrides,
    )
```

Update the module docstring's first paragraph to drop the merge from the list of things this module owns.

- [ ] **Step 4: Update the partner pipeline**

In `api/app/partner_run.py` line 40:

```python
# The chapters an analysis-only order buys. `discussion` is gone with the
# five-chapter collapse — the discussion of findings is written inside
# Chapter 5 (Kết luận và Kiến nghị), not as a chapter of its own.
ANALYSIS_CHAPTERS = ["intro", "results", "conclusion"]
```

At line 231-234, drop `merge_conclusion=True` and the comment above it that explains the merge, leaving the plain call:

```python
        sections = compose_sections(context_store, keys, language,
                                    references=references)
```

Check line 256's comment ("partner about a `conclusion` chapter that exists in no section") still reads correctly — it should, since `conclusion` is now the real chapter name.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest tests/test_compose_export.py tests/test_partner_run.py tests/test_partner_report.py -q`
Expected: PASS. Any failure naming `discussion` is a test asserting the old six-chapter shape — update it to expect five.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/tools/compose_export.py api/app/partner_run.py api/tests/test_compose_export.py api/tests/test_partner_run.py
git commit -m "refactor(export): delete the conclusion-merge machinery

With one final chapter in the canonical order there is nothing to merge.
This fixes the three export paths (auto-export, agent tool, editor) that
never called the merge and so still shipped six chapters."
```

---

### Task 3: Rewrite the conclusion prompt, delete the discussion prompt

**Files:**
- Rewrite: `orchestrator/prompts/m5/conclusion.md`
- Delete: `orchestrator/prompts/m5/discussion.md`
- Modify: `orchestrator/prompts/m5.md:8-13`

**Interfaces:**
- Consumes: nothing from earlier tasks (prompt files are loaded by name: `m5_writing.py:3076` does `(_PROMPT_DIR / f"{chapter_name}.md").read_text()`, so the canonical key `conclusion` loads `conclusion.md`)
- Produces: a `conclusion.md` carrying the full 5.1–5.7 structure

- [ ] **Step 1: Write the failing test**

Add to `orchestrator/tests/test_chapter_structure.py`:

```python
def test_every_canonical_chapter_has_a_prompt_and_no_orphans():
    # compose_chapter loads orchestrator/prompts/m5/<chapter_name>.md by name,
    # so a canonical chapter with no prompt file raises at compose time, and a
    # prompt file with no chapter is dead weight that will drift.
    from pathlib import Path
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    d = Path(__file__).resolve().parents[1] / "prompts" / "m5"
    on_disk = {p.stem for p in d.glob("*.md")}
    assert set(M5_CHAPTER_ORDER) <= on_disk
    assert "discussion" not in on_disk


def test_conclusion_prompt_carries_the_full_chapter_five_structure():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1]
            / "prompts" / "m5" / "conclusion.md").read_text(encoding="utf-8")
    for needle in ("5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"):
        assert needle in text, f"conclusion prompt lost section {needle}"
    # The limitations token must survive verbatim on its own line — it renders
    # the REAL flagged weaknesses from state. Losing it silently stops
    # limitation disclosure at export.
    assert "[[DT:limitations]]" in text
    assert "Chapter 6" not in text and "6.1" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_chapter_structure.py -q`
Expected: FAIL — `discussion.md` still exists and `conclusion.md` still says "Chapter 6".

- [ ] **Step 3: Rewrite `orchestrator/prompts/m5/conclusion.md`**

```markdown
# Compose Chapter 5 — Conclusions and Recommendations

You are writing Chapter 5, the FINAL chapter of a master's thesis.

A Vietnamese quantitative thesis has five chapters. The discussion of findings
belongs INSIDE this chapter (5.2), not in a chapter of its own — do not write a
separate discussion chapter and do not refer to "Chapter 6"; there isn't one.

## Inputs
- Research title: {research_title}
- Paradigm: {paradigm}
- Objectives: {objectives}
- Research questions: {research_questions}
- Research gaps (M2): {research_gaps}
- Themes / hypotheses results (from Chapter 4): {results} / {qual_themes}
- Language: {language}
- Citation style: {citation_style}

## References available for citation
{references_list}

## Instructions
Write a 1200-2000 word Chapter 5 with these sections:
- 5.1 Summary of findings (one paragraph per research question; state how each
  objective was met)
- 5.2 Discussion of findings (compare to prior literature; explain consistencies
  + surprises)
- 5.3 Theoretical contributions (how findings extend / refine the theory used)
- 5.4 Practical implications and recommendations (managerial / policy)
- 5.5 Limitations — introduce them in a sentence, then emit `[[DT:limitations]]` on
  its own line: DoThesis fills in the REAL flagged weaknesses (sub-threshold power, a
  not-supported hypothesis, screening removals, borderline validity) from the persisted
  state, framed for disclosure. Discuss each; invent none; hide none.
- 5.6 Directions for future research
- 5.7 Concluding remarks (concise; no new claims, no new citations)

Cite extensively in 5.2 and 5.3 to back up each interpretation. Write in {language}.

Output: Chapter 5 prose as markdown only.
```

- [ ] **Step 4: Delete the discussion prompt and fix the skill's chapter list**

```bash
git rm orchestrator/prompts/m5/discussion.md
```

In `orchestrator/prompts/m5.md`, replace lines 12-13 (`- Chapter 5: Discussion` / `- Chapter 6: Conclusion`) with:

```markdown
- Chapter 5: Conclusions and Recommendations (summary of findings, discussion of
  findings, theoretical contributions, practical recommendations, limitations,
  future research, concluding remarks)
```

- [ ] **Step 5: Check the shared instruction block**

`m5_writing.py:1654` carries a comment about instructions "duplicated (and drifting) across each prompts/m5/<chapter>.md file". Read that block and confirm it does not itself name a Discussion chapter or Chapter 6:

Run: `sed -n '1640,1680p' orchestrator/tools/m5_writing.py`

If it names either, update it to the five-chapter shape.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_chapter_structure.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add orchestrator/prompts/ orchestrator/tests/test_chapter_structure.py
git commit -m "feat(prompts): one Chapter 5 composer covering 5.1-5.7

conclusion.md takes over discussion.md's structure (which already matched
the standard VN Chapter 5) and gains 5.7 concluding remarks — the only
content the old Chapter 6 owned. The rest of Chapter 6 restated 5.1/5.3."
```

---

### Task 4: Artifacts DAG and coaching roadmap

**Files:**
- Modify: `orchestrator/artifacts.py:212-256` (`_M5_CLOSING_CHAPTERS`, `_m5_chapter_prose`, `dod_writing`), `:276-287` (`ARTIFACTS`)
- Modify: `agent/roadmap.py:18-30`, `:44`, `:64-69`
- Test: `orchestrator/tests/test_artifacts.py`, `agent/tests/test_roadmap.py`

**Interfaces:**
- Consumes: `canonical_chapter`, `M5_CHAPTER_ORDER` from Task 1
- Produces: artifact key `ch_conclusion` with `depends_on == ("ch_results", "topic")`; `ch_discussion` no longer exists. `ROADMAP["M5"] == ["write_conclusion", "export"]`.

- [ ] **Step 1: Write the failing tests**

Add to `orchestrator/tests/test_artifacts.py`:

```python
def test_no_discussion_artifact_and_conclusion_inherits_its_deps():
    from orchestrator.artifacts import ARTIFACTS
    keys = {a.key for a in ARTIFACTS}
    assert "ch_discussion" not in keys
    conc = next(a for a in ARTIFACTS if a.key == "ch_conclusion")
    # ch_discussion used to carry these; `analysis` stays reachable through
    # ch_results, which already declares it.
    assert conc.depends_on == ("ch_results", "topic")


def test_dod_writing_accepts_a_thesis_whose_final_chapter_is_the_conclusion():
    from orchestrator.artifacts import dod_writing
    slice_ = {"chapters": {n: {"prose": "x"} for n in
                           ("intro", "lit_review", "methodology", "results", "conclusion")}}
    assert dod_writing(slice_).done is True


def test_dod_writing_accepts_legacy_discussion_prose_as_the_final_chapter():
    # An in-flight project wrote its final chapter under the retired name.
    from orchestrator.artifacts import dod_writing
    slice_ = {"chapters": {n: {"prose": "x"} for n in
                           ("intro", "lit_review", "methodology", "results", "discussion")}}
    assert dod_writing(slice_).done is True
```

Add to `agent/tests/test_roadmap.py`:

```python
def test_m5_spine_has_one_writing_step():
    from agent.roadmap import ROADMAP, SUBSTEP_LABELS, SUBSTEP_ARTIFACT
    assert ROADMAP["M5"] == ["write_conclusion", "export"]
    assert "write_discussion" not in SUBSTEP_LABELS
    # final_sections is where M5's composed prose lands, so it backs the one
    # writing step that remains.
    assert SUBSTEP_ARTIFACT["M5"] == {"write_conclusion": "final_sections"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_artifacts.py ../agent/tests/test_roadmap.py -q`
Expected: FAIL — `ch_discussion` still exists; `ROADMAP["M5"]` still has three steps.

- [ ] **Step 3: Update `orchestrator/artifacts.py`**

Replace lines 212-218:

```python
# The chapters a thesis must actually have prose for before M5 can call itself
# done. A Vietnamese thesis merges discussion and conclusion into one final
# chapter ("KẾT LUẬN VÀ KIẾN NGHỊ"), which is now the only closing chapter in
# the canonical order — so this is a single name rather than a pair.
_M5_CORE_CHAPTERS = ("intro", "lit_review", "methodology", "results")
_M5_CLOSING_CHAPTER = "conclusion"
```

In `_m5_chapter_prose`, resolve stored names through the alias so a legacy
`discussion` slice still satisfies the DoD. Replace the `chapters` branch:

```python
    slice_ = slice_ or {}
    from orchestrator.tools.m5_writing import canonical_chapter  # noqa: PLC0415

    chapters = slice_.get("chapters")
    if isinstance(chapters, dict) and chapters:
        out: dict[str, str] = {}
        for stored, c in chapters.items():
            name = canonical_chapter(stored)
            # A real `conclusion` beats a legacy `discussion` aliased onto it.
            if name is None or (name in out and stored != name):
                continue
            out[name] = (c or {}).get("prose") or "" if isinstance(c, dict) else ""
        return out
```

In `dod_writing`, replace the closing-chapter check (lines 254-255):

```python
    if _M5_CLOSING_CHAPTER not in have:
        gaps.append("no conclusion chapter yet")
```

In `ARTIFACTS` (lines 285-286), delete the `ch_discussion` entry and rewire `ch_conclusion`:

```python
    # ch_discussion is gone with the five-chapter collapse; ch_conclusion
    # inherits its dependencies. `analysis` is not restated because ch_results
    # already declares it, so it stays reachable transitively.
    Artifact("ch_conclusion",  "m5_writing",    ("ch_results", "topic"),       dod_chapter("conclusion")),
```

`dod_chapter` reads `chapters.get(chapter_name)` directly; leave it — the alias belongs in `_m5_chapter_prose`, and `dod_chapter("conclusion")` on a legacy slice is covered by the module-level `dod_writing`.

- [ ] **Step 4: Update `agent/roadmap.py`**

Replace the M5 comment block and entry (lines 18-29):

```python
    # M5 owns the closing chapter — Chapter 5, "Kết luận và Kiến nghị" — not the
    # whole document. Every module composes its own chapter as it completes
    # (orchestrator.tools.m5_writing.MODULE_CHAPTERS), so by the time a student
    # reaches M5 chapters 1-4 already exist.
    #
    # One writing step, not two: the thesis has five chapters, and the
    # discussion of findings is written inside Chapter 5 rather than as a
    # chapter of its own.
    #
    # The "review" step (a committee-readiness grade sitting between assembly
    # and export) is gone. It put a review in front of the student's output,
    # which is backwards — they get the document, then fine-tune it. The
    # review_thesis tool still exists and still grades on demand; it just isn't
    # a step anyone has to walk through first. Export is terminal.
    "M5": ["write_conclusion", "export"],
```

At line 44, drop the `write_discussion` label:

```python
    "write_conclusion": "Write the conclusion",
    "export": "Export the document",
```

At lines 64-69:

```python
    # `final_sections` is where M5's composed prose lands, so it backs the one
    # writing step M5 has.
    "M5": {"write_conclusion": "final_sections"},
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_artifacts.py ../agent/tests/test_roadmap.py ../orchestrator/tests/test_planner.py -q`
Expected: PASS. `test_planner.py` exercises the artifact DAG — if it fails naming `ch_discussion`, update the expectation to the five-chapter DAG.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/artifacts.py agent/roadmap.py orchestrator/tests/test_artifacts.py agent/tests/test_roadmap.py orchestrator/tests/test_planner.py
git commit -m "feat(roadmap): M5 has one writing step and one closing artifact

ch_discussion is deleted and ch_conclusion inherits its dependencies. The
DoD accepts a legacy slice whose final chapter is still under the retired
'discussion' key."
```

---

### Task 5: Schemas and the hand-copied chapter tuples

**Files:**
- Modify: `orchestrator/schemas/m5.py:10`, `:46`
- Modify: `orchestrator/schemas/m5_editor.py:21`
- Modify: `api/app/routers/m5_editor.py:72-74`
- Test: `orchestrator/tests/test_schemas.py`

**Interfaces:**
- Consumes: `M5_CHAPTER_ORDER` from Task 1
- Produces: no new symbols; three existing copies aligned to the canonical order

- [ ] **Step 1: Write the failing test**

Add to `orchestrator/tests/test_schemas.py`:

```python
def test_every_hand_copied_chapter_list_matches_the_canonical_order():
    # Three hand-maintained copies of the chapter list is how the six/five
    # split survived: the canonical order said six, the merge said five, and
    # each copy drifted on its own. This test is cheaper than a fourth copy.
    from typing import get_args
    from orchestrator.tools.m5_writing import M5_CHAPTER_ORDER
    from orchestrator.schemas.m5 import ChapterName as M5Name
    from orchestrator.schemas.m5_editor import ChapterName as EditorName
    from api.app.routers.m5_editor import _VALID_CHAPTER_NAMES

    canonical = set(M5_CHAPTER_ORDER)
    assert set(get_args(M5Name)) == canonical
    assert set(get_args(EditorName)) == canonical
    assert _VALID_CHAPTER_NAMES == canonical
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_schemas.py -q`
Expected: FAIL — each copy still contains `"discussion"`.

- [ ] **Step 3: Drop `discussion` from all three copies**

`orchestrator/schemas/m5.py` line 10:

```python
ChapterName = Literal["intro", "lit_review", "methodology", "results", "conclusion"]
```

and line 46:

```python
        required = {"intro", "lit_review", "methodology", "results", "conclusion"}
```

`orchestrator/schemas/m5_editor.py` line 21: same `Literal` as above.

`api/app/routers/m5_editor.py` lines 72-74:

```python
# Kept in step with m5_writing.M5_CHAPTER_ORDER by a test in
# orchestrator/tests/test_schemas.py — this is a copy, not a source of truth.
_VALID_CHAPTER_NAMES = {
    "intro", "lit_review", "methodology", "results", "conclusion"
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && ./run.sh pytest ../orchestrator/tests/test_schemas.py tests/test_m5_editor_router.py -q`
Expected: PASS. If `test_m5_editor_router.py` fails PATCHing a `discussion` chapter, update that test to use `conclusion` — the route now rejects the retired name, which is correct.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/schemas/ api/app/routers/m5_editor.py orchestrator/tests/test_schemas.py api/tests/test_m5_editor_router.py
git commit -m "fix(schemas): align all three chapter-name copies to five

Adds the test that keeps them aligned — three hand-maintained copies is
how the six/five split went unnoticed."
```

---

### Task 6: Quality checks that key on the chapter name

**Files:**
- Modify: `agent/coherence.py:26`, `:576`, `:630-638`, `:731`
- Modify: `orchestrator/tools/results_render.py:682-695`
- Modify: `agent/feedback.py:18`
- Test: `agent/tests/test_coherence.py`

**Interfaces:**
- Consumes: canonical `conclusion` key from Task 1
- Produces: no new symbols

**Why this task exists:** these checks fail *open*. A stale `"discussion"` key means the check silently never fires and nothing logs — the same class of bug the whole change is removing.

- [ ] **Step 1: Write the failing test**

Add to `agent/tests/test_coherence.py`:

```python
def test_traceability_flags_an_uncited_hypothesis_in_the_conclusion_chapter():
    # The check used to read chapters["discussion"]. After the five-chapter
    # collapse that key is never written, so the check would fire on nothing.
    #
    # `literature_sources` is REQUIRED in the m2 fixture: traceability_findings
    # returns early without it (agent/coherence.py:606, "only meaningful once
    # the project has a literature base"). Verified: with it, the old
    # `discussion` key yields two findings and `conclusion` yields none — which
    # is exactly the red state this test must start from.
    from agent.coherence import traceability_findings
    m2 = {"literature_sources": [{"title": "Davis 1989"}]}
    chapters = {"conclusion": "H1 was supported by the data, plainly.\n\n"
                              "H2 was supported by the data, plainly."}
    out = traceability_findings(m2, {}, chapters)
    assert any(f["check"] == "traceability.discussion_uncited" for f in out)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && ./run.sh pytest ../agent/tests/test_coherence.py -q`
Expected: FAIL — no finding produced, because the check reads a key nothing writes.

- [ ] **Step 3: Repoint the coherence checks**

`agent/coherence.py` line 26:

```python
# The chapters whose prose reports and interprets results. `discussion` is gone
# with the five-chapter collapse — the discussion of findings is written inside
# the conclusion chapter.
_RESULT_CHAPTERS = ("results", "conclusion")
```

Lines 575-576 and 730-731 (the same two-line `present` expression appears in both functions) — replace `chapters.get("discussion")` with `chapters.get("conclusion")` in each:

```python
        present = bool((chapters.get("results") and not _is_stub(chapters.get("results")))
                       and (chapters.get("conclusion") and not _is_stub(chapters.get("conclusion"))))
```

Line 630:

```python
        # The discussion of findings lives in the conclusion chapter (5.2).
        disc = chapters.get("conclusion")
```

Leave the finding's `check` id `traceability.discussion_uncited` and its
`chapter="discussion"` field **unchanged** — renaming a finding id would break
any stored feedback keyed on it. Add a comment at line 636 saying so:

```python
                    # Finding id and `chapter` label stay "discussion": they are
                    # a stable identifier for stored feedback, not a chapter key.
```

- [ ] **Step 4: Repoint the render map and the classifier prompt**

`orchestrator/tools/results_render.py` lines 682-695 — route the discussion/limitation needles to `conclusion` and drop the retired key:

```python
_TITLE_CHAPTER = [("result", "results"), ("methodolog", "methodology"),
                  ("data collect", "methodology"), ("conclusion", "conclusion"),
                  ("discussion", "conclusion"), ("limitation", "conclusion"),
                  # Vietnamese. Without these the title map matched nothing on a
                  # Vietnamese thesis — "CHƯƠNG 4: KẾT QUẢ NGHIÊN CỨU" hit no
                  # needle — so ensure_rendered, the export-time safety net, has
                  # never once fired for the market this product is built for.
                  # "kết luận" is listed before "kết quả" only for readability;
                  # they are distinct strings and cannot both match.
                  ("kết quả", "results"), ("phương pháp", "methodology"),
                  ("thu thập dữ liệu", "methodology"), ("kết luận", "conclusion"),
                  ("thảo luận", "conclusion"), ("hạn chế", "conclusion")]

_RENDERABLE_CHAPTERS = {"results", "methodology", "conclusion"}
```

Note the needles for "discussion"/"thảo luận"/"hạn chế" are kept — a student's
imported thesis may still title a section that way, and it must map to the one
chapter that now holds that material.

`agent/feedback.py` line 18:

```python
    "most likely chapter (intro|lit_review|methodology|results|conclusion) "
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest ../agent/tests/test_coherence.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent/coherence.py agent/feedback.py orchestrator/tools/results_render.py agent/tests/test_coherence.py
git commit -m "fix(quality): repoint chapter-keyed checks at the conclusion

These checks fail open — left reading the retired 'discussion' key they
would silently never fire again. Finding ids are deliberately unchanged."
```

---

### Task 7: The agent's export tool and the auto-export hook

**Files:**
- Modify: `agent/tools/writing.py:239-240`, `:343`, `:353`
- Verify: `api/app/agent_state.py:392-402`, `:414`, `:479-521`
- Test: `agent/tests/test_export_completeness.py`, `api/tests/test_auto_export_completeness.py`

**Interfaces:**
- Consumes: `M5_CHAPTER_ORDER`, `M5_CHAPTER_TITLES` from Task 1
- Produces: no new symbols

- [ ] **Step 1: Write the failing test**

Add to `api/tests/test_auto_export_completeness.py`:

```python
def test_auto_export_emits_five_chapters_and_no_chapter_six():
    # This path never called the merge, so before the collapse it shipped a
    # Chapter 6 while the interactive export shipped five.
    from orchestrator.tools.m5_writing import sections_from_m5_slice
    slice_ = {"chapters": {n: {"prose": f"{n} prose"} for n in
                           ("intro", "lit_review", "methodology", "results", "conclusion")}}
    sections = sections_from_m5_slice(slice_)
    assert len(sections) == 5
    assert sections[-1]["title"] == "Chapter 5 — Conclusions and Recommendations"
    assert not any("Chapter 6" in s["title"] for s in sections)
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `cd api && ./run.sh pytest tests/test_auto_export_completeness.py -q`
Expected: PASS already, if Task 1 landed correctly — `sections_from_m5_slice` reads `M5_CHAPTER_ORDER`. If it FAILS, Task 1 is incomplete; fix there, not here.

- [ ] **Step 3: Update the agent tool's user-facing chapter vocabulary**

`agent/tools/writing.py` line 239-240 (the `scope` argument docstring):

```python
            example "chapter:intro|conclusion". Valid canonical names are
            intro, lit_review, methodology, results, conclusion.
```

Line 263: change `"chapter:intro|discussion"` to `"chapter:intro|conclusion"`.

Line 343 — the alias map that normalizes user-typed chapter words. Keep
`discussion` as an INPUT alias pointing at the canonical key, so a student who
types "discussion" still gets Chapter 5:

```python
                # "discussion" stays accepted as INPUT — a student may still
                # type it — but resolves to the one chapter that holds that
                # material after the five-chapter collapse.
                "discussion": "conclusion", "conclusion": "conclusion",
```

Line 353 (the error message listing valid names):

```python
                            "results, or conclusion, joined with |.",
```

- [ ] **Step 4: Verify the auto-export hook needs no change**

Run: `sed -n '388,404p;410,420p' api/app/agent_state.py`

Confirm it derives everything from `M5_CHAPTER_ORDER` / `M5_CHAPTER_TITLES` / `chapters_for_module` and holds no literal chapter list. Update line 414's docstring, which says `M5→discussion+conclusion`:

```python
        M4→results, M5→conclusion. Merges ONLY this module's chapter
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd api && ./run.sh pytest tests/test_auto_export_completeness.py ../agent/tests/test_export_completeness.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add agent/tools/writing.py api/app/agent_state.py api/tests/test_auto_export_completeness.py agent/tests/test_export_completeness.py
git commit -m "fix(export): five chapters on the agent tool and auto-export paths

'discussion' stays accepted as user INPUT and resolves to Chapter 5."
```

---

### Task 8: Web surfaces

**Files:**
- Modify: `web/app/components/editor/OutlineRail.tsx`
- Modify: `web/app/components/chat/ContextPanel.tsx`, `ModuleSlices.tsx`, `QuickActionsMenu.tsx`, `ChatPane.tsx:112`
- Test: `web/app/components/editor/__tests__/OutlineRail.test.tsx`

**Interfaces:**
- Consumes: the canonical `conclusion` key from Task 1 (the web side holds its own copy of the chapter list)
- Produces: no new symbols

- [ ] **Step 1: Baseline the pre-existing failures**

```bash
cd web && git stash && npx vitest run --reporter=basic 2>&1 | tail -20 > /tmp/vitest-baseline.txt; git stash pop
```

Keep `/tmp/vitest-baseline.txt` — ~30 tests fail before this change, and any failure listed there is not yours.

- [ ] **Step 2: Find every chapter list on the web side**

```bash
cd web && grep -rn "discussion" app/ e2e/ --include=*.ts --include=*.tsx
```

- [ ] **Step 3: Write the failing test**

In `web/app/components/editor/__tests__/OutlineRail.test.tsx`, add:

```tsx
it('shows five chapters ending at the conclusion', () => {
  render(<OutlineRail {...baseProps} />)
  expect(screen.queryByText(/Discussion/i)).not.toBeInTheDocument()
  expect(screen.queryByText(/Chapter 6|Chương 6/)).not.toBeInTheDocument()
})
```

Match `baseProps` to whatever the surrounding tests in that file already use — read them first rather than inventing a shape.

- [ ] **Step 4: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/OutlineRail.test.tsx`
Expected: FAIL — the rail still lists a Discussion chapter.

- [ ] **Step 5: Drop `discussion` from each web chapter list**

Apply to every hit from Step 2. Where a display label exists for the conclusion chapter, set it to `Kết luận và Kiến nghị` (vi) / `Conclusions and Recommendations` (en), matching Task 1's titles. Update the `ChatPane.tsx:112` comment, which reads "M5 owns Discussion + Conclusion (MODULE_CHAPTERS)":

```tsx
// M5 owns the single closing chapter (MODULE_CHAPTERS)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web && npx vitest run app/components/editor app/components/chat 2>&1 | tail -20`
Expected: PASS, or only failures already present in `/tmp/vitest-baseline.txt`.

- [ ] **Step 7: Commit**

```bash
git add web/app/
git commit -m "feat(web): five chapters in the outline rail and chat panels"
```

---

### Task 9: Full sweep and verification

**Files:**
- Verify only; fix whatever the sweep turns up

**Interfaces:**
- Consumes: everything above
- Produces: a verified five-chapter thesis on all five export paths

- [ ] **Step 1: Account for every surviving mention of the retired name**

```bash
grep -rn "discussion" --include=*.py --include=*.ts --include=*.tsx --include=*.md \
  agent/ api/ orchestrator/ web/app/ docs/superpowers/specs/2026-09-04-five-chapter-thesis-design.md \
  | grep -v node_modules
```

Every remaining hit must fall into one of these allowed categories — anything else is a miss:
- the `LEGACY_CHAPTER_ALIASES` entry and the code reading it,
- input aliases that accept a user typing "discussion" (`writing.py`, `results_render.py`),
- the stable finding id `traceability.discussion_uncited` and its comment,
- prose in comments/specs explaining the collapse.

- [ ] **Step 2: Confirm no path can emit a sixth chapter**

```bash
grep -rn "Chapter 6\|Chương 6\|chapter_6\|chapter6" --include=*.py --include=*.ts --include=*.tsx --include=*.md \
  agent/ api/ orchestrator/ web/app/ | grep -v node_modules
```

Expected: only the spec, the plan, and commit-message prose. No source file.

- [ ] **Step 3: Run the full Python suite**

```bash
cd api && ./run.sh pytest tests -q 2>&1 | tail -20
cd api && ./run.sh pytest ../orchestrator/tests ../agent/tests -q 2>&1 | tail -20
```

Expected: PASS. Report any failure with its output rather than working around it.

- [ ] **Step 4: Run the web suite and compare to baseline**

```bash
cd web && npx vitest run --reporter=basic 2>&1 | tail -20
```

Expected: no failures beyond `/tmp/vitest-baseline.txt`.

- [ ] **Step 5: Exercise a real export end to end**

The five paths must agree. Use the repo's own runner rather than a hand-built harness:

```bash
cd api && ./run.sh pytest tests -q -k "export" 2>&1 | tail -20
```

Then confirm by reading that `compose_and_export`, `partner_run`, `agent_state`'s auto-export, `writing.py`'s export tool and `m5_editor`'s `/m5/export` all build their section list from `M5_CHAPTER_ORDER` with no local chapter literal:

```bash
grep -n "M5_CHAPTER_ORDER\|M5_CHAPTER_TITLES" \
  orchestrator/tools/compose_export.py api/app/partner_run.py \
  api/app/agent_state.py agent/tools/writing.py api/app/routers/m5_editor.py
```

- [ ] **Step 6: Commit any sweep fixes**

```bash
git add -A
git commit -m "fix: account for the last references to the retired chapter"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §1 canonical key is `conclusion` | Task 1 |
| §2 conclusion composer keeps the good structure | Task 3 |
| §3 merge machinery deleted | Task 2 |
| §4 legacy prose survives | Task 1 (steps 1, 4), Task 4 (step 3) |
| §5 coherence checks follow the key | Task 6 |
| §6 roadmap loses a step | Task 4 |
| §7 schemas and validation | Task 5 |
| Testing / risks | Tasks 8, 9 |

**Type consistency:** `canonical_chapter(name) -> str | None` is defined in Task 1 and consumed by name in Tasks 1 and 4. `LEGACY_CHAPTER_ALIASES` is defined in Task 1 and referenced in Task 9. `_M5_CLOSING_CHAPTERS` (plural, a tuple) is renamed to `_M5_CLOSING_CHAPTER` (singular, a str) in Task 4 — the only rename, and both its definition and its one use site are in that task.

**Known gap deliberately left:** `sections_from_m5_slice` uses `M5_CHAPTER_TITLES[name]` unconditionally (`m5_writing.py:1974`), so the auto-export path emits English headings even for a Vietnamese thesis. Pre-existing, orthogonal to the chapter count, and fixing it here would widen the diff — worth a follow-up issue.
