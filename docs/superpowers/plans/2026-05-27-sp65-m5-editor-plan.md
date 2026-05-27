# SP6.5 — M5 Editor Surface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a WYSIWYG editor at `/chat/projects/[pid]/editor` for the six M5 chapters, with three inline AI tools (paraphrase / translate / cite) and a unified PendingEdit accept/reject machinery that also receives chat NL-rewrites.

**Architecture:** Per-chapter TipTap instances backed by `context_store.m5_writing.chapters[name].prose`. Autosave PATCH (debounced) writes prose. Selection-toolbar AI tools and chat NL-rewrites all create `PendingEdit` records on the chapter; the editor renders them as inline diffs with ✓/✗ ribbons. Accept splices `new_text` into prose; reject just drops the edit. Re-export is a separate explicit button.

**Tech Stack:** Python 3.11 (FastAPI, SQLAlchemy 2.0, Pydantic v2), TipTap (`@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-bubble-menu`), Next.js 16 + React 19, Vitest + React Testing Library, pytest.

**Spec:** `docs/superpowers/specs/2026-05-27-sp65-m5-editor-design.md`

**Convention note for this plan:** Existing storage uses `M5Output.chapters: dict[str, dict]` keyed by chapter name (`intro`, `lit_review`, etc.) — not a list. All endpoints route by chapter *name* string. The outline rail uses the fixed order `[intro, lit_review, methodology, results, discussion, conclusion]`.

---

## Phase 1 — Backend foundation (schemas + agent change)

### Task 1: `PendingEdit` schema

**Files:**
- Create: `orchestrator/schemas/m5_editor.py`
- Test: `orchestrator/tests/schemas/test_pending_edit.py`

- [ ] **Step 1: Write the failing test**

```python
# orchestrator/tests/schemas/test_pending_edit.py
from datetime import datetime, timezone
from orchestrator.schemas.m5_editor import PendingEdit


def test_pending_edit_roundtrip():
    pe = PendingEdit(
        id="abc-123",
        chapter_name="intro",
        from_offset=10, to_offset=25,
        old_text="recent studies",
        new_text="A growing body of work",
        source="paraphrase",
        pending_at=datetime(2026, 5, 27, tzinfo=timezone.utc),
    )
    dumped = pe.model_dump()
    restored = PendingEdit.model_validate(dumped)
    assert restored == pe


def test_pending_edit_rejects_unknown_source():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PendingEdit(
            id="x", chapter_name="intro",
            from_offset=0, to_offset=1,
            old_text="a", new_text="b",
            source="grammar_fix",  # not allowed
            pending_at=datetime.now(timezone.utc),
        )


def test_pending_edit_offsets_must_be_nonnegative():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        PendingEdit(
            id="x", chapter_name="intro",
            from_offset=-1, to_offset=1,
            old_text="", new_text="b",
            source="paraphrase",
            pending_at=datetime.now(timezone.utc),
        )


def test_pending_edit_degenerate_range_for_cite():
    """Cite is insertion-only — from == to, old_text == ''."""
    pe = PendingEdit(
        id="cite-1", chapter_name="intro",
        from_offset=50, to_offset=50, old_text="", new_text=" (Smith, 2024)",
        source="cite", pending_at=datetime.now(timezone.utc),
        metadata={"reference_id": "ref-abc"},
    )
    assert pe.from_offset == pe.to_offset
    assert pe.old_text == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest orchestrator/tests/schemas/test_pending_edit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'orchestrator.schemas.m5_editor'`

- [ ] **Step 3: Implement the schema**

```python
# orchestrator/schemas/m5_editor.py
"""SP6.5: PendingEdit — a not-yet-accepted modification to a chapter's prose.

Sources are unified: paraphrase/translate/cite (from inline editor toolbar)
and chat_rewrite (from M5 NL-rewrite handler) all create the same record.
The editor's AiPending mark + accept/reject ribbon is a single UI surface
for all four sources.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


PendingEditSource = Literal["paraphrase", "translate", "cite", "chat_rewrite"]
ChapterName = Literal["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


class PendingEdit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str                                       # uuid4 hex
    chapter_name: ChapterName
    from_offset: int = Field(ge=0)                # char offset into chapter.prose at creation time
    to_offset: int = Field(ge=0)                  # >= from_offset; equal means insertion
    old_text: str                                 # must equal prose[from:to] when accept fires
    new_text: str
    source: PendingEditSource
    pending_at: datetime
    metadata: dict = Field(default_factory=dict)  # e.g. {"target_lang": "vi"} or {"reference_id": "..."}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest orchestrator/tests/schemas/test_pending_edit.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/schemas/m5_editor.py orchestrator/tests/schemas/test_pending_edit.py
git commit -m "feat(orchestrator): PendingEdit schema for SP6.5 editor"
```

---

### Task 2: Extend `ChapterDraft` with `pending_edits`

**Files:**
- Modify: `orchestrator/schemas/m5.py`
- Test: `orchestrator/tests/test_schemas.py` (add to existing)

- [ ] **Step 1: Write the failing test**

Append to `orchestrator/tests/test_schemas.py`:

```python
def test_chapter_draft_pending_edits_default_empty():
    from orchestrator.schemas.m5 import ChapterDraft
    c = ChapterDraft(name="intro", prose="hello world")
    assert c.pending_edits == []


def test_chapter_draft_accepts_pending_edits():
    from datetime import datetime, timezone
    from orchestrator.schemas.m5 import ChapterDraft
    from orchestrator.schemas.m5_editor import PendingEdit
    pe = PendingEdit(
        id="x", chapter_name="intro", from_offset=0, to_offset=5,
        old_text="hello", new_text="hi", source="paraphrase",
        pending_at=datetime.now(timezone.utc),
    )
    c = ChapterDraft(name="intro", prose="hello world", pending_edits=[pe])
    assert len(c.pending_edits) == 1
    assert c.pending_edits[0].source == "paraphrase"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest orchestrator/tests/test_schemas.py::test_chapter_draft_pending_edits_default_empty -v`
Expected: FAIL — `pending_edits` is not a field on ChapterDraft.

- [ ] **Step 3: Modify ChapterDraft**

```python
# orchestrator/schemas/m5.py — add to imports
from orchestrator.schemas.m5_editor import PendingEdit

# Update ChapterDraft class:
class ChapterDraft(BaseModel):
    """One composed chapter with provenance info."""
    name: ChapterName
    prose: str
    citations_used: list[str] = Field(default_factory=list)
    uncited_warnings: list[str] = Field(default_factory=list)
    # SP6.5 — additive; defaults empty so existing M5Output data still validates
    pending_edits: list[PendingEdit] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest orchestrator/tests/test_schemas.py -v -k pending`
Expected: PASS (2 new tests). Existing M5Output tests should still pass.

Also run: `pytest orchestrator/tests/test_schemas.py -v`
Expected: full file PASS.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/schemas/m5.py orchestrator/tests/test_schemas.py
git commit -m "feat(orchestrator): ChapterDraft.pending_edits (additive for SP6.5)"
```

---

### Task 3: Inline LLM tool — `paraphrase_selection`

**Files:**
- Create: `orchestrator/tools/m5_inline.py`
- Create: `orchestrator/prompts/m5_inline/paraphrase.md`
- Test: `orchestrator/tests/tools/test_m5_inline.py`

- [ ] **Step 1: Write the prompt template**

```markdown
# orchestrator/prompts/m5_inline/paraphrase.md
# Paraphrase a selection within a chapter

You are paraphrasing a short selection from a master's thesis chapter.

## Inputs
- Chapter: {chapter_name}
- Language: {language}
- Surrounding context (paragraph before): {context_before}
- Selection to paraphrase: {selection}
- Surrounding context (paragraph after): {context_after}
- Style hint (optional): {style}

## Instructions
Rewrite ONLY the selection. Preserve meaning. Match the academic register of the surrounding context. If a style hint is provided (e.g. "more formal", "concise", "simpler"), apply it.

Do NOT add citations that were not present in the original selection.
Do NOT include any preamble, explanation, or quotation marks.

Output: the paraphrased selection only, as plain text.
```

- [ ] **Step 2: Write the failing test**

```python
# orchestrator/tests/tools/test_m5_inline.py
from unittest.mock import patch
from orchestrator.tools.m5_inline import paraphrase_selection


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_returns_new_text_only(mock_llm):
    mock_llm.return_value = "A growing body of work suggests"
    result = paraphrase_selection.invoke({
        "chapter_name": "intro",
        "language": "en",
        "context_before": "The literature is broad.",
        "selection": "recent studies have shown",
        "context_after": "that algorithmic decisions...",
        "style": "more formal",
    })
    assert result == "A growing body of work suggests"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_strips_quotes_and_whitespace(mock_llm):
    mock_llm.return_value = '  "A growing body of work suggests"  \n'
    result = paraphrase_selection.invoke({
        "chapter_name": "intro", "language": "en",
        "context_before": "", "selection": "x", "context_after": "",
    })
    assert result == "A growing body of work suggests"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_without_style_hint(mock_llm):
    mock_llm.return_value = "rewritten text"
    result = paraphrase_selection.invoke({
        "chapter_name": "lit_review", "language": "en",
        "context_before": "", "selection": "old", "context_after": "",
    })
    assert result == "rewritten text"
    # Confirm the prompt didn't crash on missing style
    mock_llm.assert_called_once()
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 4: Implement the tool**

```python
# orchestrator/tools/m5_inline.py
"""SP6.5: selection-scoped LLM tools used by the editor's inline AI features.

paraphrase_selection / translate_selection take a selection plus surrounding
context and return the rewritten selection only. The caller (API endpoint)
wraps the result in a PendingEdit and persists it to ChapterDraft.pending_edits.
"""
from __future__ import annotations

from pathlib import Path

from langchain_core.tools import tool


_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts" / "m5_inline"
_PARAPHRASE_PROMPT = (_PROMPTS_DIR / "paraphrase.md").read_text()


def _call_llm(prompt: str) -> str:
    """Real implementation routes through the project's Gemini wrapper.

    Tests monkeypatch this function. Keeping it as a module-level function
    (not an inline lambda) makes it patchable.
    """
    from orchestrator.tools.m5_writing import _get_llm  # reuse existing wrapper
    llm = _get_llm()
    return llm.invoke(prompt).content


def _strip(text: str) -> str:
    """Trim whitespace + paired surrounding quotes that LLMs sometimes emit."""
    t = text.strip()
    if len(t) >= 2 and t[0] == t[-1] and t[0] in ('"', "'"):
        t = t[1:-1].strip()
    return t


@tool
def paraphrase_selection(
    chapter_name: str,
    language: str,
    context_before: str,
    selection: str,
    context_after: str,
    style: str = "",
) -> str:
    """Paraphrase a chapter selection. Returns the rewritten selection only."""
    prompt = _PARAPHRASE_PROMPT.format(
        chapter_name=chapter_name,
        language=language,
        context_before=context_before,
        selection=selection,
        context_after=context_after,
        style=style or "(none — use a natural academic register)",
    )
    return _strip(_call_llm(prompt))
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/tools/m5_inline.py orchestrator/prompts/m5_inline/paraphrase.md orchestrator/tests/tools/test_m5_inline.py
git commit -m "feat(orchestrator): paraphrase_selection LLM tool for SP6.5"
```

---

### Task 4: Inline LLM tool — `translate_selection`

**Files:**
- Modify: `orchestrator/tools/m5_inline.py`
- Create: `orchestrator/prompts/m5_inline/translate.md`
- Modify: `orchestrator/tests/tools/test_m5_inline.py`

- [ ] **Step 1: Write the prompt template**

```markdown
# orchestrator/prompts/m5_inline/translate.md
# Translate a selection within a chapter

You are translating a short selection from a master's thesis chapter.

## Inputs
- Chapter: {chapter_name}
- Source language (auto-detected from selection): inspect the selection
- Target language: {target_lang}
- Surrounding context (paragraph before): {context_before}
- Selection to translate: {selection}
- Surrounding context (paragraph after): {context_after}

## Instructions
Translate ONLY the selection into {target_lang}. Preserve any inline citations like (Author, Year) verbatim. Match the academic register. Do not add anything that wasn't in the original selection.

Output: the translated selection only, as plain text — no preamble, no quotation marks.
```

- [ ] **Step 2: Write the failing tests**

Append to `orchestrator/tests/tools/test_m5_inline.py`:

```python
@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_returns_target_lang_text(mock_llm):
    from orchestrator.tools.m5_inline import translate_selection
    mock_llm.return_value = "Một nghiên cứu gần đây cho thấy"
    result = translate_selection.invoke({
        "chapter_name": "intro",
        "target_lang": "vi",
        "context_before": "",
        "selection": "Recent studies have shown",
        "context_after": "",
    })
    assert result == "Một nghiên cứu gần đây cho thấy"


@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_preserves_inline_citation(mock_llm):
    from orchestrator.tools.m5_inline import translate_selection
    mock_llm.return_value = "Theo (Smith, 2024), điều này quan trọng"
    result = translate_selection.invoke({
        "chapter_name": "intro", "target_lang": "vi",
        "context_before": "", "context_after": "",
        "selection": "According to (Smith, 2024), this matters",
    })
    assert "(Smith, 2024)" in result
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v -k translate`
Expected: FAIL with `cannot import name 'translate_selection'`.

- [ ] **Step 4: Implement the tool**

Append to `orchestrator/tools/m5_inline.py`:

```python
_TRANSLATE_PROMPT = (_PROMPTS_DIR / "translate.md").read_text()


@tool
def translate_selection(
    chapter_name: str,
    target_lang: str,
    context_before: str,
    selection: str,
    context_after: str,
) -> str:
    """Translate a chapter selection into target_lang. Returns translated text only."""
    prompt = _TRANSLATE_PROMPT.format(
        chapter_name=chapter_name,
        target_lang=target_lang,
        context_before=context_before,
        selection=selection,
        context_after=context_after,
    )
    return _strip(_call_llm(prompt))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/tools/m5_inline.py orchestrator/prompts/m5_inline/translate.md orchestrator/tests/tools/test_m5_inline.py
git commit -m "feat(orchestrator): translate_selection LLM tool for SP6.5"
```

---

### Task 5: `build_citation_text` helper (regex, no LLM)

**Files:**
- Modify: `orchestrator/tools/m5_inline.py`
- Modify: `orchestrator/tests/tools/test_m5_inline.py`

- [ ] **Step 1: Write the failing tests**

Append to `orchestrator/tests/tools/test_m5_inline.py`:

```python
def test_build_citation_text_uses_author_and_year():
    from orchestrator.tools.m5_inline import build_citation_text
    ref = {"author": "Smith", "year": 2024, "title": "Whatever"}
    assert build_citation_text(ref) == "(Smith, 2024)"


def test_build_citation_text_handles_string_year():
    from orchestrator.tools.m5_inline import build_citation_text
    ref = {"author": "Jones", "year": "2023"}
    assert build_citation_text(ref) == "(Jones, 2023)"


def test_build_citation_text_falls_back_when_fields_missing():
    from orchestrator.tools.m5_inline import build_citation_text
    assert build_citation_text({}) == "(Anonymous, n.d.)"
    assert build_citation_text({"author": "X"}) == "(X, n.d.)"
    assert build_citation_text({"year": 2024}) == "(Anonymous, 2024)"


def test_build_citation_text_strips_whitespace():
    from orchestrator.tools.m5_inline import build_citation_text
    assert build_citation_text({"author": "  Smith  ", "year": " 2024 "}) == "(Smith, 2024)"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v -k citation`
Expected: FAIL — `cannot import name 'build_citation_text'`.

- [ ] **Step 3: Implement the helper**

Append to `orchestrator/tools/m5_inline.py`:

```python
def build_citation_text(reference: dict) -> str:
    """Derive canonical (Author, Year) text from an M2 reference record.

    M2 papers carry at least 'author' and 'year' under normal circumstances.
    Falls back to ('Anonymous', 'n.d.') on either missing piece so that
    malformed-but-present references still produce a usable citation rather
    than blowing up the API call.
    """
    author = str(reference.get("author") or "").strip() or "Anonymous"
    year_val = reference.get("year")
    year = str(year_val).strip() if year_val not in (None, "") else "n.d."
    return f"({author}, {year})"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest orchestrator/tests/tools/test_m5_inline.py -v -k citation`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m5_inline.py orchestrator/tests/tools/test_m5_inline.py
git commit -m "feat(orchestrator): build_citation_text helper for SP6.5 cite tool"
```

---

### Task 6: Re-export `validate_citations` as standalone

The existing `validate_citations` in `orchestrator/tools/m5_writing.py` is a LangChain `@tool`. Autosave PATCH needs to re-run citation validation server-side without going through the tool decorator. We expose the underlying plain function.

**Files:**
- Modify: `orchestrator/tools/m5_writing.py`
- Modify: `orchestrator/tests/test_tools_m5.py`

- [ ] **Step 1: Write the failing test**

Append to `orchestrator/tests/test_tools_m5.py`:

```python
def test_validate_citations_plain_callable_exists():
    """SP6.5: autosave PATCH calls validate_citations_plain (no decorator)."""
    from orchestrator.tools.m5_writing import validate_citations_plain
    result = validate_citations_plain(
        prose="See (Smith, 2024) and (Unknown, 2023).",
        reference_pool=[{"author": "Smith", "year": "2024"}],
    )
    assert result["citations_used"] == ["(Smith, 2024)"]
    assert result["uncited_warnings"] == ["(Unknown, 2023)"]


def test_validate_citations_plain_dedupes_in_order():
    from orchestrator.tools.m5_writing import validate_citations_plain
    result = validate_citations_plain(
        prose="(A, 2020). Later (B, 2021). Earlier (A, 2020) again.",
        reference_pool=[{"author": "A", "year": "2020"}, {"author": "B", "year": "2021"}],
    )
    assert result["citations_used"] == ["(A, 2020)", "(B, 2021)"]
    assert result["uncited_warnings"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest orchestrator/tests/test_tools_m5.py -v -k validate_citations_plain`
Expected: FAIL — `cannot import name 'validate_citations_plain'`.

- [ ] **Step 3: Refactor — extract plain function from existing `@tool`**

Open `orchestrator/tools/m5_writing.py`. Find the existing `@tool` `validate_citations(prose, reference_pool)` definition. Extract its body into a module-level `validate_citations_plain(prose, reference_pool) -> dict` and have the `@tool` version call it:

```python
# orchestrator/tools/m5_writing.py — refactor existing validate_citations

import re

_CITATION_REGEX = re.compile(r"\(([^)]+?),\s*(\d{4}|n\.d\.)\)")


def validate_citations_plain(prose: str, reference_pool: list[dict]) -> dict:
    """Extract (Author, Year) patterns; classify as used vs uncited based on pool.

    Returns {"citations_used": [...], "uncited_warnings": [...]} preserving
    first-occurrence order with no duplicates.
    """
    pool_keys = {
        (str(r.get("author", "")).strip(), str(r.get("year", "")).strip())
        for r in reference_pool
    }
    seen: dict[str, bool] = {}    # ordered dedupe
    citations_used: list[str] = []
    uncited: list[str] = []
    for match in _CITATION_REGEX.finditer(prose):
        author, year = match.group(1).strip(), match.group(2).strip()
        text = f"({author}, {year})"
        if text in seen:
            continue
        seen[text] = True
        if (author, year) in pool_keys:
            citations_used.append(text)
        else:
            uncited.append(text)
    return {"citations_used": citations_used, "uncited_warnings": uncited}


@tool
def validate_citations(prose: str, reference_pool: list[dict]) -> dict:
    """Regex-scan prose for (Author, Year); classify each as used or uncited."""
    return validate_citations_plain(prose, reference_pool)
```

Note: if the existing implementation looks different, preserve its behavior and just extract the function. Run the full file's existing tests after refactoring:

Run: `pytest orchestrator/tests/test_tools_m5.py -v`
Expected: all pre-existing `validate_citations` tests still PASS.

- [ ] **Step 4: Run new tests**

Run: `pytest orchestrator/tests/test_tools_m5.py -v -k validate_citations_plain`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add orchestrator/tools/m5_writing.py orchestrator/tests/test_tools_m5.py
git commit -m "refactor(orchestrator): extract validate_citations_plain for SP6.5 autosave"
```

---

### Task 7: `_handle_rewrite` writes to `pending_edits` instead of `prose`

**Files:**
- Modify: `orchestrator/agents/m5_writing.py`
- Test: `orchestrator/tests/agents/test_m5_pending_edits.py`

- [ ] **Step 1: Write the failing tests**

```python
# orchestrator/tests/agents/test_m5_pending_edits.py
"""SP6.5: chat NL-rewrite no longer overwrites prose — it appends a
PendingEdit so the editor's unified accept/reject flow owns the resolution."""
from unittest.mock import patch
from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent


def _make_state(user_msg: str, partial: dict, project_id: str = "p1") -> dict:
    class _CS:
        m1_topic = {"language": "en", "research_title": "X"}
        m2_literature = {"research_gaps": []}
        m3_design = {"paradigm": "quantitative"}
        m4_analysis = {}
        m5_writing = partial
    return {
        "messages": [HumanMessage(content=user_msg)],
        "context_store": _CS(),
        "project_id": project_id,
    }


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_appends_pending_edit_not_prose(mock_rewrite):
    """A chat rewrite must not mutate chapters[i].prose directly anymore."""
    mock_rewrite.invoke.return_value = "REWRITTEN INTRO TEXT"
    partial = {
        "chapters": {
            "intro": {"name": "intro", "prose": "OLD INTRO", "pending_edits": []},
        },
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite chapter 1 to be less formal", partial)
    agent = M5Agent()
    result = agent.step(state)
    patch_data = result.context_patch
    intro = patch_data["chapters"]["intro"]
    assert intro["prose"] == "OLD INTRO"                        # unchanged
    assert len(intro["pending_edits"]) == 1
    edit = intro["pending_edits"][0]
    assert edit["source"] == "chat_rewrite"
    assert edit["new_text"] == "REWRITTEN INTRO TEXT"
    assert edit["old_text"] == "OLD INTRO"
    assert edit["from_offset"] == 0
    assert edit["to_offset"] == len("OLD INTRO")


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_emits_bubble_with_editor_link(mock_rewrite):
    mock_rewrite.invoke.return_value = "REWRITTEN"
    partial = {
        "chapters": {
            "intro": {"name": "intro", "prose": "OLD", "pending_edits": []},
        },
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite intro", partial, project_id="proj-abc")
    agent = M5Agent()
    result = agent.step(state)
    bubble_text = "\n".join(m.content for m in (result.extra_messages or []))
    assert "/editor" in bubble_text or "Open in editor" in bubble_text


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_stacks_multiple_pending_edits(mock_rewrite):
    """Two rewrites of the same chapter produce two PendingEdits."""
    mock_rewrite.invoke.side_effect = ["FIRST REWRITE", "SECOND REWRITE"]
    partial = {
        "chapters": {"intro": {"name": "intro", "prose": "OLD", "pending_edits": []}},
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite intro", partial)
    agent = M5Agent()
    first = agent.step(state)
    # Apply the patch back into partial to simulate context-store persistence
    partial["chapters"] = first.context_patch["chapters"]
    second = agent.step(_make_state("rewrite intro more concise", partial))
    edits = second.context_patch["chapters"]["intro"]["pending_edits"]
    assert len(edits) == 2
    assert edits[0]["new_text"] == "FIRST REWRITE"
    assert edits[1]["new_text"] == "SECOND REWRITE"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest orchestrator/tests/agents/test_m5_pending_edits.py -v`
Expected: FAIL — the existing `_handle_rewrite` overwrites prose.

- [ ] **Step 3: Modify `_handle_rewrite` to append PendingEdit**

In `orchestrator/agents/m5_writing.py`, find `_handle_rewrite`. Change its body so that instead of writing `chapters[name]["prose"] = new_text`, it appends a PendingEdit:

```python
# orchestrator/agents/m5_writing.py — inside M5Agent

from uuid import uuid4
from datetime import datetime, timezone
from langchain_core.messages import AIMessage
from orchestrator.schemas.m5_editor import PendingEdit


def _handle_rewrite(self, state, partial: dict) -> "ModuleStepResult":
    """SP6.5: chat NL-rewrite now lands as a PendingEdit (whole-chapter
    range) instead of overwriting prose. The user reviews + accepts in the
    editor — same accept/reject flow as paraphrase/translate/cite."""
    chapters = partial.get("chapters") or {}
    user_msg = self._latest_user_message(state["messages"])
    chapter_name = self._identify_chapter(user_msg)
    if not chapter_name or chapter_name not in chapters:
        return ModuleStepResult(
            transition=False,
            context_patch=partial,
            extra_messages=[AIMessage(content="I couldn't tell which chapter to rewrite. Try 'rewrite chapter 3' or 'rewrite methodology'.")],
        )
    old_prose = chapters[chapter_name].get("prose", "")
    context = self._extract_context_slice(state["context_store"])
    new_text = rewrite_chapter.invoke({
        "chapter_name": chapter_name,
        "current_prose": old_prose,
        "instruction": user_msg,
        "context": context,
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=0,
        to_offset=len(old_prose),
        old_text=old_prose,
        new_text=new_text,
        source="chat_rewrite",
        pending_at=datetime.now(timezone.utc),
    )
    existing = chapters[chapter_name].get("pending_edits", [])
    chapters[chapter_name]["pending_edits"] = existing + [pe.model_dump(mode="json")]
    project_id = state.get("project_id") or ""
    link = f"/chat/projects/{project_id}/editor" if project_id else "/editor"
    bubble = AIMessage(content=(
        f"Rewrite of **{chapter_name}** ready — review it in the editor "
        f"and click ✓ to accept or ✗ to reject. [Open in editor]({link})"
    ))
    new_partial = {**partial, "chapters": chapters}
    return ModuleStepResult(
        transition=False,
        context_patch=new_partial,
        extra_messages=[bubble],
    )
```

If the existing `_handle_rewrite` returns shape differs, preserve the signature but swap the body.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest orchestrator/tests/agents/test_m5_pending_edits.py -v`
Expected: PASS, 3 tests.

Also run the existing M5 agent tests to ensure no regression: `pytest orchestrator/tests/agents/ -v`
Expected: pre-existing M5 tests still PASS (compose, finalize, context-slice tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/m5_writing.py orchestrator/tests/agents/test_m5_pending_edits.py
git commit -m "feat(orchestrator): M5 chat-rewrite writes PendingEdit instead of prose"
```

---

## Phase 2 — Backend API (FastAPI endpoints under `/api/v1/projects/{pid}/m5`)

### Task 8: Router skeleton + `GET /chapters`

**Files:**
- Create: `api/app/routers/m5_editor.py`
- Modify: `api/app/main.py` (mount the router)
- Test: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing test**

```python
# api/tests/test_m5_editor_router.py
"""SP6.5: editor API smoke + GET /chapters."""
from __future__ import annotations

import uuid
import pytest


def _make_project_with_chapters(client, headers, db_session):
    from api.app.models import ContextStore, Project
    r = client.post("/api/v1/projects", json={"name": "X"}, headers=headers)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing = {
        "chapters": {
            "intro": {"name": "intro", "prose": "Hello world.", "pending_edits": []},
            "lit_review": {"name": "lit_review", "prose": "Lit body.", "pending_edits": []},
        }
    }
    db_session.commit()
    return pid


def test_get_chapters_returns_all(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/chapters", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "intro" in data
    assert data["intro"]["prose"] == "Hello world."


def test_get_chapters_returns_empty_dict_when_no_m5(orchestrator_client, auth_headers, db_session):
    r = orchestrator_client.post("/api/v1/projects", json={"name": "X"}, headers=auth_headers)
    pid = r.json()["id"]
    r = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/chapters", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {}


def test_get_chapters_404_for_other_user(orchestrator_client, auth_headers, other_user_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/chapters", headers=other_user_headers)
    assert r.status_code == 404


def test_get_chapters_requires_auth(orchestrator_client, db_session):
    fake = uuid.uuid4()
    r = orchestrator_client.get(f"/api/v1/projects/{fake}/m5/chapters")
    assert r.status_code in (401, 403)
```

If `orchestrator_client`, `auth_headers`, `other_user_headers`, `db_session` fixtures don't exist, check `api/tests/conftest.py` for the analogous ones used in `test_exports.py` and use those names.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v`
Expected: FAIL with `404 Not Found` (router not mounted).

- [ ] **Step 3: Create the router**

```python
# api/app/routers/m5_editor.py
"""SP6.5: editor API — chapter prose CRUD, inline AI tools, accept/reject."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import ContextStore, Project, User

router = APIRouter(tags=["m5_editor"])


def _owned_project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    """Reuse the SP6 exports.py pattern: 404 (not 403) to avoid existence leaks."""
    p = db.get(Project, project_id)
    if not p or p.user_id != user.id:
        raise HTTPException(status_code=404, detail={"error": {"code": "not_found"}})
    return p


def _m5_slice(db: Session, project_id: uuid.UUID) -> dict:
    cs = db.get(ContextStore, project_id)
    return (cs.m5_writing or {}) if cs else {}


@router.get("/projects/{project_id}/m5/chapters")
def list_chapters(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    m5 = _m5_slice(db, project_id)
    return m5.get("chapters", {})
```

- [ ] **Step 4: Mount the router**

Edit `api/app/main.py`. In the `if settings.orchestrator_enabled:` block, add after the `exports_router` line:

```python
from .routers import m5_editor as m5_editor_router  # SP6.5: editor surface
# ...
app.include_router(m5_editor_router.router, prefix="/api/v1")  # SP6.5
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k get_chapters`
Expected: PASS, 4 tests.

- [ ] **Step 6: Commit**

```bash
git add api/app/routers/m5_editor.py api/app/main.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): m5_editor router skeleton + GET /chapters (SP6.5)"
```

---

### Task 9: `PATCH /chapters/{name}` (autosave + re-validate citations)

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
def test_patch_chapter_updates_prose(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "Rewritten by user."},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["prose"] == "Rewritten by user."
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    assert cs.m5_writing["chapters"]["intro"]["prose"] == "Rewritten by user."


def test_patch_chapter_revalidates_citations(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    # Seed M2 ref pool with one paper
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m2_literature = {
        "research_gaps": [{"supporting_papers": [{"author": "Smith", "year": "2024"}]}]
    }
    db_session.commit()
    r = orchestrator_client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "See (Smith, 2024) and (Unknown, 2023)."},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["citations_used"] == ["(Smith, 2024)"]
    assert body["uncited_warnings"] == ["(Unknown, 2023)"]


def test_patch_unknown_chapter_returns_404(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/conclusion",  # not seeded
        json={"prose": "x"},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_patch_chapter_404_for_other_user(orchestrator_client, auth_headers, other_user_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "x"},
        headers=other_user_headers,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k patch_chapter`
Expected: FAIL with 405 Method Not Allowed.

- [ ] **Step 3: Implement PATCH endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
from pydantic import BaseModel

from sqlalchemy.orm.attributes import flag_modified

from orchestrator.tools.m5_writing import validate_citations_plain


_VALID_CHAPTER_NAMES = {"intro", "lit_review", "methodology", "results", "discussion", "conclusion"}


class PatchChapterBody(BaseModel):
    prose: str


def _collect_reference_pool(cs: ContextStore) -> list[dict]:
    """Mirror M5Agent._collect_references: dedupe by (author, year) preserving order."""
    m2 = (cs.m2_literature or {}) if cs else {}
    seen: dict[tuple, dict] = {}
    for gap in m2.get("research_gaps", []) or []:
        for paper in (gap.get("supporting_papers") or []):
            key = (str(paper.get("author", "")), str(paper.get("year", "")))
            if key not in seen:
                seen[key] = paper
    return list(seen.values())


@router.patch("/projects/{project_id}/m5/chapters/{chapter_name}")
def patch_chapter(
    project_id: uuid.UUID,
    chapter_name: str,
    body: PatchChapterBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    if chapter_name not in _VALID_CHAPTER_NAMES:
        raise HTTPException(404, detail={"error": {"code": "unknown_chapter"}})
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    if cs is None:
        raise HTTPException(404, detail={"error": {"code": "no_context"}})
    m5 = cs.m5_writing or {}
    chapters = m5.get("chapters") or {}
    if chapter_name not in chapters:
        raise HTTPException(404, detail={"error": {"code": "chapter_not_drafted"}})
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(body.prose, pool)
    chapters[chapter_name]["prose"] = body.prose
    chapters[chapter_name]["citations_used"] = validation["citations_used"]
    chapters[chapter_name]["uncited_warnings"] = validation["uncited_warnings"]
    m5["chapters"] = chapters
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")
    db.commit()
    return chapters[chapter_name]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k patch_chapter`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): PATCH /m5/chapters/{name} — autosave + revalidate citations (SP6.5)"
```

---

### Task 10: `GET /references` (M2 reference pool)

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
def test_get_references_returns_dedup_m2_pool(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    r = orchestrator_client.post("/api/v1/projects", json={"name": "X"}, headers=auth_headers)
    pid = r.json()["id"]
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m2_literature = {
        "research_gaps": [
            {"supporting_papers": [
                {"author": "Smith", "year": "2024", "title": "A"},
                {"author": "Jones", "year": "2023", "title": "B"},
            ]},
            {"supporting_papers": [
                {"author": "Smith", "year": "2024", "title": "A"},  # dup
            ]},
        ]
    }
    db_session.commit()
    r = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/references", headers=auth_headers)
    assert r.status_code == 200
    refs = r.json()
    assert len(refs) == 2
    assert all("id" in ref for ref in refs)  # endpoint must assign stable ids
    keys = {(r["author"], r["year"]) for r in refs}
    assert keys == {("Smith", "2024"), ("Jones", "2023")}


def test_get_references_returns_empty_when_no_m2(orchestrator_client, auth_headers, db_session):
    r = orchestrator_client.post("/api/v1/projects", json={"name": "X"}, headers=auth_headers)
    pid = r.json()["id"]
    r = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/references", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k get_references`
Expected: FAIL with 404.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
import hashlib


def _reference_id(ref: dict) -> str:
    """Stable derived id: sha1(author + year). Keeps the wire shape stable
    across server restarts without forcing a DB schema for references."""
    raw = f"{ref.get('author', '')}|{ref.get('year', '')}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


@router.get("/projects/{project_id}/m5/references")
def list_references(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    pool = _collect_reference_pool(cs) if cs else []
    return [{"id": _reference_id(r), **r} for r in pool]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k get_references`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): GET /m5/references — M2 reference pool with stable ids (SP6.5)"
```

---

### Task 11: `POST /chapters/{name}/paraphrase`

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
from unittest.mock import patch


@patch("orchestrator.tools.m5_inline._call_llm")
def test_paraphrase_creates_pending_edit(mock_llm, orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    from sqlalchemy.orm.attributes import flag_modified
    mock_llm.return_value = "A growing body of work suggests"
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    # Compute offsets dynamically to avoid hand-counting errors.
    full_prose = "The literature is broad. Recent studies have shown that algo decisions matter."
    target = "Recent studies have shown"
    from_o = full_prose.index(target)
    to_o = from_o + len(target)
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing["chapters"]["intro"]["prose"] = full_prose
    flag_modified(cs, "m5_writing")
    db_session.commit()
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/paraphrase",
        json={"from_offset": from_o, "to_offset": to_o, "style": "more formal"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    edit = r.json()
    assert edit["source"] == "paraphrase"
    assert edit["new_text"] == "A growing body of work suggests"
    assert edit["old_text"] == target
    assert edit["from_offset"] == from_o
    assert edit["to_offset"] == to_o
    cs2 = db_session.get(ContextStore, uuid.UUID(pid))
    assert len(cs2.m5_writing["chapters"]["intro"]["pending_edits"]) == 1


def test_paraphrase_404_unknown_chapter(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/conclusion/paraphrase",
        json={"from_offset": 0, "to_offset": 5},
        headers=auth_headers,
    )
    assert r.status_code == 404


def test_paraphrase_offsets_out_of_range_returns_400(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/paraphrase",
        json={"from_offset": 0, "to_offset": 9999},
        headers=auth_headers,
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k paraphrase`
Expected: FAIL with 404 / 405.

- [ ] **Step 3: Implement endpoint + helpers**

Append to `api/app/routers/m5_editor.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4

from orchestrator.schemas.m5_editor import PendingEdit
from orchestrator.tools.m5_inline import paraphrase_selection, translate_selection, build_citation_text


class ParaphraseBody(BaseModel):
    from_offset: int
    to_offset: int
    style: str = ""


def _validate_range(prose: str, from_offset: int, to_offset: int):
    if from_offset < 0 or to_offset < from_offset or to_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})


def _surrounding_context(prose: str, from_offset: int, to_offset: int) -> tuple[str, str]:
    """Return ~200 chars before and after the selection for LLM context."""
    before = prose[max(0, from_offset - 200): from_offset]
    after = prose[to_offset: to_offset + 200]
    return before, after


def _append_pending_edit(cs: ContextStore, chapter_name: str, pe: PendingEdit) -> dict:
    """Mutate cs.m5_writing in-place + flag for SQLAlchemy JSON change tracking."""
    m5 = cs.m5_writing or {}
    chapters = m5.get("chapters") or {}
    ch = chapters[chapter_name]
    existing = ch.get("pending_edits") or []
    edit_dict = pe.model_dump(mode="json")
    ch["pending_edits"] = existing + [edit_dict]
    chapters[chapter_name] = ch
    m5["chapters"] = chapters
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")
    return edit_dict


def _load_chapter_or_404(cs: ContextStore, chapter_name: str) -> dict:
    if chapter_name not in _VALID_CHAPTER_NAMES:
        raise HTTPException(404, detail={"error": {"code": "unknown_chapter"}})
    chapters = ((cs.m5_writing or {}).get("chapters") or {}) if cs else {}
    if chapter_name not in chapters:
        raise HTTPException(404, detail={"error": {"code": "chapter_not_drafted"}})
    return chapters[chapter_name]


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/paraphrase")
def paraphrase_chapter_selection(
    project_id: uuid.UUID,
    chapter_name: str,
    body: ParaphraseBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_range(prose, body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    language = ((cs.m1_topic or {}).get("language", "en")) if cs else "en"
    new_text = paraphrase_selection.invoke({
        "chapter_name": chapter_name,
        "language": language,
        "context_before": before,
        "selection": selection,
        "context_after": after,
        "style": body.style,
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.from_offset,
        to_offset=body.to_offset,
        old_text=selection,
        new_text=new_text,
        source="paraphrase",
        pending_at=datetime.now(timezone.utc),
        metadata={"style": body.style} if body.style else {},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k paraphrase`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/chapters/{name}/paraphrase — selection → PendingEdit (SP6.5)"
```

---

### Task 12: `POST /chapters/{name}/translate`

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
@patch("orchestrator.tools.m5_inline._call_llm")
def test_translate_creates_pending_edit_with_target_lang(mock_llm, orchestrator_client, auth_headers, db_session):
    mock_llm.return_value = "Một nghiên cứu gần đây"
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/translate",
        json={"from_offset": 0, "to_offset": 5, "target_lang": "vi"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    edit = r.json()
    assert edit["source"] == "translate"
    assert edit["new_text"] == "Một nghiên cứu gần đây"
    assert edit["metadata"]["target_lang"] == "vi"


def test_translate_400_on_missing_target_lang(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/translate",
        json={"from_offset": 0, "to_offset": 5},
        headers=auth_headers,
    )
    assert r.status_code == 422  # FastAPI body validation
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k translate`
Expected: FAIL with 404 / 405.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
class TranslateBody(BaseModel):
    from_offset: int
    to_offset: int
    target_lang: str


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/translate")
def translate_chapter_selection(
    project_id: uuid.UUID,
    chapter_name: str,
    body: TranslateBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    _validate_range(prose, body.from_offset, body.to_offset)
    before, after = _surrounding_context(prose, body.from_offset, body.to_offset)
    selection = prose[body.from_offset: body.to_offset]
    new_text = translate_selection.invoke({
        "chapter_name": chapter_name,
        "target_lang": body.target_lang,
        "context_before": before,
        "selection": selection,
        "context_after": after,
    })
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.from_offset,
        to_offset=body.to_offset,
        old_text=selection,
        new_text=new_text,
        source="translate",
        pending_at=datetime.now(timezone.utc),
        metadata={"target_lang": body.target_lang},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k translate`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/chapters/{name}/translate (SP6.5)"
```

---

### Task 13: `POST /chapters/{name}/cite`

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
def test_cite_inserts_pending_edit_with_canonical_text(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m2_literature = {
        "research_gaps": [{"supporting_papers": [{"author": "Smith", "year": "2024"}]}]
    }
    db_session.commit()
    # First fetch the ref to learn its id
    refs = orchestrator_client.get(f"/api/v1/projects/{pid}/m5/references", headers=auth_headers).json()
    ref_id = refs[0]["id"]
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 5, "reference_id": ref_id},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    edit = r.json()
    assert edit["source"] == "cite"
    assert edit["new_text"] == " (Smith, 2024)"
    assert edit["from_offset"] == edit["to_offset"] == 5
    assert edit["old_text"] == ""
    assert edit["metadata"]["reference_id"] == ref_id


def test_cite_404_on_unknown_reference(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/cite",
        json={"at_offset": 0, "reference_id": "nonexistent"},
        headers=auth_headers,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k cite`
Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
class CiteBody(BaseModel):
    at_offset: int
    reference_id: str


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/cite")
def cite_chapter(
    project_id: uuid.UUID,
    chapter_name: str,
    body: CiteBody,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    if body.at_offset < 0 or body.at_offset > len(prose):
        raise HTTPException(400, detail={"error": {"code": "offset_out_of_range"}})
    pool = _collect_reference_pool(cs)
    target = next((r for r in pool if _reference_id(r) == body.reference_id), None)
    if target is None:
        raise HTTPException(404, detail={"error": {"code": "reference_not_found"}})
    citation = " " + build_citation_text(target)
    pe = PendingEdit(
        id=uuid4().hex,
        chapter_name=chapter_name,
        from_offset=body.at_offset,
        to_offset=body.at_offset,
        old_text="",
        new_text=citation,
        source="cite",
        pending_at=datetime.now(timezone.utc),
        metadata={"reference_id": body.reference_id},
    )
    edit_dict = _append_pending_edit(cs, chapter_name, pe)
    db.commit()
    return edit_dict
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k cite`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/chapters/{name}/cite — insert canonical citation (SP6.5)"
```

---

### Task 14: `POST /pending/{eid}/accept` (with 409 on stale offsets)

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`
- Create: `api/tests/test_m5_editor_concurrency.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
def _seed_pending(db_session, project_id_str, chapter, **overrides):
    """Helper: drop a hand-rolled pending edit directly into the chapter."""
    from datetime import datetime, timezone
    from uuid import uuid4
    from api.app.models import ContextStore
    cs = db_session.get(ContextStore, uuid.UUID(project_id_str))
    edit = {
        "id": uuid4().hex,
        "chapter_name": chapter,
        "from_offset": 0,
        "to_offset": 5,
        "old_text": "Hello",
        "new_text": "Greetings",
        "source": "paraphrase",
        "pending_at": datetime.now(timezone.utc).isoformat(),
        "metadata": {},
    }
    edit.update(overrides)
    cs.m5_writing["chapters"][chapter]["pending_edits"].append(edit)
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(cs, "m5_writing")
    db_session.commit()
    return edit


def test_accept_splices_new_text_and_drops_edit(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    # Make prose match the seed
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing["chapters"]["intro"]["prose"] = "Hello world."
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(cs, "m5_writing")
    db_session.commit()
    edit = _seed_pending(db_session, pid, "intro")
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit['id']}/accept",
        headers=auth_headers,
    )
    assert r.status_code == 200
    ch = r.json()
    assert ch["prose"] == "Greetings world."
    assert ch["pending_edits"] == []


def test_accept_409_on_stale_offsets(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    from sqlalchemy.orm.attributes import flag_modified
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing["chapters"]["intro"]["prose"] = "DIFFERENT world."
    flag_modified(cs, "m5_writing")
    db_session.commit()
    edit = _seed_pending(db_session, pid, "intro")  # old_text="Hello" but prose now starts "DIFFE..."
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit['id']}/accept",
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "stale_offsets"


def test_accept_404_on_unknown_edit(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/nonexistent/accept",
        headers=auth_headers,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k accept`
Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
def _splice(prose: str, from_offset: int, to_offset: int, new_text: str) -> str:
    return prose[:from_offset] + new_text + prose[to_offset:]


def _find_and_pop_edit(chapter_dict: dict, edit_id: str) -> dict | None:
    edits = chapter_dict.get("pending_edits", [])
    for i, e in enumerate(edits):
        if e.get("id") == edit_id:
            return edits.pop(i)
    return None


@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/accept")
def accept_pending_edit(
    project_id: uuid.UUID,
    chapter_name: str,
    edit_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    prose = ch.get("prose", "")
    # Peek without popping to validate offsets first
    edits = ch.get("pending_edits", [])
    target = next((e for e in edits if e.get("id") == edit_id), None)
    if target is None:
        raise HTTPException(404, detail={"error": {"code": "edit_not_found"}})
    from_offset = target["from_offset"]
    to_offset = target["to_offset"]
    if from_offset > len(prose) or to_offset > len(prose) or prose[from_offset:to_offset] != target["old_text"]:
        raise HTTPException(
            409,
            detail={"error": {"code": "stale_offsets", "edit_id": edit_id}},
        )
    _find_and_pop_edit(ch, edit_id)
    new_prose = _splice(prose, from_offset, to_offset, target["new_text"])
    ch["prose"] = new_prose
    pool = _collect_reference_pool(cs)
    validation = validate_citations_plain(new_prose, pool)
    ch["citations_used"] = validation["citations_used"]
    ch["uncited_warnings"] = validation["uncited_warnings"]
    flag_modified(cs, "m5_writing")
    db.commit()
    return ch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k accept`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/.../accept — splice prose + drop edit + 409 stale (SP6.5)"
```

---

### Task 15: `POST /pending/{eid}/reject`

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing tests**

Append to `api/tests/test_m5_editor_router.py`:

```python
def test_reject_drops_edit_without_touching_prose(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    edit = _seed_pending(db_session, pid, "intro")
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/{edit['id']}/reject",
        headers=auth_headers,
    )
    assert r.status_code == 200
    ch = r.json()
    assert ch["prose"] == "Hello world."
    assert ch["pending_edits"] == []


def test_reject_404_on_unknown_edit(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/nope/reject",
        headers=auth_headers,
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k reject`
Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
@router.post("/projects/{project_id}/m5/chapters/{chapter_name}/pending/{edit_id}/reject")
def reject_pending_edit(
    project_id: uuid.UUID,
    chapter_name: str,
    edit_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    ch = _load_chapter_or_404(cs, chapter_name)
    popped = _find_and_pop_edit(ch, edit_id)
    if popped is None:
        raise HTTPException(404, detail={"error": {"code": "edit_not_found"}})
    flag_modified(cs, "m5_writing")
    db.commit()
    return ch
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k reject`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/.../reject — drop edit, prose untouched (SP6.5)"
```

---

### Task 16: `POST /m5/export` (re-run compile_pdf + export_docx)

**Files:**
- Modify: `api/app/routers/m5_editor.py`
- Modify: `api/tests/test_m5_editor_router.py`

- [ ] **Step 1: Write the failing test**

Append to `api/tests/test_m5_editor_router.py`:

```python
@patch("orchestrator.tools.m5_writing.export_docx.invoke")
@patch("orchestrator.tools.m5_writing.compile_pdf.invoke")
def test_export_runs_both_compilers_and_returns_artifacts(
    mock_pdf, mock_docx, orchestrator_client, auth_headers, db_session,
):
    from api.app.models import ContextStore
    mock_docx.return_value = {"s3_key": "projects/p/exports/thesis.docx", "size_bytes": 1234}
    mock_pdf.return_value = {"s3_key": "projects/p/exports/thesis.pdf", "size_bytes": 5678}
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)
    # Need all 6 chapters present for export to make sense
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    for name in ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]:
        cs.m5_writing["chapters"][name] = {"name": name, "prose": f"{name} prose.", "pending_edits": []}
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(cs, "m5_writing")
    db_session.commit()
    r = orchestrator_client.post(f"/api/v1/projects/{pid}/m5/export", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["docx"]["s3_key"] == "projects/p/exports/thesis.docx"
    assert body["pdf"]["size_bytes"] == 5678
    assert "download_url" in body["docx"]
    mock_docx.assert_called_once()
    mock_pdf.assert_called_once()


def test_export_400_when_chapters_incomplete(orchestrator_client, auth_headers, db_session):
    pid = _make_project_with_chapters(orchestrator_client, auth_headers, db_session)  # only 2 chapters
    r = orchestrator_client.post(f"/api/v1/projects/{pid}/m5/export", headers=auth_headers)
    assert r.status_code == 400
    assert "incomplete" in str(r.json()).lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest api/tests/test_m5_editor_router.py -v -k export`
Expected: FAIL.

- [ ] **Step 3: Implement endpoint**

Append to `api/app/routers/m5_editor.py`:

```python
from orchestrator.tools.m5_writing import compile_pdf, export_docx


_REQUIRED_CHAPTERS = ["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]


def _build_sections_for_export(chapters: dict) -> list[dict]:
    """Same shape M5Agent._build_sections_for_export produces.

    Each section is {"title": str, "prose": str} consumable by compile_pdf
    and export_docx, in the canonical 6-chapter order.
    """
    titles = {
        "intro": "Chapter 1 — Introduction",
        "lit_review": "Chapter 2 — Literature Review",
        "methodology": "Chapter 3 — Methodology",
        "results": "Chapter 4 — Results",
        "discussion": "Chapter 5 — Discussion",
        "conclusion": "Chapter 6 — Conclusion",
    }
    return [
        {"title": titles[name], "prose": chapters[name].get("prose", "")}
        for name in _REQUIRED_CHAPTERS
    ]


@router.post("/projects/{project_id}/m5/export")
def reexport(
    project_id: uuid.UUID,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    _owned_project(db, user, project_id)
    cs = db.get(ContextStore, project_id)
    m5 = (cs.m5_writing or {}) if cs else {}
    chapters = m5.get("chapters") or {}
    missing = [n for n in _REQUIRED_CHAPTERS if n not in chapters]
    if missing:
        raise HTTPException(400, detail={"error": {"code": "chapters_incomplete", "missing": missing}})
    sections = _build_sections_for_export(chapters)
    pid_str = str(project_id)
    docx_result = export_docx.invoke({"sections": sections, "project_id": pid_str})
    pdf_result = compile_pdf.invoke({"sections": sections, "project_id": pid_str})

    def _to_artifact(kind: str, res: dict) -> dict:
        return {
            "kind": kind,
            "s3_key": res["s3_key"],
            "size_bytes": res["size_bytes"],
            "download_url": f"/api/v1/projects/{pid_str}/exports/{res['s3_key'].split('/')[-1]}",
            "uri": "",
        }
    artifacts = [_to_artifact("docx", docx_result), _to_artifact("pdf", pdf_result)]
    m5["export_artifacts"] = artifacts
    cs.m5_writing = m5
    flag_modified(cs, "m5_writing")
    db.commit()
    return {"docx": artifacts[0], "pdf": artifacts[1]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest api/tests/test_m5_editor_router.py -v -k export`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add api/app/routers/m5_editor.py api/tests/test_m5_editor_router.py
git commit -m "feat(api): POST /m5/export — re-run compile_pdf + export_docx (SP6.5)"
```

---

### Task 17: Cross-endpoint auth + 404 sweep

**Files:**
- Create: `api/tests/test_m5_editor_auth.py`

- [ ] **Step 1: Write the auth test sweep**

```python
# api/tests/test_m5_editor_auth.py
"""SP6.5: confirm every editor endpoint enforces ownership."""
import uuid
import pytest


_ENDPOINTS_AND_METHODS = [
    ("GET",   "/m5/chapters",                       None),
    ("GET",   "/m5/chapters/intro",                 None),
    ("PATCH", "/m5/chapters/intro",                 {"prose": "x"}),
    ("GET",   "/m5/references",                     None),
    ("POST",  "/m5/chapters/intro/paraphrase",      {"from_offset": 0, "to_offset": 1}),
    ("POST",  "/m5/chapters/intro/translate",       {"from_offset": 0, "to_offset": 1, "target_lang": "vi"}),
    ("POST",  "/m5/chapters/intro/cite",            {"at_offset": 0, "reference_id": "x"}),
    ("POST",  "/m5/chapters/intro/pending/x/accept", None),
    ("POST",  "/m5/chapters/intro/pending/x/reject", None),
    ("POST",  "/m5/export",                          None),
]


def _make_project(client, headers):
    return client.post("/api/v1/projects", json={"name": "X"}, headers=headers).json()["id"]


@pytest.mark.parametrize("method,suffix,body", _ENDPOINTS_AND_METHODS)
def test_endpoint_requires_auth(method, suffix, body, orchestrator_client):
    """Without auth headers: every endpoint rejects."""
    fake_pid = uuid.uuid4()
    url = f"/api/v1/projects/{fake_pid}{suffix}"
    r = orchestrator_client.request(method, url, json=body)
    assert r.status_code in (401, 403), f"{method} {url} returned {r.status_code}"


@pytest.mark.parametrize("method,suffix,body", _ENDPOINTS_AND_METHODS)
def test_endpoint_404_for_other_user(method, suffix, body, orchestrator_client, auth_headers, other_user_headers):
    pid = _make_project(orchestrator_client, auth_headers)
    url = f"/api/v1/projects/{pid}{suffix}"
    r = orchestrator_client.request(method, url, json=body, headers=other_user_headers)
    assert r.status_code == 404, f"{method} {url} returned {r.status_code}"
```

- [ ] **Step 2: Run tests**

Run: `pytest api/tests/test_m5_editor_auth.py -v`
Expected: PASS for both sweeps (≈ 20 parametrized tests). Any 401/403 vs 404 mismatch indicates a real auth bug worth fixing.

- [ ] **Step 3: Commit**

```bash
git add api/tests/test_m5_editor_auth.py
git commit -m "test(api): SP6.5 editor endpoints auth + cross-user 404 sweep"
```

---

### Task 18: Concurrency test — autosave + accept race

**Files:**
- Create: `api/tests/test_m5_editor_concurrency.py`

- [ ] **Step 1: Write the test**

```python
# api/tests/test_m5_editor_concurrency.py
"""SP6.5: documented concurrency model.

- Autosave PATCH = last-writer-wins (no optimistic-lock token).
- Accept on stale offsets = 409.
- Two accepts on the same edit = 404 on the second (already consumed).
"""
import uuid


def _setup(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    from sqlalchemy.orm.attributes import flag_modified
    r = orchestrator_client.post("/api/v1/projects", json={"name": "X"}, headers=auth_headers)
    pid = r.json()["id"]
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing = {
        "chapters": {
            "intro": {
                "name": "intro",
                "prose": "Hello world.",
                "pending_edits": [{
                    "id": "edit-1",
                    "chapter_name": "intro",
                    "from_offset": 0, "to_offset": 5,
                    "old_text": "Hello", "new_text": "Greetings",
                    "source": "paraphrase",
                    "pending_at": "2026-05-27T00:00:00+00:00",
                    "metadata": {},
                }],
            },
        }
    }
    flag_modified(cs, "m5_writing")
    db_session.commit()
    return pid


def test_double_accept_returns_404_on_second(orchestrator_client, auth_headers, db_session):
    pid = _setup(orchestrator_client, auth_headers, db_session)
    r1 = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/edit-1/accept",
        headers=auth_headers,
    )
    assert r1.status_code == 200
    r2 = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/edit-1/accept",
        headers=auth_headers,
    )
    assert r2.status_code == 404


def test_patch_after_accept_overwrites_last_writer_wins(orchestrator_client, auth_headers, db_session):
    """Documents last-writer-wins: autosave PATCH after accept clobbers
    the splice. Acceptable in single-user/single-tab; the editor's frontend
    re-fetches after accept to avoid this in practice."""
    from api.app.models import ContextStore
    pid = _setup(orchestrator_client, auth_headers, db_session)
    orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/edit-1/accept",
        headers=auth_headers,
    )
    orchestrator_client.patch(
        f"/api/v1/projects/{pid}/m5/chapters/intro",
        json={"prose": "Original draft."},
        headers=auth_headers,
    )
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    assert cs.m5_writing["chapters"]["intro"]["prose"] == "Original draft."


def test_accept_with_shifted_prose_returns_409(orchestrator_client, auth_headers, db_session):
    from api.app.models import ContextStore
    from sqlalchemy.orm.attributes import flag_modified
    pid = _setup(orchestrator_client, auth_headers, db_session)
    # Shift prose so old_text no longer matches
    cs = db_session.get(ContextStore, uuid.UUID(pid))
    cs.m5_writing["chapters"]["intro"]["prose"] = "Modified world."
    flag_modified(cs, "m5_writing")
    db_session.commit()
    r = orchestrator_client.post(
        f"/api/v1/projects/{pid}/m5/chapters/intro/pending/edit-1/accept",
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert r.json()["detail"]["error"]["code"] == "stale_offsets"
```

- [ ] **Step 2: Run tests**

Run: `pytest api/tests/test_m5_editor_concurrency.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 3: Commit**

```bash
git add api/tests/test_m5_editor_concurrency.py
git commit -m "test(api): SP6.5 concurrency — double-accept, last-writer-wins, 409 stale"
```

---

## Phase 3 — Frontend infra (TipTap install + extensions + hooks)

### Task 19: Install TipTap dependencies

**Files:**
- Modify: `web/package.json`
- Modify: `web/package-lock.json`

- [ ] **Step 1: Install packages**

Run from `web/`:

```bash
cd web && npm install @tiptap/react @tiptap/starter-kit @tiptap/extension-bubble-menu @tiptap/core @tiptap/pm
```

- [ ] **Step 2: Verify the install**

Run: `cd web && npm list @tiptap/react`
Expected: shows installed version (e.g. `@tiptap/react@2.x.x`).

Run: `cd web && npx tsc --noEmit 2>&1 | grep -i tiptap || echo "no tiptap-related type errors"`
Expected: "no tiptap-related type errors" (existing pre-SP6.5 tsc errors in test fixtures stay, but nothing new from TipTap).

- [ ] **Step 3: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "deps(web): TipTap (react + starter-kit + bubble-menu + core + pm) for SP6.5"
```

---

### Task 20: TipTap custom mark — `AiPending`

**Files:**
- Create: `web/app/components/editor/extensions/AiPending.ts`
- Test: `web/app/components/editor/__tests__/AiPending.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/AiPending.test.ts
import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { AiPending } from "../extensions/AiPending";


function makeEditor(content = "<p>Hello world</p>") {
  return new Editor({ extensions: [StarterKit, AiPending], content });
}


describe("AiPending mark", () => {
  it("can be applied to a range and serializes attrs", () => {
    const editor = makeEditor();
    editor.commands.setTextSelection({ from: 1, to: 6 }); // "Hello"
    editor.commands.setMark("aiPending", {
      pendingId: "edit-1",
      source: "paraphrase",
      oldText: "Hello",
      newText: "Greetings",
    });
    const html = editor.getHTML();
    expect(html).toContain('data-pending-id="edit-1"');
    expect(html).toContain('data-source="paraphrase"');
    expect(html).toContain('data-old-text="Hello"');
    expect(html).toContain('class="ai-pending"');
  });

  it("can be removed by id", () => {
    const editor = makeEditor();
    editor.commands.setTextSelection({ from: 1, to: 6 });
    editor.commands.setMark("aiPending", {
      pendingId: "edit-1", source: "paraphrase",
      oldText: "Hello", newText: "Greetings",
    });
    editor.commands.unsetMark("aiPending");
    expect(editor.getHTML()).not.toContain("data-pending-id");
  });

  it("parses from HTML round-trip", () => {
    const html = '<p>x <span data-pending-id="e1" data-source="cite" data-old-text="" data-new-text=" (S, 2024)" class="ai-pending"> (S, 2024)</span></p>';
    const editor = new Editor({ extensions: [StarterKit, AiPending], content: html });
    expect(editor.getHTML()).toContain('data-pending-id="e1"');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/AiPending.test.ts`
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the mark**

```typescript
// web/app/components/editor/extensions/AiPending.ts
import { Mark, mergeAttributes } from "@tiptap/core";


export interface AiPendingAttrs {
  pendingId: string;
  source: "paraphrase" | "translate" | "cite" | "chat_rewrite";
  oldText: string;
  newText: string;
}


declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    aiPending: {
      setAiPending: (attrs: AiPendingAttrs) => ReturnType;
      unsetAiPending: () => ReturnType;
    };
  }
}


// Visual layer for the unified PendingEdit machinery. One mark serves
// paraphrase, translate, cite, and chat_rewrite — distinguished by `source`
// so CSS / portals can branch on the kind if needed.
export const AiPending = Mark.create({
  name: "aiPending",

  addAttributes() {
    return {
      pendingId: { default: null, parseHTML: el => el.getAttribute("data-pending-id"), renderHTML: a => ({ "data-pending-id": a.pendingId }) },
      source:    { default: "paraphrase", parseHTML: el => el.getAttribute("data-source"), renderHTML: a => ({ "data-source": a.source }) },
      oldText:   { default: "", parseHTML: el => el.getAttribute("data-old-text") ?? "", renderHTML: a => ({ "data-old-text": a.oldText }) },
      newText:   { default: "", parseHTML: el => el.getAttribute("data-new-text") ?? "", renderHTML: a => ({ "data-new-text": a.newText }) },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-pending-id]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "ai-pending" }), 0];
  },

  addCommands() {
    return {
      setAiPending: attrs => ({ commands }) => commands.setMark(this.name, attrs),
      unsetAiPending: () => ({ commands }) => commands.unsetMark(this.name),
    };
  },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/AiPending.test.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/extensions/AiPending.ts web/app/components/editor/__tests__/AiPending.test.ts
git commit -m "feat(web): AiPending TipTap mark — SP6.5 unified pending-edit visual layer"
```

---

### Task 21: TipTap custom mark — `CitationMark`

**Files:**
- Create: `web/app/components/editor/extensions/CitationMark.ts`
- Test: `web/app/components/editor/__tests__/CitationMark.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/CitationMark.test.ts
import { describe, it, expect } from "vitest";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { CitationMark } from "../extensions/CitationMark";


describe("CitationMark", () => {
  it("renders with data-ref attribute", () => {
    const editor = new Editor({ extensions: [StarterKit, CitationMark], content: "<p>See it.</p>" });
    editor.commands.setTextSelection({ from: 1, to: 4 }); // "See"
    editor.commands.setMark("citation", { referenceId: "ref-abc" });
    expect(editor.getHTML()).toContain('data-ref="ref-abc"');
    expect(editor.getHTML()).toContain('class="citation"');
  });

  it("round-trips through HTML", () => {
    const html = '<p>x <span data-ref="r1" class="citation">(Smith, 2024)</span></p>';
    const editor = new Editor({ extensions: [StarterKit, CitationMark], content: html });
    expect(editor.getHTML()).toContain('data-ref="r1"');
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/CitationMark.test.ts`
Expected: FAIL with "Cannot find module".

- [ ] **Step 3: Implement the mark**

```typescript
// web/app/components/editor/extensions/CitationMark.ts
import { Mark, mergeAttributes } from "@tiptap/core";


// Represents an inserted (Author, Year) — wraps the citation text and
// stores the back-link to the M2 reference id. Hover/click handlers live
// in the component layer; the mark just persists the linkage.
export const CitationMark = Mark.create({
  name: "citation",

  addAttributes() {
    return {
      referenceId: {
        default: null,
        parseHTML: el => el.getAttribute("data-ref"),
        renderHTML: a => ({ "data-ref": a.referenceId }),
      },
    };
  },

  parseHTML() {
    return [{ tag: "span[data-ref]" }];
  },

  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes, { class: "citation" }), 0];
  },
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/CitationMark.test.ts`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/extensions/CitationMark.ts web/app/components/editor/__tests__/CitationMark.test.ts
git commit -m "feat(web): CitationMark TipTap mark — back-link to M2 ref id (SP6.5)"
```

---

### Task 22: Hook — `useChapterAutosave`

**Files:**
- Create: `web/app/components/editor/hooks/useChapterAutosave.ts`
- Test: `web/app/components/editor/__tests__/useChapterAutosave.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/useChapterAutosave.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useChapterAutosave } from "../hooks/useChapterAutosave";


beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ prose: "x" }) });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});


describe("useChapterAutosave", () => {
  it("debounces multiple onChange calls into one PATCH", async () => {
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("first"); });
    act(() => { result.current.queue("second"); });
    act(() => { result.current.queue("third"); });
    expect(fetch).not.toHaveBeenCalled();
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(fetch).toHaveBeenCalledTimes(1);
    const call = (fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/v1/projects/p1/m5/chapters/intro");
    expect(call[1].method).toBe("PATCH");
    expect(JSON.parse(call[1].body).prose).toBe("third");
  });

  it("exposes saving / lastSavedAt", async () => {
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("x"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await waitFor(() => expect(result.current.saving).toBe(false));
    expect(result.current.lastSavedAt).not.toBeNull();
  });

  it("retries 3x on network failure", async () => {
    let calls = 0;
    (global.fetch as any) = vi.fn().mockImplementation(() => {
      calls++;
      if (calls < 3) return Promise.reject(new Error("net"));
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    const { result } = renderHook(() =>
      useChapterAutosave({ projectId: "p1", chapterName: "intro" })
    );
    act(() => { result.current.queue("x"); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    await act(async () => { await vi.advanceTimersByTimeAsync(250); });
    await act(async () => { await vi.advanceTimersByTimeAsync(1000); });
    expect(calls).toBe(3);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/useChapterAutosave.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

```typescript
// web/app/components/editor/hooks/useChapterAutosave.ts
import { useCallback, useRef, useState } from "react";


type Params = {
  projectId: string;
  chapterName: string;
  debounceMs?: number;
};


// Debounced PATCH /m5/chapters/{name}. Single-flight: the latest queued prose
// is what gets sent. Retries with exponential backoff (250ms / 1s / 4s) on
// network errors. After 3 retries, surfaces error via the returned state.
export function useChapterAutosave({ projectId, chapterName, debounceMs = 1000 }: Params) {
  const pendingProse = useRef<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const flush = useCallback(async () => {
    if (pendingProse.current === null) return;
    const prose = pendingProse.current;
    pendingProse.current = null;
    setSaving(true);
    const backoff = [250, 1000, 4000];
    let lastErr: Error | null = null;
    for (let i = 0; i < 3; i++) {
      try {
        const r = await fetch(
          `/api/v1/projects/${projectId}/m5/chapters/${chapterName}`,
          {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ prose }),
          }
        );
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        setLastSavedAt(new Date());
        setError(null);
        setSaving(false);
        return;
      } catch (e: any) {
        lastErr = e;
        if (i < 2) await new Promise(res => setTimeout(res, backoff[i]));
      }
    }
    setError(lastErr);
    setSaving(false);
  }, [projectId, chapterName]);

  const queue = useCallback((prose: string) => {
    pendingProse.current = prose;
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(flush, debounceMs);
  }, [flush, debounceMs]);

  return { queue, flush, saving, lastSavedAt, error };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/useChapterAutosave.test.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/hooks/useChapterAutosave.ts web/app/components/editor/__tests__/useChapterAutosave.test.ts
git commit -m "feat(web): useChapterAutosave — debounced PATCH + retry (SP6.5)"
```

---

### Task 23: Hook — `usePendingEdits`

**Files:**
- Create: `web/app/components/editor/hooks/usePendingEdits.ts`
- Test: `web/app/components/editor/__tests__/usePendingEdits.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/usePendingEdits.test.ts
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { usePendingEdits } from "../hooks/usePendingEdits";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ name: "intro", prose: "x", pending_edits: [] }),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("usePendingEdits", () => {
  it("acceptEdit hits the accept endpoint and revalidates", async () => {
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    await act(async () => { await result.current.acceptEdit("edit-1"); });
    const calls = (fetch as any).mock.calls.map((c: any[]) => c[0]);
    expect(calls).toContain("/api/v1/projects/p1/m5/chapters/intro/pending/edit-1/accept");
  });

  it("rejectEdit hits the reject endpoint", async () => {
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    await act(async () => { await result.current.rejectEdit("edit-2"); });
    const calls = (fetch as any).mock.calls.map((c: any[]) => c[0]);
    expect(calls).toContain("/api/v1/projects/p1/m5/chapters/intro/pending/edit-2/reject");
  });

  it("acceptEdit returns the conflict body on 409", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({
      ok: false, status: 409,
      json: async () => ({ detail: { error: { code: "stale_offsets", edit_id: "edit-1" } } }),
    });
    const { result } = renderHook(() =>
      usePendingEdits({ projectId: "p1", chapterName: "intro" })
    );
    const res = await result.current.acceptEdit("edit-1");
    expect(res.conflict).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/usePendingEdits.test.ts`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the hook**

```typescript
// web/app/components/editor/hooks/usePendingEdits.ts
import { useCallback } from "react";
import useSWR from "swr";


const fetcher = async (url: string) => {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
};


type Params = { projectId: string; chapterName: string };


type AcceptResult = { conflict: boolean; chapter?: any; editId: string };


export function usePendingEdits({ projectId, chapterName }: Params) {
  const url = `/api/v1/projects/${projectId}/m5/chapters/${chapterName}`;
  const { data, mutate } = useSWR(url, fetcher, { dedupingInterval: 0 });
  const pendingEdits = (data?.pending_edits ?? []) as any[];

  const acceptEdit = useCallback(async (editId: string): Promise<AcceptResult> => {
    const r = await fetch(`${url}/pending/${editId}/accept`, { method: "POST" });
    if (r.status === 409) {
      return { conflict: true, editId };
    }
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const chapter = await r.json();
    await mutate(chapter, { revalidate: false });
    return { conflict: false, chapter, editId };
  }, [url, mutate]);

  const rejectEdit = useCallback(async (editId: string) => {
    const r = await fetch(`${url}/pending/${editId}/reject`, { method: "POST" });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const chapter = await r.json();
    await mutate(chapter, { revalidate: false });
    return chapter;
  }, [url, mutate]);

  return { chapter: data, pendingEdits, acceptEdit, rejectEdit, refresh: () => mutate() };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/usePendingEdits.test.ts`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/hooks/usePendingEdits.ts web/app/components/editor/__tests__/usePendingEdits.test.ts
git commit -m "feat(web): usePendingEdits SWR hook — accept/reject + 409 surface (SP6.5)"
```

---

## Phase 4 — Frontend components (editor surface)

### Task 24: `EmptyState` — shown when no chapters drafted

**Files:**
- Create: `web/app/components/editor/EmptyState.tsx`
- Test: `web/app/components/editor/__tests__/EmptyState.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/EmptyState.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { EmptyState } from "../EmptyState";


describe("EmptyState", () => {
  it("renders the explanation copy", () => {
    render(<EmptyState projectId="abc" />);
    expect(screen.getByText(/M5 hasn't drafted/i)).toBeInTheDocument();
  });

  it("links back to the chat", () => {
    render(<EmptyState projectId="abc" />);
    const link = screen.getByRole("link", { name: /open chat/i });
    expect(link).toHaveAttribute("href", "/chat/projects/abc");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/EmptyState.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/EmptyState.tsx
import Link from "next/link";


// Editor route is always reachable; this surface appears when m5_writing.chapters
// is empty (M5 hasn't run or is mid-stream). Keeps the entry point predictable
// while pointing the user to where work actually happens.
export function EmptyState({ projectId }: { projectId: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6">
      <h2 className="text-xl font-semibold text-gray-900 mb-2">No chapters yet</h2>
      <p className="text-gray-600 mb-6 max-w-md">
        M5 hasn't drafted your chapters yet. Open the chat to start the writing module —
        the editor will populate as M5 produces each chapter.
      </p>
      <Link
        href={`/chat/projects/${projectId}`}
        className="inline-flex items-center px-4 py-2 bg-purple-600 text-white rounded-md text-sm font-medium hover:bg-purple-700"
      >
        Open chat
      </Link>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/EmptyState.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/EmptyState.tsx web/app/components/editor/__tests__/EmptyState.test.tsx
git commit -m "feat(web): EmptyState — points back to chat when chapters absent (SP6.5)"
```

---

### Task 25: `OutlineRail` — chapter switcher

**Files:**
- Create: `web/app/components/editor/OutlineRail.tsx`
- Test: `web/app/components/editor/__tests__/OutlineRail.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/OutlineRail.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { OutlineRail } from "../OutlineRail";


describe("OutlineRail", () => {
  it("renders all present chapters in canonical order", () => {
    render(
      <OutlineRail
        present={["intro", "lit_review", "methodology", "results", "discussion", "conclusion"]}
        active="methodology"
        onSelect={() => {}}
      />
    );
    const items = screen.getAllByRole("button");
    expect(items.map(b => b.textContent)).toEqual([
      "Ch 1 — Introduction",
      "Ch 2 — Literature Review",
      "Ch 3 — Methodology",
      "Ch 4 — Results",
      "Ch 5 — Discussion",
      "Ch 6 — Conclusion",
    ]);
  });

  it("highlights the active chapter", () => {
    render(<OutlineRail present={["intro", "lit_review"]} active="lit_review" onSelect={() => {}} />);
    const active = screen.getByRole("button", { name: /lit/i });
    expect(active.className).toMatch(/bg-/);  // some active styling
    expect(active).toHaveAttribute("aria-current", "true");
  });

  it("calls onSelect with the chapter name on click", () => {
    const onSelect = vi.fn();
    render(<OutlineRail present={["intro", "lit_review"]} active="intro" onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /literature/i }));
    expect(onSelect).toHaveBeenCalledWith("lit_review");
  });

  it("dims chapters not in `present`", () => {
    render(<OutlineRail present={["intro"]} active="intro" onSelect={() => {}} />);
    const drafting = screen.getByRole("button", { name: /literature/i });
    expect(drafting).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/OutlineRail.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/OutlineRail.tsx
"use client";


export type ChapterName = "intro" | "lit_review" | "methodology" | "results" | "discussion" | "conclusion";


const _ORDER: { name: ChapterName; label: string }[] = [
  { name: "intro",        label: "Ch 1 — Introduction" },
  { name: "lit_review",   label: "Ch 2 — Literature Review" },
  { name: "methodology",  label: "Ch 3 — Methodology" },
  { name: "results",      label: "Ch 4 — Results" },
  { name: "discussion",   label: "Ch 5 — Discussion" },
  { name: "conclusion",   label: "Ch 6 — Conclusion" },
];


type Props = {
  present: ChapterName[];        // which chapters M5 has produced
  active: ChapterName;
  onSelect: (name: ChapterName) => void;
};


// Left rail. Pure presentation — autosave-flush-before-switch logic lives in
// the parent so the rail stays unit-testable without server coupling.
export function OutlineRail({ present, active, onSelect }: Props) {
  return (
    <nav aria-label="Chapters" className="w-48 shrink-0 border-r border-gray-200 py-4 px-2 space-y-1">
      <div className="text-xs uppercase tracking-wider text-gray-400 px-2 mb-2">Outline</div>
      {_ORDER.map(({ name, label }) => {
        const isPresent = present.includes(name);
        const isActive = name === active;
        return (
          <button
            key={name}
            disabled={!isPresent}
            aria-current={isActive ? "true" : undefined}
            onClick={() => onSelect(name)}
            className={
              "w-full text-left text-sm px-3 py-2 rounded-md transition-colors " +
              (isActive
                ? "bg-purple-100 text-purple-900 font-medium"
                : isPresent
                ? "text-gray-700 hover:bg-gray-100"
                : "text-gray-400 cursor-not-allowed")
            }
          >
            {label}
          </button>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/OutlineRail.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/OutlineRail.tsx web/app/components/editor/__tests__/OutlineRail.test.tsx
git commit -m "feat(web): OutlineRail — 6-chapter switcher with active/disabled states (SP6.5)"
```

---

### Task 26: `PendingEditRibbon` — ✓/✗ accept/reject UI

**Files:**
- Create: `web/app/components/editor/PendingEditRibbon.tsx`
- Test: `web/app/components/editor/__tests__/PendingEditRibbon.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/PendingEditRibbon.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PendingEditRibbon } from "../PendingEditRibbon";


describe("PendingEditRibbon", () => {
  it("shows source label", () => {
    render(<PendingEditRibbon edit={{
      id: "e1", source: "paraphrase", oldText: "x", newText: "y", from_offset: 0, to_offset: 1,
    }} onAccept={() => {}} onReject={() => {}} stale={false} />);
    expect(screen.getByText(/paraphrase/i)).toBeInTheDocument();
  });

  it("calls onAccept when ✓ clicked", () => {
    const onAccept = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={onAccept} onReject={() => {}} stale={false} />);
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));
    expect(onAccept).toHaveBeenCalledWith("e1");
  });

  it("calls onReject when ✗ clicked", () => {
    const onReject = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={() => {}} onReject={onReject} stale={false} />);
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    expect(onReject).toHaveBeenCalledWith("e1");
  });

  it("renders stale state with Discard CTA", () => {
    const onReject = vi.fn();
    render(<PendingEditRibbon edit={{ id: "e1", source: "paraphrase", oldText: "", newText: "", from_offset: 0, to_offset: 0 }}
                              onAccept={() => {}} onReject={onReject} stale={true} />);
    expect(screen.getByText(/stale/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /discard/i }));
    expect(onReject).toHaveBeenCalledWith("e1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/PendingEditRibbon.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/PendingEditRibbon.tsx
"use client";


export type PendingEdit = {
  id: string;
  source: "paraphrase" | "translate" | "cite" | "chat_rewrite";
  oldText: string;
  newText: string;
  from_offset: number;
  to_offset: number;
};


type Props = {
  edit: PendingEdit;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  stale: boolean;          // server returned 409 on a previous accept attempt
};


const _LABEL: Record<PendingEdit["source"], string> = {
  paraphrase: "Paraphrase",
  translate:  "Translate",
  cite:       "Cite",
  chat_rewrite: "Chat rewrite",
};


// Floating ribbon rendered next to each AiPending mark. The actual portal
// mounting is handled by ChapterEditor's NodeView companion; this component
// is pure presentation + click handlers.
export function PendingEditRibbon({ edit, onAccept, onReject, stale }: Props) {
  if (stale) {
    return (
      <span className="inline-flex items-center gap-2 bg-red-50 border border-red-200 text-red-700 text-xs px-2 py-0.5 rounded">
        <span>Stale ({_LABEL[edit.source]})</span>
        <button
          type="button"
          onClick={() => onReject(edit.id)}
          className="font-medium hover:underline"
        >
          Discard
        </button>
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-2 bg-gray-900 text-white text-xs px-2 py-0.5 rounded">
      <span className="opacity-70">{_LABEL[edit.source]}</span>
      <button
        type="button"
        aria-label="Accept"
        onClick={() => onAccept(edit.id)}
        className="text-green-300 hover:text-green-200 font-medium"
      >
        ✓ Accept
      </button>
      <button
        type="button"
        aria-label="Reject"
        onClick={() => onReject(edit.id)}
        className="text-red-300 hover:text-red-200 font-medium"
      >
        ✗ Reject
      </button>
    </span>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/PendingEditRibbon.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/PendingEditRibbon.tsx web/app/components/editor/__tests__/PendingEditRibbon.test.tsx
git commit -m "feat(web): PendingEditRibbon — ✓/✗ accept/reject + stale state (SP6.5)"
```

---

### Task 27: `SelectionToolbar` — paraphrase/translate/cite buttons

**Files:**
- Create: `web/app/components/editor/SelectionToolbar.tsx`
- Test: `web/app/components/editor/__tests__/SelectionToolbar.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/SelectionToolbar.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { SelectionToolbar } from "../SelectionToolbar";


describe("SelectionToolbar", () => {
  it("renders three actions", () => {
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={() => {}} onCite={() => {}} />);
    expect(screen.getByRole("button", { name: /paraphrase/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /translate/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cite/i })).toBeInTheDocument();
  });

  it("fires onParaphrase when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={fn} onTranslate={() => {}} onCite={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /paraphrase/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("fires onTranslate when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={fn} onCite={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /translate/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("fires onCite when clicked", () => {
    const fn = vi.fn();
    render(<SelectionToolbar onParaphrase={() => {}} onTranslate={() => {}} onCite={fn} />);
    fireEvent.click(screen.getByRole("button", { name: /cite/i }));
    expect(fn).toHaveBeenCalledTimes(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/SelectionToolbar.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/SelectionToolbar.tsx
"use client";


type Props = {
  onParaphrase: () => void;
  onTranslate: () => void;
  onCite: () => void;
};


// Pure presentation. The parent (ChapterEditor) mounts this inside TipTap's
// BubbleMenu, which handles visibility based on selection state. Decoupling
// keeps this unit-testable without a TipTap instance.
export function SelectionToolbar({ onParaphrase, onTranslate, onCite }: Props) {
  return (
    <div className="inline-flex items-center gap-1 bg-gray-900 text-white text-xs rounded-md shadow-lg p-1">
      <button type="button" onClick={onParaphrase} className="px-2 py-1 hover:bg-gray-700 rounded">
        ✎ Paraphrase
      </button>
      <span className="text-gray-500">·</span>
      <button type="button" onClick={onTranslate} className="px-2 py-1 hover:bg-gray-700 rounded">
        🌐 Translate
      </button>
      <span className="text-gray-500">·</span>
      <button type="button" onClick={onCite} className="px-2 py-1 hover:bg-gray-700 rounded">
        📎 Cite
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/SelectionToolbar.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/SelectionToolbar.tsx web/app/components/editor/__tests__/SelectionToolbar.test.tsx
git commit -m "feat(web): SelectionToolbar — 3-action floating menu (SP6.5)"
```

---

### Task 28: `CitePopover` — typeahead over M2 references

**Files:**
- Create: `web/app/components/editor/CitePopover.tsx`
- Test: `web/app/components/editor/__tests__/CitePopover.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/CitePopover.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { CitePopover } from "../CitePopover";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ([
      { id: "r1", author: "Smith", year: "2024", title: "EU AI Act analysis" },
      { id: "r2", author: "Jones", year: "2023", title: "Algorithmic accountability" },
    ]),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("CitePopover", () => {
  it("loads and lists references from /m5/references", async () => {
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    expect(screen.getByText(/Jones/i)).toBeInTheDocument();
  });

  it("filters by typeahead query", async () => {
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Jones" } });
    await waitFor(() => {
      expect(screen.queryByText(/Smith/i)).not.toBeInTheDocument();
      expect(screen.getByText(/Jones/i)).toBeInTheDocument();
    });
  });

  it("calls onSelect with the reference id", async () => {
    const onSelect = vi.fn();
    render(<CitePopover projectId="p1" onSelect={onSelect} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Smith/i)).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Smith/i).closest("button")!);
    expect(onSelect).toHaveBeenCalledWith("r1");
  });

  it("shows empty-pool CTA when references list is empty", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    render(<CitePopover projectId="p1" onSelect={() => {}} onClose={() => {}} />);
    await waitFor(() => expect(screen.getByText(/No references/i)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/CitePopover.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/CitePopover.tsx
"use client";

import { useEffect, useState } from "react";


type Reference = { id: string; author: string; year: string; title?: string };


type Props = {
  projectId: string;
  onSelect: (referenceId: string) => void;
  onClose: () => void;
};


export function CitePopover({ projectId, onSelect, onClose }: Props) {
  const [refs, setRefs] = useState<Reference[] | null>(null);
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/projects/${projectId}/m5/references`)
      .then(r => r.json())
      .then(data => {
        if (!cancelled) setRefs(data);
      })
      .catch(() => {
        if (!cancelled) setRefs([]);
      });
    return () => { cancelled = true; };
  }, [projectId]);

  const filtered = (refs ?? []).filter(r => {
    if (!query) return true;
    const q = query.toLowerCase();
    return (
      r.author?.toLowerCase().includes(q) ||
      r.year?.toString().includes(q) ||
      r.title?.toLowerCase().includes(q)
    );
  });

  return (
    <div
      role="dialog"
      aria-label="Insert citation"
      className="bg-white border border-purple-300 rounded-md shadow-lg p-2 w-64 z-50"
    >
      <input
        type="text"
        autoFocus
        value={query}
        onChange={e => setQuery(e.target.value)}
        placeholder="Search references…"
        className="w-full text-sm px-2 py-1 border border-gray-200 rounded mb-2"
      />
      {refs === null && <div className="text-xs text-gray-400 px-2 py-1">Loading…</div>}
      {refs !== null && refs.length === 0 && (
        <div className="text-xs text-gray-500 px-2 py-2">
          No references yet. Citations are added in M2.{" "}
          <a href={`/chat/projects/${projectId}`} className="text-purple-600 underline">Open chat</a>
        </div>
      )}
      {refs !== null && refs.length > 0 && (
        <div className="max-h-48 overflow-y-auto flex flex-col gap-0.5">
          {filtered.map(r => (
            <button
              key={r.id}
              type="button"
              onClick={() => { onSelect(r.id); onClose(); }}
              className="text-left text-xs px-2 py-1.5 hover:bg-purple-50 rounded"
            >
              <div className="font-medium text-gray-900">
                {r.author} ({r.year})
              </div>
              {r.title && <div className="text-gray-500 truncate">{r.title}</div>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/CitePopover.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/CitePopover.tsx web/app/components/editor/__tests__/CitePopover.test.tsx
git commit -m "feat(web): CitePopover — typeahead over M2 ref pool (SP6.5)"
```

---

### Task 29: `TranslateMenu` — target-language picker

**Files:**
- Create: `web/app/components/editor/TranslateMenu.tsx`
- Test: `web/app/components/editor/__tests__/TranslateMenu.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/TranslateMenu.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { TranslateMenu } from "../TranslateMenu";


describe("TranslateMenu", () => {
  it("renders default language options", () => {
    render(<TranslateMenu defaultLang="vi" onConfirm={() => {}} onClose={() => {}} />);
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    const option = screen.getByRole("option", { name: /vietnamese/i }) as HTMLOptionElement;
    expect(option.selected).toBe(true);
  });

  it("calls onConfirm with selected language", () => {
    const onConfirm = vi.fn();
    render(<TranslateMenu defaultLang="en" onConfirm={onConfirm} onClose={() => {}} />);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "fr" } });
    fireEvent.click(screen.getByRole("button", { name: /translate/i }));
    expect(onConfirm).toHaveBeenCalledWith("fr");
  });

  it("cancel closes without confirming", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    render(<TranslateMenu defaultLang="en" onConfirm={onConfirm} onClose={onClose} />);
    fireEvent.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/TranslateMenu.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/TranslateMenu.tsx
"use client";

import { useState } from "react";


// Small popover with a target-language picker. Default value is whatever the
// project's m1_topic.language is; persisted to localStorage between sessions
// so frequent translators don't re-pick every time.
const _LANGUAGES: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "vi", label: "Vietnamese" },
  { code: "fr", label: "French" },
  { code: "es", label: "Spanish" },
  { code: "de", label: "German" },
  { code: "zh", label: "Chinese" },
  { code: "ja", label: "Japanese" },
  { code: "ko", label: "Korean" },
];


type Props = {
  defaultLang: string;
  onConfirm: (targetLang: string) => void;
  onClose: () => void;
};


export function TranslateMenu({ defaultLang, onConfirm, onClose }: Props) {
  const [lang, setLang] = useState(defaultLang || "en");

  return (
    <div role="dialog" aria-label="Translate selection" className="bg-white border border-purple-300 rounded-md shadow-lg p-3 w-56 z-50">
      <label className="text-xs text-gray-600 mb-1 block">Target language</label>
      <select
        value={lang}
        onChange={e => setLang(e.target.value)}
        className="w-full text-sm px-2 py-1 border border-gray-200 rounded mb-2"
      >
        {_LANGUAGES.map(l => (
          <option key={l.code} value={l.code}>{l.label}</option>
        ))}
      </select>
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onClose}
                className="text-xs px-3 py-1 text-gray-600 hover:bg-gray-100 rounded">
          Cancel
        </button>
        <button type="button" onClick={() => { onConfirm(lang); onClose(); }}
                className="text-xs px-3 py-1 bg-purple-600 text-white rounded hover:bg-purple-700">
          Translate
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/TranslateMenu.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/TranslateMenu.tsx web/app/components/editor/__tests__/TranslateMenu.test.tsx
git commit -m "feat(web): TranslateMenu — target-lang picker popover (SP6.5)"
```

---

### Task 30: `ReExportBar` — header with status + Re-export button

**Files:**
- Create: `web/app/components/editor/ReExportBar.tsx`
- Test: `web/app/components/editor/__tests__/ReExportBar.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/ReExportBar.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ReExportBar } from "../ReExportBar";


describe("ReExportBar", () => {
  it("shows last-export status", () => {
    const t = new Date(Date.now() - 5 * 60 * 1000);
    render(<ReExportBar lastExportAt={t} editsSinceExport={3} onReExport={() => Promise.resolve()} exporting={false} />);
    expect(screen.getByText(/last export/i)).toBeInTheDocument();
    expect(screen.getByText(/3 edits/i)).toBeInTheDocument();
  });

  it("calls onReExport when button clicked", async () => {
    const onReExport = vi.fn().mockResolvedValue(undefined);
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={onReExport} exporting={false} />);
    fireEvent.click(screen.getByRole("button", { name: /re-export/i }));
    expect(onReExport).toHaveBeenCalled();
  });

  it("disables the button while exporting", () => {
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={true} />);
    expect(screen.getByRole("button", { name: /exporting/i })).toBeDisabled();
  });

  it("shows error state when error provided", () => {
    render(<ReExportBar lastExportAt={null} editsSinceExport={0} onReExport={() => Promise.resolve()} exporting={false} error={new Error("S3 down")} />);
    expect(screen.getByText(/export failed/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/ReExportBar.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/ReExportBar.tsx
"use client";


type Props = {
  lastExportAt: Date | null;
  editsSinceExport: number;
  onReExport: () => Promise<void>;
  exporting: boolean;
  error?: Error | null;
};


function _formatRelative(t: Date | null): string {
  if (!t) return "never";
  const diff = Date.now() - t.getTime();
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  return `${h}h ago`;
}


// Pinned at the top of the editor surface. Always visible; conveys both
// "is your downloadable artifact fresh" and "how to refresh it." The freshness
// counter (`editsSinceExport`) is driven by the parent that watches the
// useChapterAutosave hook across all six chapters.
export function ReExportBar({ lastExportAt, editsSinceExport, onReExport, exporting, error }: Props) {
  return (
    <div className="flex items-center justify-between border-b border-gray-200 px-6 py-3 bg-white">
      <div className="text-sm">
        <span className="text-gray-500">Last export: </span>
        <span className="font-medium text-gray-900">{_formatRelative(lastExportAt)}</span>
        {editsSinceExport > 0 && (
          <span className="text-gray-500 ml-2">· {editsSinceExport} edits since</span>
        )}
        {error && (
          <span className="ml-3 text-red-600 text-xs">Export failed — {error.message}</span>
        )}
      </div>
      <button
        type="button"
        disabled={exporting}
        onClick={onReExport}
        className="text-sm px-4 py-1.5 bg-purple-600 text-white rounded-md font-medium hover:bg-purple-700 disabled:opacity-60 disabled:cursor-not-allowed"
      >
        {exporting ? "Exporting…" : "Re-export"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/ReExportBar.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/ReExportBar.tsx web/app/components/editor/__tests__/ReExportBar.test.tsx
git commit -m "feat(web): ReExportBar — freshness status + Re-export button (SP6.5)"
```

---

### Task 31: `SourcesRail` — read-only M2 reference browser

**Files:**
- Create: `web/app/components/editor/SourcesRail.tsx`
- Test: `web/app/components/editor/__tests__/SourcesRail.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/SourcesRail.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { SourcesRail } from "../SourcesRail";


beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ([
      { id: "r1", author: "Smith", year: "2024" },
      { id: "r2", author: "Jones", year: "2023" },
    ]),
  });
});
afterEach(() => vi.restoreAllMocks());


describe("SourcesRail", () => {
  it("renders M2 references", async () => {
    render(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Smith/)).toBeInTheDocument());
    expect(screen.getByText(/Jones/)).toBeInTheDocument();
  });

  it("shows count in header", async () => {
    render(<SourcesRail projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Sources/i)).toBeInTheDocument());
    expect(screen.getByText(/2/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/SourcesRail.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/SourcesRail.tsx
"use client";

import useSWR from "swr";


type Reference = { id: string; author: string; year: string; title?: string };


const fetcher = (url: string) => fetch(url).then(r => r.json());


// Right rail. Read-only browser of the M2 reference pool. Insertion happens
// via the SelectionToolbar's Cite popover; this rail is for "what's available
// to me" at-a-glance.
export function SourcesRail({ projectId }: { projectId: string }) {
  const { data } = useSWR<Reference[]>(`/api/v1/projects/${projectId}/m5/references`, fetcher);
  const refs = data ?? [];
  return (
    <aside className="w-56 shrink-0 border-l border-gray-200 py-4 px-3 overflow-y-auto">
      <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
        Sources ({refs.length})
      </div>
      {refs.length === 0 ? (
        <div className="text-xs text-gray-500">No references yet.</div>
      ) : (
        <ul className="space-y-1">
          {refs.map(r => (
            <li key={r.id} className="text-xs text-gray-700 bg-gray-50 rounded px-2 py-1">
              <div className="font-medium text-gray-900">{r.author} ({r.year})</div>
              {r.title && <div className="text-gray-500 truncate">{r.title}</div>}
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/SourcesRail.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/SourcesRail.tsx web/app/components/editor/__tests__/SourcesRail.test.tsx
git commit -m "feat(web): SourcesRail — read-only M2 reference browser (SP6.5)"
```

---

### Task 32: `ChapterEditor` — TipTap mount + selection toolbar + pending-edit reconciliation

This is the most complex component. We split it into 3 sub-steps: (32a) basic mount + autosave, (32b) selection toolbar wiring, (32c) pending-edit AiPending reconciliation.

**Files:**
- Create: `web/app/components/editor/ChapterEditor.tsx`
- Test: `web/app/components/editor/__tests__/ChapterEditor.test.tsx`

- [ ] **Step 1: Write the failing test (32a — mount + autosave wiring)**

```typescript
// web/app/components/editor/__tests__/ChapterEditor.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act, waitFor } from "@testing-library/react";
import { ChapterEditor } from "../ChapterEditor";


beforeEach(() => {
  vi.useFakeTimers();
  global.fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ name: "intro", prose: "Hello world.", pending_edits: [] }),
  });
});
afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});


describe("ChapterEditor — mount + autosave", () => {
  it("renders the chapter prose", async () => {
    render(<ChapterEditor projectId="p1" chapterName="intro" initialProse="Hello world." pendingEdits={[]} onPendingMutate={() => {}} onDirty={() => {}} />);
    await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/ChapterEditor.test.tsx`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement ChapterEditor (full component)**

```typescript
// web/app/components/editor/ChapterEditor.tsx
"use client";

import { useEditor, EditorContent, BubbleMenu } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useMemo, useState, useCallback, useRef } from "react";

import { AiPending } from "./extensions/AiPending";
import { CitationMark } from "./extensions/CitationMark";
import { SelectionToolbar } from "./SelectionToolbar";
import { CitePopover } from "./CitePopover";
import { TranslateMenu } from "./TranslateMenu";
import { PendingEditRibbon, type PendingEdit } from "./PendingEditRibbon";
import { useChapterAutosave } from "./hooks/useChapterAutosave";


type Props = {
  projectId: string;
  chapterName: string;
  initialProse: string;
  pendingEdits: PendingEdit[];
  defaultTargetLang?: string;
  onPendingMutate: () => void;         // call after server mutation so parent can refresh chapter
  onDirty: (dirty: boolean) => void;   // call when local edits become unsaved / saved
};


// Mounts one TipTap instance per chapter. Owns:
//   - autosave (PATCH on debounced edit)
//   - selection toolbar (paraphrase / translate / cite buttons via BubbleMenu)
//   - pending-edit reconciliation (apply AiPending marks for each server-side edit;
//     remove marks no longer on the server; surface accept/reject handlers per ribbon)
//   - stale-state tracking (an accept that 409'd flips that edit's ribbon to "Discard")
export function ChapterEditor({
  projectId,
  chapterName,
  initialProse,
  pendingEdits,
  defaultTargetLang,
  onPendingMutate,
  onDirty,
}: Props) {
  const [showCite, setShowCite] = useState(false);
  const [showTranslate, setShowTranslate] = useState(false);
  const [staleIds, setStaleIds] = useState<Set<string>>(new Set());
  const selectionRef = useRef<{ from: number; to: number } | null>(null);

  const autosave = useChapterAutosave({ projectId, chapterName });

  const editor = useEditor({
    extensions: [StarterKit, AiPending, CitationMark],
    content: `<p>${initialProse.replace(/\n/g, "</p><p>")}</p>`,
    onUpdate({ editor }) {
      const text = editor.getText();
      autosave.queue(text);
      onDirty(true);
    },
    onSelectionUpdate({ editor }) {
      const { from, to } = editor.state.selection;
      selectionRef.current = from === to ? null : { from, to };
    },
    immediatelyRender: false,
  });

  // Apply AiPending marks for every pending edit not already marked.
  // Remove marks whose pending_id is no longer in the list.
  useEffect(() => {
    if (!editor) return;
    const currentIds = new Set(pendingEdits.map(e => e.id));
    // Remove stale marks
    editor.state.doc.descendants((node, pos) => {
      node.marks.forEach(m => {
        if (m.type.name === "aiPending" && !currentIds.has(m.attrs.pendingId)) {
          editor.chain().setTextSelection({ from: pos, to: pos + node.nodeSize }).unsetMark("aiPending").run();
        }
      });
    });
    // Add missing marks. We tolerate offset drift by aligning to oldText prefix where possible.
    pendingEdits.forEach(edit => {
      const tr = editor.state.tr;
      const hasMark = (() => {
        let found = false;
        editor.state.doc.descendants(node => {
          if (found) return false;
          node.marks.forEach(m => {
            if (m.type.name === "aiPending" && m.attrs.pendingId === edit.id) found = true;
          });
          return !found;
        });
        return found;
      })();
      if (hasMark) return;
      const from = edit.from_offset + 1; // ProseMirror positions are 1-based at doc top
      const to = edit.to_offset + 1;
      if (from <= to && to <= editor.state.doc.content.size) {
        const markType = editor.schema.marks.aiPending;
        editor.view.dispatch(
          tr.addMark(from, to === from ? from + 1 : to, markType.create({
            pendingId: edit.id,
            source: edit.source,
            oldText: edit.oldText,
            newText: edit.newText,
          }))
        );
      }
    });
  }, [editor, pendingEdits]);

  // Action handlers — each one captures the current selection then POSTs the relevant endpoint.
  const _withSelection = useCallback(async (kind: "paraphrase" | "translate" | "cite", body: any) => {
    const sel = selectionRef.current;
    if (!sel && kind !== "cite") return;
    const url = `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/${kind}`;
    const payload = kind === "cite"
      ? { at_offset: editor?.state.selection.from ? editor.state.selection.from - 1 : 0, ...body }
      : { from_offset: sel!.from - 1, to_offset: sel!.to - 1, ...body };
    const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if (r.ok) {
      onPendingMutate();
    }
  }, [projectId, chapterName, editor, onPendingMutate]);

  const handleAccept = useCallback(async (editId: string) => {
    const r = await fetch(
      `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/accept`,
      { method: "POST" }
    );
    if (r.status === 409) {
      setStaleIds(prev => new Set(prev).add(editId));
      return;
    }
    if (r.ok) onPendingMutate();
  }, [projectId, chapterName, onPendingMutate]);

  const handleReject = useCallback(async (editId: string) => {
    const r = await fetch(
      `/api/v1/projects/${projectId}/m5/chapters/${chapterName}/pending/${editId}/reject`,
      { method: "POST" }
    );
    if (r.ok) {
      setStaleIds(prev => {
        const next = new Set(prev);
        next.delete(editId);
        return next;
      });
      onPendingMutate();
    }
  }, [projectId, chapterName, onPendingMutate]);

  useEffect(() => {
    if (autosave.lastSavedAt) onDirty(false);
  }, [autosave.lastSavedAt, onDirty]);

  if (!editor) return <div>Loading editor…</div>;

  return (
    <div className="flex-1 px-8 py-6 overflow-y-auto">
      <BubbleMenu editor={editor}>
        {!showCite && !showTranslate && (
          <SelectionToolbar
            onParaphrase={() => _withSelection("paraphrase", {})}
            onTranslate={() => setShowTranslate(true)}
            onCite={() => setShowCite(true)}
          />
        )}
        {showTranslate && (
          <TranslateMenu
            defaultLang={defaultTargetLang || "vi"}
            onConfirm={(targetLang) => _withSelection("translate", { target_lang: targetLang })}
            onClose={() => setShowTranslate(false)}
          />
        )}
        {showCite && (
          <CitePopover
            projectId={projectId}
            onSelect={(refId) => _withSelection("cite", { reference_id: refId })}
            onClose={() => setShowCite(false)}
          />
        )}
      </BubbleMenu>
      <EditorContent editor={editor} className="prose max-w-none" />

      {pendingEdits.length > 0 && (
        <div className="mt-6 border-t border-gray-200 pt-4 space-y-2">
          <div className="text-xs uppercase tracking-wider text-gray-400">Pending edits ({pendingEdits.length})</div>
          {pendingEdits.map(edit => (
            <div key={edit.id} className="bg-gray-50 rounded-md p-2 text-xs">
              <div className="text-gray-500 mb-1">
                <span className="line-through">{edit.oldText.slice(0, 80) || "(insertion)"}</span>
                {" → "}
                <span className="text-gray-900">{edit.newText.slice(0, 80)}</span>
              </div>
              <PendingEditRibbon
                edit={edit}
                onAccept={handleAccept}
                onReject={handleReject}
                stale={staleIds.has(edit.id)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/ChapterEditor.test.tsx`
Expected: PASS, 1 test.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/ChapterEditor.tsx web/app/components/editor/__tests__/ChapterEditor.test.tsx
git commit -m "feat(web): ChapterEditor — TipTap mount + autosave + selection toolbar + pending-edit reconciliation (SP6.5)"
```

---

### Task 33: `ThesisEditor` — top-level layout

**Files:**
- Create: `web/app/components/editor/ThesisEditor.tsx`
- Test: `web/app/components/editor/__tests__/ThesisEditor.test.tsx`

- [ ] **Step 1: Write the failing test**

```typescript
// web/app/components/editor/__tests__/ThesisEditor.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { ThesisEditor } from "../ThesisEditor";


beforeEach(() => {
  global.fetch = vi.fn().mockImplementation(async (url: string) => {
    if (typeof url === "string" && url.endsWith("/m5/chapters")) {
      return { ok: true, json: async () => ({
        intro: { name: "intro", prose: "Intro prose.", pending_edits: [] },
        lit_review: { name: "lit_review", prose: "Lit body.", pending_edits: [] },
      }) };
    }
    if (typeof url === "string" && url.includes("/m5/references")) {
      return { ok: true, json: async () => [] };
    }
    if (typeof url === "string" && url.includes("/m5/chapters/")) {
      return { ok: true, json: async () => ({ name: "intro", prose: "Intro prose.", pending_edits: [] }) };
    }
    return { ok: true, json: async () => ({}) };
  });
});
afterEach(() => vi.restoreAllMocks());


describe("ThesisEditor", () => {
  it("renders EmptyState when no chapters", async () => {
    (global.fetch as any) = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    render(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/M5 hasn't drafted/i)).toBeInTheDocument());
  });

  it("renders OutlineRail with present chapters when populated", async () => {
    render(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Ch 1 — Introduction/)).toBeInTheDocument());
    expect(screen.getByText(/Ch 2 — Literature Review/)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/editor/__tests__/ThesisEditor.test.tsx`
Expected: FAIL.

- [ ] **Step 3: Implement**

```typescript
// web/app/components/editor/ThesisEditor.tsx
"use client";

import { useState, useEffect, useCallback } from "react";
import useSWR from "swr";

import { OutlineRail, type ChapterName } from "./OutlineRail";
import { ChapterEditor } from "./ChapterEditor";
import { SourcesRail } from "./SourcesRail";
import { ReExportBar } from "./ReExportBar";
import { EmptyState } from "./EmptyState";


const fetcher = (url: string) => fetch(url).then(r => r.json());


type ChapterDict = Record<string, {
  name: string;
  prose: string;
  pending_edits: Array<{
    id: string;
    source: "paraphrase" | "translate" | "cite" | "chat_rewrite";
    old_text: string;
    new_text: string;
    from_offset: number;
    to_offset: number;
  }>;
}>;


function _toPendingEdits(raw: ChapterDict[string]["pending_edits"]) {
  return raw.map(e => ({
    id: e.id,
    source: e.source,
    oldText: e.old_text,
    newText: e.new_text,
    from_offset: e.from_offset,
    to_offset: e.to_offset,
  }));
}


// Top-level editor surface. Owns the chapter selection state, the
// editsSinceExport counter, and orchestrates re-export. Per-chapter logic
// (autosave + AiPending + selection toolbar) lives inside ChapterEditor —
// this component is layout + global state.
export function ThesisEditor({ projectId }: { projectId: string }) {
  const url = `/api/v1/projects/${projectId}/m5/chapters`;
  const { data: chapters, mutate } = useSWR<ChapterDict>(url, fetcher);
  const [active, setActive] = useState<ChapterName>("intro");
  const [lastExportAt, setLastExportAt] = useState<Date | null>(null);
  const [editsSinceExport, setEditsSinceExport] = useState(0);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<Error | null>(null);

  const handleDirty = useCallback((dirty: boolean) => {
    if (dirty) setEditsSinceExport(n => n + 1);
  }, []);

  const handleReExport = useCallback(async () => {
    setExporting(true);
    setExportError(null);
    try {
      const r = await fetch(`/api/v1/projects/${projectId}/m5/export`, { method: "POST" });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body?.detail?.error?.code || `HTTP ${r.status}`);
      }
      setLastExportAt(new Date());
      setEditsSinceExport(0);
    } catch (e: any) {
      setExportError(e);
    } finally {
      setExporting(false);
    }
  }, [projectId]);

  const onPendingMutate = useCallback(() => { void mutate(); }, [mutate]);

  // Beforeunload warning if dirty
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (editsSinceExport > 0) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [editsSinceExport]);

  if (!chapters) return <div className="flex items-center justify-center min-h-screen text-gray-500">Loading…</div>;
  if (Object.keys(chapters).length === 0) return <EmptyState projectId={projectId} />;

  const presentNames = Object.keys(chapters) as ChapterName[];
  const activeChapter = chapters[active];

  return (
    <div className="flex flex-col min-h-screen">
      <ReExportBar
        lastExportAt={lastExportAt}
        editsSinceExport={editsSinceExport}
        onReExport={handleReExport}
        exporting={exporting}
        error={exportError}
      />
      <div className="flex flex-1">
        <OutlineRail present={presentNames} active={active} onSelect={setActive} />
        {activeChapter ? (
          <ChapterEditor
            key={active}            // remount on chapter switch — clean editor state
            projectId={projectId}
            chapterName={active}
            initialProse={activeChapter.prose}
            pendingEdits={_toPendingEdits(activeChapter.pending_edits)}
            onPendingMutate={onPendingMutate}
            onDirty={handleDirty}
          />
        ) : (
          <div className="flex-1 flex items-center justify-center text-gray-400">
            Select a chapter to edit.
          </div>
        )}
        <SourcesRail projectId={projectId} />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/editor/__tests__/ThesisEditor.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/editor/ThesisEditor.tsx web/app/components/editor/__tests__/ThesisEditor.test.tsx
git commit -m "feat(web): ThesisEditor — layout + chapter switching + re-export orchestration (SP6.5)"
```

---

### Task 34: Route + layout for `/editor`

**Files:**
- Create: `web/app/(chat)/chat/projects/[pid]/editor/page.tsx`
- Create: `web/app/(chat)/chat/projects/[pid]/editor/layout.tsx`

- [ ] **Step 1: Create the layout**

```typescript
// web/app/(chat)/chat/projects/[pid]/editor/layout.tsx
import { ReactNode } from "react";


// Minimal layout — the editor surface is full-height and manages its own
// navigation. We don't reuse the chat shell here because the editor's outline
// rail replaces the threads sidebar.
export default function EditorLayout({ children }: { children: ReactNode }) {
  return <div className="bg-white min-h-screen">{children}</div>;
}
```

- [ ] **Step 2: Create the page**

```typescript
// web/app/(chat)/chat/projects/[pid]/editor/page.tsx
import { ThesisEditor } from "../../../../../components/editor/ThesisEditor";


export default async function EditorPage({ params }: { params: Promise<{ pid: string }> }) {
  const { pid } = await params;
  return <ThesisEditor projectId={pid} />;
}
```

- [ ] **Step 3: Smoke-check the build**

Run from `web/`:

```bash
cd web && npx next build 2>&1 | tail -40
```

Expected: build succeeds; the new route appears in the generated routes table.

- [ ] **Step 4: Commit**

```bash
git add 'web/app/(chat)/chat/projects/[pid]/editor/page.tsx' 'web/app/(chat)/chat/projects/[pid]/editor/layout.tsx'
git commit -m "feat(web): /chat/projects/[pid]/editor route entry for SP6.5"
```

---

## Phase 5 — Chat ↔ editor wiring + integration + roadmap

### Task 35: ChatHeader — "Open editor" button

**Files:**
- Modify: `web/app/components/chat/ChatHeader.tsx`
- Modify: `web/app/components/chat/ChatHeader.test.tsx`

- [ ] **Step 1: Read the existing ChatHeader to understand its props**

Run: `cat web/app/components/chat/ChatHeader.tsx | head -40`

You'll see the existing prop shape (likely `projectId`, `projectName`, etc.). Add a conditional "Open editor" link that's visible when `hasChapters` is true.

- [ ] **Step 2: Write the failing test**

Append to `web/app/components/chat/ChatHeader.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ChatHeader } from "./ChatHeader";


describe("ChatHeader — open-editor button (SP6.5)", () => {
  it("does not show 'Open editor' when chapters are absent", () => {
    render(<ChatHeader projectId="p1" projectName="X" hasChapters={false} />);
    expect(screen.queryByRole("link", { name: /open editor/i })).not.toBeInTheDocument();
  });

  it("shows 'Open editor' link to /chat/projects/{pid}/editor when chapters present", () => {
    render(<ChatHeader projectId="p1" projectName="X" hasChapters={true} />);
    const link = screen.getByRole("link", { name: /open editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });
});
```

If existing ChatHeader doesn't have `hasChapters` prop yet, the test will fail on render — that's the expected failure.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/chat/ChatHeader.test.tsx -t "Open editor"`
Expected: FAIL.

- [ ] **Step 4: Modify ChatHeader**

Open `web/app/components/chat/ChatHeader.tsx`. Add a `hasChapters?: boolean` prop and the conditional Link. Example diff (adapt to existing structure):

```typescript
// Add to Props type
hasChapters?: boolean;

// In the component header area (alongside any other right-side buttons), add:
{hasChapters && (
  <Link
    href={`/chat/projects/${projectId}/editor`}
    className="inline-flex items-center px-3 py-1 text-sm bg-purple-600 text-white rounded-md hover:bg-purple-700"
  >
    Open editor
  </Link>
)}
```

If `Link` isn't imported, add `import Link from "next/link";`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/chat/ChatHeader.test.tsx -t "Open editor"`
Expected: PASS, 2 tests.

Also run full ChatHeader tests to confirm no regression:

Run: `cd web && npx vitest run app/components/chat/ChatHeader.test.tsx`
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add web/app/components/chat/ChatHeader.tsx web/app/components/chat/ChatHeader.test.tsx
git commit -m "feat(web): ChatHeader 'Open editor' button gated on hasChapters (SP6.5)"
```

---

### Task 36: ChatPane — pass hasChapters to ChatHeader

ChatHeader's new `hasChapters` prop needs to come from somewhere — the parent ChatPane already loads the project state via SWR (it reads `context_store` for module progress). We thread the chapters-present flag.

**Files:**
- Modify: `web/app/components/chat/ChatPane.tsx`
- Modify: `web/app/components/chat/ChatPane.test.tsx`

- [ ] **Step 1: Find where ChatHeader is rendered in ChatPane**

Run: `cd web && grep -n "ChatHeader" app/components/chat/ChatPane.tsx`

You'll see one render site. Locate the SWR fetch for project state or `context_store` near the top of the component.

- [ ] **Step 2: Write the failing test (just verify the prop is passed)**

Append to `web/app/components/chat/ChatPane.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, waitFor, screen } from "@testing-library/react";
import { ChatPane } from "./ChatPane";


describe("ChatPane → ChatHeader integration (SP6.5)", () => {
  it("passes hasChapters=true when m5_writing.chapters has entries", async () => {
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (typeof url === "string" && url.endsWith("/threads")) {
        return { ok: true, json: async () => [] };
      }
      if (typeof url === "string" && url.includes("/projects/p1")) {
        return { ok: true, json: async () => ({
          id: "p1", name: "X",
          context_store: { m5_writing: { chapters: { intro: { prose: "x" } } } },
        }) };
      }
      return { ok: true, json: async () => ({}) };
    });
    render(<ChatPane projectId="p1" threadId="t1" />);
    await waitFor(() => expect(screen.queryByRole("link", { name: /open editor/i })).toBeInTheDocument());
  });
});
```

This test depends on the existing ChatPane shape. If it fetches different URLs, adapt the mock to match.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/chat/ChatPane.test.tsx -t "Open editor"`
Expected: FAIL — ChatHeader currently renders without `hasChapters`.

- [ ] **Step 4: Modify ChatPane**

Open `web/app/components/chat/ChatPane.tsx`. Where the project SWR data is in scope, derive:

```typescript
const hasChapters = Object.keys(
  project?.context_store?.m5_writing?.chapters ?? {}
).length > 0;
```

Pass it to ChatHeader:

```typescript
<ChatHeader projectId={projectId} projectName={project?.name} hasChapters={hasChapters} />
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/chat/ChatPane.test.tsx`
Expected: PASS (including the new test and all existing tests).

- [ ] **Step 6: Commit**

```bash
git add web/app/components/chat/ChatPane.tsx web/app/components/chat/ChatPane.test.tsx
git commit -m "feat(web): ChatPane threads hasChapters → ChatHeader (SP6.5)"
```

---

### Task 37: MessageBubble — render "Open in editor" CTA for rewrite-result bubbles

The M5 agent's chat-rewrite handler now emits a bubble that includes `[Open in editor](...)` markdown. MessageBubble currently renders `content` as `whitespace-pre-wrap` plain text. We add minimal markdown-link rendering for this one pattern.

**Files:**
- Modify: `web/app/components/chat/MessageBubble.tsx`
- Modify: `web/app/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Write the failing test**

Append to `web/app/components/chat/MessageBubble.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";


describe("MessageBubble — markdown link rendering (SP6.5)", () => {
  it("renders [text](url) as an anchor", () => {
    render(<MessageBubble role="assistant" content="Rewrite ready — [Open in editor](/chat/projects/p1/editor)" />);
    const link = screen.getByRole("link", { name: /open in editor/i });
    expect(link).toHaveAttribute("href", "/chat/projects/p1/editor");
  });

  it("leaves plain content untouched", () => {
    render(<MessageBubble role="assistant" content="No links here." />);
    expect(screen.getByText("No links here.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd web && npx vitest run app/components/chat/MessageBubble.test.tsx -t "markdown link"`
Expected: FAIL.

- [ ] **Step 3: Modify MessageBubble**

In `web/app/components/chat/MessageBubble.tsx`, replace the line `<div className="whitespace-pre-wrap">{content}</div>` with a helper-rendered version:

```typescript
// At top of file, alongside other helpers:
function _renderWithLinks(text: string): React.ReactNode[] {
  // Minimal markdown-link parser: [label](url). Preserves intervening text.
  const out: React.ReactNode[] = [];
  const regex = /\[([^\]]+)\]\(([^)]+)\)/g;
  let last = 0;
  let match: RegExpExecArray | null;
  let key = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) out.push(text.slice(last, match.index));
    out.push(
      <a
        key={`lnk-${key++}`}
        href={match[2]}
        className="underline text-purple-700 hover:text-purple-900"
      >
        {match[1]}
      </a>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// Replace the existing content render line with:
<div className="whitespace-pre-wrap">{_renderWithLinks(content)}</div>
```

Add `import React from "react";` if not already imported.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd web && npx vitest run app/components/chat/MessageBubble.test.tsx`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add web/app/components/chat/MessageBubble.tsx web/app/components/chat/MessageBubble.test.tsx
git commit -m "feat(web): MessageBubble renders [text](url) anchors — surfaces 'Open in editor' from M5 rewrites (SP6.5)"
```

---

### Task 38: End-to-end frontend integration — paraphrase → ribbon → accept

**Files:**
- Create: `web/app/components/editor/__tests__/editor-flow.integration.test.tsx`

- [ ] **Step 1: Write the integration test**

```typescript
// web/app/components/editor/__tests__/editor-flow.integration.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, waitFor, screen, fireEvent } from "@testing-library/react";
import { ThesisEditor } from "../ThesisEditor";


/**
 * Drives the editor through paraphrase → ribbon → accept end-to-end at the
 * fetch boundary. No real TipTap selection events — instead we verify that
 * the pending-edit list flows correctly through the server contract.
 */
describe("editor flow — chat rewrite → pending edit visible", () => {
  beforeEach(() => {
    let chapter = {
      name: "intro",
      prose: "Hello world.",
      pending_edits: [{
        id: "e1",
        source: "chat_rewrite",
        old_text: "Hello world.",
        new_text: "Greetings, world.",
        from_offset: 0,
        to_offset: 12,
      }],
    };
    global.fetch = vi.fn().mockImplementation(async (url: string, init?: any) => {
      if (typeof url === "string" && url.endsWith("/m5/chapters")) {
        return { ok: true, json: async () => ({ intro: chapter }) };
      }
      if (typeof url === "string" && url.endsWith("/m5/references")) {
        return { ok: true, json: async () => [] };
      }
      if (typeof url === "string" && url.endsWith("/m5/chapters/intro")) {
        return { ok: true, json: async () => chapter };
      }
      if (typeof url === "string" && url.includes("/pending/e1/accept")) {
        chapter = { ...chapter, prose: "Greetings, world.", pending_edits: [] };
        return { ok: true, json: async () => chapter };
      }
      if (typeof url === "string" && url.includes("/pending/e1/reject")) {
        chapter = { ...chapter, pending_edits: [] };
        return { ok: true, json: async () => chapter };
      }
      return { ok: true, json: async () => ({}) };
    });
  });
  afterEach(() => vi.restoreAllMocks());

  it("renders chat-rewrite pending edit + accepts it", async () => {
    render(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Pending edits/i)).toBeInTheDocument());
    expect(screen.getByText(/Greetings, world/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /accept/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Pending edits/i)).not.toBeInTheDocument();
    });
  });

  it("rejects the pending edit and keeps prose untouched", async () => {
    render(<ThesisEditor projectId="p1" />);
    await waitFor(() => expect(screen.getByText(/Pending edits/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    await waitFor(() => {
      expect(screen.queryByText(/Pending edits/i)).not.toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test**

Run: `cd web && npx vitest run app/components/editor/__tests__/editor-flow.integration.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/editor/__tests__/editor-flow.integration.test.tsx
git commit -m "test(web): SP6.5 editor end-to-end — pending edit → accept/reject"
```

---

### Task 39: Update platform pivot roadmap

**Files:**
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Update SP6 "Out of scope" section + add SP6.5 section**

Open `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`. Find the Sub-project 6 "Out of scope" block that currently reads:

```
- **WYSIWYG section editor, inline paraphrase / translate / cite tools → SP6.5**
```

Insert a new Sub-project 6.5 section after Sub-project 6:

```markdown
## Sub-project 6.5 — M5 Editor Surface ✅

**Status:** Shipped 2026-MM-DD (branch `feat/sp65-m5-editor`; TipTap WYSIWYG + 3 inline AI tools + unified PendingEdit accept/reject)

**Spec:** `docs/superpowers/specs/2026-05-27-sp65-m5-editor-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp65-m5-editor-plan.md`

**Delivers:**
- Dedicated editor route `/chat/projects/[pid]/editor` with per-chapter TipTap instances + outline rail + sources rail
- Three inline AI tools (paraphrase / translate / cite) via floating BubbleMenu — all produce `PendingEdit` records
- Unified accept/reject machinery: chat NL-rewrites now also land as `PendingEdit` instead of overwriting prose
- Autosave-debounced PATCH + explicit Re-export button (last-export status + edits-since counter)
- 409 stale-offset conflict path for accept
- `AiPending` TipTap custom mark + `CitationMark` for inline references
- 19 new API endpoints under `/m5/`, full auth + ownership coverage

**Decisions worth remembering for post-pivot work:**
- `PendingEdit.source` enum is the extensibility surface — adding a new AI tool means a new endpoint + adding to the enum, nothing else
- TipTap custom marks > custom nodes for "decorate existing text" features
- Chat as coordinator, editor as canvas — durable separation as more module editors land

**Out of scope (deferred):**
- Citation Manager UI (style switching, Zotero/Mendeley) → SP6.6
- LaTeX / Google Docs export → post-pivot
- Real-time multi-user collab → post-pivot
- Live web-search for citations → post-pivot
- AI style-consistency audit → post-pivot
```

Then in the "Status log" table at the bottom of the file, append a row:

```
| 2026-MM-DD | 6.5 | ⬜ → ✅ | M5 editor surface shipped — TipTap WYSIWYG + 3 inline AI tools + unified PendingEdit accept/reject |
```

Replace `2026-MM-DD` with the actual ship date.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs: SP6.5 shipped — roadmap entry + status log"
```

---

## End-of-plan checklist

After all 39 tasks ship, run the full test suite to confirm no regressions:

```bash
pytest -q                                        # backend (orchestrator + api)
cd web && npx vitest run                         # frontend
cd web && npx tsc --noEmit 2>&1 | grep -v ".next/dev/types" | grep error || echo "no new type errors"
```

Expected:
- Backend: existing tests still pass; new tests pass.
- Frontend: existing tests still pass; new tests pass.
- tsc: no new errors (pre-existing `.next/dev/types/` and test-fixture JSX errors are unrelated).

Branch + PR:
```bash
git checkout -b feat/sp65-m5-editor   # if not already on it
git push -u origin feat/sp65-m5-editor
gh pr create --title "feat: SP6.5 — M5 editor surface" --body "..."
```

---

## Out of scope (matches spec)

- Citation Manager UI (style switching, Zotero/Mendeley) → SP6.6
- LaTeX / Google Docs export → post-pivot
- Real-time multi-user collaboration → post-pivot
- Slash commands → post-pivot
- Live web-search for new citations → post-pivot
- AI-assisted style consistency check → post-pivot
- Editor-side named-checkpoint revision history → post-pivot
- Mobile responsive editor — desktop-first; mobile is post-pivot
