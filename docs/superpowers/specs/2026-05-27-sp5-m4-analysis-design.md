# SP5 — M4 Adaptive Analysis Design Spec

**Date:** 2026-05-27
**Owner:** Cao Nguyen
**Parent roadmap:** `docs/superpowers/2026-05-26-platform-pivot-roadmap.md` (Sub-project 5)
**Depends on:** SP1 (orchestration foundation), SP3 (widget protocol), SP4 (list_editor variant + paradigm-aware ModuleAgent pattern)
**Status:** 🟡 (designed; awaiting plan)

---

## Goal

Replace the SP1-stub `run_analysis_step` with real per-step parsers + execution + plain-language interpretation, driven by an editable analysis outline. The user pastes their analysis output (SPSS / SmartPLS / R lavaan / transcript text); the agent parses each outline step into structured numbers, formats markdown tables with threshold checks, and writes per-step results to `M4Output.results` for M5 (Chapter 4 composer) to consume.

**Explicit non-goal for SP5:** file uploads (`.sav`, `.spv`, `.xlsx`). Paste-text only. File ingestion is a follow-up sub-project (SP5.5).

---

## Locked decisions (from brainstorming)

| # | Question | Answer |
|---|---|---|
| Q1 (scope) | Sub-project scope | **C.** Paste-text only — no file uploads. Sidesteps S3 plumbing + per-vendor binary parsers. |
| Q1 (execution) | Per-step execution model | **C.** Auto-run all steps + sequential per-step rendering. Each step emits its own AIMessage in one LangGraph update. |
| Q2 (extraction) | Paste-text extraction strategy | **C.** Hybrid: regex-first per format; LLM fallback on regex miss; stub on both miss. |
| Q3 (rendering) | Result rendering format | **C.** Plain markdown tables in chat + structured `results` dict in `M4Output`. No new widget variant. |
| Q4 (ad-hoc) | Ad-hoc analysis trigger | **B.** Natural-language LLM-detected intent → `run_extra_analysis` tool. No slash command. |
| Q5 (qual depth) | Qualitative coding pipeline depth | **C.** Codes + themes only; no writeup (M5 owns Chapter 4 composition). |

---

## Architecture

Single `M4Agent` extends the SP3/SP4 ModuleAgent pattern. The agent's field walk is driven by `_outline_template_key()` which reads `m3_design.tool` (SmartPLS → Outline B, SPSS → Outline A, etc.). The walk shape per outline type is in `_FIELDS_BY_OUTLINE_TYPE`. Pseudo-fields `_run_execution` and `_run_qual_pipeline` trigger an execution phase inside `M4Agent.step()` that emits N back-to-back `AIMessage`s in one LangGraph update — one per outline step — for the SSE stream to forward.

Each step's extraction follows a hybrid path: format-specific regex parser → LLM fallback on regex miss → stub on both miss. The `parser` field on each `StepResult` records which path produced the value, enabling audit trails and parser tightening.

The widget protocol from SP3/SP4 is reused unchanged. Outline editing uses the `list_editor` variant added in SP4. No new widget arms, no new SSE event types, no new HTTP endpoints. Frontend work for SP5 is limited to extending `summarizeList` for three new outline-field names and one ChatPane integration test.

Ad-hoc analysis (PRD §6.4.6) lands as a tool call decided by the LLM in the system prompt — when the user asks for an analysis beyond the confirmed outline, the agent calls `run_extra_analysis(step_description, data_paste)` which appends a `StepResult` to `M4Output.custom_analyses`.

The qualitative pipeline ships only 2 steps (codes → themes) per Q5=C; Braun & Clarke's writeup phase moves to M5 where it belongs alongside Chapter 4 composition.

---

## File map

### NEW backend files

```
orchestrator/tools/m4_parsers/__init__.py                  # package + startup consistency check
orchestrator/tools/m4_parsers/spss.py                      # SPSS paste-text regex parser
orchestrator/tools/m4_parsers/smartpls.py                  # SmartPLS report regex parser
orchestrator/tools/m4_parsers/lavaan.py                    # R lavaan output regex parser
orchestrator/tools/m4_parsers/transcript.py                # qual transcript helpers + code/theme tools
orchestrator/tools/m4_parsers/llm_fallback.py              # extract_step_data LLM tool
orchestrator/tools/m4_parsers/golden/spss_cronbach.txt     # golden fixtures (anonymized)
orchestrator/tools/m4_parsers/golden/spss_regression.txt
orchestrator/tools/m4_parsers/golden/smartpls_loadings.txt
orchestrator/tools/m4_parsers/golden/smartpls_paths.txt
orchestrator/tools/m4_parsers/golden/lavaan_cfa.txt
orchestrator/tools/m4_parsers/golden/transcript_short.txt
orchestrator/tests/tools/test_m4_parsers/test_spss.py
orchestrator/tests/tools/test_m4_parsers/test_smartpls.py
orchestrator/tests/tools/test_m4_parsers/test_lavaan.py
orchestrator/tests/tools/test_m4_parsers/test_transcript.py
orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py
orchestrator/tests/agents/test_m4_outline.py
orchestrator/tests/agents/test_m4_execution.py
orchestrator/tests/agents/test_m4_ad_hoc.py
api/tests/test_m4_round_trip.py
```

### MODIFIED backend files

```
orchestrator/agents/m4_analysis.py                         # rewrite — outline-aware override + execution phase + ad-hoc
orchestrator/schemas/m4.py                                 # add StepResult + extend M4Output
orchestrator/tools/m4_analysis.py                          # extend run_analysis_step (real) + run_extra_analysis (new)
orchestrator/prompts/m4.md                                 # rewrite — paste-prompt + outline + ad-hoc guidance
orchestrator/tests/test_tools_m4.py                        # extend
orchestrator/tests/test_schemas.py                         # extend with M4 validator tests
orchestrator/tests/test_agents_m4.py                       # update existing auto-mode if schema impacts it
api/tests/test_chat_messages_widgets.py                    # extend with analysis_outline contract test
```

### MODIFIED frontend files

```
web/app/components/chat/widgets/synthesize.ts              # add analysis_outline / outline_quant / outline_qual cases
web/app/components/chat/widgets/synthesize.test.ts         # extend
web/app/components/chat/ChatPane.test.tsx                  # extend with analysis_outline integration test
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md      # flip SP5 to ✅
```

---

## Schema — `orchestrator/schemas/m4.py`

```python
"""M4 Data Analysis output schema (SP5 — adaptive analysis with real parsers)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DataType = Literal["SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"]
Parser = Literal["regex", "llm_fallback", "stub"]


class StepResult(BaseModel):
    """One outline step's parsed output."""
    step_name: str
    table: list[dict] = Field(default_factory=list)  # rows of structured numbers
    thresholds_met: bool | None = None               # null when step has no thresholds
    interpretation: str = ""                          # plain-language paragraph
    raw_paste_excerpt: str = ""                       # debug + retraceability
    parser: Parser = "regex"


class M4Output(BaseModel):
    data_type_detected: DataType
    analysis_outline: dict                            # {sections: [{name, description, thresholds?}], confirmed_by_user: bool}
    data_paste: str = ""                              # capped at 50KB
    results: dict[str, StepResult] = Field(default_factory=dict)  # keyed by step_name
    qual_codes: list[dict] = Field(default_factory=list)   # qual-only: [{code, quote, line_no?}]
    qual_themes: list[dict] = Field(default_factory=list)  # qual-only: [{theme, codes: [str]}]
    custom_analyses: list[StepResult] = Field(default_factory=list)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _require_artifacts_on_confirm(self):
        """Paradigm-specific minimum artifacts when confirmed."""
        if self.confirmed_at is None:
            return self
        if self.data_type_detected == "Qualitative":
            if not self.qual_codes or not self.qual_themes:
                raise ValueError("qual analysis requires qual_codes + qual_themes when confirmed")
        elif self.data_type_detected in ("SPSS", "SmartPLS", "CB-SEM"):
            if not self.results:
                raise ValueError(f"{self.data_type_detected} analysis requires results when confirmed")
        elif self.data_type_detected == "Mixed":
            if not self.results or not self.qual_codes or not self.qual_themes:
                raise ValueError("mixed analysis requires both quant results and qual artifacts when confirmed")
        return self
```

---

## Agent — `M4Agent`

```python
"""M4 — Data Analysis agent (SP5 adaptive analysis with paste-text parsers)."""
import json
from pathlib import Path

from langchain_core.messages import AIMessage

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.agents.widgets import ListEditorHint, ListItem
from orchestrator.schemas.m4 import M4Output, StepResult
from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline, interpret_result,
    run_analysis_step, run_extra_analysis,
)
from orchestrator.tools.m4_parsers import dispatch_parse, format_step_as_markdown


# SP5: outline-type-aware field walk. Keys are resolved from m3_design.tool.
_FIELDS_BY_OUTLINE_TYPE = {
    "SPSS":        ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "SmartPLS":    ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "CB-SEM":      ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "Qualitative": ["data_paste", "analysis_outline", "_run_qual_pipeline", "_summary"],
    "Mixed":       ["data_paste_quant", "outline_quant", "_run_execution",
                    "data_paste_qual",  "outline_qual",  "_run_qual_pipeline", "_summary"],
}


class M4Agent(ModuleAgent):
    schema = M4Output
    module_key = "M4"
    # ... system_prompt + tools list

    # SP5 class-level caches populated by step()
    _render_outline_type: str | None = None
    _render_paste_text: str = ""
    _render_outline: dict | None = None

    def step(self, state):
        """Stash outline type + paste text + confirmed outline so the hint hook
        can read them. Also dispatches execution-phase emission when the field
        walk hits a pseudo-field (_run_execution / _run_qual_pipeline)."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        m3 = state["context_store"].m3_design or {}
        # Prefer data_type_detected (post-paste) over m3.tool (pre-paste).
        cls._render_outline_type = (
            partial.get("data_type_detected")
            or self._outline_template_key_from_tool(m3.get("tool"))
        )
        cls._render_paste_text = partial.get("data_paste", "")
        cls._render_outline = partial.get("analysis_outline")

        # Execution-phase dispatch: when next missing field is a pseudo-field,
        # run the loop and return a ModuleStepResult with N AIMessages.
        missing = self._next_missing_field(partial)
        if missing in ("_run_execution", "_run_qual_pipeline"):
            return self._dispatch_execution(state, partial, missing)
        return super().step(state)

    def _outline_template_key_from_tool(self, tool: str | None) -> str:
        if tool is None:
            return "Unknown"
        t = tool.lower()
        if "smartpls" in t:
            return "SmartPLS"
        if "amos" in t or "lavaan" in t:
            return "CB-SEM"
        if "spss" in t or "stata" in t:
            return "SPSS"
        if "nvivo" in t or "atlas" in t or "manual" in t:
            return "Qualitative"
        return "Unknown"

    def _resolved_outline_key(self, partial: dict) -> str | None:
        """Pick the _FIELDS_BY_OUTLINE_TYPE key. For mixed paradigm, the agent's
        previous m3_design.paradigm gates this branch; mixed always returns 'Mixed'."""
        from orchestrator.state import get_module_slice
        # Use the cached render_outline_type populated by step(). For mixed paradigm,
        # m3.paradigm overrides — both data sources land in this method.
        return self._render_outline_type

    def _next_missing_field(self, partial: dict) -> str | None:
        key = self._resolved_outline_key(partial)
        if key is None or key not in _FIELDS_BY_OUTLINE_TYPE:
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_OUTLINE_TYPE[key]:
            v = partial.get(name)
            if name in ("_run_execution", "_run_qual_pipeline", "_summary"):
                # Pseudo-fields are "filled" by side-effect of step(); the walk
                # advances when their corresponding marker key is set.
                if not partial.get(f"{name}_done"):
                    return name
                continue
            if v is None or v == "" or v == []:
                return name
        return None

    def render_hint_for_field(self, field_name: str) -> dict | None:
        if field_name in ("analysis_outline", "outline_quant", "outline_qual"):
            template_key = self._render_outline_type or "SPSS"
            sections = self._load_outline_template(template_key, field_name)
            items = [
                ListItem(
                    id=f"s{i}", text=s["name"],
                    meta={"thresholds": s.get("thresholds", "")},
                )
                for i, s in enumerate(sections)
            ]
            return ListEditorHint(
                field_name=field_name,
                title=f"{template_key} analysis outline — edit and confirm",
                initial_items=items,
                allow_nested=False,
            ).model_dump()
        return None  # free-text for data_paste*; None for pseudo-fields

    def _dispatch_execution(self, state, partial, pseudo_field):
        """Run all outline steps in one operation, emit N+1 AIMessages."""
        if pseudo_field == "_run_qual_pipeline":
            return self._run_qual_pipeline(state, partial)
        return self._run_quant_execution(state, partial)

    def _run_quant_execution(self, state, partial):
        outline = partial.get("analysis_outline") or {}
        sections = outline.get("sections", [])
        results: dict[str, dict] = dict(partial.get("results", {}))
        messages: list[AIMessage] = []
        for section in sections:
            step_name = section["name"]
            sr = run_analysis_step.invoke({
                "step_name": step_name,
                "data": {"paste": self._render_paste_text,
                         "data_type": self._render_outline_type},
            })
            results[step_name] = sr
            messages.append(AIMessage(content=format_step_as_markdown(sr)))
        # Final summary
        summary = self._build_execution_summary(results)
        messages.append(AIMessage(content=summary))
        partial["results"] = results
        partial["_run_execution_done"] = True
        partial["_awaiting_confirm"] = True
        return ModuleStepResult(
            assistant_message="",  # multi-message: see messages list below
            context_patch=partial,
            transition=False, needs_user_reply=True,
            extra_messages=messages,  # graph node attaches these AIMessages
        )

    # _run_qual_pipeline analogous: calls suggest_qual_codes + cluster_codes_into_themes,
    # writes to partial["qual_codes"]/["qual_themes"], emits 2 step messages + 1 summary.
```

**Note on `extra_messages`.** The base `ModuleStepResult` has `assistant_message: str` (single message). For SP5 we extend the dataclass with `extra_messages: list[AIMessage] = field(default_factory=list)` and update `_agent_node_factory` in `orchestrator/graph.py` to include them in the returned `messages` list when present. This is a small additive change to the graph wiring that other agents can opt into later. See "Risks" §3 for the rationale on doing this in the graph (not via the base step()).

---

## Parsers — `orchestrator/tools/m4_parsers/`

```python
# __init__.py
from .spss import parse_spss
from .smartpls import parse_smartpls
from .lavaan import parse_lavaan
from .transcript import suggest_qual_codes, cluster_codes_into_themes
from .llm_fallback import extract_step_data

_PARSERS = {
    "SPSS": parse_spss,
    "SmartPLS": parse_smartpls,
    "CB-SEM": parse_lavaan,
}


def dispatch_parse(data_type: str, text: str, step_name: str):
    """Regex-first, LLM-fallback. Returns StepResult dict or None."""
    parser = _PARSERS.get(data_type)
    if parser is None:
        return None
    result = parser(text, step_name)
    if result is not None:
        return result
    # Fallback path: LLM extraction with the step name + a hint of expected schema.
    return extract_step_data.invoke({
        "text": text, "step_name": step_name,
        "data_type": data_type,
    })


def format_step_as_markdown(step_result: dict) -> str:
    """Build the markdown body for a per-step AIMessage."""
    name = step_result["step_name"]
    rows = step_result.get("table", [])
    interp = step_result.get("interpretation", "")
    md = f"**{name}**\n\n"
    if rows:
        cols = list(rows[0].keys())
        md += "| " + " | ".join(cols) + " |\n"
        md += "| " + " | ".join("---" for _ in cols) + " |\n"
        for r in rows:
            md += "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n"
        md += "\n"
    md += interp
    return md
```

Each format module (`spss.py`, `smartpls.py`, `lavaan.py`, `transcript.py`) exports `parse_<format>(text, step_name) -> dict | None` (the StepResult dict shape). Each contains regex extractors keyed by step name. On no-match, returns None (signaling fallback). On match, returns a StepResult dict with `parser="regex"` and `thresholds_met` computed against literature-standard thresholds.

`llm_fallback.py` exports an `@tool extract_step_data(text, step_name, data_type)` that calls the LLM with a JSON-schema prompt + safe fallback to None on malformed.

`__init__.py` includes a startup consistency check: `assert every step in _OUTLINE_TEMPLATES[tool] has a step_extractors[tool] key` — fires at import time if a step is in the outline but not parsed.

---

## Updated tool — `run_analysis_step` (real, not stub)

```python
# orchestrator/tools/m4_analysis.py
@tool
def run_analysis_step(step_name: str, data: dict) -> dict:
    """Parse one outline step from the user's pasted analysis output.

    Hybrid extraction: regex-first per format, LLM fallback on miss, stub on
    both miss. The returned StepResult dict's `parser` field records the path.
    """
    text = data.get("paste", "")
    data_type = data.get("data_type", "Unknown")
    result = dispatch_parse(data_type, text, step_name)
    if result is None:
        # Both regex and LLM fallback failed — return a stub StepResult.
        return StepResult(
            step_name=step_name,
            interpretation="(unable to parse this step from the paste; please paste this step's output separately)",
            parser="stub",
        ).model_dump()
    return result
```

---

## New tool — `run_extra_analysis`

```python
@tool
def run_extra_analysis(step_description: str, data_paste: str) -> dict:
    """Ad-hoc analysis requested via natural language. Used when the user asks
    for an analysis beyond the confirmed outline (PRD §6.4.6).

    Calls the LLM to extract a StepResult-shaped result; appends to
    M4Output.custom_analyses via the agent (not via the parser dispatch).
    """
    return extract_step_data.invoke({
        "text": data_paste, "step_name": step_description,
        "data_type": "AdHoc",
    })
```

The agent's system prompt (`orchestrator/prompts/m4.md`) instructs:
> When the user requests an analysis beyond the confirmed outline (e.g. "also run a mediation test on H3", "rerun the regression with control variables"), call `run_extra_analysis(step_description, data_paste)`. Append the result to `M4Output.custom_analyses`. Render the result as a per-step markdown table in your reply.

---

## Frontend — `summarizeList` extension

Three new field-name cases in `synthesize.ts`:

```typescript
case "analysis_outline":
case "outline_quant":
case "outline_qual":
  return [
    "My analysis outline:",
    ...items.map((s, i) => {
      const thresholds = (s.meta?.thresholds as string | undefined);
      return thresholds
        ? `${i + 1}. ${s.text} — ${thresholds}`
        : `${i + 1}. ${s.text}`;
    }),
  ].join("\n");
```

Numbered, with inline thresholds — this is the natural shape for an academic chapter's analysis outline.

---

## Data flow — quantitative happy path

```
supervisor → M4
M4Agent.step()
  m3_design.tool = "SmartPLS" → _render_outline_type = "SmartPLS"
  field walk: data_paste → analysis_outline → _run_execution → _summary
  next missing = "data_paste"
  render_hint_for_field returns None
  assistant: "Paste your SmartPLS report output and I'll run the outline."
user: <pastes ~30KB of SmartPLS report>
M4Agent.step()
  _extract_answer reads paste-text into partial["data_paste"]
  next missing = "analysis_outline"
  render_hint_for_field returns ListEditorHint with 8 SmartPLS steps + thresholds
assistant + widget: "Confirm the 8-step PLS-SEM outline below."
user: <edits if needed, clicks Confirm>
M4Agent.step()
  _extract_answer parses "My analysis outline:\n1. Outer Loadings — ≥ 0.7\n..." → partial["analysis_outline"]
  next missing = "_run_execution"
  step() dispatches _run_quant_execution(state, partial):
    for each section: parse → StepResult → format markdown
    emits 8 AIMessages + 1 summary AIMessage
  graph node attaches all 9 messages; chat router gen() loops and emits SSE for each
user sees 8 result bubbles stream in, then a confirmation prompt
user: "yes"
M4Agent finalizes:
  confirmed_at = utc_now()
  @model_validator passes
  transition=True → supervisor routes onward
```

**Qualitative happy path:** Same shape, but `_FIELDS_BY_OUTLINE_TYPE["Qualitative"]` walks `data_paste → analysis_outline (2 steps) → _run_qual_pipeline → _summary`. `_run_qual_pipeline` calls `suggest_qual_codes(transcript) → cluster_codes_into_themes(codes)` and emits 2 step messages + 1 summary. Writes to `partial["qual_codes"]` and `partial["qual_themes"]`.

**Mixed happy path:** Walks `data_paste_quant → outline_quant → _run_execution → data_paste_qual → outline_qual → _run_qual_pipeline → _summary`. ~9 chat turns total.

**Ad-hoc flow:** After confirmation prompt or mid-execution, user says "also run a mediation test on H3". The agent's `_ask_next_question` LLM call recognizes the ad-hoc intent (per system prompt instruction), calls `run_extra_analysis`, appends to `partial["custom_analyses"]`, emits one markdown step message. Returns to where it was in the walk.

---

## Testing strategy

### Backend unit tests

| File | What it covers |
|---|---|
| `orchestrator/tests/test_tools_m4.py` (extend) | run_analysis_step dispatches to parsers + LLM fallback + stub paths; run_extra_analysis returns StepResult shape; existing detect_data_type / generate_analysis_outline tests stay |
| `tests/tools/test_m4_parsers/test_spss.py` (NEW) | Golden fixture tests for SPSS step extractors (Cronbach, EFA, regression, ANOVA) — assert StepResult.table rows + thresholds_met |
| `tests/tools/test_m4_parsers/test_smartpls.py` (NEW) | Golden fixture tests for 8 SmartPLS steps |
| `tests/tools/test_m4_parsers/test_lavaan.py` (NEW) | Golden fixture tests for CFA + structural model |
| `tests/tools/test_m4_parsers/test_transcript.py` (NEW) | Paragraph splits + speaker tagging; suggest_qual_codes + cluster_codes_into_themes (LLM stubbed) |
| `tests/tools/test_m4_parsers/test_llm_fallback.py` (NEW) | extract_step_data with stubbed LLM: returns StepResult on valid JSON, None on malformed |
| `tests/test_schemas.py` (extend) | StepResult round-trip; M4Output @model_validator enforces confirm-time rules for SPSS / Qualitative / Mixed |
| `tests/agents/test_m4_outline.py` (NEW) | _outline_template_key_from_tool returns correct outline key per m3.tool; _FIELDS_BY_OUTLINE_TYPE walks correctly per outline key; analysis_outline ListEditorHint shape |
| `tests/agents/test_m4_execution.py` (NEW) | After confirmed outline + paste, _run_quant_execution emits N+1 AIMessages with correct content; StepResults land in partial["results"]; parser fallback path stubbed |
| `tests/agents/test_m4_ad_hoc.py` (NEW) | LLM detects ad-hoc intent → calls run_extra_analysis → result appended to partial["custom_analyses"] |
| `tests/test_agents_m4.py` (extend) | Existing M4 auto-mode test stays; assert it still passes against the new StepResult shape |

### Backend integration tests

| File | What it covers |
|---|---|
| `api/tests/test_chat_messages_widgets.py` (extend) | analysis_outline list_editor SSE round-trip (contract test — no router changes) |
| `api/tests/test_m4_round_trip.py` (NEW) | Synthesized "My analysis outline:\n1. ..." → _extract_answer("analysis_outline") returns expected {sections: [...]}; same for outline_quant, outline_qual, data_paste field |

### Frontend tests

| File | What it covers |
|---|---|
| `widgets/synthesize.test.ts` (extend) | summarizeList for analysis_outline/outline_quant/outline_qual produces "My analysis outline:\n1. <step> — <thresholds>" format |
| `ChatPane.test.tsx` (extend) | One integration test: server returns thread with analysis_outline list_editor → click Confirm → POST body contains synthesized text |

### Mocking strategy

- Parsers: real regex on golden fixtures (deterministic, no LLM)
- LLM fallback: `monkeypatch.setattr(<module>._get_llm, ...)` per SP3/SP4 pattern
- Agent: same monkeypatch
- No real Gemini calls in CI

### Golden fixtures

`orchestrator/tools/m4_parsers/golden/` holds anonymized representative outputs:
- `spss_cronbach.txt` — typical SPSS Reliability output
- `spss_regression.txt` — regression coefficients table
- `smartpls_loadings.txt` — measurement model output
- `smartpls_paths.txt` — structural model output
- `lavaan_cfa.txt` — CFA fit indices
- `transcript_short.txt` — 3-paragraph interview with INTERVIEWER:/PARTICIPANT: tags

~50KB total across ~10 files.

### Regression gates

SP5 ships green iff:
- All new tests pass
- `orchestrator/tests/` baseline holds (currently 152 pass after SP4) — no new failures
- `web/` baseline holds (currently 102 pass after SP4) + new SP5 tests
- `api/tests/` shows 52 baseline failures unchanged vs `.baseline_failures_2026-05-26.txt`; 0 new failures

---

## Non-goals (explicit)

| Non-goal | Why deferred | Lands in |
|---|---|---|
| File uploads (`.sav`, `.spv`, `.xlsx`, `.docx`) — pyreadstat / openpyxl / python-docx | Q1=C — paste-text only | SP5.5 (M4 file ingestion) |
| Stata `.log` parser | Less common in master's theses | SP5.5 |
| NVivo `.xlsx` / Atlas.ti exports | Vendor-specific schemas; needs curation | SP5.5 |
| CB-SEM / AMOS / R lavaan full 8-step outline | Lavaan paste-text parsing is in scope; SmartPLS-style 8-step rigor for CB-SEM deferred | Refinement once SmartPLS lands |
| Result-card widget (`result_card` arm of WidgetHint) | Q3=C — plain markdown for V1 | Optional SP5.5 polish |
| Slash-command `/run-extra` UX | Q4=B — NL intent only | Optional post-V1 |
| Braun & Clarke writeup step (theme→prose) | Q5=C — qual stops at codes+themes | SP6 (M5 Writing) |
| Live execution against external SPSS / R / SmartPLS APIs | We parse pasted output; we don't run analyses | Out — fundamental scope |
| Per-step "rerun this step" button | Needs result_card widget; ad-hoc analysis via NL covers same need | Post-V1 |

---

## Risks & mitigations

1. **Regex fragility against vendor format drift.** SPSS v27/v28 reformat tables subtly; SmartPLS reports change between versions. **Mitigation:** golden-fixture tests pin known shapes; LLM fallback handles long-tail variations; the `parser` field on StepResult records the source so we can audit regex coverage and tighten over time.

2. **LLM extraction hallucination.** `extract_step_data` and `run_extra_analysis` could fabricate numbers not in the source paste. **Mitigation:** the LLM prompt explicitly says "return only numbers present in the source text; on uncertainty return null for that cell"; tests stub the LLM for both clean and malformed responses; `parser="llm_fallback"` flag in StepResult tells M5 and the user the source is uncertain.

3. **Multi-message AIMessage emission per step needs a graph-node change.** Today `_agent_node_factory` in `orchestrator/graph.py` returns a single AIMessage. SP5 extends `ModuleStepResult` with an `extra_messages: list[AIMessage]` field; the graph node concatenates `[primary_ai] + extra_messages` into the `messages` list. This is a small additive change that other agents can opt into later (e.g. SP6 may want per-section streaming).

4. **`data_paste` size can exceed JSONB column comfort.** **Mitigation:** soft-cap at 50KB in `_extract_answer` for `data_paste*` fields; on truncation, the agent says "Your paste exceeded 50KB — I've kept the first 50KB. Paste any specific section separately if needed."

5. **Threshold-met logic is per-step hardcoded.** **Mitigation:** thresholds live in the per-step extractor (e.g. `_extract_spss_cronbach` checks `alpha >= 0.7`) rather than in M4Agent; isolates rule-knowledge to parser modules. Adding thresholds = touching parser, not agent.

6. **Mixed paradigm has 7-9 turns total** — long. **Mitigation:** same as SP4 mixed (chat-skip works); the per-step execution streaming makes the path feel less like a slog (results pour in one bubble at a time).

7. **Outline templates may drift between `_OUTLINE_TEMPLATES` dict and parser `step_extractors`.** A step in the outline but not in the parser silently falls through to stub. **Mitigation:** `m4_parsers/__init__.py` startup consistency check asserts every step in `_OUTLINE_TEMPLATES[tool]` has a corresponding `step_extractors[tool]` key; failures raise a clear error in tests + CI.

8. **`data_type_detected` and `m3_design.tool` may disagree.** User picked SmartPLS in M3 but pasted SPSS output. **Mitigation:** `_render_outline_type` prefers `partial.data_type_detected` (set after paste) over `m3.tool` (pre-paste); the agent emits a warning AIMessage when they disagree ("I see SPSS output but M3 said SmartPLS — switching the outline").

---

## Success criteria

- A user picking quantitative + SPSS pastes their output → walks ~4 chat turns → exports a complete M4Output (5-6 step entries in `results`) the M5 chapter-4 composer can consume.
- A user picking qualitative pastes a transcript → walks ~4 chat turns → exports M4Output with structured `qual_codes` + `qual_themes`.
- A user picking mixed walks both flows in sequence (~9 turns) and gets both artifact sets.
- All chat flows reuse SP3/SP4 widgets (`list_editor`) and the SP3 send path — no new HTTP endpoints, no new SSE event types, no new widget variants.
- `web/`, `orchestrator/`, `api/` regression baselines hold.
- Golden-fixture parser tests catch a deliberately-broken regex (try changing one parser's expected column order; assert the fixture test fails; revert).

---

## What's next after SP5 ships

**SP6 — M5 Writing & Finalization.** M5 reads `m4_analysis.results` (per-step structured tables) + `m4_analysis.qual_codes` + `m4_analysis.qual_themes` to compose Chapter 4. The Braun & Clarke writeup step deferred from SP5 lands here. M5 also owns Chapter 1-3 composition (using `m1_topic`, `m2_literature`, `m3_design`), inline citation insertion, paraphrase / translate tools, and the WYSIWYG section editor in the chat UI.

**SP5.5 (optional follow-up) — M4 file ingestion.** Add binary parsers (pyreadstat for `.sav`, openpyxl/python-docx for NVivo exports, lxml for `.spv` XML) behind the existing SP2 upload subsystem. Adds a third widget variant `upload_panel` for the upload-and-detect UX (PRD §6.4.2). Reuses SP5's outline/execution machinery entirely.

**SP5.6 (optional follow-up) — result_card widget.** Adds a typed `result_card` arm to `WidgetHint` for per-step result bubbles with inline "rerun" / "edit" affordances. Backward-compatible with SP5's markdown rendering (the agent picks card vs markdown based on a config flag).
