> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP4 — M3 Research Design (multi-method) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `M3Agent` paradigm-aware (quant / qual / mixed) with a flat improved `M3Output` schema, three new qual-flow tools, and one new widget variant (`list_editor`) extending the SP3 protocol.

**Architecture:** Single `M3Agent` overrides `_next_missing_field` to walk a paradigm-specific ordered field list (`_FIELDS_BY_PARADIGM`). New `ListEditorHint` Pydantic variant joins the SP3 `WidgetHint` discriminated union. Frontend gains `ListEditorWidget` with local state + batch-synthesize-on-Confirm. Mixed flow = composition of quant + qual branches; no new mixed-only code.

**Tech Stack:** Python 3.10+, Pydantic v2, FastAPI, LangChain 1.x, LangGraph 1.2+, React 19, Next.js 16, TypeScript, Tailwind 3, Vitest 2, MSW 2.

**Spec:** `docs/superpowers/specs/2026-05-27-sp4-m3-multi-method-design.md`
**Depends on:** Sub-projects 1, 2, 3, 7 (all on master).

---

## File map

### NEW backend files

```
orchestrator/prompts/m3/_options_tool_quant.json
orchestrator/prompts/m3/_options_tool_qual.json
orchestrator/prompts/m3/_options_design_qual.json
orchestrator/prompts/m3/_options_mixed_design_type.json
orchestrator/tests/agents/test_m3_paradigm_branching.py
orchestrator/tests/agents/test_m3_widgets.py
api/tests/test_m3_round_trip.py
```

### MODIFIED backend files

```
orchestrator/agents/widgets.py                          # add ListItem + ListEditorHint + extend WidgetHint union
orchestrator/tests/agents/test_widgets.py               # extend with ListEditorHint tests
orchestrator/schemas/m3.py                              # add paradigm-specific fields + @model_validator
orchestrator/tests/test_schemas.py                      # extend with M3Output validator tests
orchestrator/tools/m3_design.py                         # add suggest_themes + compose_interview_guide + suggest_purposive_criteria
orchestrator/tests/test_tools_m3.py                     # extend with qual tool tests
orchestrator/agents/m3_design.py                        # rewrite: paradigm-aware override + render_hint_for_field
orchestrator/prompts/m3.md                              # rewrite for paradigm branching + widget invitations
orchestrator/tests/test_agents_m3.py                    # update existing M3 auto-mode test if schema impacts it
api/tests/test_chat_messages_widgets.py                 # extend with list_editor SSE event coverage
```

### NEW frontend files

```
web/app/components/chat/widgets/ListEditorWidget.tsx
web/app/components/chat/widgets/ListEditorWidget.test.tsx
```

### MODIFIED frontend files

```
web/app/components/chat/widgets/types.ts                # add ListItem + ListEditorHint + extend WidgetHint
web/app/components/chat/widgets/types.test.ts           # extend fixture for ListEditorHint shape
web/app/components/chat/widgets/synthesize.ts           # add summarizeList helper + per-field list synthesizers
web/app/components/chat/widgets/synthesize.test.ts      # extend
web/app/components/chat/widgets/WidgetRenderer.tsx      # add 'list_editor' case to dispatch switch
web/app/components/chat/widgets/WidgetRenderer.test.tsx # extend
web/app/components/chat/MessageBubble.test.tsx          # +list_editor bubble-render test
web/app/components/chat/ChatPane.test.tsx               # +list_editor integration test
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md   # flip SP4 to ✅
```

---

## Task index (19 tasks)

| Phase | Tasks |
|---|---|
| A. Backend widget primitive | 1. `ListItem` + `ListEditorHint` Pydantic models |
| B. Backend schema | 2. `M3Output` extension + `@model_validator` |
| C. Backend options + tools | 3. Static option JSONs · 4. `suggest_themes` tool · 5. `compose_interview_guide` tool · 6. `suggest_purposive_criteria` tool |
| D. Backend M3 agent | 7. Paradigm-aware `_next_missing_field` · 8. `render_hint_for_field` for card_grid fields · 9. `render_hint_for_field` for list_editor fields · 10. M3 prompt rewrite |
| E. Backend API | 11. Chat router list_editor SSE coverage |
| F. Frontend types + synthesize | 12. `types.ts` extension · 13. `synthesize.ts` extension |
| G. Frontend widget | 14. `ListEditorWidget` component · 15. `WidgetRenderer` dispatch |
| H. Frontend integration | 16. `MessageBubble` list_editor test · 17. `ChatPane` integration |
| I. Backend round-trip | 18. `test_m3_round_trip.py` |
| J. Wrap-up | 19. Regression + roadmap flip |

---

## Phase A — Backend widget primitive

### Task 1: `ListItem` + `ListEditorHint` Pydantic models

**Files:**
- Modify: `orchestrator/agents/widgets.py`
- Modify: `orchestrator/tests/agents/test_widgets.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/agents/test_widgets.py`:

```python
def test_list_item_minimal():
    from orchestrator.agents.widgets import ListItem
    i = ListItem(id="t1", text="Theme 1")
    assert i.id == "t1"
    assert i.text == "Theme 1"
    assert i.sub_items == []
    assert i.meta == {}


def test_list_item_with_nested_sub_items():
    from orchestrator.agents.widgets import ListItem
    i = ListItem(
        id="t1", text="Theme 1",
        sub_items=[ListItem(id="s1", text="Sub A"), ListItem(id="s2", text="Sub B")],
        meta={"hypothesis": "H1"},
    )
    assert len(i.sub_items) == 2
    assert i.sub_items[0].text == "Sub A"
    assert i.meta["hypothesis"] == "H1"


def test_list_editor_hint_minimal():
    from orchestrator.agents.widgets import ListEditorHint, ListItem
    h = ListEditorHint(
        field_name="themes",
        title="Pick themes",
        initial_items=[ListItem(id="t1", text="A")],
    )
    assert h.widget_type == "list_editor"
    assert h.allow_nested is False
    assert h.confirm_label == "Confirm"
    assert h.reset_label == "Reset to suggested"


def test_list_editor_hint_model_dump():
    from orchestrator.agents.widgets import ListEditorHint, ListItem
    h = ListEditorHint(
        field_name="themes",
        title="Pick themes",
        initial_items=[ListItem(id="t1", text="A",
                                sub_items=[ListItem(id="s1", text="B")])],
        allow_nested=True,
    )
    blob = h.model_dump()
    assert blob["widget_type"] == "list_editor"
    assert blob["allow_nested"] is True
    assert blob["initial_items"][0]["sub_items"][0]["text"] == "B"


def test_widget_hint_union_resolves_list_editor():
    """The discriminated WidgetHint union should resolve a dict-shaped
    ListEditorHint payload to the correct variant."""
    from pydantic import TypeAdapter
    from orchestrator.agents.widgets import WidgetHint

    adapter = TypeAdapter(WidgetHint)
    payload = {
        "widget_type": "list_editor",
        "field_name": "themes",
        "title": "T",
        "initial_items": [{"id": "t1", "text": "A"}],
    }
    parsed = adapter.validate_python(payload)
    assert parsed.widget_type == "list_editor"
    assert parsed.field_name == "themes"
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/agents/test_widgets.py -v
```

Expected: FAIL — `cannot import name 'ListItem'` and `cannot import name 'ListEditorHint'`.

- [ ] **Step 3: Extend `orchestrator/agents/widgets.py`**

Replace the existing file body. The new file is:

```python
"""Pydantic models for module-agent widget render hints.

Each `WidgetHint` variant is serialized via `.model_dump()` into the
`messages.tool_calls_json` JSONB column. The frontend's WidgetRenderer
dispatches on `widget_type` to pick the right React component.

Future sub-projects (SP5-SP6) add new variants (e.g. `model_builder`,
`outline_editor`) to the discriminated union below — existing variants
and consumers are unaffected.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CardOption(BaseModel):
    value: str
    label: str
    description: str = ""
    icon: str | None = None


class CardGridHint(BaseModel):
    widget_type: Literal["card_grid"] = "card_grid"
    field_name: str
    title: str
    options: list[CardOption]
    columns: int = 3


# --- SP4: list_editor variant -------------------------------------------------

class ListItem(BaseModel):
    """One row in a ListEditorHint. sub_items lets the widget render a single
    level of nesting (e.g. themes → sub-themes). meta is a free-form bag for
    variant-specific extras (e.g. {"hypothesis": "H1"} on conceptual_model paths)."""
    id: str
    text: str
    sub_items: list["ListItem"] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


ListItem.model_rebuild()


class ListEditorHint(BaseModel):
    """Editable list. User edits locally, clicks Confirm to submit one final-state
    message (per Q5 decision in the SP4 design spec). Pairs with the
    summarizeList helper on the frontend that turns the final items into
    a bulleted natural-language message."""
    widget_type: Literal["list_editor"] = "list_editor"
    field_name: str
    title: str
    initial_items: list[ListItem]
    allow_nested: bool = False
    confirm_label: str = "Confirm"
    reset_label: str = "Reset to suggested"


# Discriminated union — future variants land here.
WidgetHint = Annotated[
    Union[CardGridHint, ListEditorHint],
    Field(discriminator="widget_type"),
]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_widgets.py -v
git add orchestrator/agents/widgets.py orchestrator/tests/agents/test_widgets.py
git commit -m "feat(orchestrator): ListItem + ListEditorHint + WidgetHint union extension"
```

Expected: 5 existing + 5 new = 10 PASS.

---

## Phase B — Backend schema

### Task 2: `M3Output` extension + `@model_validator`

**Files:**
- Modify: `orchestrator/schemas/m3.py`
- Modify: `orchestrator/tests/test_schemas.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_schemas.py`:

```python
def test_m3_output_unconfirmed_partial_is_valid():
    """In-progress partials should validate even without paradigm-specific fields."""
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        # No conceptual_model, no scale_items — but confirmed_at not set.
    )
    assert out.confirmed_at is None


def test_m3_output_quant_confirm_requires_artifacts():
    """Setting confirmed_at on a quant paradigm requires conceptual_model + scale_items."""
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="quantitative",
            design="PLS-SEM", tool="SmartPLS",
            sampling_strategy="convenience", target_sample_size=200,
            confirmed_at=datetime.now(timezone.utc),
            # missing conceptual_model + scale_items
        )


def test_m3_output_quant_confirm_with_artifacts_validates():
    out = M3Output(
        paradigm="quantitative",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="convenience", target_sample_size=200,
        conceptual_model={"constructs": ["TL", "EE"], "paths": []},
        scale_items=[{"construct": "TL", "items": ["I1", "I2"]}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.conceptual_model is not None


def test_m3_output_qual_confirm_requires_qual_artifacts():
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="qualitative",
            design="Thematic Analysis", tool="NVivo",
            sampling_strategy="purposive", target_sample_size=12,
            confirmed_at=datetime.now(timezone.utc),
            # missing themes + interview_guide + purposive_criteria
        )


def test_m3_output_mixed_confirm_requires_design_type_and_both_sets():
    with pytest.raises(ValidationError):
        M3Output(
            paradigm="mixed",
            design="PLS-SEM", tool="SmartPLS",
            sampling_strategy="hybrid", target_sample_size=200,
            confirmed_at=datetime.now(timezone.utc),
            # missing mixed_design_type + qual artifacts
        )


def test_m3_output_mixed_confirm_with_full_artifacts_validates():
    out = M3Output(
        paradigm="mixed",
        design="PLS-SEM", tool="SmartPLS",
        sampling_strategy="quant: random N=200; qual: purposive N=12",
        target_sample_size=200,
        mixed_design_type="sequential_explanatory",
        conceptual_model={"constructs": ["TL"], "paths": []},
        scale_items=[{"construct": "TL", "items": ["I1"]}],
        themes=[{"id": "t1", "theme": "Leadership style", "sub_themes": []}],
        interview_guide={"sections": [{"phase": "main", "questions": []}]},
        purposive_criteria=[{"criterion": "tenure >= 6 months"}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert out.mixed_design_type == "sequential_explanatory"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -20
```

Expected: FAIL — the new fields don't exist on `M3Output` and the validator isn't there yet.

- [ ] **Step 3: Replace `orchestrator/schemas/m3.py`**

```python
"""M3 Research Design output schema. Mirrors PRD §6.3.6.

SP4 makes paradigm-specific fields explicit and enforces them via a
@model_validator that only fires when `confirmed_at` is being set
(in-progress partials remain valid)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common import Paradigm

MixedDesignType = Literal["sequential_explanatory", "sequential_exploratory"]


class M3Output(BaseModel):
    # Shared common fields
    paradigm: Paradigm
    design: str = Field(..., description="e.g. PLS-SEM, Thematic Analysis, Sequential Explanatory")
    tool: str = Field(..., description="SmartPLS, NVivo, SPSS, ...")
    sampling_strategy: str
    target_sample_size: int = Field(..., gt=0)
    confirmed_at: datetime | None = None

    # Quant-only (required when paradigm == quantitative, or part of mixed)
    conceptual_model: dict | None = None
    scale_items: list[dict] | None = None
    hypotheses: list[dict] | None = None

    # Qual-only (required when paradigm == qualitative, or part of mixed)
    themes: list[dict] | None = None
    interview_guide: dict | None = None
    purposive_criteria: list[dict] | None = None

    # Mixed-only
    mixed_design_type: MixedDesignType | None = None

    # Backward-compat fields (existing M5 consumers read these names)
    constructs: list[dict] = Field(default_factory=list)
    questionnaire_text: str | None = None

    @model_validator(mode="after")
    def _require_by_paradigm(self):
        """Paradigm-specific required-field check, only fires when confirmed."""
        if self.confirmed_at is None:
            return self

        if self.paradigm == "quantitative":
            if not self.conceptual_model:
                raise ValueError("quantitative paradigm requires conceptual_model when confirmed")
            if not self.scale_items:
                raise ValueError("quantitative paradigm requires scale_items when confirmed")

        elif self.paradigm == "qualitative":
            if not self.themes:
                raise ValueError("qualitative paradigm requires themes when confirmed")
            if not self.interview_guide:
                raise ValueError("qualitative paradigm requires interview_guide when confirmed")
            if not self.purposive_criteria:
                raise ValueError("qualitative paradigm requires purposive_criteria when confirmed")

        elif self.paradigm == "mixed":
            if not self.mixed_design_type:
                raise ValueError("mixed paradigm requires mixed_design_type when confirmed")
            if not (self.conceptual_model and self.scale_items):
                raise ValueError("mixed paradigm requires quant artifacts when confirmed")
            if not (self.themes and self.interview_guide and self.purposive_criteria):
                raise ValueError("mixed paradigm requires qual artifacts when confirmed")

        return self
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -20
git add orchestrator/schemas/m3.py orchestrator/tests/test_schemas.py
git commit -m "feat(orchestrator): M3Output paradigm-specific fields + confirm-time validator"
```

Expected: existing schemas tests + 6 new M3 tests PASS.

---

## Phase C — Backend options + tools

### Task 3: Static option JSON files

**Files:**
- Create: `orchestrator/prompts/m3/_options_tool_quant.json`
- Create: `orchestrator/prompts/m3/_options_tool_qual.json`
- Create: `orchestrator/prompts/m3/_options_design_qual.json`
- Create: `orchestrator/prompts/m3/_options_mixed_design_type.json`

- [ ] **Step 1: Create the directory**

```bash
mkdir -p /Users/caonguyenvan/project/dothesis/orchestrator/prompts/m3
```

- [ ] **Step 2: Create `_options_tool_quant.json`**

```json
[
  {"value": "SmartPLS",     "label": "SmartPLS",        "description": "Variance-based SEM; small-to-medium samples with latent variables"},
  {"value": "AMOS",         "label": "IBM AMOS",        "description": "Covariance-based SEM; needs N ≥ 200; classic publishable choice"},
  {"value": "R lavaan",     "label": "R lavaan",        "description": "Open-source CB-SEM in R; reproducible workflows"},
  {"value": "SPSS",         "label": "SPSS",            "description": "Regression / ANOVA / mediation via PROCESS macro; no latent SEM"},
  {"value": "Stata",        "label": "Stata",           "description": "Regression / SEM via the sem command; common in economics"}
]
```

- [ ] **Step 3: Create `_options_tool_qual.json`**

```json
[
  {"value": "NVivo",        "label": "NVivo",           "description": "Industry-standard CAQDAS; coding, themes, queries"},
  {"value": "Atlas.ti",     "label": "Atlas.ti",        "description": "Code-and-retrieve with network views; similar to NVivo"},
  {"value": "Manual",       "label": "Manual (Word/Excel)", "description": "Hand-coding in spreadsheets; fine for small samples"}
]
```

- [ ] **Step 4: Create `_options_design_qual.json`**

```json
[
  {"value": "Thematic Analysis",   "label": "Thematic Analysis",  "description": "Identify, analyse, report patterns (Braun & Clarke 2006)"},
  {"value": "Grounded Theory",     "label": "Grounded Theory",    "description": "Build theory from data through coding cycles (Glaser & Strauss)"},
  {"value": "Phenomenological",    "label": "Phenomenological",   "description": "Explore lived experience of a phenomenon"},
  {"value": "Case Study",          "label": "Case Study",         "description": "Deep analysis of one or more bounded cases (Yin)"}
]
```

- [ ] **Step 5: Create `_options_mixed_design_type.json`**

```json
[
  {"value": "sequential_explanatory", "label": "Sequential Explanatory", "description": "Quant survey first → qual interviews after to explain unexpected results"},
  {"value": "sequential_exploratory", "label": "Sequential Exploratory", "description": "Qual interviews first → quant survey after to test constructs you discovered"}
]
```

- [ ] **Step 6: Validate + commit**

```bash
cd /Users/caonguyenvan/project/dothesis
python -c "import json; [json.load(open(f'orchestrator/prompts/m3/_options_{n}.json')) for n in ('tool_quant', 'tool_qual', 'design_qual', 'mixed_design_type')]"
git add orchestrator/prompts/m3/_options_*.json
git commit -m "feat(orchestrator): M3 card-grid option JSON files (tool quant/qual, design qual, mixed type)"
```

Expected: silent JSON validation success.

---

### Task 4: `suggest_themes` tool

**Files:**
- Modify: `orchestrator/tools/m3_design.py`
- Modify: `orchestrator/tests/test_tools_m3.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_tools_m3.py`:

```python
def test_suggest_themes_returns_structured(monkeypatch):
    import json
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import suggest_themes

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"id": "t1", "theme": "Cách thức lãnh đạo",
         "sub_themes": ["Tầm nhìn", "Giao tiếp"]},
        {"id": "t2", "theme": "Biểu hiện gắn kết",
         "sub_themes": ["Nhận thức", "Cảm xúc"]},
    ])
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_themes.invoke({
        "research_question": "How does transformational leadership affect engagement?",
        "paradigm": "qualitative",
        "gaps_summary": "",
    })
    assert isinstance(out, list)
    assert len(out) == 2
    assert out[0]["theme"] == "Cách thức lãnh đạo"
    assert "Tầm nhìn" in out[0]["sub_themes"]


def test_suggest_themes_returns_empty_on_malformed(monkeypatch):
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import suggest_themes

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_themes.invoke({
        "research_question": "x", "paradigm": "qualitative", "gaps_summary": "",
    })
    assert out == []
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py::test_suggest_themes_returns_structured -v
```

Expected: FAIL — `cannot import name 'suggest_themes'`.

- [ ] **Step 3: Append the tool to `orchestrator/tools/m3_design.py`**

```python
@tool
def suggest_themes(research_question: str, paradigm: str,
                   gaps_summary: str = "") -> list[dict]:
    """Suggest 3-5 themes (with sub-themes) for qualitative analysis.

    Returns: [{id, theme, sub_themes: [str]}, ...]
    Falls back to [] on malformed LLM response so the agent can show an
    empty list_editor for the user to fill from scratch.
    """
    llm = _get_llm()
    prompt = (
        "Suggest 3-5 themes for a qualitative analysis. For each theme, give 2-3 "
        "sub-themes. Respond with ONLY a JSON array: "
        '[{"id":"t1","theme":"<theme>","sub_themes":["<sub>","<sub>"]}, ...].\n\n'
        f"Research question: {research_question}\n"
        f"Paradigm: {paradigm}\n"
        f"Literature gaps summary (from M2): {gaps_summary or '(none provided)'}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_themes: malformed LLM response, returning empty list")
        return []
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py -v 2>&1 | tail -10
git add orchestrator/tools/m3_design.py orchestrator/tests/test_tools_m3.py
git commit -m "feat(orchestrator): suggest_themes tool"
```

Expected: existing M3-tool tests + 2 new PASS.

---

### Task 5: `compose_interview_guide` tool

**Files:**
- Modify: `orchestrator/tools/m3_design.py`
- Modify: `orchestrator/tests/test_tools_m3.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_compose_interview_guide_returns_structured(monkeypatch):
    import json
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import compose_interview_guide

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "sections": [
            {"phase": "intro", "time_minutes": 5,
             "questions": [{"q": "Tell me about your role.", "probes": []}]},
            {"phase": "main", "time_minutes": 40,
             "questions": [
                 {"q": "How does your manager inspire you?",
                  "probes": ["Can you give an example?"]},
             ]},
            {"phase": "closing", "time_minutes": 5,
             "questions": [{"q": "Anything you'd like to add?", "probes": []}]},
        ]
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = compose_interview_guide.invoke({
        "themes": [{"theme": "Leadership style", "sub_themes": ["vision"]}],
        "research_question": "How does TL affect EE?",
    })
    assert "sections" in out
    assert len(out["sections"]) == 3
    assert out["sections"][1]["questions"][0]["probes"] == ["Can you give an example?"]


def test_compose_interview_guide_falls_back_on_malformed(monkeypatch):
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import compose_interview_guide

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "garbage"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = compose_interview_guide.invoke({
        "themes": [], "research_question": "x",
    })
    # Fallback: one minimal main-phase section
    assert "sections" in out
    assert len(out["sections"]) >= 1
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py::test_compose_interview_guide_returns_structured -v
```

Expected: FAIL — `cannot import name 'compose_interview_guide'`.

- [ ] **Step 3: Append the tool**

```python
@tool
def compose_interview_guide(themes: list[dict], research_question: str) -> dict:
    """Build a semi-structured interview guide from themes.

    Returns: {sections: [{phase: "intro"|"main"|"closing", time_minutes,
              questions: [{q, probes: [str]}]}]}
    Falls back to a one-section minimal guide on malformed LLM response.
    """
    llm = _get_llm()
    prompt = (
        "Build a semi-structured interview guide. Three sections: intro (5 min, "
        "warm-up and consent), main (40-50 min, theme-driven questions with probes), "
        "closing (5 min, wrap-up). For each main-phase question, give 1-2 probes. "
        "Respond with ONLY a JSON object: "
        '{"sections":[{"phase":"intro","time_minutes":5,"questions":[{"q":"...","probes":[]}]},'
        '{"phase":"main","time_minutes":40,"questions":[{"q":"...","probes":["..."]}]},'
        '{"phase":"closing","time_minutes":5,"questions":[{"q":"...","probes":[]}]}]}.\n\n'
        f"Research question: {research_question}\n"
        f"Themes: {json.dumps(themes, ensure_ascii=False)}"
    )
    try:
        return dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("compose_interview_guide: malformed LLM response, returning fallback")
        return {
            "sections": [
                {"phase": "main", "time_minutes": 45,
                 "questions": [{"q": "Tell me about your experience.", "probes": []}]},
            ]
        }
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py -v 2>&1 | tail -10
git add orchestrator/tools/m3_design.py orchestrator/tests/test_tools_m3.py
git commit -m "feat(orchestrator): compose_interview_guide tool"
```

Expected: all M3-tool tests PASS.

---

### Task 6: `suggest_purposive_criteria` tool

**Files:**
- Modify: `orchestrator/tools/m3_design.py`
- Modify: `orchestrator/tests/test_tools_m3.py`

- [ ] **Step 1: Append the failing tests**

```python
def test_suggest_purposive_criteria_returns_structured(monkeypatch):
    import json
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import suggest_purposive_criteria

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "criteria": [
            "Employees at SMEs (< 300 staff)",
            "At least 6 months tenure",
            "Has a direct line manager",
        ],
        "strategies": ["Snowball", "Maximum variation"],
        "saturation_min": 10, "saturation_max": 15,
    })
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_purposive_criteria.invoke({
        "research_question": "How does TL affect EE in Vietnamese SMEs?",
        "paradigm": "qualitative",
    })
    assert "criteria" in out
    assert len(out["criteria"]) == 3
    assert out["saturation_min"] == 10


def test_suggest_purposive_criteria_falls_back_on_malformed(monkeypatch):
    from unittest.mock import MagicMock
    from orchestrator.tools.m3_design import suggest_purposive_criteria

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "{ broken"
    monkeypatch.setattr("orchestrator.tools.m3_design._get_llm", lambda: fake_llm)

    out = suggest_purposive_criteria.invoke({
        "research_question": "x", "paradigm": "qualitative",
    })
    assert "criteria" in out
    assert isinstance(out["criteria"], list)
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py::test_suggest_purposive_criteria_returns_structured -v
```

- [ ] **Step 3: Append the tool**

```python
@tool
def suggest_purposive_criteria(research_question: str,
                                paradigm: str) -> dict:
    """Propose sampling criteria and strategies for qualitative purposive sampling.

    Returns: {criteria: list[str], strategies: list[str],
              saturation_min: int, saturation_max: int}
    Falls back to a generic criteria list on malformed LLM response.
    """
    llm = _get_llm()
    prompt = (
        "Propose purposive sampling criteria and supplementary strategies for "
        "a qualitative study. Provide 3-5 criteria, 1-3 strategies, and a "
        "saturation range. Respond with ONLY a JSON object: "
        '{"criteria":["..."],"strategies":["Snowball","Maximum variation"],'
        '"saturation_min":10,"saturation_max":15}.\n\n'
        f"Research question: {research_question}\nParadigm: {paradigm}"
    )
    try:
        return dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_purposive_criteria: malformed LLM response, returning fallback")
        return {
            "criteria": ["Participants directly experience the phenomenon under study"],
            "strategies": ["Snowball", "Maximum variation"],
            "saturation_min": 10, "saturation_max": 15,
        }
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m3.py -v 2>&1 | tail -10
git add orchestrator/tools/m3_design.py orchestrator/tests/test_tools_m3.py
git commit -m "feat(orchestrator): suggest_purposive_criteria tool"
```

Expected: all M3-tool tests PASS.

---

## Phase D — Backend M3 agent

### Task 7: Paradigm-aware `_next_missing_field`

**Files:**
- Modify: `orchestrator/agents/m3_design.py`
- Create: `orchestrator/tests/agents/test_m3_paradigm_branching.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m3_paradigm_branching.py`:

```python
"""Tests for M3Agent's paradigm-aware _next_missing_field override."""
from orchestrator.agents.m3_design import M3Agent


def test_quant_walk_order():
    agent = M3Agent()
    partial = {"paradigm": "quantitative"}
    # All quant required fields empty → first missing = "design"
    assert agent._next_missing_field(partial) == "design"

    partial["design"] = "PLS-SEM"
    assert agent._next_missing_field(partial) == "tool"

    partial["tool"] = "SmartPLS"
    assert agent._next_missing_field(partial) == "conceptual_model"

    partial["conceptual_model"] = {"constructs": ["TL"], "paths": []}
    assert agent._next_missing_field(partial) == "scale_items"

    partial["scale_items"] = [{"construct": "TL", "items": ["I1"]}]
    assert agent._next_missing_field(partial) == "target_sample_size"

    partial["target_sample_size"] = 200
    assert agent._next_missing_field(partial) == "sampling_strategy"

    partial["sampling_strategy"] = "convenience"
    assert agent._next_missing_field(partial) is None  # all filled


def test_qual_walk_order():
    agent = M3Agent()
    partial = {"paradigm": "qualitative"}
    assert agent._next_missing_field(partial) == "design"

    partial.update({"design": "Thematic Analysis", "tool": "NVivo"})
    assert agent._next_missing_field(partial) == "themes"

    partial["themes"] = [{"id": "t1", "theme": "X"}]
    assert agent._next_missing_field(partial) == "interview_guide"

    partial["interview_guide"] = {"sections": [{"phase": "main"}]}
    assert agent._next_missing_field(partial) == "purposive_criteria"


def test_mixed_first_field_is_design_type():
    agent = M3Agent()
    partial = {"paradigm": "mixed"}
    assert agent._next_missing_field(partial) == "mixed_design_type"


def test_mixed_seq_explanatory_walk_switches_after_design_type():
    agent = M3Agent()
    partial = {"paradigm": "mixed", "mixed_design_type": "sequential_explanatory"}
    # After mixed_design_type is filled, walk starts with quant fields.
    assert agent._next_missing_field(partial) == "design"


def test_mixed_seq_exploratory_walk_starts_with_qual():
    """Exploratory order in _FIELDS_BY_PARADIGM is:
    [mixed_design_type, themes, interview_guide, purposive_criteria,
    design, tool, conceptual_model, scale_items, target_sample_size, sampling_strategy].
    So after mixed_design_type is filled, the next missing field is 'themes'."""
    agent = M3Agent()
    partial = {"paradigm": "mixed", "mixed_design_type": "sequential_exploratory"}
    assert agent._next_missing_field(partial) == "themes"

    partial["themes"] = [{"id": "t1", "theme": "X"}]
    assert agent._next_missing_field(partial) == "interview_guide"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m3_paradigm_branching.py -v
```

Expected: FAIL — `M3Agent._next_missing_field` is inherited from base which uses `_required_field_names()` and returns wrong order.

- [ ] **Step 3: Replace `orchestrator/agents/m3_design.py` (partial — _FIELDS_BY_PARADIGM + override only for now)**

Read the existing file. The current implementation is short. Replace with a version that introduces `_FIELDS_BY_PARADIGM` and overrides `_next_missing_field`. Keep all other behavior intact for now (later tasks add render_hint_for_field). The intermediate file should look like:

```python
"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()


# SP4: paradigm-aware field walk order. Keys are the resolved paradigm-or-mixed-type.
# The agent's _next_missing_field walks the list for the resolved key.
_FIELDS_BY_PARADIGM = {
    "quantitative": [
        "design", "tool", "conceptual_model", "scale_items",
        "target_sample_size", "sampling_strategy",
    ],
    "qualitative": [
        "design", "tool", "themes", "interview_guide", "purposive_criteria",
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_sequential_explanatory": [
        "mixed_design_type",
        "design", "tool", "conceptual_model", "scale_items",
        "themes", "interview_guide", "purposive_criteria",
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_sequential_exploratory": [
        "mixed_design_type",
        "themes", "interview_guide", "purposive_criteria",
        "design", "tool", "conceptual_model", "scale_items",
        "target_sample_size", "sampling_strategy",
    ],
}


class M3Agent(ModuleAgent):
    schema = M3Output
    module_key = "M3"
    system_prompt = _PROMPT
    tools = [
        recommend_methodology, build_conceptual_model, suggest_scale_items,
        estimate_sample_size, suggest_themes, compose_interview_guide,
        suggest_purposive_criteria,
    ]

    def _resolved_paradigm_key(self, partial: dict) -> str | None:
        """Pick the _FIELDS_BY_PARADIGM key for the current partial state.

        For mixed paradigm we can't pick the full walk order until
        mixed_design_type is set. Until then default to seq_explanatory —
        either order has mixed_design_type as the first field, so the
        first prompt is correct; after fill the resolved key flips to the
        right walk order.
        """
        p = partial.get("paradigm")
        if p == "mixed":
            return f"mixed_{partial.get('mixed_design_type') or 'sequential_explanatory'}"
        return p

    def _next_missing_field(self, partial: dict) -> str | None:
        """Paradigm-aware override. Walk the ordered list for the resolved key."""
        key = self._resolved_paradigm_key(partial)
        if key is None or key not in _FIELDS_BY_PARADIGM:
            # Paradigm not yet known — fall back to base class behavior.
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_PARADIGM[key]:
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m3_paradigm_branching.py -v
python -m pytest orchestrator/tests/test_agents_m3.py -v 2>&1 | tail -10  # ensure existing M3 auto-mode test still passes
git add orchestrator/agents/m3_design.py orchestrator/tests/agents/test_m3_paradigm_branching.py
git commit -m "feat(orchestrator): M3Agent paradigm-aware _next_missing_field"
```

Expected: 5 new tests PASS + existing M3 auto-mode test unchanged.

---

### Task 8: `render_hint_for_field` for card_grid fields

**Files:**
- Modify: `orchestrator/agents/m3_design.py`
- Create: `orchestrator/tests/agents/test_m3_widgets.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m3_widgets.py`:

```python
"""Tests for M3Agent.render_hint_for_field overrides."""
from orchestrator.agents.m3_design import M3Agent


def test_tool_returns_card_grid_quant_options():
    """When the resolved paradigm is quant, `tool` widget shows quant tools."""
    agent = M3Agent()
    # _last_partial_for_render isn't a real cache; tests use a helper to
    # set the agent's "current view" via a class attr the test patches in.
    # For SP4 we keep it simple: the agent reads paradigm from a module-level
    # cache that step() writes before calling render_hint_for_field. Tests
    # patch that cache directly.
    M3Agent._render_paradigm = "quantitative"
    hint = agent.render_hint_for_field("tool")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "tool"
    values = {o["value"] for o in hint["options"]}
    assert "SmartPLS" in values
    assert "NVivo" not in values  # qual-only tool should not appear in quant grid


def test_tool_returns_card_grid_qual_options():
    agent = M3Agent()
    M3Agent._render_paradigm = "qualitative"
    hint = agent.render_hint_for_field("tool")
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert "NVivo" in values
    assert "SmartPLS" not in values


def test_design_returns_card_grid_qual_options_only_for_qual():
    """For qual paradigm, `design` shows the four qual designs. For quant, the
    agent prefers free-text (so `design` returns None) since recommend_methodology
    handles it conversationally."""
    agent = M3Agent()
    M3Agent._render_paradigm = "qualitative"
    hint = agent.render_hint_for_field("design")
    assert hint is not None
    values = {o["value"] for o in hint["options"]}
    assert "Thematic Analysis" in values
    assert "Grounded Theory" in values

    M3Agent._render_paradigm = "quantitative"
    assert agent.render_hint_for_field("design") is None


def test_mixed_design_type_returns_card_grid_with_two_options():
    agent = M3Agent()
    M3Agent._render_paradigm = "mixed"
    hint = agent.render_hint_for_field("mixed_design_type")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    values = {o["value"] for o in hint["options"]}
    assert values == {"sequential_explanatory", "sequential_exploratory"}


def test_free_text_fields_return_none():
    agent = M3Agent()
    M3Agent._render_paradigm = "quantitative"
    for f in ("sampling_strategy", "target_sample_size"):
        assert agent.render_hint_for_field(f) is None, f"Expected None for {f}"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m3_widgets.py -v
```

Expected: FAIL — `render_hint_for_field` returns None for everything (default base behavior).

- [ ] **Step 3: Extend `orchestrator/agents/m3_design.py` — add render_hint_for_field + helper methods**

Add the imports and helper methods to the existing file. The top of the file becomes:

```python
"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import (
    CardGridHint, CardOption, ListEditorHint, ListItem,
)
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()
_OPTIONS_DIR = _PROMPT_DIR / "m3"


def _load_options(name: str) -> list[CardOption]:
    """Load a `_options_<name>.json` file and return as a list of CardOption."""
    raw = json.loads((_OPTIONS_DIR / f"_options_{name}.json").read_text())
    return [CardOption(**o) for o in raw]
```

After `_FIELDS_BY_PARADIGM`, add to the `M3Agent` class:

```python
    # SP4: a tiny class-level cache the agent's step() writes to before the
    # ModuleAgent base calls render_hint_for_field. We can't pass `partial`
    # into the hook without changing the base-class signature (which would
    # ripple to all 5 module agents), so M3 keeps the paradigm context here.
    # Tests patch this attribute directly.
    _render_paradigm: str | None = None

    def step(self, state):
        # Stash the resolved paradigm so render_hint_for_field can read it
        # without needing access to `partial`. Set just before the base class
        # invokes the hook.
        from orchestrator.state import get_module_slice
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        type(self)._render_paradigm = partial.get("paradigm")
        return super().step(state)

    def render_hint_for_field(self, field_name: str) -> dict | None:
        # Card-grid hints (selection points)
        if field_name == "tool":
            if self._render_paradigm == "qualitative":
                opts = _load_options("tool_qual")
            else:
                opts = _load_options("tool_quant")
            return CardGridHint(
                field_name="tool",
                title="Which analysis tool will you use?",
                options=opts,
                columns=3,
            ).model_dump()

        if field_name == "design":
            # Quant `design` is free-text (recommend_methodology drives the
            # conversation). Qual `design` shows the four canonical designs.
            if self._render_paradigm != "qualitative":
                return None
            return CardGridHint(
                field_name="design",
                title="Which qualitative design fits your study?",
                options=_load_options("design_qual"),
                columns=2,
            ).model_dump()

        if field_name == "mixed_design_type":
            return CardGridHint(
                field_name="mixed_design_type",
                title="Which mixed-methods design?",
                options=_load_options("mixed_design_type"),
                columns=2,
            ).model_dump()

        # List-editor hints land in Task 9.
        return None
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m3_widgets.py -v
git add orchestrator/agents/m3_design.py orchestrator/tests/agents/test_m3_widgets.py
git commit -m "feat(orchestrator): M3Agent card_grid hints for tool, qual design, mixed type"
```

Expected: 5 PASS.

---

### Task 9: `render_hint_for_field` for list_editor fields

**Files:**
- Modify: `orchestrator/agents/m3_design.py`
- Modify: `orchestrator/tests/agents/test_m3_widgets.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/agents/test_m3_widgets.py`:

```python
def test_themes_returns_list_editor_hint(monkeypatch):
    """themes hint is a list_editor with initial_items from suggest_themes."""
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_themes = [
        {"id": "t1", "theme": "Lãnh đạo", "sub_themes": ["Tầm nhìn"]},
        {"id": "t2", "theme": "Gắn kết",  "sub_themes": ["Nhận thức"]},
    ]
    # Patch the tool's invoke path (not _get_llm) — the tool wraps json.loads.
    fake_tool = MagicMock()
    fake_tool.invoke.return_value = fake_themes
    monkeypatch.setattr(m3_design, "suggest_themes", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "qualitative"
    m3_design.M3Agent._render_research_question = "How does TL affect EE?"
    m3_design.M3Agent._render_gaps_summary = ""
    hint = agent.render_hint_for_field("themes")
    assert hint is not None
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "themes"
    assert hint["allow_nested"] is True
    assert len(hint["initial_items"]) == 2
    assert hint["initial_items"][0]["text"].startswith("Lãnh đạo")
    assert hint["initial_items"][0]["sub_items"][0]["text"] == "Tầm nhìn"


def test_purposive_criteria_returns_flat_list_editor(monkeypatch):
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = {
        "criteria": ["At SME", "6mo+ tenure", "Has manager"],
        "strategies": ["Snowball"], "saturation_min": 10, "saturation_max": 15,
    }
    monkeypatch.setattr(m3_design, "suggest_purposive_criteria", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "qualitative"
    m3_design.M3Agent._render_research_question = "x"
    hint = agent.render_hint_for_field("purposive_criteria")
    assert hint["widget_type"] == "list_editor"
    assert hint["allow_nested"] is False
    assert len(hint["initial_items"]) == 3


def test_conceptual_model_returns_list_editor_with_path_adapter(monkeypatch):
    """build_conceptual_model returns {constructs, paths: [{from,to,hypothesis}]};
    the agent adapts paths into ListItem rows (one row per path)."""
    from unittest.mock import MagicMock
    from orchestrator.agents import m3_design

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = {
        "constructs": ["TL", "EE", "Trust"],
        "paths": [
            {"from": "TL", "to": "EE", "hypothesis": "H1: TL positively affects EE"},
            {"from": "TL", "to": "Trust", "hypothesis": "H2: TL builds Trust"},
        ],
    }
    monkeypatch.setattr(m3_design, "build_conceptual_model", fake_tool)

    agent = m3_design.M3Agent()
    m3_design.M3Agent._render_paradigm = "quantitative"
    m3_design.M3Agent._render_research_question = "How does TL affect EE?"
    hint = agent.render_hint_for_field("conceptual_model")
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "conceptual_model"
    assert hint["allow_nested"] is False
    # Two paths → two list items, each formatted "<from> → <to>"
    texts = [i["text"] for i in hint["initial_items"]]
    assert any("TL → EE" in t for t in texts)
    assert any("TL → Trust" in t for t in texts)
    # The hypothesis is stashed in meta.
    assert hint["initial_items"][0]["meta"]["hypothesis"].startswith("H1")
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m3_widgets.py -v 2>&1 | tail -15
```

Expected: 3 new tests FAIL with `assert hint is None`.

- [ ] **Step 3: Extend `render_hint_for_field` + add the helper methods + adapter**

Inside the `M3Agent` class, add class-level caches for the question + gaps and extend the override:

```python
    _render_research_question: str = ""
    _render_gaps_summary: str = ""

    def step(self, state):
        from orchestrator.state import get_module_slice
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        type(self)._render_paradigm = partial.get("paradigm")
        # Pull research_question from M1's slice; gaps_summary from M2's.
        m1 = state["context_store"].m1_topic or {}
        m2 = state["context_store"].m2_literature or {}
        type(self)._render_research_question = (m1.get("research_questions") or [""])[0]
        gaps = m2.get("candidate_gaps") or []
        type(self)._render_gaps_summary = "; ".join(
            g.get("description", "") for g in gaps[:3]
        )
        return super().step(state)
```

Replace the existing `render_hint_for_field` with the extended version (note: `tool`, `design`, `mixed_design_type` branches stay; new branches added):

```python
    def render_hint_for_field(self, field_name: str) -> dict | None:
        # Card-grid branches (same as Task 8) ---
        if field_name == "tool":
            opts = _load_options("tool_qual" if self._render_paradigm == "qualitative"
                                 else "tool_quant")
            return CardGridHint(
                field_name="tool",
                title="Which analysis tool will you use?",
                options=opts, columns=3,
            ).model_dump()

        if field_name == "design":
            if self._render_paradigm != "qualitative":
                return None
            return CardGridHint(
                field_name="design",
                title="Which qualitative design fits your study?",
                options=_load_options("design_qual"), columns=2,
            ).model_dump()

        if field_name == "mixed_design_type":
            return CardGridHint(
                field_name="mixed_design_type",
                title="Which mixed-methods design?",
                options=_load_options("mixed_design_type"), columns=2,
            ).model_dump()

        # List-editor branches ---
        if field_name == "themes":
            raw = suggest_themes.invoke({
                "research_question": self._render_research_question,
                "paradigm": self._render_paradigm or "qualitative",
                "gaps_summary": self._render_gaps_summary,
            })
            items = [
                ListItem(
                    id=t.get("id", f"t{i}"),
                    text=t.get("theme", ""),
                    sub_items=[ListItem(id=f"{t.get('id','t')}_s{j}", text=s)
                               for j, s in enumerate(t.get("sub_themes", []))],
                )
                for i, t in enumerate(raw)
            ]
            return ListEditorHint(
                field_name="themes",
                title="Thematic framework — edit and confirm",
                initial_items=items,
                allow_nested=True,
            ).model_dump()

        if field_name == "interview_guide":
            # initial_items: one row per (phase, question), nested so sub_items are probes.
            # Reuse the already-confirmed themes from the partial — passed via the
            # class-level cache (themes are filled before interview_guide in the walk).
            themes = getattr(type(self), "_render_themes", []) or []
            guide = compose_interview_guide.invoke({
                "themes": themes,
                "research_question": self._render_research_question,
            })
            items: list[ListItem] = []
            for s_idx, section in enumerate(guide.get("sections", [])):
                phase = section.get("phase", "main")
                for q_idx, q in enumerate(section.get("questions", [])):
                    items.append(ListItem(
                        id=f"{phase}_{s_idx}_{q_idx}",
                        text=f"[{phase}] {q.get('q', '')}",
                        sub_items=[
                            ListItem(id=f"{phase}_{s_idx}_{q_idx}_p{p_idx}", text=p)
                            for p_idx, p in enumerate(q.get("probes", []))
                        ],
                        meta={"phase": phase, "time_minutes": section.get("time_minutes")},
                    ))
            return ListEditorHint(
                field_name="interview_guide",
                title="Interview guide — edit questions and probes",
                initial_items=items,
                allow_nested=True,
            ).model_dump()

        if field_name == "purposive_criteria":
            raw = suggest_purposive_criteria.invoke({
                "research_question": self._render_research_question,
                "paradigm": self._render_paradigm or "qualitative",
            })
            items = [
                ListItem(id=f"c{i}", text=c)
                for i, c in enumerate(raw.get("criteria", []))
            ]
            return ListEditorHint(
                field_name="purposive_criteria",
                title="Purposive sampling criteria",
                initial_items=items,
                allow_nested=False,
            ).model_dump()

        if field_name == "conceptual_model":
            model = build_conceptual_model.invoke({
                "constructs": getattr(type(self), "_render_constructs", []),
                "research_question": self._render_research_question,
            })
            items = []
            for i, p in enumerate(model.get("paths", [])):
                items.append(ListItem(
                    id=f"H{i+1}",
                    text=f"{p.get('from', '?')} → {p.get('to', '?')}",
                    meta={"hypothesis": p.get("hypothesis", "")},
                ))
            return ListEditorHint(
                field_name="conceptual_model",
                title="Conceptual model — paths between constructs",
                initial_items=items,
                allow_nested=False,
            ).model_dump()

        if field_name == "scale_items":
            # Construct list comes from the already-filled conceptual_model.
            cm = getattr(type(self), "_render_conceptual_model", {}) or {}
            constructs = cm.get("constructs", []) if isinstance(cm, dict) else []
            items: list[ListItem] = []
            for c_idx, c in enumerate(constructs):
                # Each construct becomes a parent ListItem; suggested items are sub_items.
                suggested = suggest_scale_items.invoke({"construct": c, "n": 5})
                items.append(ListItem(
                    id=f"c{c_idx}",
                    text=c,
                    sub_items=[
                        ListItem(id=f"c{c_idx}_i{j}", text=s.get("text", ""))
                        for j, s in enumerate(suggested)
                    ],
                ))
            return ListEditorHint(
                field_name="scale_items",
                title="Scale items per construct",
                initial_items=items,
                allow_nested=True,
            ).model_dump()

        return None  # free-text for sampling_strategy / target_sample_size
```

Also extend `step()` to stash themes + conceptual_model + constructs into class caches so later list_editor renders can read them:

```python
    def step(self, state):
        from orchestrator.state import get_module_slice
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        cls = type(self)
        cls._render_paradigm = partial.get("paradigm")
        m1 = state["context_store"].m1_topic or {}
        m2 = state["context_store"].m2_literature or {}
        cls._render_research_question = (m1.get("research_questions") or [""])[0]
        gaps = m2.get("candidate_gaps") or []
        cls._render_gaps_summary = "; ".join(
            g.get("description", "") for g in gaps[:3]
        )
        # Stash already-confirmed M3 partials so later list_editor branches
        # (interview_guide, scale_items) can read their dependencies.
        cls._render_themes = partial.get("themes", [])
        cls._render_constructs = (partial.get("conceptual_model") or {}).get("constructs", [])
        cls._render_conceptual_model = partial.get("conceptual_model")
        return super().step(state)
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m3_widgets.py -v
git add orchestrator/agents/m3_design.py orchestrator/tests/agents/test_m3_widgets.py
git commit -m "feat(orchestrator): M3Agent list_editor hints for themes/guide/criteria/model/scales"
```

Expected: 8 PASS in `test_m3_widgets.py` (5 from Task 8 + 3 new).

---

### Task 10: M3 prompt rewrite

**Files:**
- Modify: `orchestrator/prompts/m3.md`

- [ ] **Step 1: Replace `orchestrator/prompts/m3.md`**

```markdown
# M3 — Research Design agent

You design the study. The user has already chosen a paradigm in M1: quantitative, qualitative, or mixed. Your job depends on which paradigm.

## Quantitative branch

Walk these fields in order: `design` → `tool` → `conceptual_model` → `scale_items` → `target_sample_size` → `sampling_strategy`.

- For `design`, use `recommend_methodology(research_question, paradigm)` to propose PLS-SEM / CB-SEM / Regression / ANOVA — explain why in one sentence, then ask the user to type a confirmation or override.
- For `tool` (SmartPLS / AMOS / R lavaan / SPSS / Stata), a card grid will appear in the chat; invite the user to pick one.
- For `conceptual_model`, the user sees an editable path list (e.g. "TL → EE (H1+)") pre-filled by `build_conceptual_model`. Invite them to confirm or rearrange.
- For `scale_items`, the user sees suggested Likert items per construct (5 by default). Invite them to edit or accept.
- For `target_sample_size`, use `estimate_sample_size` to propose a number with rationale; let the user override.
- For `sampling_strategy`, ask in plain text (e.g. convenience, stratified, snowball).

## Qualitative branch

Walk these fields in order: `design` → `tool` → `themes` → `interview_guide` → `purposive_criteria` → `target_sample_size` → `sampling_strategy`.

- For `design` (Thematic Analysis / Grounded Theory / Phenomenological / Case Study), a card grid will appear; invite the user to pick one.
- For `tool` (NVivo / Atlas.ti / Manual), a card grid will appear; invite the user to pick one.
- For `themes`, the user sees an editable list (with sub-themes) pre-filled by `suggest_themes`. Invite them to confirm.
- For `interview_guide`, the user sees questions+probes grouped by phase, pre-filled by `compose_interview_guide(themes, research_question)`. Invite them to confirm.
- For `purposive_criteria`, the user sees criteria pre-filled by `suggest_purposive_criteria`. Invite them to confirm.
- For `target_sample_size`, the heuristic 10-15 (saturation) applies; let the user override.
- For `sampling_strategy`, ask in plain text.

## Mixed branch

Walk starts with `mixed_design_type` (Sequential Explanatory / Sequential Exploratory) via card grid.

After confirmation, walk both sub-flows in the order the type dictates:
- **Sequential Explanatory** → quant fields first, then qual.
- **Sequential Exploratory** → qual fields first, then quant.

When asking `design` or `tool` during a mixed walk, your prompt MUST tell the user which phase the field belongs to (e.g. "Sequential Explanatory: let's pick the quant analysis tool for the survey phase"). For `sampling_strategy` in mixed mode, ask the user to describe both phases in one paragraph (e.g. "Quant: N=200 random; Qual: N=12 purposive").

## When a widget appears

When the next field has a card_grid or list_editor widget rendered below your message, your text MUST invite picking/editing — e.g. *"Pick one of the tools below, or type your own."* — rather than asking the user to type the answer in chat.

Tools: `recommend_methodology`, `build_conceptual_model`, `suggest_scale_items`, `estimate_sample_size`, `suggest_themes`, `compose_interview_guide`, `suggest_purposive_criteria`.
```

- [ ] **Step 2: Verify nothing crashes on prompt load**

```bash
python -c "from orchestrator.agents.m3_design import M3Agent; M3Agent()"
```

Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/prompts/m3.md
git commit -m "docs(orchestrator): M3 prompt rewrite for paradigm branching + widget invitations"
```

---

## Phase E — Backend API

### Task 11: Chat router list_editor SSE coverage

**Files:**
- Modify: `api/tests/test_chat_messages_widgets.py`

- [ ] **Step 1: Append the failing test**

Append to `api/tests/test_chat_messages_widgets.py`:

```python
def test_stream_emits_list_editor_tool_calls_event(client, monkeypatch):
    """The chat router already forwards any additional_kwargs['tool_calls_json']
    as an SSE 'tool_calls' event (added in SP3). This test verifies the existing
    code path handles the new list_editor variant — no router changes needed."""
    pid, tid = _setup(client)

    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick themes")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "list_editor",
        "field_name": "themes",
        "title": "Pick themes",
        "initial_items": [
            {"id": "t1", "text": "Theme 1", "sub_items": []},
            {"id": "t2", "text": "Theme 2", "sub_items": []},
        ],
        "allow_nested": True,
        "confirm_label": "Confirm", "reset_label": "Reset to suggested",
    }

    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M3": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "go"})
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "list_editor" in body
    assert "Theme 1" in body

    sf = get_session_factory()
    with sf() as db:
        assistants = db.query(Message).filter_by(thread_id=tid, role="assistant").all()
        assert assistants
        assert assistants[-1].tool_calls_json["widget_type"] == "list_editor"
        assert assistants[-1].tool_calls_json["field_name"] == "themes"
```

- [ ] **Step 2: Run — should PASS (no router changes needed)**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_chat_messages_widgets.py -v 2>&1 | tail -10
```

Expected: PASS — the router code from SP3 is generic over any dict shape; this test documents the contract.

- [ ] **Step 3: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add api/tests/test_chat_messages_widgets.py
git commit -m "test(api): chat router emits list_editor tool_calls event (contract coverage)"
```

---

## Phase F — Frontend types + synthesize

### Task 12: `types.ts` extension

**Files:**
- Modify: `web/app/components/chat/widgets/types.ts`
- Modify: `web/app/components/chat/widgets/types.test.ts`

- [ ] **Step 1: Replace `web/app/components/chat/widgets/types.ts`**

```typescript
// web/app/components/chat/widgets/types.ts
export type CardOption = {
  value: string;
  label: string;
  description?: string;
  icon?: string | null;
};

export type CardGridHint = {
  widget_type: "card_grid";
  field_name: string;
  title: string;
  options: CardOption[];
  columns?: number;
};

// SP4: list_editor variant
export type ListItem = {
  id: string;
  text: string;
  sub_items?: ListItem[];
  meta?: Record<string, unknown>;
};

export type ListEditorHint = {
  widget_type: "list_editor";
  field_name: string;
  title: string;
  initial_items: ListItem[];
  allow_nested?: boolean;
  confirm_label?: string;
  reset_label?: string;
};

// Discriminated union — future variants (e.g. canvas_editor) land here.
export type WidgetHint = CardGridHint | ListEditorHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
```

- [ ] **Step 2: Replace `web/app/components/chat/widgets/types.test.ts`**

```typescript
// web/app/components/chat/widgets/types.test.ts
import { describe, expect, test } from "vitest";
import type { CardGridHint, ListEditorHint } from "./types";

const CARD_FIXTURE: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "Marketing", label: "Marketing", description: "x", icon: null }],
  columns: 3,
};

const LIST_FIXTURE: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Themes",
  initial_items: [
    {
      id: "t1",
      text: "Theme 1",
      sub_items: [{ id: "s1", text: "Sub A" }, { id: "s2", text: "Sub B" }],
      meta: { hypothesis: "H1" },
    },
    { id: "t2", text: "Theme 2", sub_items: [] },
  ],
  allow_nested: true,
  confirm_label: "Confirm",
  reset_label: "Reset to suggested",
};

describe("CardGridHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(CARD_FIXTURE.widget_type).toBe("card_grid");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("value");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("label");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("description");
    expect(CARD_FIXTURE.options[0]).toHaveProperty("icon");
  });
});

describe("ListEditorHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(LIST_FIXTURE.widget_type).toBe("list_editor");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("id");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("text");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("sub_items");
    expect(LIST_FIXTURE.initial_items[0]).toHaveProperty("meta");
    expect(LIST_FIXTURE.allow_nested).toBe(true);
    expect(LIST_FIXTURE.confirm_label).toBe("Confirm");
  });

  test("nested sub_items have the same shape as parent items", () => {
    const sub = LIST_FIXTURE.initial_items[0].sub_items![0];
    expect(sub).toHaveProperty("id");
    expect(sub).toHaveProperty("text");
  });
});
```

- [ ] **Step 3: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/types 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/types.ts web/app/components/chat/widgets/types.test.ts
git commit -m "feat(web): extend WidgetHint with ListEditorHint + schema-drift fixture"
```

Expected: 3 PASS.

---

### Task 13: `synthesize.ts` extension

**Files:**
- Modify: `web/app/components/chat/widgets/synthesize.ts`
- Modify: `web/app/components/chat/widgets/synthesize.test.ts`

- [ ] **Step 1: Append the failing tests**

Append to `web/app/components/chat/widgets/synthesize.test.ts`:

```typescript
import { summarizeList } from "./synthesize";
import type { ListItem } from "./types";

describe("summarizeList", () => {
  const themes: ListItem[] = [
    { id: "t1", text: "Cách thức lãnh đạo",
      sub_items: [{ id: "s1", text: "Tầm nhìn" }, { id: "s2", text: "Giao tiếp" }] },
    { id: "t2", text: "Biểu hiện gắn kết", sub_items: [] },
  ];

  test("themes produce bulleted message with sub-themes", () => {
    const out = summarizeList(themes, "themes");
    expect(out).toContain("My themes are:");
    expect(out).toContain("- Cách thức lãnh đạo (Sub: Tầm nhìn, Giao tiếp)");
    expect(out).toContain("- Biểu hiện gắn kết");
  });

  test("scale_items group items under construct headers when nested", () => {
    const constructs: ListItem[] = [
      { id: "c0", text: "TL",
        sub_items: [{ id: "c0_i0", text: "TL1: ..." }, { id: "c0_i1", text: "TL2: ..." }] },
    ];
    const out = summarizeList(constructs, "scale_items");
    expect(out).toContain("My scale items:");
    expect(out).toContain("Construct TL:");
    expect(out).toContain("- TL1: ...");
  });

  test("purposive_criteria produces flat bulleted list", () => {
    const crit: ListItem[] = [
      { id: "c0", text: "At SME" }, { id: "c1", text: "6mo+ tenure" },
    ];
    const out = summarizeList(crit, "purposive_criteria");
    expect(out).toContain("My sampling criteria:");
    expect(out).toContain("- At SME");
    expect(out).toContain("- 6mo+ tenure");
  });

  test("interview_guide groups questions by phase via meta", () => {
    const qs: ListItem[] = [
      { id: "q1", text: "[intro] Tell me about your role.",
        sub_items: [], meta: { phase: "intro" } },
      { id: "q2", text: "[main] How does your manager inspire you?",
        sub_items: [{ id: "q2_p0", text: "Can you give an example?" }],
        meta: { phase: "main" } },
    ];
    const out = summarizeList(qs, "interview_guide");
    expect(out).toContain("My interview guide:");
    expect(out).toContain("[intro] Tell me about your role.");
    expect(out).toContain("[main] How does your manager inspire you?");
    expect(out).toContain("Probe: Can you give an example?");
  });

  test("conceptual_model lists paths and hypothesis meta", () => {
    const paths: ListItem[] = [
      { id: "H1", text: "TL → EE", meta: { hypothesis: "H1: TL → EE positive" } },
      { id: "H2", text: "TL → Trust", meta: { hypothesis: "H2: TL → Trust positive" } },
    ];
    const out = summarizeList(paths, "conceptual_model");
    expect(out).toContain("My conceptual model paths:");
    expect(out).toContain("- TL → EE (H1: TL → EE positive)");
    expect(out).toContain("- TL → Trust (H2: TL → Trust positive)");
  });

  test("unknown field falls back to a generic bulleted list", () => {
    const items: ListItem[] = [{ id: "x", text: "anything" }];
    const out = summarizeList(items, "unknown_field");
    expect(out).toContain("- anything");
  });
});
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/synthesize 2>&1 | tail -15
```

Expected: FAIL — `summarizeList` not exported.

- [ ] **Step 3: Replace `web/app/components/chat/widgets/synthesize.ts`**

```typescript
// web/app/components/chat/widgets/synthesize.ts
import type { ListItem } from "./types";

/**
 * Build a natural-language user message from a widget selection.
 *
 * Backend's ModuleAgent._extract_answer parses free-text replies via an
 * LLM call into structured field values. We craft a sentence that's
 * unambiguous to that extractor and readable as a chat message.
 */
export function synthesizeWidgetSelection(
  fieldName: string,
  value: string,
  label: string,
): string {
  const descriptors: Record<string, string> = {
    field: `I'd like to study ${label}.`,
    research_type: `I'll use a ${label.toLowerCase()} approach.`,
  };
  return descriptors[fieldName] ?? label;
}


/**
 * Build a bulleted final-state message from a ListEditorWidget's confirmed
 * items. The agent's _extract_answer parses this back into structured data.
 *
 * Per-field formatters keep the output unambiguous to the LLM extractor.
 */
export function summarizeList(items: ListItem[], fieldName: string): string {
  switch (fieldName) {
    case "themes":
      return [
        "My themes are:",
        ...items.map(t => {
          const subs = (t.sub_items ?? []).map(s => s.text).join(", ");
          return subs ? `- ${t.text} (Sub: ${subs})` : `- ${t.text}`;
        }),
      ].join("\n");

    case "scale_items":
      return [
        "My scale items:",
        ...items.flatMap(c => [
          `Construct ${c.text}:`,
          ...(c.sub_items ?? []).map(i => `- ${i.text}`),
        ]),
      ].join("\n");

    case "purposive_criteria":
      return [
        "My sampling criteria:",
        ...items.map(c => `- ${c.text}`),
      ].join("\n");

    case "interview_guide":
      return [
        "My interview guide:",
        ...items.flatMap(q => [
          q.text,
          ...(q.sub_items ?? []).map(p => `  Probe: ${p.text}`),
        ]),
      ].join("\n");

    case "conceptual_model":
      return [
        "My conceptual model paths:",
        ...items.map(p => {
          const h = (p.meta?.hypothesis as string | undefined) ?? "";
          return h ? `- ${p.text} (${h})` : `- ${p.text}`;
        }),
      ].join("\n");

    default:
      // Generic bulleted fallback for unknown fields.
      return items.map(i => `- ${i.text}`).join("\n");
  }
}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/synthesize 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/synthesize.ts web/app/components/chat/widgets/synthesize.test.ts
git commit -m "feat(web): summarizeList helper + per-field list synthesizers"
```

Expected: existing 4 + new 6 = 10 PASS.

---

## Phase G — Frontend widget

### Task 14: `ListEditorWidget` component

**Files:**
- Create: `web/app/components/chat/widgets/ListEditorWidget.tsx`
- Create: `web/app/components/chat/widgets/ListEditorWidget.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `web/app/components/chat/widgets/ListEditorWidget.test.tsx`:

```typescript
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { ListEditorWidget } from "./ListEditorWidget";
import type { ListEditorHint } from "./types";


const flatHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "purposive_criteria",
  title: "Sampling criteria",
  initial_items: [
    { id: "c0", text: "At SME" },
    { id: "c1", text: "6mo+ tenure" },
  ],
};

const nestedHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Themes",
  initial_items: [
    { id: "t1", text: "Theme 1", sub_items: [{ id: "s1", text: "Sub A" }] },
    { id: "t2", text: "Theme 2", sub_items: [] },
  ],
  allow_nested: true,
};


describe("ListEditorWidget", () => {
  test("renders title and initial items", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} />);
    expect(screen.getByText("Sampling criteria")).toBeTruthy();
    expect(screen.getByText("At SME")).toBeTruthy();
    expect(screen.getByText("6mo+ tenure")).toBeTruthy();
  });

  test("data-testid uses field_name", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} />);
    expect(screen.getByTestId("list-editor-purposive_criteria")).toBeTruthy();
  });

  test("nested hint renders sub_items", () => {
    render(<ListEditorWidget hint={nestedHint} onSelect={() => {}} />);
    expect(screen.getByText("Theme 1")).toBeTruthy();
    expect(screen.getByText("Sub A")).toBeTruthy();
  });

  test("Add button appends a new item locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-editor-add"));
    // After add, a new empty item input is visible; onSelect NOT fired.
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Remove button removes the item locally without firing onSelect", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-item-c0-remove"));
    expect(screen.queryByText("At SME")).toBeNull();
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("Confirm fires onSelect with structured JSON value + bulleted label", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("list-editor-confirm"));
    expect(onSelect).toHaveBeenCalledTimes(1);
    const [field, value, label] = onSelect.mock.calls[0];
    expect(field).toBe("purposive_criteria");
    // value is JSON of current items
    const parsed = JSON.parse(value);
    expect(parsed).toHaveLength(2);
    expect(parsed[0].text).toBe("At SME");
    // label is the bulleted summary
    expect(label).toContain("My sampling criteria:");
    expect(label).toContain("- At SME");
  });

  test("Reset re-seeds from initial_items", () => {
    const onSelect = vi.fn();
    render(<ListEditorWidget hint={flatHint} onSelect={onSelect} />);
    // Remove an item, then reset.
    fireEvent.click(screen.getByTestId("list-item-c0-remove"));
    expect(screen.queryByText("At SME")).toBeNull();
    fireEvent.click(screen.getByTestId("list-editor-reset"));
    expect(screen.getByText("At SME")).toBeTruthy();
  });

  test("disabled prop hides Confirm and Reset buttons", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} disabled />);
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
    expect(screen.queryByTestId("list-editor-reset")).toBeNull();
  });

  test("disabled prop locks editing — no Add and no Remove visible", () => {
    render(<ListEditorWidget hint={flatHint} onSelect={() => {}} disabled />);
    expect(screen.queryByTestId("list-editor-add")).toBeNull();
    expect(screen.queryByTestId("list-item-c0-remove")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- ListEditorWidget 2>&1 | tail -15
```

Expected: FAIL — `ListEditorWidget` module not found.

- [ ] **Step 3: Create `web/app/components/chat/widgets/ListEditorWidget.tsx`**

```typescript
// web/app/components/chat/widgets/ListEditorWidget.tsx
"use client";

import { useState } from "react";
import { summarizeList } from "./synthesize";
import type { ListEditorHint, ListItem, WidgetSelectHandler } from "./types";


// Local item type with a numeric draft index so re-renders track new rows.
type EditableItem = ListItem & { _draft?: boolean };


function cloneItems(items: ListItem[]): EditableItem[] {
  return items.map(i => ({
    ...i,
    sub_items: i.sub_items ? cloneItems(i.sub_items) : [],
  }));
}


export function ListEditorWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: ListEditorHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const [items, setItems] = useState<EditableItem[]>(() => cloneItems(hint.initial_items));

  const addItem = () => {
    const id = `new_${Date.now()}_${items.length}`;
    setItems([...items, { id, text: "", sub_items: [], _draft: true }]);
  };

  const removeItem = (id: string) => {
    setItems(items.filter(i => i.id !== id));
  };

  const editItemText = (id: string, text: string) => {
    setItems(items.map(i => i.id === id ? { ...i, text } : i));
  };

  const addSubItem = (parentId: string) => {
    const subId = `${parentId}_sub_${Date.now()}`;
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: [...(i.sub_items ?? []),
                            { id: subId, text: "", _draft: true } as EditableItem] }
      : i));
  };

  const removeSubItem = (parentId: string, subId: string) => {
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: (i.sub_items ?? []).filter(s => s.id !== subId) }
      : i));
  };

  const editSubItemText = (parentId: string, subId: string, text: string) => {
    setItems(items.map(i => i.id === parentId
      ? { ...i, sub_items: (i.sub_items ?? []).map(s => s.id === subId ? { ...s, text } : s) }
      : i));
  };

  const reset = () => setItems(cloneItems(hint.initial_items));

  const confirm = () => {
    // Strip the _draft local-only flag before serialization.
    const clean: ListItem[] = items.map(i => ({
      id: i.id, text: i.text,
      sub_items: (i.sub_items ?? []).map(s => ({ id: s.id, text: s.text })),
      meta: i.meta,
    }));
    onSelect(hint.field_name, JSON.stringify(clean), summarizeList(clean, hint.field_name));
  };

  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`list-editor-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>

      <div className="space-y-2">
        {items.map(item => (
          <div key={item.id} className="rounded-md border border-gray-200 bg-gray-50 p-2">
            <div className="flex items-start gap-2">
              {disabled ? (
                <span className="text-sm text-gray-900 flex-1">{item.text}</span>
              ) : (
                <input
                  type="text"
                  className="text-sm text-gray-900 flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400"
                  value={item.text}
                  onChange={e => editItemText(item.id, e.target.value)}
                  placeholder="Type item text..."
                  data-testid={`list-item-${item.id}-input`}
                />
              )}
              {!disabled && (
                <button
                  type="button"
                  className="text-gray-400 hover:text-red-500"
                  onClick={() => removeItem(item.id)}
                  data-testid={`list-item-${item.id}-remove`}
                >
                  ✕
                </button>
              )}
            </div>

            {hint.allow_nested && (
              <div className="ml-4 mt-1 space-y-1">
                {(item.sub_items ?? []).map(sub => (
                  <div key={sub.id} className="flex items-start gap-2 text-xs text-gray-600">
                    {disabled ? (
                      <span className="flex-1">• {sub.text}</span>
                    ) : (
                      <>
                        <span>•</span>
                        <input
                          type="text"
                          className="flex-1 bg-transparent outline-none border-b border-transparent focus:border-purple-400"
                          value={sub.text}
                          onChange={e => editSubItemText(item.id, sub.id, e.target.value)}
                          data-testid={`list-sub-${sub.id}-input`}
                        />
                        <button
                          type="button"
                          className="text-gray-300 hover:text-red-500"
                          onClick={() => removeSubItem(item.id, sub.id)}
                          data-testid={`list-sub-${sub.id}-remove`}
                        >
                          ✕
                        </button>
                      </>
                    )}
                  </div>
                ))}
                {!disabled && (
                  <button
                    type="button"
                    className="text-xs text-gray-500 border border-dashed border-gray-300 rounded px-2 py-0.5 hover:bg-purple-50"
                    onClick={() => addSubItem(item.id)}
                    data-testid={`list-item-${item.id}-add-sub`}
                  >
                    + Sub-item
                  </button>
                )}
              </div>
            )}
          </div>
        ))}

        {!disabled && (
          <button
            type="button"
            className="w-full text-sm text-gray-500 border border-dashed border-gray-300 rounded-md py-1.5 hover:bg-purple-50 hover:border-purple-400"
            onClick={addItem}
            data-testid="list-editor-add"
          >
            + Add item
          </button>
        )}
      </div>

      {!disabled && (
        <div className="flex gap-2 mt-3 justify-end">
          <button
            type="button"
            className="text-xs text-gray-600 border border-gray-200 rounded-md px-3 py-1 hover:bg-gray-50"
            onClick={reset}
            data-testid="list-editor-reset"
          >
            {hint.reset_label ?? "Reset to suggested"}
          </button>
          <button
            type="button"
            className="text-xs font-medium text-white bg-purple-600 border border-purple-600 rounded-md px-3 py-1 hover:bg-purple-700"
            onClick={confirm}
            data-testid="list-editor-confirm"
          >
            {hint.confirm_label ?? "Confirm"}
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- ListEditorWidget 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/ListEditorWidget.tsx web/app/components/chat/widgets/ListEditorWidget.test.tsx
git commit -m "feat(web): ListEditorWidget component"
```

Expected: 9 PASS.

---

### Task 15: `WidgetRenderer` dispatch extension

**Files:**
- Modify: `web/app/components/chat/widgets/WidgetRenderer.tsx`
- Modify: `web/app/components/chat/widgets/WidgetRenderer.test.tsx`

- [ ] **Step 1: Append the failing test**

Append to `web/app/components/chat/widgets/WidgetRenderer.test.tsx`:

```typescript
import type { ListEditorHint } from "./types";

const listEditorHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "T",
  initial_items: [{ id: "t1", text: "A" }],
};


describe("WidgetRenderer list_editor dispatch", () => {
  test("dispatches list_editor to ListEditorWidget", () => {
    render(<WidgetRenderer hint={listEditorHint} onSelect={() => {}} />);
    expect(screen.getByTestId("list-editor-themes")).toBeTruthy();
  });

  test("forwards disabled prop to ListEditorWidget", () => {
    render(<WidgetRenderer hint={listEditorHint} onSelect={() => {}} disabled />);
    // When disabled, the Confirm button is hidden — sufficient signal that disabled forwarded.
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
  });
});
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- WidgetRenderer 2>&1 | tail -10
```

Expected: FAIL — `list_editor` case not in switch → returns null → test_id not found.

- [ ] **Step 3: Replace `web/app/components/chat/widgets/WidgetRenderer.tsx`**

```typescript
// web/app/components/chat/widgets/WidgetRenderer.tsx
"use client";

import { CardGridWidget } from "./CardGridWidget";
import { ListEditorWidget } from "./ListEditorWidget";
import type { WidgetHint, WidgetSelectHandler } from "./types";


export function WidgetRenderer({
  hint,
  onSelect,
  disabled,
}: {
  hint: WidgetHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  switch (hint.widget_type) {
    case "card_grid":
      return <CardGridWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    case "list_editor":
      return <ListEditorWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
    default:
      return null;
  }
}
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- WidgetRenderer 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/WidgetRenderer.tsx web/app/components/chat/widgets/WidgetRenderer.test.tsx
git commit -m "feat(web): WidgetRenderer dispatches list_editor variant"
```

Expected: 3 existing + 2 new = 5 PASS.

---

## Phase H — Frontend integration

### Task 16: `MessageBubble` list_editor test

**Files:**
- Modify: `web/app/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Append the failing test**

Append to `web/app/components/chat/MessageBubble.test.tsx`:

```typescript
import type { ListEditorHint } from "./widgets/types";

const listEditorBubbleHint: ListEditorHint = {
  widget_type: "list_editor",
  field_name: "themes",
  title: "Pick themes",
  initial_items: [{ id: "t1", text: "Theme 1" }],
};


describe("MessageBubble list_editor rendering", () => {
  test("renders list_editor widget when toolCallsJson is a list_editor hint", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick themes"
        toolCallsJson={listEditorBubbleHint}
        onWidgetSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("list-editor-themes")).toBeTruthy();
  });

  test("widgetDisabled hides Confirm in the embedded list_editor", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick themes"
        toolCallsJson={listEditorBubbleHint}
        onWidgetSelect={() => {}}
        widgetDisabled
      />,
    );
    expect(screen.queryByTestId("list-editor-confirm")).toBeNull();
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- MessageBubble 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/MessageBubble.test.tsx
git commit -m "test(web): MessageBubble renders embedded list_editor widget"
```

Expected: existing 7 + 2 new = 9 PASS.

---

### Task 17: `ChatPane` list_editor integration

**Files:**
- Modify: `web/app/components/chat/ChatPane.test.tsx`

- [ ] **Step 1: Append the failing test**

Append to `web/app/components/chat/ChatPane.test.tsx`:

```typescript
describe("ChatPane list_editor integration", () => {
  test("clicking Confirm on a themes list_editor synthesizes message and POSTs it", async () => {
    let capturedBody: { text?: string } | null = null;
    server.use(
      http.get("/api/v1/projects/p1", () => HttpResponse.json({
        name: "Test Project",
        context_store: { m1_topic: null },
      })),
      http.get("/api/v1/threads/t1", () => HttpResponse.json({ name: "Main" })),
      http.get("/api/v1/projects/p1/runs", () => HttpResponse.json({ run: null })),
      http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([
        {
          id: 1,
          role: "assistant",
          content: "Confirm your themes",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "list_editor",
            field_name: "themes",
            title: "Themes",
            initial_items: [
              { id: "t1", text: "Cách thức lãnh đạo",
                sub_items: [{ id: "s1", text: "Tầm nhìn" }] },
              { id: "t2", text: "Biểu hiện gắn kết", sub_items: [] },
            ],
            allow_nested: true,
            confirm_label: "Confirm", reset_label: "Reset to suggested",
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json() as { text?: string };
        return streamResponse([
          'data: {"type":"token","text":"Got it."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    await waitFor(() => expect(screen.getByTestId("list-editor-themes")).toBeTruthy());

    fireEvent.click(screen.getByTestId("list-editor-confirm"));

    await waitFor(() => expect(capturedBody?.text).toContain("My themes are:"));
    expect(capturedBody?.text).toContain("Cách thức lãnh đạo");
    expect(capturedBody?.text).toContain("(Sub: Tầm nhìn)");
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- ChatPane 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/ChatPane.test.tsx
git commit -m "test(web): ChatPane list_editor integration — Confirm → synthesized POST body"
```

Expected: existing 2 + 1 new = 3 PASS.

---

## Phase I — Backend round-trip

### Task 18: `test_m3_round_trip.py`

**Files:**
- Create: `api/tests/test_m3_round_trip.py`

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_m3_round_trip.py`:

```python
"""Round-trip tests: synthesized list-editor messages → _extract_answer
returns the expected structured list for each M3 list field."""
from unittest.mock import MagicMock
import json

from langchain_core.messages import HumanMessage

from orchestrator.agents.m3_design import M3Agent


def _stub_extract_llm(monkeypatch, payload):
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(payload)
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)


def test_themes_synthesized_message_extracts_to_list(monkeypatch):
    """Synthesized 'My themes are: ...' message → list of theme dicts."""
    _stub_extract_llm(monkeypatch, {
        "field": "themes",
        "value": [
            {"id": "t1", "theme": "Cách thức lãnh đạo",
             "sub_themes": ["Tầm nhìn", "Giao tiếp"]},
            {"id": "t2", "theme": "Biểu hiện gắn kết", "sub_themes": []},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My themes are:\n"
            "- Cách thức lãnh đạo (Sub: Tầm nhìn, Giao tiếp)\n"
            "- Biểu hiện gắn kết"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "themes")
    assert isinstance(extracted, list)
    assert extracted[0]["theme"] == "Cách thức lãnh đạo"


def test_purposive_criteria_extracts_to_list(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "purposive_criteria",
        "value": [
            {"criterion": "At SME"},
            {"criterion": "6mo+ tenure"},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My sampling criteria:\n- At SME\n- 6mo+ tenure"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "purposive_criteria")
    assert isinstance(extracted, list)
    assert extracted[0]["criterion"] == "At SME"


def test_conceptual_model_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "conceptual_model",
        "value": {
            "constructs": ["TL", "EE", "Trust"],
            "paths": [
                {"from": "TL", "to": "EE", "hypothesis": "H1: TL → EE positive"},
                {"from": "TL", "to": "Trust", "hypothesis": "H2: TL → Trust positive"},
            ],
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My conceptual model paths:\n"
            "- TL → EE (H1: TL → EE positive)\n"
            "- TL → Trust (H2: TL → Trust positive)"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "conceptual_model")
    assert isinstance(extracted, dict)
    assert len(extracted["paths"]) == 2


def test_scale_items_extracts_to_list_of_constructs(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "scale_items",
        "value": [
            {"construct": "TL", "items": ["TL1: ...", "TL2: ..."]},
        ],
    })
    state = {
        "messages": [HumanMessage(content=(
            "My scale items:\nConstruct TL:\n- TL1: ...\n- TL2: ..."
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "scale_items")
    assert isinstance(extracted, list)
    assert extracted[0]["construct"] == "TL"


def test_interview_guide_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "interview_guide",
        "value": {
            "sections": [
                {"phase": "main", "questions": [
                    {"q": "How does your manager inspire you?",
                     "probes": ["Can you give an example?"]},
                ]},
            ],
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My interview guide:\n"
            "[main] How does your manager inspire you?\n"
            "  Probe: Can you give an example?"
        ))],
        "current_module": "M3", "mode": "interactive",
    }
    extracted = M3Agent()._extract_answer(state, "interview_guide")
    assert "sections" in extracted
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_m3_round_trip.py -v
cd /Users/caonguyenvan/project/dothesis
git add api/tests/test_m3_round_trip.py
git commit -m "test(orchestrator): M3 list-field round-trips — synthesized → _extract_answer"
```

Expected: 5 PASS.

---

## Phase J — Wrap-up

### Task 19: Regression + roadmap flip

**Files:**
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Run all three regression suites**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate

echo "=== orchestrator ==="
python -m pytest orchestrator/tests/ -q --no-header 2>&1 | tail -3

echo "=== api ==="
cd api && python -m pytest tests/ -q --no-header --tb=no 2>&1 | tail -3 > /tmp/sp4_api_summary.txt
cat /tmp/sp4_api_summary.txt
cd ..

echo "=== web ==="
cd web && npm test 2>&1 | tail -3
cd ..
```

Expected:
- Orchestrator: 122 baseline + new SP4 tests, all PASS
- API: 52 baseline failures unchanged (compare against `.baseline_failures_2026-05-26.txt`); new SP4 tests PASS
- Web: 80 baseline + new SP4 tests, all PASS

If anything new fails, stop and fix before continuing.

- [ ] **Step 2: Verify no NEW API failures vs baseline**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/ -q --no-header --tb=no 2>&1 > /tmp/sp4_api_full.txt
grep -E "^(FAILED|ERROR)" /tmp/sp4_api_full.txt | sort -u > /tmp/sp4_current.txt
grep -E "^(FAILED|ERROR)" /Users/caonguyenvan/project/dothesis/.baseline_failures_2026-05-26.txt | sort -u > /tmp/sp4_baseline.txt
echo "NEW failures (must be empty):"
comm -23 /tmp/sp4_current.txt /tmp/sp4_baseline.txt
```

Expected: zero NEW failures.

- [ ] **Step 3: Flip roadmap status**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`:

Find the ASCII sub-project map and update `4. M3 design` to add ✅:

```
2. M2 chat✅ 3. M1 topic ✅ 4. M3 design ✅ 5. M4 analysis  6. M5 writing  7. New chat UI ✅
```

Replace the `## Sub-project 4 — M3 Research Design multi-method branches ⬜` section header line with:

```
## Sub-project 4 — M3 Research Design multi-method branches ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp4-m3-multi-method`; paradigm-aware agent + list_editor widget + 3 new qual tools)

**Spec:** `docs/superpowers/specs/2026-05-27-sp4-m3-multi-method-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp4-m3-multi-method-plan.md`

**Delivers:**
- Single `M3Agent` with paradigm-aware `_next_missing_field` walking `_FIELDS_BY_PARADIGM[paradigm]`; mixed flow composes quant + qual branches in order
- Improved flat `M3Output` schema with paradigm-specific optionals + `@model_validator` that fires only when `confirmed_at` is set
- Three new qualitative-flow tools: `suggest_themes`, `compose_interview_guide`, `suggest_purposive_criteria`
- Four static option JSON files (`_options_tool_quant.json`, `_options_tool_qual.json`, `_options_design_qual.json`, `_options_mixed_design_type.json`)
- New widget variant `ListEditorHint` joins the SP3 `WidgetHint` discriminated union; `ListEditorWidget` React component with local state + batch synthesize on Confirm
- `summarizeList` helper builds per-field bulleted final-state messages routed through the existing send path

**Decisions worth remembering for SP5-SP6:**
- Paradigm-aware field walks can live entirely in a single ModuleAgent override (`_next_missing_field`) — no sub-graph needed when branches differ only in *fields asked*, not in *conversational phases*
- New widget variants extend the WidgetHint discriminated union; existing variants and the `WidgetRenderer` default-null forward-compat stay untouched
- List_editor batch-confirm + per-field synthesizer keeps the LLM extraction unambiguous and the chat noise low
```

Append to the Status log:

```
| 2026-05-27 | 4 | ⬜ → ✅ | M3 multi-method shipped — paradigm-aware agent + list_editor widget + 3 new qual tools |
```

- [ ] **Step 4: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs: SP4 shipped — roadmap flip to ✅"
```

---

## Done criteria checklist

- [ ] All 19 tasks committed in order on branch `feat/sp4-m3-multi-method`
- [ ] All web tests pass (`cd web && npm test`)
- [ ] All orchestrator tests pass (`python -m pytest orchestrator/tests/ -q`)
- [ ] API tests show only baseline failures + new tests passing (diff vs `.baseline_failures_2026-05-26.txt` is empty)
- [ ] `npm run build` succeeds in `web/`
- [ ] Schema-drift test catches a deliberately-broken Pydantic↔TS mismatch (try removing a field from `ListEditorHint` Python class; assert TS build fails; revert)
- [ ] Roadmap flipped to ✅ for SP4
- [ ] End-to-end manual smoke (optional): start `./dev.sh`, hit `/chat`, create a project with `paradigm = qualitative`, walk through the qual fields, confirm each list_editor widget renders + Reset + Confirm work + the synthesized message appears in chat

---

## What's next after SP4 ships

**SP5 — M4 Adaptive Analysis** is next. M4 reads `m3_design.paradigm` to pick an outline template, `m3_design.tool` to choose a parser, and `m3_design.conceptual_model` / `m3_design.themes` for content. SP4's flat-schema choice keeps M4's consumer code simple — it reads one type and switches behavior on `paradigm`. SP4's `list_editor` variant carries forward and may be reused for M4's outline-step editing.
