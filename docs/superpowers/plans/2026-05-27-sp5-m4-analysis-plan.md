> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP5 — M4 Adaptive Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace M4's SP1-stub execution with real per-step parsers + outline-editing UX + ad-hoc analysis. Paste-text only (no file uploads). Hybrid regex-first / LLM-fallback extraction. Per-step rendering via multi-message emission. Qual pipeline = codes+themes only.

**Architecture:** Single `M4Agent` extends SP3/SP4 ModuleAgent. Field walk is driven by `m3_design.tool` via `_FIELDS_BY_OUTLINE_TYPE`. Pseudo-fields `_run_execution` / `_run_qual_pipeline` trigger an execution phase that emits N back-to-back `AIMessage`s in one LangGraph update via a new `ModuleStepResult.extra_messages` field. Per-format parsers live under `orchestrator/tools/m4_parsers/`.

**Tech Stack:** Python 3.10+, Pydantic v2, LangChain 1.x, LangGraph 1.2+, React 19, Vitest 2.

**Spec:** `docs/superpowers/specs/2026-05-27-sp5-m4-analysis-design.md`
**Depends on:** Sub-projects 1, 2, 3, 4, 7 (all on master).

---

## File map

### NEW backend files

```
orchestrator/tools/m4_parsers/__init__.py
orchestrator/tools/m4_parsers/spss.py
orchestrator/tools/m4_parsers/smartpls.py
orchestrator/tools/m4_parsers/lavaan.py
orchestrator/tools/m4_parsers/transcript.py
orchestrator/tools/m4_parsers/llm_fallback.py
orchestrator/tools/m4_parsers/golden/spss_cronbach.txt
orchestrator/tools/m4_parsers/golden/spss_regression.txt
orchestrator/tools/m4_parsers/golden/smartpls_loadings.txt
orchestrator/tools/m4_parsers/golden/smartpls_paths.txt
orchestrator/tools/m4_parsers/golden/lavaan_cfa.txt
orchestrator/tools/m4_parsers/golden/transcript_short.txt
orchestrator/tests/tools/__init__.py
orchestrator/tests/tools/test_m4_parsers/__init__.py
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
orchestrator/schemas/m4.py                  # add StepResult + extend M4Output + @model_validator
orchestrator/tests/test_schemas.py          # extend with M4Output validator tests
orchestrator/agents/base.py                 # add ModuleStepResult.extra_messages field
orchestrator/graph.py                       # _agent_node_factory forwards extra_messages
orchestrator/tests/test_graph.py            # add test for extra_messages emission
orchestrator/agents/m4_analysis.py          # rewrite — outline-aware override + execution phase
orchestrator/tools/m4_analysis.py           # real run_analysis_step + add run_extra_analysis
orchestrator/tests/test_tools_m4.py         # extend with new tool behavior
orchestrator/tests/test_agents_m4.py        # update existing auto-mode test for new schema shape
orchestrator/prompts/m4.md                  # rewrite for paste-prompt + outline + ad-hoc
api/tests/test_chat_messages_widgets.py     # extend with analysis_outline contract test
```

### MODIFIED frontend files

```
web/app/components/chat/widgets/synthesize.ts            # add 3 outline-field cases
web/app/components/chat/widgets/synthesize.test.ts       # extend
web/app/components/chat/ChatPane.test.tsx                # extend with outline integration test
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md   # flip SP5 to ✅
```

---

## Task index (21 tasks)

| Phase | Tasks |
|---|---|
| A. Foundations | 1. `StepResult` + extend `M4Output` + validator · 2. `ModuleStepResult.extra_messages` + graph forwarding |
| B. Parsers | 3. Parser package skeleton + consistency check · 4. SPSS parser · 5. SmartPLS parser · 6. R lavaan parser · 7. Transcript helpers + qual tools · 8. LLM fallback · 9. `dispatch_parse` + `format_step_as_markdown` |
| C. Tools | 10. Real `run_analysis_step` · 11. `run_extra_analysis` tool |
| D. Agent | 12. `_FIELDS_BY_OUTLINE_TYPE` + walk override · 13. `render_hint_for_field` for outline fields · 14. `_run_quant_execution` · 15. `_run_qual_pipeline` · 16. Ad-hoc detection · 17. M4 prompt rewrite |
| E. API + Frontend | 18. Chat router list_editor contract test · 19. `synthesize.ts` extension · 20. ChatPane integration test |
| F. Round-trip + wrap-up | 21. Backend round-trip tests · regression + roadmap flip (combined) |

(Final count is 21 tasks; the table folds tasks 21+22 together because the round-trip tests run alongside the regression sweep.)

---

## Phase A — Foundations

### Task 1: `StepResult` + extend `M4Output` + `@model_validator`

**Files:**
- Modify: `orchestrator/schemas/m4.py`
- Modify: `orchestrator/tests/test_schemas.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_schemas.py`:

```python
def test_step_result_minimal():
    from orchestrator.schemas.m4 import StepResult
    sr = StepResult(step_name="Cronbach's Alpha")
    assert sr.step_name == "Cronbach's Alpha"
    assert sr.table == []
    assert sr.thresholds_met is None
    assert sr.interpretation == ""
    assert sr.parser == "regex"


def test_step_result_full():
    from orchestrator.schemas.m4 import StepResult
    sr = StepResult(
        step_name="Reliability",
        table=[{"construct": "TL", "alpha": 0.84, "n_items": 5}],
        thresholds_met=True,
        interpretation="All scales reliable.",
        raw_paste_excerpt="Cronbach's Alpha\n.840",
        parser="regex",
    )
    blob = sr.model_dump()
    assert blob["table"][0]["alpha"] == 0.84
    assert blob["parser"] == "regex"


def test_m4_unconfirmed_partial_is_valid_minimal():
    """In-progress partials are valid even with no results."""
    from orchestrator.schemas.m4 import M4Output
    out = M4Output(
        data_type_detected="SPSS",
        analysis_outline={"sections": [], "confirmed_by_user": False},
    )
    assert out.confirmed_at is None
    assert out.results == {}


def test_m4_spss_confirm_requires_results():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="SPSS",
            analysis_outline={"sections": [{"name": "Descriptive"}], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            # missing results
        )


def test_m4_qualitative_confirm_requires_codes_and_themes():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="Qualitative",
            analysis_outline={"sections": [], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            qual_codes=[{"code": "leadership style", "quote": "..."}],
            # missing qual_themes
        )


def test_m4_qualitative_confirm_with_codes_and_themes_validates():
    from datetime import datetime, timezone
    from orchestrator.schemas.m4 import M4Output
    out = M4Output(
        data_type_detected="Qualitative",
        analysis_outline={"sections": [{"name": "Initial coding"}], "confirmed_by_user": True},
        qual_codes=[{"code": "leadership style", "quote": "..."}],
        qual_themes=[{"theme": "Leadership", "codes": ["leadership style"]}],
        confirmed_at=datetime.now(timezone.utc),
    )
    assert len(out.qual_codes) == 1
    assert len(out.qual_themes) == 1


def test_m4_mixed_confirm_requires_both_sets():
    from datetime import datetime, timezone
    from pydantic import ValidationError
    from orchestrator.schemas.m4 import M4Output
    with pytest.raises(ValidationError):
        M4Output(
            data_type_detected="Mixed",
            analysis_outline={"sections": [], "confirmed_by_user": True},
            confirmed_at=datetime.now(timezone.utc),
            results={"Descriptive": {"step_name": "Descriptive"}},
            qual_codes=[],
            qual_themes=[],
        )
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -20
```

Expected: FAIL — `StepResult` doesn't exist; M4Output validator doesn't enforce paradigm rules.

- [ ] **Step 3: Replace `orchestrator/schemas/m4.py`**

```python
"""M4 Data Analysis output schema (SP5 — adaptive analysis with real parsers)."""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DataType = Literal["SPSS", "SmartPLS", "CB-SEM", "Qualitative", "Mixed", "Unknown"]
Parser = Literal["regex", "llm_fallback", "stub"]


class StepResult(BaseModel):
    """One outline step's parsed output. The `parser` field records which path
    produced the values so we can audit regex coverage over time."""
    step_name: str
    table: list[dict] = Field(default_factory=list)
    thresholds_met: bool | None = None
    interpretation: str = ""
    raw_paste_excerpt: str = ""
    parser: Parser = "regex"


class M4Output(BaseModel):
    data_type_detected: DataType
    analysis_outline: dict                                  # {sections: [...], confirmed_by_user: bool}
    data_paste: str = ""                                    # capped at 50KB by the agent
    results: dict[str, dict] = Field(default_factory=dict)  # step_name → StepResult dict
    qual_codes: list[dict] = Field(default_factory=list)
    qual_themes: list[dict] = Field(default_factory=list)
    custom_analyses: list[dict] = Field(default_factory=list)
    # Existing field — preserved for back-compat with M5 readers
    interpretations: dict = Field(default_factory=dict)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def _require_artifacts_on_confirm(self):
        """Paradigm-specific minimum artifacts when confirmed. Fires only when
        confirmed_at is set — in-progress partials remain valid."""
        if self.confirmed_at is None:
            return self
        if self.data_type_detected == "Qualitative":
            if not self.qual_codes:
                raise ValueError("qualitative analysis requires qual_codes when confirmed")
            if not self.qual_themes:
                raise ValueError("qualitative analysis requires qual_themes when confirmed")
        elif self.data_type_detected in ("SPSS", "SmartPLS", "CB-SEM"):
            if not self.results:
                raise ValueError(
                    f"{self.data_type_detected} analysis requires results when confirmed"
                )
        elif self.data_type_detected == "Mixed":
            if not self.results:
                raise ValueError("mixed analysis requires quant results when confirmed")
            if not self.qual_codes or not self.qual_themes:
                raise ValueError("mixed analysis requires qual_codes + qual_themes when confirmed")
        return self
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_schemas.py -v 2>&1 | tail -15
git add orchestrator/schemas/m4.py orchestrator/tests/test_schemas.py
git commit -m "feat(orchestrator): StepResult + M4Output paradigm-aware validator"
```

Expected: existing + 7 new tests PASS.

---

### Task 2: `ModuleStepResult.extra_messages` + graph forwarding

**Files:**
- Modify: `orchestrator/agents/base.py`
- Modify: `orchestrator/graph.py`
- Modify: `orchestrator/tests/test_graph.py`

- [ ] **Step 1: Append the failing test**

Append to `orchestrator/tests/test_graph.py`:

```python
def test_graph_node_emits_extra_messages_from_step_result(monkeypatch):
    """When ModuleStepResult.extra_messages is non-empty, the graph node
    emits the primary AIMessage followed by each extra message in order."""
    from langchain_core.messages import AIMessage, HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from orchestrator.agents.base import ModuleStepResult
    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.graph import build_graph
    from orchestrator.state import ContextStore

    extra1 = AIMessage(content="step 1 result")
    extra2 = AIMessage(content="step 2 result")

    def fake_step(self, state):
        return ModuleStepResult(
            assistant_message="primary",
            context_patch={"confirmed_at": "2026-05-27"},
            transition=False, needs_user_reply=True,
            extra_messages=[extra1, extra2],
        )
    monkeypatch.setattr(M1Agent, "step", fake_step)

    cs = ContextStore(**{
        m: {"confirmed_at": "2026-05-26"}
        for m in ("m2_literature", "m3_design", "m4_analysis", "m5_writing")
    })
    g = build_graph(interactive=False, checkpointer=MemorySaver())
    final = g.invoke({
        "messages": [HumanMessage(content="start")],
        "current_module": "M1",
        "context_store": cs,
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "test-extra-msgs"}})

    ai_msgs = [m for m in final["messages"] if m.__class__.__name__ == "AIMessage"]
    contents = [m.content for m in ai_msgs]
    # The primary message + both extras must appear in order.
    assert "primary" in contents
    assert "step 1 result" in contents
    assert "step 2 result" in contents
    primary_idx = contents.index("primary")
    s1_idx = contents.index("step 1 result")
    s2_idx = contents.index("step 2 result")
    assert primary_idx < s1_idx < s2_idx
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_graph.py::test_graph_node_emits_extra_messages_from_step_result -v
```

Expected: FAIL — `ModuleStepResult` has no `extra_messages` field; graph node doesn't forward them.

- [ ] **Step 3: Extend `ModuleStepResult` in `orchestrator/agents/base.py`**

Find the `@dataclass class ModuleStepResult` block. Add the new field at the end:

```python
@dataclass
class ModuleStepResult:
    """What a module's step() returns to the graph runner."""
    assistant_message: str
    context_patch: dict
    transition: bool
    needs_user_reply: bool = False
    tool_calls_json: dict | None = None
    # SP5: additional AIMessages the graph node should emit after the primary
    # assistant_message. Used by M4 to stream per-step execution results.
    # Default empty list keeps SP3/SP4 callers untouched.
    extra_messages: list = field(default_factory=list)
```

Add the `field` import at the top of `base.py` if not already there:

```python
from dataclasses import dataclass, field
```

- [ ] **Step 4: Update `_agent_node_factory` in `orchestrator/graph.py`**

Find `_agent_node_factory` (around lines 52-79). The current `_node` returns:

```python
        ai = AIMessage(content=result.assistant_message)
        if result.tool_calls_json:
            ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

        return {
            "messages": [ai],
            "context_store": cs,
        }
```

Change the return to concatenate the extras (when present):

```python
        ai = AIMessage(content=result.assistant_message)
        if result.tool_calls_json:
            ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json

        # SP5: forward extra_messages (M4's per-step execution emissions).
        # The chat router's SSE loop already handles N messages per LangGraph
        # update — see api/app/routers/chat.py gen().
        messages = [ai]
        if result.extra_messages:
            messages.extend(result.extra_messages)

        return {
            "messages": messages,
            "context_store": cs,
        }
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/test_graph.py -v 2>&1 | tail -15
# Also confirm SP3/SP4 tests still pass — extra_messages default is [] so existing callers are unaffected
python -m pytest orchestrator/tests/agents/test_module_agent_render_hint.py orchestrator/tests/test_agents_m1.py -v 2>&1 | tail -10
git add orchestrator/agents/base.py orchestrator/graph.py orchestrator/tests/test_graph.py
git commit -m "feat(orchestrator): ModuleStepResult.extra_messages + graph forwards them"
```

Expected: new graph test + all existing tests PASS.

---

## Phase B — Parsers

### Task 3: Parser package skeleton + consistency check

**Files:**
- Create: `orchestrator/tools/m4_parsers/__init__.py`
- Create: `orchestrator/tests/tools/__init__.py`
- Create: `orchestrator/tests/tools/test_m4_parsers/__init__.py`

- [ ] **Step 1: Create empty test-dir init files**

```bash
mkdir -p /Users/caonguyenvan/project/dothesis/orchestrator/tests/tools/test_m4_parsers
mkdir -p /Users/caonguyenvan/project/dothesis/orchestrator/tools/m4_parsers/golden
touch /Users/caonguyenvan/project/dothesis/orchestrator/tests/tools/__init__.py
touch /Users/caonguyenvan/project/dothesis/orchestrator/tests/tools/test_m4_parsers/__init__.py
```

- [ ] **Step 2: Create `orchestrator/tools/m4_parsers/__init__.py`**

```python
"""SP5: per-format paste-text parsers for M4 outline steps.

Each format module exports `parse_<format>(text, step_name) -> dict | None`.
On regex match: returns a StepResult-shaped dict with `parser="regex"`.
On no match: returns None, triggering LLM fallback in `dispatch_parse`.
"""
from __future__ import annotations


# Lazy imports inside dispatch_parse / format_step_as_markdown so the package
# doesn't crash on import if a parser module has a transient error in dev.


def dispatch_parse(data_type: str, text: str, step_name: str) -> dict | None:
    """Regex-first, LLM-fallback. Returns a StepResult dict or None.

    Returning None means both regex and LLM fallback failed — caller should
    produce a stub StepResult so the outline walk continues without crashing.
    """
    from .spss import parse_spss
    from .smartpls import parse_smartpls
    from .lavaan import parse_lavaan
    from .llm_fallback import extract_step_data

    parsers = {
        "SPSS": parse_spss,
        "SmartPLS": parse_smartpls,
        "CB-SEM": parse_lavaan,
    }
    parser = parsers.get(data_type)
    if parser is not None:
        result = parser(text, step_name)
        if result is not None:
            return result
    # Fallback path
    return extract_step_data.invoke({
        "text": text,
        "step_name": step_name,
        "data_type": data_type,
    })


def format_step_as_markdown(step_result: dict) -> str:
    """Build the markdown body for a per-step AIMessage."""
    name = step_result.get("step_name", "Step")
    rows = step_result.get("table") or []
    interp = step_result.get("interpretation", "")
    md = f"**{name}**\n\n"
    if rows:
        cols = list(rows[0].keys())
        md += "| " + " | ".join(cols) + " |\n"
        md += "| " + " | ".join("---" for _ in cols) + " |\n"
        for r in rows:
            md += "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n"
        md += "\n"
    if interp:
        md += interp
    return md
```

- [ ] **Step 3: Write the failing test**

Create `orchestrator/tests/tools/test_m4_parsers/test_dispatch.py`:

```python
"""Tests for dispatch_parse + format_step_as_markdown in m4_parsers/__init__.py."""
from unittest.mock import MagicMock


def test_format_step_as_markdown_with_table():
    from orchestrator.tools.m4_parsers import format_step_as_markdown
    sr = {
        "step_name": "Reliability",
        "table": [{"construct": "TL", "alpha": 0.84}],
        "interpretation": "Reliable.",
    }
    md = format_step_as_markdown(sr)
    assert "**Reliability**" in md
    assert "| construct | alpha |" in md
    assert "TL" in md
    assert "Reliable." in md


def test_format_step_as_markdown_without_table():
    from orchestrator.tools.m4_parsers import format_step_as_markdown
    sr = {"step_name": "Summary", "interpretation": "Done."}
    md = format_step_as_markdown(sr)
    assert "**Summary**" in md
    assert "Done." in md
    assert "|" not in md  # no table when rows are empty


def test_dispatch_parse_unknown_type_uses_llm_fallback(monkeypatch):
    """For data_type with no regex parser registered, dispatch falls through to LLM."""
    from orchestrator.tools.m4_parsers import dispatch_parse

    fake_llm_tool = MagicMock()
    fake_llm_tool.invoke.return_value = {
        "step_name": "x", "table": [], "interpretation": "via llm",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback.extract_step_data",
        fake_llm_tool,
    )
    result = dispatch_parse("Unknown", "some text", "x")
    assert result["parser"] == "llm_fallback"
```

- [ ] **Step 4: Run — should FAIL (llm_fallback not yet created)**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_dispatch.py -v 2>&1 | tail -10
```

Expected: FAIL with `ImportError` on `llm_fallback` (Task 8 creates it).

- [ ] **Step 5: Create the stub parser files (real impl in Tasks 4-7)**

Create `orchestrator/tools/m4_parsers/spss.py`:
```python
"""SPSS paste-text parser (Task 4 adds real extractors)."""
from __future__ import annotations


def parse_spss(text: str, step_name: str) -> dict | None:
    """Return a StepResult dict for the given SPSS step, or None to fallback."""
    return None  # filled in by Task 4
```

Create `orchestrator/tools/m4_parsers/smartpls.py`:
```python
"""SmartPLS paste-text parser (Task 5 adds real extractors)."""
from __future__ import annotations


def parse_smartpls(text: str, step_name: str) -> dict | None:
    return None  # filled in by Task 5
```

Create `orchestrator/tools/m4_parsers/lavaan.py`:
```python
"""R lavaan paste-text parser (Task 6 adds real extractors)."""
from __future__ import annotations


def parse_lavaan(text: str, step_name: str) -> dict | None:
    return None  # filled in by Task 6
```

Create `orchestrator/tools/m4_parsers/llm_fallback.py`:
```python
"""LLM extraction fallback (Task 8 adds real implementation)."""
from __future__ import annotations

from langchain_core.tools import tool


@tool
def extract_step_data(text: str, step_name: str, data_type: str) -> dict | None:
    """LLM-driven step data extraction. Task 8 replaces this stub."""
    return None  # filled in by Task 8
```

- [ ] **Step 6: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_dispatch.py -v 2>&1 | tail -10
git add orchestrator/tools/m4_parsers/ orchestrator/tests/tools/
git commit -m "feat(orchestrator): m4_parsers package skeleton + dispatch_parse + format_step_as_markdown"
```

Expected: 3 dispatch tests PASS.

---

### Task 4: SPSS parser + golden fixtures

**Files:**
- Modify: `orchestrator/tools/m4_parsers/spss.py`
- Create: `orchestrator/tools/m4_parsers/golden/spss_cronbach.txt`
- Create: `orchestrator/tools/m4_parsers/golden/spss_regression.txt`
- Create: `orchestrator/tests/tools/test_m4_parsers/test_spss.py`

- [ ] **Step 1: Create golden fixtures**

Create `orchestrator/tools/m4_parsers/golden/spss_cronbach.txt`:

```
Reliability Statistics

Cronbach's Alpha    N of Items
.840                5

Construct: Transformational Leadership (TL)

Item-Total Statistics

                  Scale Mean if Item Deleted    Cronbach's Alpha if Item Deleted
TL1               16.32                          .810
TL2               16.45                          .815
TL3               16.21                          .825
TL4               16.50                          .830
TL5               16.30                          .795

----

Reliability Statistics

Cronbach's Alpha    N of Items
.620                4

Construct: Trust

Item-Total Statistics
Trust1              12.15                          .580
Trust2              12.34                          .595
Trust3              12.10                          .530
Trust4              12.22                          .610
```

Create `orchestrator/tools/m4_parsers/golden/spss_regression.txt`:

```
Coefficients

Model        Unstandardized B    Std. Error    Standardized Beta    t        Sig.
(Constant)   1.234               .312                                3.954    .000
TL           .452                .078          .421                  5.795    .000
Trust        .328                .089          .305                  3.685    .000

Model Summary
R       R Square    Adjusted R Square    Std. Error of the Estimate
.712    .507        .502                  .58432

ANOVA
                 Sum of Squares    df      Mean Square    F        Sig.
Regression       102.345            2       51.173          149.93   .000
Residual         99.755             292     .342
Total            202.100            294

Collinearity Statistics
                 Tolerance    VIF
TL               .842         1.188
Trust            .842         1.188
```

- [ ] **Step 2: Write the failing tests**

Create `orchestrator/tests/tools/test_m4_parsers/test_spss.py`:

```python
"""Golden-fixture tests for SPSS paste-text parser."""
from pathlib import Path

import pytest

from orchestrator.tools.m4_parsers.spss import parse_spss


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_spss_cronbach_extracts_constructs_and_alphas():
    text = _load_golden("spss_cronbach.txt")
    result = parse_spss(text, "Reliability (Cronbach's Alpha)")
    assert result is not None
    assert result["step_name"] == "Reliability (Cronbach's Alpha)"
    assert result["parser"] == "regex"
    constructs = {row["construct"]: row for row in result["table"]}
    assert "Transformational Leadership (TL)" in constructs
    assert "Trust" in constructs
    assert constructs["Transformational Leadership (TL)"]["alpha"] == 0.840
    assert constructs["Trust"]["alpha"] == 0.620


def test_spss_cronbach_flags_threshold_breach():
    """Trust α=0.62 is below 0.7 → thresholds_met should be False."""
    text = _load_golden("spss_cronbach.txt")
    result = parse_spss(text, "Reliability (Cronbach's Alpha)")
    assert result["thresholds_met"] is False
    assert "below" in result["interpretation"].lower() or "0.7" in result["interpretation"]


def test_spss_regression_extracts_coefficients():
    text = _load_golden("spss_regression.txt")
    result = parse_spss(text, "Regression Analysis")
    assert result is not None
    assert result["step_name"] == "Regression Analysis"
    # At least two predictors (TL, Trust) + R² found
    table_predictors = {row["predictor"] for row in result["table"] if row.get("predictor") != "(Constant)"}
    assert "TL" in table_predictors
    assert "Trust" in table_predictors


def test_spss_unknown_step_returns_none():
    """Unrecognized step name → None (signals fallback to LLM)."""
    result = parse_spss("any text", "Some unknown step")
    assert result is None


def test_spss_empty_text_returns_none():
    assert parse_spss("", "Reliability (Cronbach's Alpha)") is None
```

- [ ] **Step 3: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_spss.py -v 2>&1 | tail -15
```

Expected: FAIL — `parse_spss` returns None for everything.

- [ ] **Step 4: Implement the SPSS extractors**

Replace `orchestrator/tools/m4_parsers/spss.py`:

```python
"""SPSS paste-text parser — regex extractors for common SPSS output tables.

Each step extractor reads the user's pasted SPSS output and returns a
StepResult-shaped dict. On regex miss, returns None so the dispatcher
falls back to LLM extraction.
"""
from __future__ import annotations

import re


# Cronbach pairs (alpha, N items) and the immediately-preceding "Construct:" label.
_CRONBACH_BLOCK = re.compile(
    r"Cronbach's\s+Alpha\s+N\s+of\s+Items\s+"
    r"(?P<alpha>\.\d+|\d+\.\d+)\s+(?P<n>\d+)\s+"
    r"Construct:\s*(?P<construct>[^\n]+)",
    re.IGNORECASE,
)


def _extract_cronbach(text: str) -> dict | None:
    matches = list(_CRONBACH_BLOCK.finditer(text))
    if not matches:
        return None
    rows = []
    all_meet = True
    for m in matches:
        alpha = float(m.group("alpha"))
        if alpha < 0.7:
            all_meet = False
        rows.append({
            "construct": m.group("construct").strip(),
            "alpha": alpha,
            "n_items": int(m.group("n")),
            "threshold_met": alpha >= 0.7,
        })
    flagged = [r["construct"] for r in rows if not r["threshold_met"]]
    interp = (
        "All scales meet the α ≥ 0.7 threshold (Nunnally, 1978)."
        if all_meet
        else f"⚠️ α below 0.7 for: {', '.join(flagged)}. Consider dropping weak items or reformulating."
    )
    return {
        "step_name": "Reliability (Cronbach's Alpha)",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


# Regression coefficient table — predictor name + standardized Beta + Sig.
_REGRESSION_ROW = re.compile(
    r"^(?P<predictor>\w[\w\s]*?)\s+"
    r"(?P<b>-?\d+\.\d+|\.\d+)\s+"            # Unstandardized B
    r"(?P<se>-?\d+\.\d+|\.\d+)\s+"           # Std. Error
    r"(?P<beta>-?\d+\.\d+|\.\d+)?\s*"        # Standardized Beta (absent for constant)
    r"(?P<t>-?\d+\.\d+)\s+"                  # t
    r"(?P<sig>\.\d+|\d+\.\d+)\s*$",          # Sig.
    re.MULTILINE,
)
_RSQ = re.compile(r"R\s+R\s*Square[^\n]*\n([\d.]+)\s+([\d.]+)\s+([\d.]+)", re.IGNORECASE)
_VIF_ROW = re.compile(r"^(?P<predictor>\w[\w\s]*?)\s+(?P<tol>\.\d+|\d+\.\d+)\s+(?P<vif>\d+\.\d+)\s*$",
                       re.MULTILINE)


def _extract_regression(text: str) -> dict | None:
    coefs = list(_REGRESSION_ROW.finditer(text))
    if not coefs:
        return None
    rows = []
    for m in coefs:
        predictor = m.group("predictor").strip()
        if predictor.lower() in ("model", "(constant)"):
            # Keep the constant but tag it
            rows.append({
                "predictor": "(Constant)",
                "B": float(m.group("b")),
                "beta": None,
                "t": float(m.group("t")),
                "sig": float(m.group("sig")),
                "significant": float(m.group("sig")) < 0.05,
            })
            continue
        rows.append({
            "predictor": predictor,
            "B": float(m.group("b")),
            "beta": float(m.group("beta")) if m.group("beta") else None,
            "t": float(m.group("t")),
            "sig": float(m.group("sig")),
            "significant": float(m.group("sig")) < 0.05,
        })

    # R², adjusted R²
    rsq_match = _RSQ.search(text)
    r2 = float(rsq_match.group(2)) if rsq_match else None

    # VIF table — augment predictor rows with VIF
    vif_map = {m.group("predictor").strip(): float(m.group("vif"))
               for m in _VIF_ROW.finditer(text)}
    for row in rows:
        if row["predictor"] in vif_map:
            row["VIF"] = vif_map[row["predictor"]]

    significant = [r["predictor"] for r in rows
                   if r["predictor"] != "(Constant)" and r["significant"]]
    interp_parts = []
    if significant:
        interp_parts.append(
            f"Significant predictors: {', '.join(significant)} (p < 0.05)."
        )
    if r2 is not None:
        interp_parts.append(f"R² = {r2:.3f}.")
    high_vif = [r["predictor"] for r in rows if r.get("VIF", 0) > 10]
    if high_vif:
        interp_parts.append(f"⚠️ Multicollinearity (VIF > 10) for: {', '.join(high_vif)}.")
    interp = " ".join(interp_parts) or "Regression results extracted."

    return {
        "step_name": "Regression Analysis",
        "table": rows,
        "thresholds_met": not high_vif,
        "interpretation": interp,
        "parser": "regex",
    }


# Dispatch — each step name maps to its extractor function.
_SPSS_EXTRACTORS = {
    "Reliability (Cronbach's Alpha)": _extract_cronbach,
    "Regression Analysis": _extract_regression,
    # EFA, Correlation, ANOVA extractors land in a follow-up; LLM fallback
    # handles them today.
}


def parse_spss(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _SPSS_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_spss.py -v 2>&1 | tail -15
git add orchestrator/tools/m4_parsers/spss.py orchestrator/tools/m4_parsers/golden/spss_*.txt orchestrator/tests/tools/test_m4_parsers/test_spss.py
git commit -m "feat(orchestrator): SPSS paste-text parser (Cronbach + regression) + golden fixtures"
```

Expected: 5 SPSS tests PASS.

---

### Task 5: SmartPLS parser + golden fixtures

**Files:**
- Modify: `orchestrator/tools/m4_parsers/smartpls.py`
- Create: `orchestrator/tools/m4_parsers/golden/smartpls_loadings.txt`
- Create: `orchestrator/tools/m4_parsers/golden/smartpls_paths.txt`
- Create: `orchestrator/tests/tools/test_m4_parsers/test_smartpls.py`

- [ ] **Step 1: Create golden fixtures**

Create `orchestrator/tools/m4_parsers/golden/smartpls_loadings.txt`:

```
Outer Loadings

           TL        EE        Trust
TL1        0.842
TL2        0.795
TL3        0.821
TL4        0.778
EE1                  0.811
EE2                  0.785
EE3                  0.792
Trust1                         0.755
Trust2                         0.713
Trust3                         0.602

Construct Reliability and Validity

           Cronbach's Alpha    Composite Reliability    Average Variance Extracted (AVE)
TL         0.832                0.890                    0.671
EE         0.756                0.860                    0.673
Trust      0.625                0.798                    0.572
```

Create `orchestrator/tools/m4_parsers/golden/smartpls_paths.txt`:

```
Path Coefficients

                    Original Sample (O)    T Statistics (|O/STDEV|)    P Values
TL -> EE            0.452                  6.234                       0.000
TL -> Trust         0.380                  4.987                       0.000
Trust -> EE         0.298                  3.451                       0.001

R Square

           R Square    R Square Adjusted
EE         0.527        0.520
Trust      0.144        0.140

Heterotrait-Monotrait Ratio (HTMT)

           TL        EE        Trust
TL
EE         0.625
Trust      0.582     0.501
```

- [ ] **Step 2: Write the failing tests**

Create `orchestrator/tests/tools/test_m4_parsers/test_smartpls.py`:

```python
"""Golden-fixture tests for SmartPLS paste-text parser."""
from pathlib import Path

from orchestrator.tools.m4_parsers.smartpls import parse_smartpls


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_smartpls_outer_loadings_extracts_per_construct():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Outer Loadings")
    assert result is not None
    assert result["parser"] == "regex"
    # Rows are per-item with their loading on their construct.
    by_item = {row["item"]: row for row in result["table"]}
    assert "TL1" in by_item
    assert by_item["TL1"]["loading"] == 0.842
    assert by_item["Trust3"]["loading"] == 0.602  # below 0.7 threshold
    assert by_item["Trust3"]["threshold_met"] is False


def test_smartpls_outer_loadings_flags_below_threshold():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Outer Loadings")
    assert result["thresholds_met"] is False
    assert "Trust3" in result["interpretation"]


def test_smartpls_ave_cr_extracts_validity():
    text = _load_golden("smartpls_loadings.txt")
    result = parse_smartpls(text, "Convergent Validity: AVE & CR")
    assert result is not None
    by_construct = {row["construct"]: row for row in result["table"]}
    assert "TL" in by_construct
    assert by_construct["TL"]["AVE"] == 0.671
    assert by_construct["TL"]["CR"] == 0.890


def test_smartpls_path_coefficients_extracts():
    text = _load_golden("smartpls_paths.txt")
    result = parse_smartpls(text, "Path Coefficients (Bootstrap 5000)")
    assert result is not None
    by_path = {row["path"]: row for row in result["table"]}
    assert "TL -> EE" in by_path
    assert by_path["TL -> EE"]["beta"] == 0.452
    assert by_path["TL -> EE"]["p"] == 0.000
    assert by_path["TL -> EE"]["significant"] is True


def test_smartpls_htmt_extracts_pairs():
    text = _load_golden("smartpls_paths.txt")
    result = parse_smartpls(text, "Discriminant Validity: HTMT & Fornell-Larcker")
    assert result is not None
    pairs = {(row["construct_a"], row["construct_b"]): row["htmt"] for row in result["table"]}
    assert (("EE", "TL") in pairs) or (("TL", "EE") in pairs)


def test_smartpls_unknown_step_returns_none():
    assert parse_smartpls("text", "Some unknown step") is None
```

- [ ] **Step 3: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_smartpls.py -v 2>&1 | tail -15
```

- [ ] **Step 4: Implement the SmartPLS extractors**

Replace `orchestrator/tools/m4_parsers/smartpls.py`:

```python
"""SmartPLS report paste-text parser."""
from __future__ import annotations

import re


def _extract_outer_loadings(text: str) -> dict | None:
    """Outer Loadings table — item rows with one numeric column per construct."""
    if "Outer Loadings" not in text:
        return None
    # Find the header line with construct names following "Outer Loadings"
    block_match = re.search(
        r"Outer Loadings\s*\n\s*((?:[A-Za-z][\w]*\s*)+)\n((?:.+\n?)+?)(?=\n\s*\n|Construct Reliability|\Z)",
        text,
    )
    if not block_match:
        return None
    header = block_match.group(1).split()
    body = block_match.group(2)
    rows = []
    for line in body.splitlines():
        parts = line.split()
        if not parts:
            continue
        item = parts[0]
        # Find the first numeric column among the remaining parts; the construct
        # is determined by which header position the number falls under.
        # Simpler: find the single numeric value in the row.
        for i, p in enumerate(parts[1:]):
            try:
                loading = float(p)
            except ValueError:
                continue
            construct = header[i] if i < len(header) else "?"
            rows.append({
                "item": item,
                "construct": construct,
                "loading": loading,
                "threshold_met": loading >= 0.7,
            })
            break
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [r["item"] for r in rows if not r["threshold_met"]]
    interp = (
        "All outer loadings ≥ 0.7 (Hair et al., 2019)."
        if all_meet
        else f"⚠️ Items below 0.7: {', '.join(failed)}. Consider dropping these from the construct."
    )
    return {
        "step_name": "Outer Loadings",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_AVE_ROW = re.compile(
    r"^(?P<construct>\w[\w]*?)\s+(?P<alpha>\d+\.\d+)\s+(?P<cr>\d+\.\d+)\s+(?P<ave>\d+\.\d+)\s*$",
    re.MULTILINE,
)


def _extract_ave_cr(text: str) -> dict | None:
    matches = list(_AVE_ROW.finditer(text))
    if not matches:
        return None
    rows = []
    all_meet = True
    for m in matches:
        ave = float(m.group("ave"))
        cr = float(m.group("cr"))
        alpha = float(m.group("alpha"))
        meets = ave >= 0.5 and cr >= 0.7 and alpha >= 0.7
        if not meets:
            all_meet = False
        rows.append({
            "construct": m.group("construct"),
            "alpha": alpha, "CR": cr, "AVE": ave,
            "threshold_met": meets,
        })
    failed = [r["construct"] for r in rows if not r["threshold_met"]]
    interp = (
        "Convergent validity established (AVE ≥ 0.5, CR ≥ 0.7, α ≥ 0.7)."
        if all_meet
        else f"⚠️ Convergent validity issues for: {', '.join(failed)}."
    )
    return {
        "step_name": "Convergent Validity: AVE & CR",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_PATH_ROW = re.compile(
    r"^(?P<src>\w[\w]*?)\s+->\s+(?P<dst>\w[\w]*?)\s+"
    r"(?P<beta>-?\d+\.\d+)\s+(?P<t>\d+\.\d+)\s+(?P<p>\d+\.\d+)\s*$",
    re.MULTILINE,
)


def _extract_path_coefficients(text: str) -> dict | None:
    matches = list(_PATH_ROW.finditer(text))
    if not matches:
        return None
    rows = []
    for m in matches:
        p = float(m.group("p"))
        rows.append({
            "path": f"{m.group('src')} -> {m.group('dst')}",
            "beta": float(m.group("beta")),
            "t": float(m.group("t")),
            "p": p,
            "significant": p < 0.05,
        })
    significant = [r["path"] for r in rows if r["significant"]]
    all_significant = all(r["significant"] for r in rows)
    interp = (
        f"All {len(rows)} hypothesized paths are significant (p < 0.05)."
        if all_significant
        else f"Significant paths: {', '.join(significant) if significant else 'none'}."
    )
    return {
        "step_name": "Path Coefficients (Bootstrap 5000)",
        "table": rows,
        "thresholds_met": all_significant,
        "interpretation": interp,
        "parser": "regex",
    }


def _extract_htmt(text: str) -> dict | None:
    """HTMT matrix — extract pairwise ratios; flag any > 0.85."""
    block = re.search(
        r"Heterotrait-Monotrait Ratio \(HTMT\)\s*\n((?:.+\n?)+?)(?=\n\s*\n|\Z)",
        text,
    )
    if not block:
        return None
    body = block.group(1)
    lines = [l for l in body.splitlines() if l.strip()]
    if not lines:
        return None
    # First non-empty line is the header row with construct names.
    header = lines[0].split()
    rows = []
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        construct_a = parts[0]
        for i, p in enumerate(parts[1:]):
            try:
                htmt = float(p)
            except ValueError:
                continue
            construct_b = header[i] if i < len(header) else "?"
            if construct_a != construct_b:
                rows.append({
                    "construct_a": construct_a,
                    "construct_b": construct_b,
                    "htmt": htmt,
                    "threshold_met": htmt < 0.85,
                })
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [f"{r['construct_a']}-{r['construct_b']}" for r in rows if not r["threshold_met"]]
    interp = (
        "Discriminant validity established (HTMT < 0.85; Henseler et al., 2015)."
        if all_meet
        else f"⚠️ HTMT ≥ 0.85 for: {', '.join(failed)}. Constructs may overlap."
    )
    return {
        "step_name": "Discriminant Validity: HTMT & Fornell-Larcker",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_SMARTPLS_EXTRACTORS = {
    "Outer Loadings": _extract_outer_loadings,
    "Convergent Validity: AVE & CR": _extract_ave_cr,
    "Path Coefficients (Bootstrap 5000)": _extract_path_coefficients,
    "Discriminant Validity: HTMT & Fornell-Larcker": _extract_htmt,
    # VIF, R², f², Q², mediation extractors land in a follow-up; LLM fallback
    # handles them today.
}


def parse_smartpls(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _SMARTPLS_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_smartpls.py -v 2>&1 | tail -15
git add orchestrator/tools/m4_parsers/smartpls.py orchestrator/tools/m4_parsers/golden/smartpls_*.txt orchestrator/tests/tools/test_m4_parsers/test_smartpls.py
git commit -m "feat(orchestrator): SmartPLS paste-text parser (loadings, AVE/CR, paths, HTMT) + golden fixtures"
```

Expected: 6 SmartPLS tests PASS.

---

### Task 6: R lavaan parser + golden fixture

**Files:**
- Modify: `orchestrator/tools/m4_parsers/lavaan.py`
- Create: `orchestrator/tools/m4_parsers/golden/lavaan_cfa.txt`
- Create: `orchestrator/tests/tools/test_m4_parsers/test_lavaan.py`

- [ ] **Step 1: Create the golden fixture**

Create `orchestrator/tools/m4_parsers/golden/lavaan_cfa.txt`:

```
lavaan 0.6-15 ended normally after 38 iterations

  Estimator                                         ML
  Optimization method                           NLMINB
  Number of model parameters                        21

  Number of observations                           300

Model Test User Model:
                                                  Standard
  Test Statistic                                   245.872
  Degrees of freedom                                  124
  P-value (Chi-square)                              0.000

Model Test Baseline Model:
  Test statistic                                  1832.451
  Degrees of freedom                                  153
  P-value                                            0.000

User Model versus Baseline Model:
  Comparative Fit Index (CFI)                       0.945
  Tucker-Lewis Index (TLI)                          0.932
  Root Mean Square Error of Approximation:
  RMSEA                                             0.057
  90 Percent confidence interval - lower            0.048
  90 Percent confidence interval - upper            0.066

  Standardized Root Mean Square Residual:
  SRMR                                              0.054

Latent Variables:
                   Estimate   Std.Err   z-value   P(>|z|)
  TL =~
    TL1               1.000
    TL2               0.985     0.062    15.872     0.000
    TL3               1.012     0.064    15.812     0.000
    TL4               0.951     0.065    14.628     0.000

  EE =~
    EE1               1.000
    EE2               0.962     0.058    16.586     0.000
    EE3               0.978     0.061    16.030     0.000
```

- [ ] **Step 2: Write the failing tests**

Create `orchestrator/tests/tools/test_m4_parsers/test_lavaan.py`:

```python
"""Golden-fixture tests for R lavaan paste-text parser."""
from pathlib import Path

from orchestrator.tools.m4_parsers.lavaan import parse_lavaan


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_lavaan_cfa_extracts_fit_indices():
    text = _load_golden("lavaan_cfa.txt")
    result = parse_lavaan(text, "Confirmatory Factor Analysis (CFI/TLI/RMSEA)")
    assert result is not None
    assert result["parser"] == "regex"
    indices = {row["index"]: row["value"] for row in result["table"]}
    assert indices["CFI"] == 0.945
    assert indices["TLI"] == 0.932
    assert indices["RMSEA"] == 0.057
    assert indices["SRMR"] == 0.054


def test_lavaan_cfa_threshold_check():
    """CFI ≥ 0.90, TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08 — all met in fixture."""
    text = _load_golden("lavaan_cfa.txt")
    result = parse_lavaan(text, "Confirmatory Factor Analysis (CFI/TLI/RMSEA)")
    assert result["thresholds_met"] is True


def test_lavaan_unknown_step_returns_none():
    assert parse_lavaan("text", "Some unknown step") is None
```

- [ ] **Step 3: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_lavaan.py -v 2>&1 | tail -15
```

- [ ] **Step 4: Implement the lavaan extractor**

Replace `orchestrator/tools/m4_parsers/lavaan.py`:

```python
"""R lavaan paste-text parser — CFA + structural model fit indices."""
from __future__ import annotations

import re


_FIT_INDEX_PATTERNS = {
    "CFI":   r"Comparative Fit Index \(CFI\)\s+(\d+\.\d+)",
    "TLI":   r"Tucker-Lewis Index \(TLI\)\s+(\d+\.\d+)",
    "RMSEA": r"RMSEA\s+(\d+\.\d+)",
    "SRMR":  r"SRMR\s+(\d+\.\d+)",
}


def _extract_cfa(text: str) -> dict | None:
    rows = []
    for index_name, pattern in _FIT_INDEX_PATTERNS.items():
        m = re.search(pattern, text)
        if not m:
            continue
        value = float(m.group(1))
        # Standard thresholds: CFI/TLI ≥ 0.90; RMSEA ≤ 0.08; SRMR ≤ 0.08
        if index_name in ("CFI", "TLI"):
            met = value >= 0.90
        else:
            met = value <= 0.08
        rows.append({
            "index": index_name,
            "value": value,
            "threshold_met": met,
        })
    if not rows:
        return None
    all_meet = all(r["threshold_met"] for r in rows)
    failed = [r["index"] for r in rows if not r["threshold_met"]]
    interp = (
        "Model fit meets Hu & Bentler (1999) standards (CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08)."
        if all_meet
        else f"⚠️ Fit indices below threshold: {', '.join(failed)}. Consider model respecification."
    )
    return {
        "step_name": "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
        "table": rows,
        "thresholds_met": all_meet,
        "interpretation": interp,
        "parser": "regex",
    }


_LAVAAN_EXTRACTORS = {
    "Confirmatory Factor Analysis (CFI/TLI/RMSEA)": _extract_cfa,
    # Structural Model, Mediation, etc. — extend in follow-ups.
}


def parse_lavaan(text: str, step_name: str) -> dict | None:
    if not text:
        return None
    extractor = _LAVAAN_EXTRACTORS.get(step_name)
    if extractor is None:
        return None
    return extractor(text)
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_lavaan.py -v 2>&1 | tail -10
git add orchestrator/tools/m4_parsers/lavaan.py orchestrator/tools/m4_parsers/golden/lavaan_cfa.txt orchestrator/tests/tools/test_m4_parsers/test_lavaan.py
git commit -m "feat(orchestrator): R lavaan paste-text parser (CFA fit indices) + golden fixture"
```

Expected: 3 lavaan tests PASS.

---

### Task 7: Transcript helpers + qual coding tools

**Files:**
- Modify: `orchestrator/tools/m4_parsers/transcript.py`
- Create: `orchestrator/tools/m4_parsers/golden/transcript_short.txt`
- Create: `orchestrator/tests/tools/test_m4_parsers/test_transcript.py`

- [ ] **Step 1: Create the golden fixture**

Create `orchestrator/tools/m4_parsers/golden/transcript_short.txt`:

```
INTERVIEWER: Tell me about your manager's leadership style.

PARTICIPANT: She really inspires us. Every Monday morning she paints a picture of where we're going as a team, and somehow it makes Tuesday feel less like a slog. I trust her judgment because she explains the why behind each decision.

INTERVIEWER: Can you give an example of feeling engaged at work?

PARTICIPANT: Last month we shipped a product launch. I felt completely absorbed. I forgot to eat lunch. That kind of engagement only happens when you trust the people around you and feel safe enough to take risks.

INTERVIEWER: How does trust play into your work?

PARTICIPANT: Without psychological safety I'd hold back ideas. With my current manager I can say "this won't work" and we'd discuss it openly. That changes everything about how I show up.
```

- [ ] **Step 2: Write the failing tests**

Create `orchestrator/tests/tools/test_m4_parsers/test_transcript.py`:

```python
"""Tests for transcript helpers + qual coding tools."""
import json
from pathlib import Path
from unittest.mock import MagicMock

from orchestrator.tools.m4_parsers.transcript import (
    cluster_codes_into_themes,
    split_transcript_into_segments,
    suggest_qual_codes,
)


_GOLDEN = Path(__file__).resolve().parent.parent.parent.parent / "tools" / "m4_parsers" / "golden"


def _load_golden(name: str) -> str:
    return (_GOLDEN / name).read_text()


def test_split_transcript_extracts_speaker_turns():
    """Split into segments by INTERVIEWER:/PARTICIPANT: prefix."""
    text = _load_golden("transcript_short.txt")
    segments = split_transcript_into_segments(text)
    assert len(segments) >= 6  # 3 interviewer + 3 participant turns
    speakers = {s["speaker"] for s in segments}
    assert "INTERVIEWER" in speakers
    assert "PARTICIPANT" in speakers


def test_suggest_qual_codes_returns_code_plus_quote(monkeypatch):
    """suggest_qual_codes returns [{code, quote, line_no?}, ...] from the transcript."""
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"code": "leadership vision",
         "quote": "Every Monday morning she paints a picture of where we're going as a team"},
        {"code": "engagement-absorption",
         "quote": "I felt completely absorbed. I forgot to eat lunch."},
        {"code": "psychological safety",
         "quote": "I can say 'this won't work' and we'd discuss it openly."},
    ])
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    text = _load_golden("transcript_short.txt")
    codes = suggest_qual_codes.invoke({"transcript": text})
    assert isinstance(codes, list)
    assert len(codes) == 3
    assert codes[0]["code"] == "leadership vision"
    assert "Monday" in codes[0]["quote"]


def test_suggest_qual_codes_returns_empty_on_malformed(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    codes = suggest_qual_codes.invoke({"transcript": "anything"})
    assert codes == []


def test_cluster_codes_into_themes(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps([
        {"theme": "Leadership behavior",
         "codes": ["leadership vision"]},
        {"theme": "Employee engagement and safety",
         "codes": ["engagement-absorption", "psychological safety"]},
    ])
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    codes = [
        {"code": "leadership vision", "quote": "..."},
        {"code": "engagement-absorption", "quote": "..."},
        {"code": "psychological safety", "quote": "..."},
    ]
    themes = cluster_codes_into_themes.invoke({"codes": codes})
    assert isinstance(themes, list)
    assert len(themes) == 2
    assert themes[0]["theme"] == "Leadership behavior"


def test_cluster_codes_falls_back_on_malformed(monkeypatch):
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "{ broken"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.transcript._get_llm",
        lambda: fake_llm,
    )
    themes = cluster_codes_into_themes.invoke({"codes": []})
    assert themes == []
```

- [ ] **Step 3: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_transcript.py -v 2>&1 | tail -15
```

- [ ] **Step 4: Implement the transcript module**

Replace `orchestrator/tools/m4_parsers/transcript.py`:

```python
"""Qualitative transcript helpers + AI-driven coding/theming tools."""
from __future__ import annotations

import json
import logging
import os
import re

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    # Centralised LLM factory — monkeypatchable in tests.
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.2,
    )


_SPEAKER_PATTERN = re.compile(r"^\s*([A-Z][A-Z _-]+):\s*", re.MULTILINE)


def split_transcript_into_segments(transcript: str) -> list[dict]:
    """Split a transcript into speaker turns. Returns [{speaker, text}, ...].

    Speakers are detected by ALL-CAPS prefix + colon at start of line
    (e.g. INTERVIEWER:, PARTICIPANT:, P1:).
    """
    matches = list(_SPEAKER_PATTERN.finditer(transcript))
    if not matches:
        return [{"speaker": "?", "text": transcript.strip()}]
    segments = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(transcript)
        text = transcript[start:end].strip()
        if text:
            segments.append({"speaker": m.group(1).strip(), "text": text})
    return segments


@tool
def suggest_qual_codes(transcript: str) -> list[dict]:
    """Extract initial codes from a qualitative interview transcript.

    Returns: [{code: str, quote: str}, ...]
    Each code is a short label; quote is the verbatim text the code applies to.
    Falls back to [] on malformed LLM response.
    """
    llm = _get_llm()
    prompt = (
        "Extract initial codes from this interview transcript (Braun & Clarke style "
        "line-by-line coding). For each code, give the verbatim quote it applies to. "
        "Aim for 5-12 codes total. Respond with ONLY a JSON array: "
        '[{"code":"<short label>","quote":"<verbatim>"}, ...].\n\n'
        f"Transcript:\n{transcript[:30000]}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("suggest_qual_codes: malformed LLM response, returning empty list")
        return []


@tool
def cluster_codes_into_themes(codes: list[dict]) -> list[dict]:
    """Cluster initial codes into themes.

    Input: [{code, quote}, ...]
    Returns: [{theme: str, codes: [str]}, ...]
    Falls back to [] on malformed.
    """
    llm = _get_llm()
    prompt = (
        "Cluster these initial codes into 3-5 themes for a thematic analysis "
        "(Braun & Clarke 2006). Each theme groups related codes. Respond with "
        'ONLY a JSON array: [{"theme":"<name>","codes":["<code>", "<code>"]}, ...].\n\n'
        f"Codes: {json.dumps(codes, ensure_ascii=False)}"
    )
    try:
        return list(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning("cluster_codes_into_themes: malformed LLM response, returning empty list")
        return []
```

- [ ] **Step 5: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_transcript.py -v 2>&1 | tail -15
git add orchestrator/tools/m4_parsers/transcript.py orchestrator/tools/m4_parsers/golden/transcript_short.txt orchestrator/tests/tools/test_m4_parsers/test_transcript.py
git commit -m "feat(orchestrator): transcript split + suggest_qual_codes + cluster_codes_into_themes"
```

Expected: 5 transcript tests PASS.

---

### Task 8: LLM fallback `extract_step_data`

**Files:**
- Modify: `orchestrator/tools/m4_parsers/llm_fallback.py`
- Create: `orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py`:

```python
"""Tests for the LLM extraction fallback path."""
import json
from unittest.mock import MagicMock


def test_extract_step_data_returns_structured(monkeypatch):
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "step_name": "EFA",
        "table": [
            {"factor": "F1", "items": 4, "eigenvalue": 3.421},
        ],
        "thresholds_met": True,
        "interpretation": "KMO = 0.812; 4 factors extracted.",
        "parser": "llm_fallback",
    })
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )

    result = extract_step_data.invoke({
        "text": "any SPSS output here",
        "step_name": "EFA",
        "data_type": "SPSS",
    })
    assert result is not None
    assert result["step_name"] == "EFA"
    assert result["table"][0]["factor"] == "F1"
    assert result["parser"] == "llm_fallback"


def test_extract_step_data_returns_none_on_malformed(monkeypatch):
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "not valid json"
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )

    result = extract_step_data.invoke({
        "text": "x", "step_name": "y", "data_type": "SPSS",
    })
    assert result is None


def test_extract_step_data_forces_llm_fallback_parser_tag(monkeypatch):
    """Even if the LLM returns parser='regex', we override it to llm_fallback."""
    from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data

    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = json.dumps({
        "step_name": "x", "table": [], "interpretation": "",
        "parser": "regex",  # WRONG — the function must overwrite this
    })
    monkeypatch.setattr(
        "orchestrator.tools.m4_parsers.llm_fallback._get_llm",
        lambda: fake_llm,
    )
    result = extract_step_data.invoke({
        "text": "x", "step_name": "x", "data_type": "SPSS",
    })
    assert result["parser"] == "llm_fallback"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Implement the LLM fallback**

Replace `orchestrator/tools/m4_parsers/llm_fallback.py`:

```python
"""LLM extraction fallback for paste-text steps that regex can't parse.

Used by `dispatch_parse` when a format's regex parser returns None
(no match). The LLM is prompted to extract the same StepResult-shaped
dict the regex parsers produce. The `parser` field is always set to
`"llm_fallback"` so M5 and audit logs can tell the source apart.
"""
from __future__ import annotations

import json
import logging
import os

from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


def _get_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.1,
    )


@tool
def extract_step_data(text: str, step_name: str, data_type: str) -> dict | None:
    """LLM extraction of a single outline step.

    Returns a StepResult dict with parser="llm_fallback", or None on
    malformed LLM response.

    The prompt instructs the LLM to return ONLY numbers present in the
    source text and to use null for any cell it cannot verify, to limit
    hallucinated values.
    """
    llm = _get_llm()
    prompt = (
        f"Extract the data for the '{step_name}' analysis step from this "
        f"{data_type} output. Return ONLY a JSON object with this shape: "
        '{"step_name":"<step>","table":[{...}],"thresholds_met":<bool|null>,'
        '"interpretation":"<plain-language paragraph>"}. '
        "Critical: only include numbers that appear in the source text. For "
        "any cell you cannot verify, use null. Do NOT fabricate values.\n\n"
        f"Source text:\n{text[:20000]}"
    )
    try:
        result = dict(json.loads(llm.invoke(prompt).content))
    except (json.JSONDecodeError, TypeError):
        logger.warning(
            "extract_step_data: malformed LLM response for step=%s, returning None",
            step_name,
        )
        return None
    # Force the parser tag — never trust what the LLM returned.
    result["parser"] = "llm_fallback"
    result.setdefault("step_name", step_name)
    return result
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py -v 2>&1 | tail -10
# Also re-run the dispatch test from Task 3 — it should now PASS in full
python -m pytest orchestrator/tests/tools/test_m4_parsers/test_dispatch.py -v 2>&1 | tail -10
git add orchestrator/tools/m4_parsers/llm_fallback.py orchestrator/tests/tools/test_m4_parsers/test_llm_fallback.py
git commit -m "feat(orchestrator): extract_step_data LLM fallback tool"
```

Expected: 3 llm_fallback tests PASS + the 3 dispatch tests from Task 3 still PASS.

---

## Phase C — Tools

### Task 9: Real `run_analysis_step` + `run_extra_analysis`

**Files:**
- Modify: `orchestrator/tools/m4_analysis.py`
- Modify: `orchestrator/tests/test_tools_m4.py`

- [ ] **Step 1: Append the failing tests**

Append to `orchestrator/tests/test_tools_m4.py`:

```python
def test_run_analysis_step_dispatches_to_spss_parser(monkeypatch):
    """run_analysis_step calls dispatch_parse with the data_type from `data`."""
    from orchestrator.tools.m4_analysis import run_analysis_step

    # Fake the dispatcher to confirm it's invoked with the right args.
    captured = {}
    def fake_dispatch(data_type, text, step_name):
        captured["data_type"] = data_type
        captured["step_name"] = step_name
        return {"step_name": step_name, "table": [], "interpretation": "ok",
                "parser": "regex"}
    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.dispatch_parse", fake_dispatch
    )
    result = run_analysis_step.invoke({
        "step_name": "Regression Analysis",
        "data": {"paste": "raw spss text", "data_type": "SPSS"},
    })
    assert captured["data_type"] == "SPSS"
    assert captured["step_name"] == "Regression Analysis"
    assert result["parser"] == "regex"


def test_run_analysis_step_returns_stub_on_dispatch_none(monkeypatch):
    """When dispatch returns None, run_analysis_step returns a stub StepResult."""
    from orchestrator.tools.m4_analysis import run_analysis_step

    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.dispatch_parse",
        lambda dt, t, s: None,
    )
    result = run_analysis_step.invoke({
        "step_name": "Unparseable Step",
        "data": {"paste": "garbage", "data_type": "SPSS"},
    })
    assert result["parser"] == "stub"
    assert "unable" in result["interpretation"].lower()


def test_run_extra_analysis_returns_step_result(monkeypatch):
    """run_extra_analysis routes to extract_step_data + tags as custom."""
    from orchestrator.tools.m4_analysis import run_extra_analysis

    fake_extract = MagicMock()
    fake_extract.invoke.return_value = {
        "step_name": "mediation H3", "table": [], "interpretation": "Mediation tested.",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(
        "orchestrator.tools.m4_analysis.extract_step_data", fake_extract
    )
    result = run_extra_analysis.invoke({
        "step_description": "mediation test on H3",
        "data_paste": "some output",
    })
    assert result["step_name"]
    assert result["interpretation"] == "Mediation tested."
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/test_tools_m4.py -v 2>&1 | tail -15
```

Expected: existing tests still pass; 3 new tests fail (current `run_analysis_step` is a stub, `run_extra_analysis` doesn't exist).

- [ ] **Step 3: Update `orchestrator/tools/m4_analysis.py`**

Replace the existing `run_analysis_step` body and add `run_extra_analysis`. Existing imports + `_get_llm` + `detect_data_type` + `_OUTLINE_TEMPLATES` + `generate_analysis_outline` + `interpret_result` STAY. Replace just `run_analysis_step` and append `run_extra_analysis`:

```python
# At the top — add imports for the new dispatchers
from orchestrator.tools.m4_parsers import dispatch_parse
from orchestrator.tools.m4_parsers.llm_fallback import extract_step_data


@tool
def run_analysis_step(step_name: str, data: dict) -> dict:
    """SP5: parse one outline step from the user's pasted analysis output.

    Hybrid extraction: regex-first via dispatch_parse, LLM fallback on miss,
    stub StepResult on both miss. The returned dict's `parser` field records
    the source path so M5 and audit logs can distinguish regex from LLM
    extraction.
    """
    text = data.get("paste", "")
    data_type = data.get("data_type", "Unknown")
    result = dispatch_parse(data_type, text, step_name)
    if result is not None:
        return result
    # Both regex and LLM fallback failed — return a stub so the walk continues.
    return {
        "step_name": step_name,
        "table": [],
        "thresholds_met": None,
        "interpretation": (
            "(unable to parse this step from the paste; please paste this step's "
            "output separately or describe the result)"
        ),
        "raw_paste_excerpt": text[:200],
        "parser": "stub",
    }


@tool
def run_extra_analysis(step_description: str, data_paste: str) -> dict:
    """SP5: ad-hoc analysis requested via natural language (PRD §6.4.6).

    Routes to the LLM extractor with the user's free-text step description.
    The caller (M4Agent) appends the result to M4Output.custom_analyses.
    """
    result = extract_step_data.invoke({
        "text": data_paste,
        "step_name": step_description,
        "data_type": "AdHoc",
    })
    if result is None:
        return {
            "step_name": step_description,
            "table": [],
            "interpretation": "(unable to perform this ad-hoc analysis from the paste)",
            "parser": "stub",
        }
    return result
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_tools_m4.py -v 2>&1 | tail -15
git add orchestrator/tools/m4_analysis.py orchestrator/tests/test_tools_m4.py
git commit -m "feat(orchestrator): real run_analysis_step (dispatch_parse) + run_extra_analysis tool"
```

Expected: existing M4-tool tests + 3 new tests PASS.

---

## Phase D — Agent

### Task 10: M4Agent `_FIELDS_BY_OUTLINE_TYPE` + walk override

**Files:**
- Modify: `orchestrator/agents/m4_analysis.py`
- Create: `orchestrator/tests/agents/test_m4_outline.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m4_outline.py`:

```python
"""Tests for M4Agent outline-type-aware field walk."""
from orchestrator.agents.m4_analysis import M4Agent


def test_outline_template_key_from_tool_smartpls():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("SmartPLS") == "SmartPLS"
    assert agent._outline_template_key_from_tool("smartpls") == "SmartPLS"


def test_outline_template_key_from_tool_spss():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("SPSS") == "SPSS"
    assert agent._outline_template_key_from_tool("Stata") == "SPSS"


def test_outline_template_key_from_tool_cbsem():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("AMOS") == "CB-SEM"
    assert agent._outline_template_key_from_tool("R lavaan") == "CB-SEM"


def test_outline_template_key_from_tool_qual():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool("NVivo") == "Qualitative"
    assert agent._outline_template_key_from_tool("Atlas.ti") == "Qualitative"
    assert agent._outline_template_key_from_tool("Manual") == "Qualitative"


def test_outline_template_key_from_tool_unknown():
    agent = M4Agent()
    assert agent._outline_template_key_from_tool(None) == "Unknown"
    assert agent._outline_template_key_from_tool("Mystery Tool") == "Unknown"


def test_walk_order_spss():
    """SPSS walk: data_paste → analysis_outline → _run_execution → _summary."""
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    # All fields empty → first missing = "data_paste"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste"
    partial["data_paste"] = "spss output here"
    assert agent._next_missing_field(partial) == "analysis_outline"
    partial["analysis_outline"] = {"sections": [{"name": "Reliability"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_execution"
    partial["_run_execution_done"] = True
    assert agent._next_missing_field(partial) == "_summary"


def test_walk_order_qualitative():
    agent = M4Agent()
    M4Agent._render_outline_type = "Qualitative"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste"
    partial["data_paste"] = "transcript here"
    assert agent._next_missing_field(partial) == "analysis_outline"
    partial["analysis_outline"] = {"sections": [{"name": "Initial coding"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_qual_pipeline"


def test_walk_order_mixed():
    agent = M4Agent()
    M4Agent._render_outline_type = "Mixed"
    partial = {}
    assert agent._next_missing_field(partial) == "data_paste_quant"
    partial["data_paste_quant"] = "x"
    assert agent._next_missing_field(partial) == "outline_quant"
    partial["outline_quant"] = {"sections": [{"name": "x"}], "confirmed_by_user": True}
    assert agent._next_missing_field(partial) == "_run_execution"
    partial["_run_execution_done"] = True
    assert agent._next_missing_field(partial) == "data_paste_qual"
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m4_outline.py -v 2>&1 | tail -15
```

Expected: FAIL — `_outline_template_key_from_tool` doesn't exist; current `_next_missing_field` is base-class behavior.

- [ ] **Step 3: Replace `orchestrator/agents/m4_analysis.py`**

```python
"""M4 — Data Analysis agent (SP5 adaptive analysis with paste-text parsers)."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m4 import M4Output
from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline, interpret_result,
    run_analysis_step, run_extra_analysis,
)
from orchestrator.tools.m4_parsers.transcript import (
    cluster_codes_into_themes, suggest_qual_codes,
)


_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m4.md").read_text()


# SP5: outline-type-aware field walk. Keys resolved from m3_design.tool via
# _outline_template_key_from_tool. Pseudo-fields _run_execution and
# _run_qual_pipeline trigger an execution phase inside step().
_FIELDS_BY_OUTLINE_TYPE = {
    "SPSS":        ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "SmartPLS":    ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "CB-SEM":      ["data_paste", "analysis_outline", "_run_execution", "_summary"],
    "Qualitative": ["data_paste", "analysis_outline", "_run_qual_pipeline", "_summary"],
    "Mixed":       ["data_paste_quant", "outline_quant", "_run_execution",
                    "data_paste_qual",  "outline_qual",  "_run_qual_pipeline", "_summary"],
    # Unknown defaults to SPSS-like flow so the agent still functions.
    "Unknown":     ["data_paste", "analysis_outline", "_run_execution", "_summary"],
}

_PSEUDO_FIELDS = {"_run_execution", "_run_qual_pipeline", "_summary"}


class M4Agent(ModuleAgent):
    schema = M4Output
    module_key = "M4"
    system_prompt = _PROMPT
    tools = [
        detect_data_type, generate_analysis_outline, run_analysis_step,
        interpret_result, run_extra_analysis,
        suggest_qual_codes, cluster_codes_into_themes,
    ]

    # SP5 class-level caches (populated by step())
    _render_outline_type: str | None = None
    _render_paste_text: str = ""
    _render_outline: dict | None = None
    _render_paradigm: str | None = None

    def _outline_template_key_from_tool(self, tool: str | None) -> str:
        """Map an M3-recorded analysis tool name to an outline template key."""
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
        """Pick the _FIELDS_BY_OUTLINE_TYPE key for the current state.

        Mixed paradigm always returns "Mixed". Otherwise prefer the cached
        _render_outline_type (set by step() from m3.tool or partial.data_type_detected).
        """
        if self._render_paradigm == "mixed":
            return "Mixed"
        return self._render_outline_type

    def _next_missing_field(self, partial: dict) -> str | None:
        """Outline-type-aware override. Walk the ordered list for the resolved key.

        Pseudo-fields (_run_execution, _run_qual_pipeline, _summary) advance when
        their `<name>_done` marker key is set in the partial."""
        key = self._resolved_outline_key(partial)
        if key is None or key not in _FIELDS_BY_OUTLINE_TYPE:
            return super()._next_missing_field(partial)
        for name in _FIELDS_BY_OUTLINE_TYPE[key]:
            if name in _PSEUDO_FIELDS:
                if not partial.get(f"{name}_done"):
                    return name
                continue
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m4_outline.py -v 2>&1 | tail -15
# Update the existing M4 auto-mode test (test_agents_m4.py) — schema now uses StepResult
# in `results` and validator enforces qual_codes/qual_themes for Qualitative.
# The fake_llm content in that test should be updated to include compatible data.
git add orchestrator/agents/m4_analysis.py orchestrator/tests/agents/test_m4_outline.py
git commit -m "feat(orchestrator): M4Agent _FIELDS_BY_OUTLINE_TYPE + paradigm-aware walk"
```

Expected: 8 new outline tests PASS.

- [ ] **Step 5: Update existing M4 auto-mode test**

The existing `orchestrator/tests/test_agents_m4.py::test_m4_auto_produces_outline_and_results` may fail because the new schema requires the @model_validator to pass. Verify it still passes; if it fails, update the fake LLM payload to include `results` keyed by step name with a StepResult-shaped value:

```bash
python -m pytest orchestrator/tests/test_agents_m4.py -v 2>&1 | tail -15
```

If the test fails because of the validator, edit `test_agents_m4.py` to ensure the auto-mode LLM payload includes a step result that survives the @model_validator. Then commit any test edits:

```bash
git add orchestrator/tests/test_agents_m4.py
git commit -m "test(orchestrator): update M4 auto-mode test for SP5 schema shape"
```

(If the test passes unchanged, skip this step.)

---

### Task 11: M4Agent `step()` cache population + `render_hint_for_field`

**Files:**
- Modify: `orchestrator/agents/m4_analysis.py`
- Create: `orchestrator/tests/agents/test_m4_widgets.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m4_widgets.py`:

```python
"""Tests for M4Agent render_hint_for_field — emits ListEditorHint for outline fields."""
from orchestrator.agents.m4_analysis import M4Agent


def test_analysis_outline_returns_list_editor_for_spss():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    hint = agent.render_hint_for_field("analysis_outline")
    assert hint is not None
    assert hint["widget_type"] == "list_editor"
    assert hint["field_name"] == "analysis_outline"
    assert hint["allow_nested"] is False
    # SPSS template has at least the 6 standard steps
    step_names = [i["text"] for i in hint["initial_items"]]
    assert "Descriptive Statistics" in step_names
    assert "Reliability (Cronbach's Alpha)" in step_names


def test_analysis_outline_returns_list_editor_for_smartpls():
    agent = M4Agent()
    M4Agent._render_outline_type = "SmartPLS"
    hint = agent.render_hint_for_field("analysis_outline")
    step_names = [i["text"] for i in hint["initial_items"]]
    assert "Outer Loadings" in step_names
    assert "Path Coefficients (Bootstrap 5000)" in step_names


def test_analysis_outline_returns_list_editor_for_qualitative():
    agent = M4Agent()
    M4Agent._render_outline_type = "Qualitative"
    hint = agent.render_hint_for_field("analysis_outline")
    step_names = [i["text"] for i in hint["initial_items"]]
    # Qual gets the 2-step pipeline per Q5=C
    assert any("coding" in s.lower() or "code" in s.lower() for s in step_names)
    assert any("theme" in s.lower() for s in step_names)


def test_outline_quant_and_outline_qual_emit_list_editor_for_mixed():
    agent = M4Agent()
    M4Agent._render_outline_type = "Mixed"
    M4Agent._render_paradigm = "mixed"
    h1 = agent.render_hint_for_field("outline_quant")
    assert h1 is not None and h1["widget_type"] == "list_editor"
    h2 = agent.render_hint_for_field("outline_qual")
    assert h2 is not None and h2["widget_type"] == "list_editor"


def test_data_paste_returns_none():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    for f in ("data_paste", "data_paste_quant", "data_paste_qual"):
        assert agent.render_hint_for_field(f) is None


def test_pseudo_fields_return_none():
    agent = M4Agent()
    M4Agent._render_outline_type = "SPSS"
    for f in ("_run_execution", "_run_qual_pipeline", "_summary"):
        assert agent.render_hint_for_field(f) is None
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m4_widgets.py -v 2>&1 | tail -10
```

- [ ] **Step 3: Extend `M4Agent` with `step()` + `render_hint_for_field`**

Add the following to the `M4Agent` class in `orchestrator/agents/m4_analysis.py`:

```python
    # Outline templates per outline-type-key. For SPSS/SmartPLS/CB-SEM we
    # reuse and extend the existing _OUTLINE_TEMPLATES dict from tools/m4_analysis.py.
    # Qualitative gets the 2-step pipeline per Q5=C.
    _AGENT_OUTLINE_TEMPLATES = {
        "SPSS": [
            {"name": "Descriptive Statistics", "thresholds": ""},
            {"name": "Reliability (Cronbach's Alpha)", "thresholds": "α ≥ 0.7"},
            {"name": "EFA", "thresholds": "KMO ≥ 0.5, factor loading ≥ 0.5"},
            {"name": "Correlation Matrix", "thresholds": "r < 0.85"},
            {"name": "Regression Analysis", "thresholds": "VIF < 10"},
            {"name": "ANOVA / t-tests", "thresholds": "p < 0.05"},
        ],
        "SmartPLS": [
            {"name": "Outer Loadings", "thresholds": "≥ 0.7"},
            {"name": "Convergent Validity: AVE & CR", "thresholds": "AVE ≥ 0.5, CR ≥ 0.7"},
            {"name": "Discriminant Validity: HTMT & Fornell-Larcker", "thresholds": "HTMT < 0.85"},
            {"name": "Collinearity: VIF", "thresholds": "VIF < 5"},
            {"name": "Path Coefficients (Bootstrap 5000)", "thresholds": "p < 0.05"},
            {"name": "R² and Adjusted R²", "thresholds": ""},
            {"name": "Effect size (f²)", "thresholds": "≥ 0.02 small, ≥ 0.15 medium, ≥ 0.35 large"},
            {"name": "Predictive Relevance (Q²)", "thresholds": "Q² > 0"},
        ],
        "CB-SEM": [
            {"name": "Confirmatory Factor Analysis (CFI/TLI/RMSEA)",
             "thresholds": "CFI/TLI ≥ 0.90, RMSEA ≤ 0.08, SRMR ≤ 0.08"},
            {"name": "Discriminant Validity", "thresholds": "HTMT < 0.85"},
            {"name": "Structural Model", "thresholds": "p < 0.05"},
            {"name": "Mediation/Moderation", "thresholds": ""},
        ],
        "Qualitative": [
            {"name": "Initial coding (extract codes + verbatim quotes)", "thresholds": ""},
            {"name": "Theme generation (cluster codes into themes)", "thresholds": ""},
        ],
        "Unknown": [
            {"name": "Generic descriptive", "thresholds": ""},
            {"name": "Generic inferential", "thresholds": ""},
        ],
    }

    def step(self, state):
        """Populate caches before the base class invokes render_hint_for_field.

        Reads m3_design.tool, m3_design.paradigm, partial.data_type_detected,
        partial.data_paste, partial.analysis_outline. The execution-phase
        dispatch (Task 12) hooks in via _next_missing_field returning a
        pseudo-field; this step() override just refreshes the caches.
        """
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        m3 = state["context_store"].m3_design or {}
        # Prefer post-paste data_type_detected over m3.tool if it disagrees.
        cls._render_paradigm = m3.get("paradigm")
        cls._render_outline_type = (
            partial.get("data_type_detected")
            or self._outline_template_key_from_tool(m3.get("tool"))
        )
        cls._render_paste_text = partial.get("data_paste", "")
        cls._render_outline = partial.get("analysis_outline")
        return super().step(state)

    def render_hint_for_field(self, field_name: str) -> dict | None:
        from orchestrator.agents.widgets import ListEditorHint, ListItem

        if field_name in ("analysis_outline", "outline_quant", "outline_qual"):
            # outline_quant uses the quant template (SPSS/SmartPLS/CB-SEM —
            # for mixed, prefer SmartPLS as the most common publishable choice).
            # outline_qual uses the Qualitative template.
            if field_name == "outline_qual":
                template_key = "Qualitative"
            elif field_name == "outline_quant":
                template_key = "SmartPLS"
            else:
                template_key = self._render_outline_type or "SPSS"
            sections = self._AGENT_OUTLINE_TEMPLATES.get(
                template_key, self._AGENT_OUTLINE_TEMPLATES["Unknown"]
            )
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
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m4_widgets.py -v 2>&1 | tail -15
git add orchestrator/agents/m4_analysis.py orchestrator/tests/agents/test_m4_widgets.py
git commit -m "feat(orchestrator): M4Agent step() cache population + render_hint_for_field for outlines"
```

Expected: 6 new widget tests PASS.

---

### Task 12: M4Agent `_run_quant_execution` (per-step emission)

**Files:**
- Modify: `orchestrator/agents/m4_analysis.py`
- Create: `orchestrator/tests/agents/test_m4_execution.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m4_execution.py`:

```python
"""Tests for M4Agent execution phase — per-step AIMessage emission."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_run_quant_execution_emits_one_message_per_step(monkeypatch):
    """After paste + outline are filled, _run_execution emits N step messages + 1 summary."""
    # Stub the parser dispatcher to return predictable StepResult dicts.
    def fake_run_step(invoke_args):
        step_name = invoke_args.get("step_name") if isinstance(invoke_args, dict) else None
        return {
            "step_name": step_name,
            "table": [{"x": 1}],
            "thresholds_met": True,
            "interpretation": f"OK for {step_name}",
            "parser": "regex",
        }

    # The agent calls run_analysis_step.invoke(...) so we patch the bound method.
    from orchestrator.agents import m4_analysis as m4_mod
    fake_tool = MagicMock()
    fake_tool.invoke.side_effect = lambda kw: fake_run_step(kw)
    monkeypatch.setattr(m4_mod, "run_analysis_step", fake_tool)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "SPSS", "paradigm": "quantitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "SPSS",
                "data_paste": "any spss output",
                "analysis_outline": {
                    "sections": [
                        {"name": "Descriptive Statistics"},
                        {"name": "Reliability (Cronbach's Alpha)"},
                    ],
                    "confirmed_by_user": True,
                },
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    # Primary assistant_message + 2 step extras + 1 summary extra = 3 in extra_messages
    # (primary is the summary OR an empty string — see implementation)
    assert len(result.extra_messages) >= 2  # at least the 2 step messages
    # Each step message's content contains the step name and a markdown table.
    contents = [m.content for m in result.extra_messages]
    assert any("Descriptive Statistics" in c for c in contents)
    assert any("Reliability" in c for c in contents)
    # The marker is set so the walk advances
    assert result.context_patch.get("_run_execution_done") is True
    # results dict has both step entries
    assert "Descriptive Statistics" in result.context_patch.get("results", {})
    assert "Reliability (Cronbach's Alpha)" in result.context_patch.get("results", {})


def test_run_qual_pipeline_emits_codes_and_themes_messages(monkeypatch):
    """Qual pipeline emits step messages for codes + themes + a summary."""
    from orchestrator.agents import m4_analysis as m4_mod

    fake_codes = MagicMock()
    fake_codes.invoke.return_value = [
        {"code": "leadership vision", "quote": "..."},
        {"code": "engagement", "quote": "..."},
    ]
    fake_themes = MagicMock()
    fake_themes.invoke.return_value = [
        {"theme": "Leadership", "codes": ["leadership vision"]},
        {"theme": "Engagement", "codes": ["engagement"]},
    ]
    monkeypatch.setattr(m4_mod, "suggest_qual_codes", fake_codes)
    monkeypatch.setattr(m4_mod, "cluster_codes_into_themes", fake_themes)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="ok")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "NVivo", "paradigm": "qualitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "Qualitative",
                "data_paste": "INTERVIEWER: ...\nPARTICIPANT: ...",
                "analysis_outline": {
                    "sections": [
                        {"name": "Initial coding (extract codes + verbatim quotes)"},
                        {"name": "Theme generation (cluster codes into themes)"},
                    ],
                    "confirmed_by_user": True,
                },
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    assert result.context_patch.get("_run_qual_pipeline_done") is True
    assert len(result.context_patch["qual_codes"]) == 2
    assert len(result.context_patch["qual_themes"]) == 2
    contents = [m.content for m in result.extra_messages]
    assert any("Initial coding" in c or "codes" in c.lower() for c in contents)
    assert any("Theme" in c or "themes" in c.lower() for c in contents)
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m4_execution.py -v 2>&1 | tail -10
```

Expected: FAIL — execution phase not yet implemented.

- [ ] **Step 3: Add execution methods to `M4Agent`**

Add to the `M4Agent` class (after `render_hint_for_field`):

```python
    def step(self, state):
        """Populate caches, then dispatch execution phase if we're at a pseudo-field.

        This step() override replaces the one from Task 11 — same cache logic
        plus execution dispatch.
        """
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        m3 = state["context_store"].m3_design or {}
        cls._render_paradigm = m3.get("paradigm")
        cls._render_outline_type = (
            partial.get("data_type_detected")
            or self._outline_template_key_from_tool(m3.get("tool"))
        )
        cls._render_paste_text = partial.get("data_paste", "")
        cls._render_outline = partial.get("analysis_outline")

        # Execution-phase dispatch when next missing field is a pseudo-field.
        missing = self._next_missing_field(partial)
        if missing == "_run_execution":
            return self._run_quant_execution(state, partial)
        if missing == "_run_qual_pipeline":
            return self._run_qual_pipeline(state, partial)
        return super().step(state)

    def _run_quant_execution(self, state, partial):
        """Loop confirmed outline sections, dispatch to run_analysis_step, emit per-step AIMessage."""
        from langchain_core.messages import AIMessage
        from orchestrator.agents.base import ModuleStepResult
        from orchestrator.tools.m4_parsers import format_step_as_markdown

        outline = partial.get("analysis_outline") or {}
        sections = outline.get("sections", []) or []
        results: dict[str, dict] = dict(partial.get("results", {}))
        extra: list = []
        for section in sections:
            step_name = section["name"]
            sr = run_analysis_step.invoke({
                "step_name": step_name,
                "data": {
                    "paste": self._render_paste_text,
                    "data_type": self._render_outline_type or "Unknown",
                },
            })
            results[step_name] = sr
            extra.append(AIMessage(content=format_step_as_markdown(sr)))
        partial["results"] = results
        partial["_run_execution_done"] = True
        partial["_awaiting_confirm"] = True
        summary = self._build_execution_summary(results)
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
            extra_messages=extra,
        )

    def _run_qual_pipeline(self, state, partial):
        """Two-step qual pipeline (Q5=C): codes + themes. Emit one message per step."""
        from langchain_core.messages import AIMessage
        from orchestrator.agents.base import ModuleStepResult

        codes = suggest_qual_codes.invoke({"transcript": self._render_paste_text})
        themes = cluster_codes_into_themes.invoke({"codes": codes})
        partial["qual_codes"] = codes
        partial["qual_themes"] = themes
        partial["_run_qual_pipeline_done"] = True
        partial["_awaiting_confirm"] = True

        code_msg = self._format_qual_codes_markdown(codes)
        theme_msg = self._format_qual_themes_markdown(themes)
        summary = (
            f"Qualitative pipeline complete: {len(codes)} codes clustered "
            f"into {len(themes)} themes. Confirm to move on to Chapter 4 writing."
        )
        return ModuleStepResult(
            assistant_message=summary,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
            extra_messages=[AIMessage(content=code_msg), AIMessage(content=theme_msg)],
        )

    def _build_execution_summary(self, results: dict[str, dict]) -> str:
        """One-paragraph summary of step thresholds for the user's confirm prompt."""
        total = len(results)
        breached = [name for name, sr in results.items()
                    if sr.get("thresholds_met") is False]
        if not breached:
            return (
                f"All {total} steps met their thresholds. "
                "Confirm to move on to Chapter 4 writing?"
            )
        flagged = ", ".join(breached)
        return (
            f"Ran {total} steps. ⚠️ {len(breached)} flagged threshold breaches: {flagged}. "
            "Review the per-step results above. Confirm to move on, or ask for an "
            "ad-hoc analysis to investigate further."
        )

    def _format_qual_codes_markdown(self, codes: list[dict]) -> str:
        if not codes:
            return "**Initial coding** — no codes extracted."
        rows = "\n".join(
            f"- **{c.get('code', '?')}** — \"{c.get('quote', '')[:120]}\""
            for c in codes
        )
        return f"**Initial coding** — {len(codes)} codes extracted:\n\n{rows}"

    def _format_qual_themes_markdown(self, themes: list[dict]) -> str:
        if not themes:
            return "**Theme generation** — no themes clustered."
        rows = "\n".join(
            f"- **{t.get('theme', '?')}** — codes: {', '.join(t.get('codes', []))}"
            for t in themes
        )
        return f"**Theme generation** — {len(themes)} themes:\n\n{rows}"
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m4_execution.py -v 2>&1 | tail -15
# Confirm earlier-task tests still pass
python -m pytest orchestrator/tests/agents/test_m4_outline.py orchestrator/tests/agents/test_m4_widgets.py -v 2>&1 | tail -10
git add orchestrator/agents/m4_analysis.py orchestrator/tests/agents/test_m4_execution.py
git commit -m "feat(orchestrator): M4Agent _run_quant_execution + _run_qual_pipeline"
```

Expected: 2 new execution tests PASS + all prior M4 tests still PASS.

---

### Task 13: Ad-hoc analysis detection in `step()`

**Files:**
- Modify: `orchestrator/agents/m4_analysis.py`
- Create: `orchestrator/tests/agents/test_m4_ad_hoc.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m4_ad_hoc.py`:

```python
"""Tests for M4Agent ad-hoc analysis detection (Q4=B — NL intent)."""
import json
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_ad_hoc_request_appends_to_custom_analyses(monkeypatch):
    """When the user requests an analysis outside the confirmed outline AND all
    outline fields are already filled (confirmed), the agent calls
    run_extra_analysis and appends the result to custom_analyses."""
    # Patch run_extra_analysis to return a known StepResult.
    from orchestrator.agents import m4_analysis as m4_mod

    fake_extra = MagicMock()
    fake_extra.invoke.return_value = {
        "step_name": "mediation H3",
        "table": [{"path": "TL → Trust → EE", "indirect": 0.113, "p": 0.004}],
        "thresholds_met": True,
        "interpretation": "Significant mediation effect.",
        "parser": "llm_fallback",
    }
    monkeypatch.setattr(m4_mod, "run_extra_analysis", fake_extra)

    # Stub the LLM (used by _ask_next_question) so the agent's NL path actually
    # produces a clarifying message; the ad-hoc detection is wired separately.
    fake_llm = MagicMock()
    fake_llm.invoke.return_value.content = "ok, ran the mediation test"
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake_llm)

    agent = M4Agent()
    state = {
        "messages": [HumanMessage(content="also run a mediation test on H3")],
        "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"tool": "SmartPLS", "paradigm": "quantitative",
                       "confirmed_at": "2026-05-26"},
            m4_analysis={
                "data_type_detected": "SmartPLS",
                "data_paste": "any output",
                "analysis_outline": {"sections": [{"name": "Outer Loadings"}],
                                     "confirmed_by_user": True},
                "results": {"Outer Loadings": {"step_name": "Outer Loadings",
                                                "table": [], "parser": "regex"}},
                "_run_execution_done": True,
                # No _summary_done yet — agent is awaiting confirm.
            },
        ),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    result = agent.step(state)
    # If ad-hoc was detected and dispatched, custom_analyses has the new entry.
    assert any(
        sr.get("step_name") == "mediation H3"
        for sr in result.context_patch.get("custom_analyses", [])
    )
```

- [ ] **Step 2: Run — should FAIL**

```bash
python -m pytest orchestrator/tests/agents/test_m4_ad_hoc.py -v 2>&1 | tail -10
```

Expected: FAIL — agent has no ad-hoc detection yet.

- [ ] **Step 3: Add ad-hoc detection to `step()`**

Update the `step()` method on `M4Agent` to detect ad-hoc requests when at the `_summary` pseudo-field (i.e. execution is done and we're awaiting confirm):

```python
    def step(self, state):
        """Populate caches, dispatch execution phase, OR detect ad-hoc request."""
        from orchestrator.state import get_module_slice
        cls = type(self)
        partial = dict(get_module_slice(state["context_store"], self.module_key))
        m3 = state["context_store"].m3_design or {}
        cls._render_paradigm = m3.get("paradigm")
        cls._render_outline_type = (
            partial.get("data_type_detected")
            or self._outline_template_key_from_tool(m3.get("tool"))
        )
        cls._render_paste_text = partial.get("data_paste", "")
        cls._render_outline = partial.get("analysis_outline")

        # Ad-hoc detection: if execution is done and the latest user message
        # looks like an extra-analysis request, route to run_extra_analysis
        # before the base class's confirm flow takes over.
        if partial.get("_run_execution_done") or partial.get("_run_qual_pipeline_done"):
            if self._is_ad_hoc_request(state["messages"]):
                return self._handle_ad_hoc(state, partial)

        missing = self._next_missing_field(partial)
        if missing == "_run_execution":
            return self._run_quant_execution(state, partial)
        if missing == "_run_qual_pipeline":
            return self._run_qual_pipeline(state, partial)
        return super().step(state)

    _AD_HOC_KEYWORDS = (
        "also run", "also test", "rerun", "re-run", "run again",
        "mediation", "moderation", "moderate", "controlling for",
        "with control", "ad-hoc", "extra analysis", "additional analysis",
    )

    def _is_ad_hoc_request(self, messages) -> bool:
        """Heuristic: scan the latest user message for ad-hoc keywords."""
        from langchain_core.messages import HumanMessage
        last_user = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        if not last_user:
            return False
        text = last_user.lower()
        return any(kw in text for kw in self._AD_HOC_KEYWORDS)

    def _handle_ad_hoc(self, state, partial):
        """Route an ad-hoc user message to run_extra_analysis + append to custom_analyses."""
        from langchain_core.messages import AIMessage, HumanMessage
        from orchestrator.agents.base import ModuleStepResult
        from orchestrator.tools.m4_parsers import format_step_as_markdown

        last_user = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            "",
        )
        sr = run_extra_analysis.invoke({
            "step_description": last_user.strip(),
            "data_paste": self._render_paste_text,
        })
        custom = list(partial.get("custom_analyses", []))
        custom.append(sr)
        partial["custom_analyses"] = custom
        msg = format_step_as_markdown(sr)
        return ModuleStepResult(
            assistant_message=msg,
            context_patch=partial,
            transition=False,
            needs_user_reply=True,
        )
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m4_ad_hoc.py -v 2>&1 | tail -10
# Confirm execution tests still pass (ad-hoc path is mutually exclusive)
python -m pytest orchestrator/tests/agents/test_m4_execution.py -v 2>&1 | tail -10
git add orchestrator/agents/m4_analysis.py orchestrator/tests/agents/test_m4_ad_hoc.py
git commit -m "feat(orchestrator): M4Agent ad-hoc analysis detection (NL intent → custom_analyses)"
```

Expected: 1 new ad-hoc test PASS + 2 execution tests still PASS.

---

### Task 14: M4 prompt rewrite

**Files:**
- Modify: `orchestrator/prompts/m4.md`

- [ ] **Step 1: Replace `orchestrator/prompts/m4.md`**

```markdown
# M4 — Data Analysis agent

You analyze the data. The user has already confirmed a paradigm and an analysis tool in M3 (e.g. quantitative + SPSS, qualitative + NVivo, mixed). Your job depends on the tool / data type.

## Quantitative branch (SPSS / SmartPLS / CB-SEM)

Walk these fields in order: `data_paste` → `analysis_outline` → (auto execution) → confirm.

- For `data_paste`: invite the user to paste their full analysis output. Example: *"Paste your SmartPLS report or SPSS output below — paste everything in one go and I'll work through the outline step by step."*
- For `analysis_outline`: a card grid will appear with the standard steps for the detected tool + thresholds. Invite the user to confirm or edit.
- After confirmation, **you do not run steps one at a time in chat**. The execution phase fires automatically: each step is parsed, interpreted, and emitted as its own message in the stream. You will see the bubbles arrive; the user reads through them and then the system asks for a final confirm.

## Qualitative branch

Walk these fields in order: `data_paste` → `analysis_outline` → (auto execution) → confirm.

- For `data_paste`: invite the user to paste their transcript(s). Multiple speakers should use ALL-CAPS prefix + colon (e.g. `INTERVIEWER:`, `PARTICIPANT:`).
- For `analysis_outline`: the 2-step pipeline (initial coding + theme generation) appears. Invite the user to confirm.
- The execution phase emits a code-listing message followed by a theme-listing message. The full writeup of Chapter 4 happens in M5.

## Mixed branch

Walks both quant and qual sub-flows in sequence. You will ask for two separate pastes (quant first, then qual) and two separate outline confirmations.

## Ad-hoc analysis (PRD §6.4.6)

When the user requests an analysis beyond the confirmed outline — for example:
- "also run a mediation test on H3"
- "rerun the regression with control variables"
- "check moderation by gender"

— the system routes the request to `run_extra_analysis(step_description, data_paste)` and appends the result to `M4Output.custom_analyses`. You don't need to call the tool explicitly — keyword detection handles routing.

## When a widget appears

When the next field has a list_editor widget rendered below your message, your text MUST invite confirming/editing — e.g. *"Confirm the outline below or edit before I run the steps."* — rather than asking the user to type the answer.

## Threshold breaches

When a step's `thresholds_met` is False, your interpretation prose flags the breach (the parsers handle this with ⚠️ markers). On user request, dispatch ad-hoc analysis to investigate.

Tools: `detect_data_type`, `generate_analysis_outline`, `run_analysis_step`, `interpret_result`, `run_extra_analysis`, `suggest_qual_codes`, `cluster_codes_into_themes`.
```

- [ ] **Step 2: Verify nothing crashes on prompt load**

```bash
python -c "from orchestrator.agents.m4_analysis import M4Agent; M4Agent()"
```

Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add orchestrator/prompts/m4.md
git commit -m "docs(orchestrator): M4 prompt rewrite for paste-flow + ad-hoc + per-step execution"
```

---

## Phase E — API + Frontend

### Task 15: Chat router analysis_outline SSE contract test

**Files:**
- Modify: `api/tests/test_chat_messages_widgets.py`

- [ ] **Step 1: Append the test**

Append to `api/tests/test_chat_messages_widgets.py`:

```python
def test_stream_emits_analysis_outline_tool_calls_event(client, monkeypatch):
    """SP5 contract test — the SP3 router forwards analysis_outline list_editor
    payloads through the SSE stream and persistence path. No router changes."""
    pid, tid = _setup(client)

    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick your outline")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "list_editor",
        "field_name": "analysis_outline",
        "title": "SPSS analysis outline",
        "initial_items": [
            {"id": "s0", "text": "Descriptive Statistics", "sub_items": [], "meta": {"thresholds": ""}},
            {"id": "s1", "text": "Reliability (Cronbach's Alpha)", "sub_items": [],
             "meta": {"thresholds": "α ≥ 0.7"}},
        ],
        "allow_nested": False,
        "confirm_label": "Confirm", "reset_label": "Reset to suggested",
    }

    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M4": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(f"/api/v1/threads/{tid}/messages", json={"text": "go"})
    assert resp.status_code == 200
    body = resp.text
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "list_editor" in body
    assert "analysis_outline" in body
    assert "Reliability" in body

    sf = get_session_factory()
    with sf() as db:
        assistants = db.query(Message).filter_by(thread_id=tid, role="assistant").all()
        assert assistants
        assert assistants[-1].tool_calls_json["field_name"] == "analysis_outline"
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_chat_messages_widgets.py -v 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add api/tests/test_chat_messages_widgets.py
git commit -m "test(api): chat router emits analysis_outline tool_calls event (contract coverage)"
```

Expected: PASS on first run — SP3 router is generic over any dict shape.

---

### Task 16: `synthesize.ts` extension for outline fields

**Files:**
- Modify: `web/app/components/chat/widgets/synthesize.ts`
- Modify: `web/app/components/chat/widgets/synthesize.test.ts`

- [ ] **Step 1: Append the failing tests**

Append to `web/app/components/chat/widgets/synthesize.test.ts`:

```typescript
describe("summarizeList — SP5 analysis outline fields", () => {
  const outlineItems: ListItem[] = [
    { id: "s0", text: "Descriptive Statistics", meta: {} },
    { id: "s1", text: "Reliability (Cronbach's Alpha)", meta: { thresholds: "α ≥ 0.7" } },
    { id: "s2", text: "Regression Analysis", meta: { thresholds: "VIF < 10" } },
  ];

  test("analysis_outline produces numbered list with thresholds", () => {
    const out = summarizeList(outlineItems, "analysis_outline");
    expect(out).toContain("My analysis outline:");
    expect(out).toContain("1. Descriptive Statistics");
    expect(out).toContain("2. Reliability (Cronbach's Alpha) — α ≥ 0.7");
    expect(out).toContain("3. Regression Analysis — VIF < 10");
  });

  test("outline_quant uses the same format", () => {
    const out = summarizeList(outlineItems, "outline_quant");
    expect(out).toContain("My analysis outline:");
    expect(out).toContain("1. Descriptive Statistics");
  });

  test("outline_qual uses the same format", () => {
    const out = summarizeList(outlineItems, "outline_qual");
    expect(out).toContain("My analysis outline:");
  });

  test("steps without thresholds omit the em-dash", () => {
    const items: ListItem[] = [{ id: "s0", text: "Step One", meta: {} }];
    const out = summarizeList(items, "analysis_outline");
    expect(out).toContain("1. Step One");
    expect(out).not.toContain("Step One —");
  });
});
```

- [ ] **Step 2: Run — should FAIL**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/synthesize 2>&1 | tail -10
```

Expected: FAIL — the switch falls through to the generic fallback (no "My analysis outline:" header).

- [ ] **Step 3: Update `web/app/components/chat/widgets/synthesize.ts`**

Add three new cases to the `summarizeList` switch (before the `default:` branch):

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

- [ ] **Step 4: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/synthesize 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/synthesize.ts web/app/components/chat/widgets/synthesize.test.ts
git commit -m "feat(web): summarizeList supports analysis_outline + outline_quant + outline_qual"
```

Expected: existing 10 + 4 new = 14 PASS.

---

### Task 17: ChatPane integration test for analysis_outline

**Files:**
- Modify: `web/app/components/chat/ChatPane.test.tsx`

- [ ] **Step 1: Append the failing test**

Append to `web/app/components/chat/ChatPane.test.tsx`:

```typescript
describe("ChatPane analysis_outline integration", () => {
  test("clicking Confirm on an analysis_outline list_editor synthesizes POST body", async () => {
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
          content: "Confirm the outline below",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "list_editor",
            field_name: "analysis_outline",
            title: "SPSS outline",
            initial_items: [
              { id: "s0", text: "Descriptive Statistics", sub_items: [], meta: {} },
              { id: "s1", text: "Reliability (Cronbach's Alpha)", sub_items: [],
                meta: { thresholds: "α ≥ 0.7" } },
            ],
            allow_nested: false,
            confirm_label: "Confirm", reset_label: "Reset to suggested",
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json() as { text?: string };
        return streamResponse([
          'data: {"type":"token","text":"Running..."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    renderFresh(<ChatPane projectId="p1" threadId="t1" />);

    await waitFor(() => expect(screen.getByTestId("list-editor-analysis_outline")).toBeTruthy());

    fireEvent.click(screen.getByTestId("list-editor-confirm"));

    await waitFor(() => expect(capturedBody?.text).toContain("My analysis outline:"));
    expect(capturedBody?.text).toContain("1. Descriptive Statistics");
    expect(capturedBody?.text).toContain("2. Reliability (Cronbach's Alpha) — α ≥ 0.7");
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- ChatPane 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/ChatPane.test.tsx
git commit -m "test(web): ChatPane analysis_outline integration — click Confirm → synthesized POST body"
```

Expected: existing 3 + 1 new = 4 PASS.

---

## Phase F — Round-trip + Wrap-up

### Task 18: Backend round-trip tests

**Files:**
- Create: `api/tests/test_m4_round_trip.py`

- [ ] **Step 1: Write the failing tests**

Create `api/tests/test_m4_round_trip.py`:

```python
"""Round-trip tests: synthesized list-editor messages → _extract_answer
returns expected structured values for M4 outline fields."""
from unittest.mock import MagicMock
import json

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent


def _stub_extract_llm(monkeypatch, payload):
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(payload)
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake)


def test_analysis_outline_synthesized_message_extracts_to_dict(monkeypatch):
    """The bulleted 'My analysis outline:\n1. Descriptive Statistics\n2. ...'
    message should extract to a {sections: [...]} dict."""
    _stub_extract_llm(monkeypatch, {
        "field": "analysis_outline",
        "value": {
            "sections": [
                {"name": "Descriptive Statistics"},
                {"name": "Reliability (Cronbach's Alpha)", "thresholds": "α ≥ 0.7"},
            ],
            "confirmed_by_user": True,
        },
    })
    state = {
        "messages": [HumanMessage(content=(
            "My analysis outline:\n"
            "1. Descriptive Statistics\n"
            "2. Reliability (Cronbach's Alpha) — α ≥ 0.7"
        ))],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "analysis_outline")
    assert isinstance(extracted, dict)
    assert "sections" in extracted
    assert extracted["sections"][1]["name"].startswith("Reliability")


def test_outline_quant_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "outline_quant",
        "value": {"sections": [{"name": "Outer Loadings"}], "confirmed_by_user": True},
    })
    state = {
        "messages": [HumanMessage(content="My analysis outline:\n1. Outer Loadings — ≥ 0.7")],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "outline_quant")
    assert extracted["sections"][0]["name"] == "Outer Loadings"


def test_outline_qual_extracts_to_dict(monkeypatch):
    _stub_extract_llm(monkeypatch, {
        "field": "outline_qual",
        "value": {"sections": [
            {"name": "Initial coding"},
            {"name": "Theme generation"},
        ], "confirmed_by_user": True},
    })
    state = {
        "messages": [HumanMessage(content=(
            "My analysis outline:\n1. Initial coding\n2. Theme generation"
        ))],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "outline_qual")
    assert len(extracted["sections"]) == 2


def test_data_paste_free_text_extracts_as_string(monkeypatch):
    """The data_paste field is free-text — the LLM extractor returns it
    as a plain string."""
    _stub_extract_llm(monkeypatch, {
        "field": "data_paste",
        "value": "Reliability Statistics\nCronbach's Alpha .840",
    })
    state = {
        "messages": [HumanMessage(content="Reliability Statistics\nCronbach's Alpha .840")],
        "current_module": "M4", "mode": "interactive",
    }
    extracted = M4Agent()._extract_answer(state, "data_paste")
    assert "Cronbach" in extracted
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_m4_round_trip.py -v 2>&1 | tail -10
cd /Users/caonguyenvan/project/dothesis
git add api/tests/test_m4_round_trip.py
git commit -m "test(orchestrator): M4 round-trip — synthesized outline → _extract_answer"
```

Expected: 4 PASS.

---

### Task 19: Final regression + roadmap flip

**Files:**
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Run the three regression suites**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate

echo "=== orchestrator ==="
python -m pytest orchestrator/tests/ -q --no-header --tb=no 2>&1 | tail -3

echo "=== api ==="
cd api && python -m pytest tests/ -q --no-header --tb=no 2>&1 > /tmp/sp5_api_full.txt
tail -3 /tmp/sp5_api_full.txt
cd ..

echo "=== web ==="
cd web && npm test 2>&1 | tail -3
cd ..
```

Expected:
- Orchestrator: 152 (SP4 baseline) + new SP5 tests = ~190+ pass; 0 NEW failures
- API: 52 baseline failures unchanged; 104 (SP4) + ~5 new = ~109 pass
- Web: 102 (SP4) + ~5 new = ~107 pass

- [ ] **Step 2: Diff API failures vs baseline**

```bash
cd /Users/caonguyenvan/project/dothesis
grep -E "^(FAILED|ERROR)" /tmp/sp5_api_full.txt | sort -u > /tmp/sp5_current.txt
grep -E "^(FAILED|ERROR)" /Users/caonguyenvan/project/dothesis/.baseline_failures_2026-05-26.txt | sort -u > /tmp/sp5_baseline.txt
echo "NEW failures from SP5 (must be empty):"
comm -23 /tmp/sp5_current.txt /tmp/sp5_baseline.txt
```

Expected: zero NEW failures.

- [ ] **Step 3: Flip roadmap status**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`:

Find the ASCII sub-project map and update `5. M4 analysis` to add ✅:

```
2. M2 chat✅ 3. M1 topic ✅ 4. M3 design ✅ 5. M4 analysis ✅ 6. M5 writing  7. New chat UI ✅
```

Replace the `## Sub-project 5 — M4 Adaptive Analysis ⬜` section header with:

```
## Sub-project 5 — M4 Adaptive Analysis ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp5-m4-analysis`; paste-text parsers + per-step execution + ad-hoc analysis + qual codes/themes)

**Spec:** `docs/superpowers/specs/2026-05-27-sp5-m4-analysis-design.md`
**Plan:** `docs/superpowers/plans/2026-05-27-sp5-m4-analysis-plan.md`

**Delivers:**
- Single `M4Agent` with outline-type-aware `_FIELDS_BY_OUTLINE_TYPE` walk driven by `m3_design.tool` (SPSS / SmartPLS / CB-SEM / Qualitative / Mixed / Unknown)
- Real per-format paste-text parsers: SPSS (Cronbach + regression), SmartPLS (loadings + AVE/CR + paths + HTMT), R lavaan (CFA fit indices), transcript (qual codes + themes)
- Hybrid regex-first / LLM-fallback / stub extraction; the `StepResult.parser` field records the source for audit
- Per-step `AIMessage` emission via new `ModuleStepResult.extra_messages` (graph node forwards them; chat router already loops over messages)
- Natural-language ad-hoc analysis detection routes to `run_extra_analysis` + appends to `M4Output.custom_analyses`
- 2-step qual pipeline (codes → themes); writeup deferred to M5
- Frontend extension: 3 new `summarizeList` cases for outline fields; reuses SP4's `list_editor` widget unchanged

**Decisions worth remembering for SP6:**
- Multi-message-per-update via `extra_messages` is a clean additive change that other modules can use
- The hybrid parser pattern (regex + LLM fallback + stub) is reusable for other "extract structured data from messy text" needs
- The `parser` field on result records (`regex` / `llm_fallback` / `stub`) is critical for audit trails and threshold-confidence

**Out of scope (deferred):**
- File uploads (`.sav`, `.spv`, `.xlsx`) → SP5.5 reuses SP2's upload subsystem
- Stata `.log`, NVivo XLSX, Atlas.ti exports → SP5.5
- CB-SEM full 8-step rigor → refinement once SmartPLS is stable
- `result_card` widget variant + per-step rerun buttons → optional SP5.5
- Slash-command `/run-extra` → optional post-V1
- Braun & Clarke writeup step → SP6 (M5 Writing owns Chapter 4 composition)
```

Append to the Status log:

```
| 2026-05-27 | 5 | ⬜ → ✅ | M4 adaptive analysis shipped — paste-text parsers + per-step execution + ad-hoc + qual codes/themes |
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs: SP5 shipped — roadmap flip to ✅"
```

---

## Done criteria checklist

- [ ] All 19 tasks committed in order on branch `feat/sp5-m4-analysis`
- [ ] All web tests pass (`cd web && npm test`)
- [ ] All orchestrator tests pass (`python -m pytest orchestrator/tests/ -q`)
- [ ] API tests show only baseline failures + new tests passing (diff vs `.baseline_failures_2026-05-26.txt` is empty)
- [ ] `npm run build` succeeds in `web/`
- [ ] Parser consistency check passes (every step in `_AGENT_OUTLINE_TEMPLATES` either has a parser extractor or is documented as LLM-fallback-only)
- [ ] Roadmap flipped to ✅ for SP5
- [ ] End-to-end manual smoke (optional): start `./dev.sh`, hit `/chat`, create a quant + SPSS project through M3, advance to M4, paste a sample SPSS output, confirm outline, watch per-step results stream in

---

## What's next after SP5 ships

**SP6 — M5 Writing & Finalization.** M5 reads `m4_analysis.results` (per-step structured tables) + `m4_analysis.qual_codes` + `m4_analysis.qual_themes` to compose Chapter 4, plus the M1/M2/M3 outputs for Chapters 1-3. The Braun & Clarke writeup step deferred from SP5 lands here. M5 also owns the WYSIWYG section editor, inline citation insertion, paraphrase/translate tools.

**SP5.5 (optional follow-up) — M4 file ingestion.** Add binary parsers (pyreadstat, openpyxl, python-docx, lxml) behind SP2's upload subsystem. Adds an `upload_panel` widget variant for the upload-and-detect UX. Reuses SP5's outline/execution machinery unchanged.
