> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP4 — M3 Research Design (multi-method) Design Spec

**Date:** 2026-05-27
**Owner:** Cao Nguyen
**Parent roadmap:** `docs/superpowers/2026-05-26-platform-pivot-roadmap.md` (Sub-project 4)
**Depends on:** SP1 (orchestration foundation), SP3 (widget protocol + `card_grid`)
**Status:** 🟡 (designed; awaiting plan)

---

## Goal

Make M3 paradigm-aware. The single `M3Agent` walks a different ordered field list for `quantitative`, `qualitative`, and `mixed`, producing a complete-enough Chapter-3 artifact set (conceptual model OR thematic framework + interview guide, plus sampling) for M4/M5 to consume. Extend the SP3 widget protocol with one new variant — `list_editor` — for editable lists (themes, scale items, interview questions, purposive criteria, conceptual-model paths).

**Explicit non-goal for SP4:** the PRD §6.3.3-i drag-and-drop canvas. Paths between constructs are represented as a flat `list_editor` of "A → B (H1+)" rows. The canvas is its own future sub-project.

---

## Locked decisions (from brainstorming)

| # | Question | Answer |
|---|---|---|
| Q1 | Agent topology | **A.** Single `M3Agent`, paradigm-aware fields (mirror SP3's M1 pattern). No sub-graph. |
| Q2 | Schema shape | **A.** Improved flat `M3Output` with paradigm-specific optionals + `@model_validator` enforcing required-by-paradigm at confirm time. |
| Q3 | Widget variant scope | **B.** Add one new variant: `list_editor`. Reuse `card_grid` for every selection point. |
| Q4 | Mixed methods scope | **A.** Full mixed runs both sub-flows in sequence (composition of existing quant + qual branches; no new "mixed-only" code). |
| Q5 | `list_editor` click semantics | **C.** Batch synthesize on Confirm — client-side local state, single round-trip per field. |
| Q6 | Scale items source | **A.** LLM only via existing `suggest_scale_items` tool. Curated canonical scales deferred. |

---

## Architecture

Single `M3Agent` extends the shared `ModuleAgent` clarification loop. The agent's required-fields walk is paradigm-aware: `_FIELDS_BY_PARADIGM` maps each paradigm key to an ordered list of fields the agent asks about. The base `ModuleAgent` is unchanged — M3 overrides `_next_missing_field` to consult `partial["paradigm"]` and pick the right list.

`M3Output` Pydantic schema stays one class (no top-level discriminated union). All paradigm-specific fields are optional at type-level. A `@model_validator(mode="after")` enforces required-by-paradigm rules **only when `confirmed_at` is being set** — in-progress partials remain valid.

The widget protocol from SP3 gains one new arm: `ListEditorHint`. The `WidgetHint = Annotated[Union[CardGridHint, ListEditorHint], Field(discriminator="widget_type")]` discriminated union expands once. `WidgetRenderer.tsx` adds a `"list_editor"` case in its switch. All other widget-protocol surfaces (SSE event shape, `messages.tool_calls_json` JSONB column, `MessageBubble` conditional render, `MessageList` `widgetDisabled` semantics, `ChatPane.onWidgetSelect` synthesize-and-send) stay unchanged.

Two new qualitative-flow tools land in `orchestrator/tools/m3_design.py`: `suggest_themes` and `compose_interview_guide`. A third — `suggest_purposive_criteria` — produces the sampling-strategy fields. All three follow the existing pattern (`@tool` decorator, LLM call, JSON parse, safe fallback dict on malformed response).

Mixed flow is purely composition: `_FIELDS_BY_PARADIGM["mixed_seq_explanatory"]` is `["mixed_design_type"] + QUANT_FIELDS + QUAL_FIELDS`; the exploratory variant flips the suffix order. No mixed-only branch code.

---

## Schema — `orchestrator/schemas/m3.py`

```python
"""M3 Research Design output schema."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, model_validator

from .common import Paradigm

MixedDesignType = Literal["sequential_explanatory", "sequential_exploratory"]


class M3Output(BaseModel):
    # Common fields — present for every paradigm
    paradigm: Paradigm
    design: str = Field(..., description="e.g. PLS-SEM, Thematic Analysis, Sequential Explanatory")
    tool: str = Field(..., description="SmartPLS, NVivo, SPSS, ...")
    sampling_strategy: str
    target_sample_size: int = Field(..., gt=0)
    confirmed_at: datetime | None = None

    # Quant-only — required when paradigm == "quantitative" (or part of mixed)
    conceptual_model: dict | None = None     # {constructs: [...], paths: [{from, to, hypothesis}]}
    scale_items: list[dict] | None = None    # grouped by construct
    hypotheses: list[dict] | None = None

    # Qual-only — required when paradigm == "qualitative" (or part of mixed)
    themes: list[dict] | None = None         # [{id, theme, sub_themes: [...]}]
    interview_guide: dict | None = None      # {sections: [{phase, time_minutes, questions: [...]}]}
    purposive_criteria: list[dict] | None = None

    # Mixed-only
    mixed_design_type: MixedDesignType | None = None

    # Kept for backward compatibility (existing M5 consumers read this name)
    constructs: list[dict] = Field(default_factory=list)
    questionnaire_text: str | None = None

    @model_validator(mode="after")
    def _require_by_paradigm(self):
        """Enforce paradigm-specific required fields at confirm time only."""
        if self.confirmed_at is None:
            return self  # in-progress partials are allowed to be incomplete

        if self.paradigm == "quantitative":
            assert self.conceptual_model, "quantitative paradigm requires conceptual_model"
            assert self.scale_items, "quantitative paradigm requires scale_items"
        elif self.paradigm == "qualitative":
            assert self.themes, "qualitative paradigm requires themes"
            assert self.interview_guide, "qualitative paradigm requires interview_guide"
            assert self.purposive_criteria, "qualitative paradigm requires purposive_criteria"
        elif self.paradigm == "mixed":
            assert self.mixed_design_type, "mixed paradigm requires mixed_design_type"
            # Both sub-paradigm artifacts required
            assert self.conceptual_model and self.scale_items, "mixed requires quant artifacts"
            assert self.themes and self.interview_guide and self.purposive_criteria, \
                "mixed requires qual artifacts"
        return self
```

---

## Agent — `orchestrator/agents/m3_design.py`

```python
"""M3 — Research Design agent (paradigm-aware multi-method)."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption, ListEditorHint, ListItem
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, compose_interview_guide, estimate_sample_size,
    recommend_methodology, suggest_purposive_criteria, suggest_scale_items,
    suggest_themes,
)


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m3.md").read_text()


# Field walk order per paradigm. M3 overrides _next_missing_field to consult
# this map. Each key is the resolved paradigm-or-mixed-type.
_FIELDS_BY_PARADIGM = {
    "quantitative": [
        "design", "tool", "conceptual_model", "scale_items",
        "target_sample_size", "sampling_strategy",
    ],
    "qualitative": [
        "design", "tool", "themes", "interview_guide", "purposive_criteria",
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_seq_explanatory": [
        "mixed_design_type",
        # Quant first
        "design", "tool", "conceptual_model", "scale_items",
        # Qual second (reuses the same `design` + `tool` slots — the agent's
        # prompt explains to the user that this round picks the qual design
        # and analysis tool, and treats the previously-filled fields as quant.
        # An optional V2 enhancement would split into design_quant/design_qual.)
        "themes", "interview_guide", "purposive_criteria",
        # Shared at the end
        "target_sample_size", "sampling_strategy",
    ],
    "mixed_seq_exploratory": [
        "mixed_design_type",
        # Qual first
        "themes", "interview_guide", "purposive_criteria",
        # Quant second
        "design", "tool", "conceptual_model", "scale_items",
        # Shared at the end
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
        """Return the key into _FIELDS_BY_PARADIGM for current partial state.

        For mixed paradigm we can't pick a walk order until mixed_design_type is set.
        Until then we return `mixed_seq_explanatory` as a default — it just causes
        mixed_design_type to be the first asked field, then the walk re-resolves.
        """
        p = partial.get("paradigm")
        if p == "mixed":
            return f"mixed_{(partial.get('mixed_design_type') or 'seq_explanatory')}"
        return p

    def _next_missing_field(self, partial: dict) -> str | None:
        """Paradigm-aware override. Walk the ordered list for the resolved key."""
        key = self._resolved_paradigm_key(partial)
        if key is None:
            # paradigm not yet filled — fall back to the base class behavior
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_PARADIGM[key]:
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None

    def render_hint_for_field(self, field_name: str) -> dict | None:
        # Card-grid hints (selection points)
        if field_name == "tool":
            return CardGridHint(
                field_name="tool",
                title="Which analysis tool will you use?",
                options=self._tool_options(),
                columns=3,
            ).model_dump()
        if field_name == "design":
            return CardGridHint(
                field_name="design",
                title="Which research design fits your study?",
                options=self._design_options_for_current_paradigm(),
                columns=2,
            ).model_dump()
        if field_name == "mixed_design_type":
            return CardGridHint(
                field_name="mixed_design_type",
                title="Which mixed-methods design?",
                options=[
                    CardOption(value="sequential_explanatory",
                               label="Sequential Explanatory",
                               description="Quantitative survey first, qualitative interviews after to explain results"),
                    CardOption(value="sequential_exploratory",
                               label="Sequential Exploratory",
                               description="Qualitative first to build constructs, quantitative survey after to test"),
                ],
                columns=2,
            ).model_dump()

        # List-editor hints (editable list fields)
        if field_name == "themes":
            return self._list_editor_for_themes()
        if field_name == "interview_guide":
            return self._list_editor_for_interview_guide()
        if field_name == "purposive_criteria":
            return self._list_editor_for_purposive_criteria()
        if field_name == "conceptual_model":
            return self._list_editor_for_conceptual_model()
        if field_name == "scale_items":
            return self._list_editor_for_scale_items()

        return None  # free-text for sampling_strategy / target_sample_size

    # ...helper methods _tool_options, _design_options_for_current_paradigm,
    # _list_editor_for_themes, _list_editor_for_interview_guide,
    # _list_editor_for_purposive_criteria, _list_editor_for_conceptual_model,
    # _list_editor_for_scale_items each load static option JSONs and/or
    # call tools to produce initial_items, then return ListEditorHint(...).model_dump()
```

The helper methods load `_options_{tool|design_quant|design_qual}.json` for static card-grid options and call the respective tools (`suggest_themes`, `compose_interview_guide`, etc.) with the project's `research_question` (read from `partial`'s sibling slice — passed via the ContextStore traversal already implemented in SP1).

---

## Widgets — `orchestrator/agents/widgets.py`

Extend the SP3 discriminated union:

```python
class ListItem(BaseModel):
    id: str
    text: str
    sub_items: list["ListItem"] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)

ListItem.model_rebuild()


class ListEditorHint(BaseModel):
    """Editable list. User edits locally, clicks Confirm to submit one final-state message."""
    widget_type: Literal["list_editor"] = "list_editor"
    field_name: str
    title: str
    initial_items: list[ListItem]
    allow_nested: bool = False
    confirm_label: str = "Confirm"
    reset_label: str = "Reset to suggested"


# Discriminated union grows by one arm.
WidgetHint = Annotated[
    Union[CardGridHint, ListEditorHint],
    Field(discriminator="widget_type"),
]
```

---

## New tools — `orchestrator/tools/m3_design.py`

Three new `@tool`-decorated functions following the existing pattern (LLM call → JSON parse → safe-fallback dict on malformed):

```python
@tool
def suggest_themes(research_question: str, paradigm: str,
                   gaps_summary: str = "") -> list[dict]:
    """Suggest 3-5 themes for qualitative analysis.

    Returns: [{id, theme, sub_themes: [str]}, ...]
    """
    # LLM call, fallback to [] on malformed.


@tool
def compose_interview_guide(themes: list[dict], research_question: str) -> dict:
    """Build a semi-structured interview guide from themes.

    Returns: {sections: [{phase: "intro"|"main"|"closing", time_minutes,
              questions: [{q, probes: [str]}]}]}
    """
    # LLM call, fallback to a minimal one-section guide on malformed.


@tool
def suggest_purposive_criteria(research_question: str,
                                paradigm: str) -> dict:
    """Propose sampling criteria and strategies for qualitative purposive sampling.

    Returns: {criteria: [str], strategies: [str], saturation_min: int, saturation_max: int}
    """
    # LLM call, fallback to a generic criteria list on malformed.
```

---

## Frontend — TS types

```typescript
// web/app/components/chat/widgets/types.ts (extended)
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

export type WidgetHint = CardGridHint | ListEditorHint;
```

---

## Frontend — `ListEditorWidget.tsx`

A React client component with these contracts:

- **Props:** `{ hint: ListEditorHint, onSelect: WidgetSelectHandler, disabled?: boolean }`
- **Local state:** seeded from `hint.initial_items` on first render. Add/edit/remove/reorder mutate this state only.
- **UI elements:** title; item rows with editable text (double-click to edit) and ✕ remove; if `allow_nested`, each item shows a `+ Sub-item` button and renders its `sub_items` indented; footer with `[Reset] [Confirm]` buttons.
- **Confirm click:** calls `onSelect(hint.field_name, JSON.stringify(items), summarizeList(items, hint.field_name))`. The second argument carries the structured JSON; the third is the natural-language bulleted summary used as the chat message body.
- **Reset click:** re-seeds local state from `hint.initial_items`. No backend call.
- **Disabled prop:** locks all editing; hides Confirm/Reset buttons; items render read-only.
- **`data-testid`:** `list-editor-${hint.field_name}` for the container; `list-item-${item.id}` per row.

`summarizeList(items, field_name)` is a small helper colocated in `synthesize.ts` (kept close to the per-field descriptors). It produces:
- For `themes`: `"My themes are:\n- Theme 1: <text> (Sub: <sub1>, <sub2>)\n- Theme 2: <text>..."`
- For `scale_items`: `"My scale items:\n- <text>\n- <text>..."` (grouped under construct headers if items use nested form)
- For `conceptual_model`: `"My conceptual model paths:\n- A → B (H1+)\n- ..."`
- For `interview_guide`: walks the nested sections + questions and produces a multi-line message
- For `purposive_criteria`: `"My sampling criteria:\n- ..."`

---

## Frontend — `WidgetRenderer.tsx` extension

```typescript
switch (hint.widget_type) {
  case "card_grid":
    return <CardGridWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
  case "list_editor":
    return <ListEditorWidget hint={hint} onSelect={onSelect} disabled={disabled} />;
  default:
    return null;
}
```

`MessageBubble`, `MessageList`, `useChat`, `ChatPane` — unchanged. They already plumb `toolCallsJson`/`onWidgetSelect`/`widgetDisabled` and the synthesize-then-send path.

---

## Data flow — happy-path traces

### Quantitative

1. supervisor routes to M3
2. `M3Agent.step()` reads `paradigm = "quantitative"` from `m1_topic`
3. `_resolved_paradigm_key → "quantitative"`; `_next_missing_field → "design"`
4. `render_hint_for_field("design") → CardGridHint`
5. user picks "PLS-SEM" → synthesize "I'll use PLS-SEM." → POST → agent extracts → `partial["design"] = "PLS-SEM"`
6. next missing = `"tool"` → `CardGridHint(SmartPLS / AMOS / R lavaan)` → user picks → extract
7. next missing = `"conceptual_model"` → `ListEditorHint(initial_items = build_conceptual_model(constructs, RQ).paths)` → user edits → Confirm → synthesize bulleted message → agent extracts → `partial["conceptual_model"]`
8. next missing = `"scale_items"` → `ListEditorHint(allow_nested=true, initial_items = constructs grouped → suggest_scale_items per construct)` → same cycle
9. `"target_sample_size"` → free-text (agent recommends via `estimate_sample_size`, user types value)
10. `"sampling_strategy"` → free-text
11. all fields filled → summary → user confirms → `confirmed_at` set → `@model_validator` checks quant required fields → success → supervisor routes onward

### Qualitative

`design` (card_grid: Thematic / Grounded / Phenomenological / Case Study) → `tool` (card_grid: NVivo / Atlas.ti / Manual) → `themes` (list_editor, nested, from `suggest_themes`) → `interview_guide` (list_editor, nested, from `compose_interview_guide(themes)`) → `purposive_criteria` (list_editor, flat, from `suggest_purposive_criteria`) → free-text size + strategy → confirm.

### Mixed (sequential explanatory)

`mixed_design_type` (card_grid) → walk QUANT_FIELDS in order → walk QUAL_FIELDS in order → free-text size + strategy → confirm. ~12 field turns; user can chat-skip ("keep the qual phase light") and the agent's free-text override accepts.

---

## Testing strategy

### Backend unit tests

| File | What it covers |
|---|---|
| `orchestrator/tests/agents/test_widgets.py` (extend) | `ListEditorHint` Pydantic round-trip; `WidgetHint` union resolves `list_editor` |
| `orchestrator/tests/agents/test_module_agent_render_hint.py` (extend) | Subclass returning `ListEditorHint` flows through; `tool_calls_json` carries the new shape |
| `orchestrator/tests/agents/test_m3_paradigm_branching.py` (NEW) | `_resolved_paradigm_key` + `_next_missing_field` correct for each paradigm; mixed switches after `mixed_design_type` |
| `orchestrator/tests/agents/test_m3_widgets.py` (NEW) | M3Agent emits `card_grid` for tool/design/mixed_design_type; emits `list_editor` for conceptual_model/scale_items/themes/interview_guide/purposive_criteria; free-text fields return None |
| `orchestrator/tests/tools/test_m3_qual_tools.py` (NEW) | `suggest_themes`, `compose_interview_guide`, `suggest_purposive_criteria` — stubbed LLM, structural assertions, fallback-on-malformed coverage |
| `orchestrator/tests/schemas/test_m3_output_validator.py` (NEW) | `@model_validator` enforces required-by-paradigm only when `confirmed_at` set; in-progress partials allowed |

### Backend integration tests

| File | What it covers |
|---|---|
| `api/tests/test_chat_messages_widgets.py` (extend) | SSE emits `tool_calls` for stubbed `list_editor` payload; persistence path round-trips the new shape |
| `api/tests/test_m3_round_trip.py` (NEW) | Synthesized bulleted message → `_extract_answer` returns expected list (per field: themes, scale_items, interview_guide, purposive_criteria, conceptual_model) |

### Frontend tests

| File | What it covers |
|---|---|
| `widgets/types.test.ts` (extend) | `ListEditorHint` fixture matches Pydantic dump shape (build-fails-on-drift guard) |
| `widgets/ListEditorWidget.test.tsx` (NEW) | Renders initial_items (flat + nested); add/edit/remove mutate local state without firing onSelect; Confirm fires onSelect with structured JSON + bulleted label; Reset re-seeds; disabled hides buttons + locks editing |
| `widgets/WidgetRenderer.test.tsx` (extend) | Dispatches `list_editor` to `ListEditorWidget`; unknown `widget_type` still returns null |
| `widgets/synthesize.test.ts` (extend) | List-aware synthesizers (themes, scale_items, interview_guide, purposive_criteria, conceptual_model) produce expected bulleted messages |
| `MessageBubble.test.tsx` (extend) | List_editor widget renders in bubble; disabled prop forwards |
| `ChatPane.test.tsx` (extend) | Integration: server returns thread with one assistant message carrying `themes` list_editor hint → render → user adds a theme → Confirm → asserts POST body's text contains synthesized "My themes are: ..." |

### Mocking

LLM-backed tools stubbed via `monkeypatch.setattr(<tool>._get_llm, ...)` exactly like SP3's M1 widget tests. No real Gemini calls in CI. PRD's example outputs become fixture content.

### Regression gates

SP4 ships green iff:
- All new tests pass
- `orchestrator/tests/` baseline holds (currently 122 pass)
- `web/` baseline holds (currently 80 pass) + new SP4 tests green
- `api/tests/` shows 52 baseline failures unchanged vs `.baseline_failures_2026-05-26.txt`; 0 new failures

---

## Non-goals (explicit)

| Non-goal | Why deferred | Lands in |
|---|---|---|
| Drag-and-drop conceptual-model canvas (PRD §6.3.3-i) | Highest-effort UI piece; needs its own design treatment | Separate post-pivot sub-project |
| Curated canonical scale library (Cronbach alpha + citations) | Real curation work; needs product-market signal | Post-pivot |
| Live Cohen / Hair / G*Power sample-size calculator widget | Existing heuristic tool is good enough for V1 | Post-pivot |
| Per-construct multi-method comparison matrix (PLS-SEM vs CB-SEM trade-offs) | `recommend_methodology` one-line rationale is sufficient | Out |
| Export interview guide to .docx in M3 | M5 owns document export | Out (M5 already does this) |
| Live Cronbach alpha on Likert items | Needs pilot data | M4 |
| Branching within a paradigm by design type | `_FIELDS_BY_PARADIGM` keys on paradigm only; design-specific nuance lives in the system prompt + free-text questions | V1 acceptable, revisit if needed |

---

## Risks & mitigations

1. **LLM extraction of `list_editor` Confirm messages is fragile.** Synthesized bulleted messages route through `_extract_answer` (LLM call). Mitigation: structured punctuation in the synthesized message (the extractor prompt is updated to recognize the bulleted pattern); fall back to a chat clarification turn if parsing yields empty/malformed; round-trip test per list field.

2. **`@model_validator` + in-progress partials.** The validator only fires when `confirmed_at` is being set. In-progress partials with `themes=None` remain valid. Test path covers both states.

3. **`build_conceptual_model` returns `{constructs, paths}`, but `list_editor` consumes `ListItem[]`.** A small pure-Python adapter maps `{from, to, hypothesis}` paths → `[{id: f"H{n}", text: f"{from} → {to}", meta: {hypothesis}}]`. One unit test.

4. **Mixed flow length.** ~12 turns for mixed. Mitigation: per-bubble Confirm cadence; chat-skip fallback for users who want a light secondary phase.

5. **`_next_missing_field` override is M3-only.** Other agents stay on the base behavior. M3 overrides the method (not the underlying `_required_field_names`), which keeps the base class abstraction clean. Decision rationale lives in a code comment on the override.

6. **Widget protocol drift between Pydantic dump and TS type.** SP3 ships a fixture-parity test; SP4 extends the fixture to cover `ListEditorHint`. Frontend build fails on drift.

7. **Roadmap "highest-effort" tag for SP4.** V1 scope is much tighter than the full PRD §6.3 because we deferred the canvas + curated scales + calculator widgets. Roadmap entry will note the deferred surface.

8. **Mixed-paradigm collapses two phases into a single `target_sample_size` and `sampling_strategy`.** The current `M3Output` schema has singular fields. A real mixed study typically has different N and sampling for the quant phase (e.g. N=200 random) vs the qual phase (N=12 purposive). For V1 the user describes both phases in the single `sampling_strategy` free-text field (e.g. "Quant: N=200 random; Qual: N=12 purposive"); M5's Chapter-3 composer reads this as-is. A future schema split into `quant_sample_size`/`qual_sample_size` is a non-breaking additive change.

9. **Mixed-paradigm reuses `design` and `tool` for two phases.** Similarly, mixed users fill `design` + `tool` ONCE per the walk. The agent prompt clarifies which phase the field belongs to when it asks (e.g. "Sequential Explanatory: let's pick the quant analysis tool for the survey phase"). If the user wants distinct design/tool entries per phase, the qual-phase choice lives in the system prompt context but isn't stored as a separate field. Same V2 enhancement as risk #8.

---

## Success criteria

- A user picking `quantitative` walks 6 fields (design → tool → conceptual_model → scale_items → target_sample_size → sampling_strategy) and exports a complete M3Output the M5 chapter-3 composer can read.
- A user picking `qualitative` walks 7 fields (design → tool → themes → interview_guide → purposive_criteria → target_sample_size → sampling_strategy) and gets a structured interview guide + purposive sampling plan.
- A user picking `mixed` walks both branches in the order their `mixed_design_type` choice dictates (~12 turns) and gets both artifact sets.
- All clicks reuse the SP3 send path — no new HTTP endpoints.
- `web/`, `orchestrator/`, `api/` regression baselines hold.
- Schema-drift guard (`widgets/types.test.ts`) catches a deliberately broken Pydantic↔TS mismatch.

---

## What's next after SP4 ships

- **SP5 — M4 Adaptive Analysis.** M4 reads `m3_design.paradigm` to pick an outline template; reads `m3_design.tool` to choose a parser; reads `m3_design.conceptual_model` or `m3_design.themes` for content. SP4's flat-schema choice keeps M4's consumer code simple.
- **SP6 — M5 Writing.** Chapter 3 composer template branches on paradigm, reading the same fields.
- **Canvas as its own sub-project.** Drag-and-drop conceptual-model builder can land as a `canvas_editor` widget variant later, replacing the `list_editor` path-row UI without protocol changes (it's just another arm of the discriminated union).
- **Curated canonical scale library.** Optional post-pivot enhancement of `suggest_scale_items`; surfaces as a card-grid of pre-validated scales.
