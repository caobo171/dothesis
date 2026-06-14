> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# SP3 M1 Card-Grid Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the first module-specific widget UX in the chat shell — backend `render_hint_for_field` hook on ModuleAgent + frontend `WidgetRenderer` dispatch + two concrete `card_grid` widgets (FieldPicker, ResearchTypePicker) wired so clicking a card synthesizes a natural-language user message via the existing send path.

**Architecture:** Discriminated-union render hint protocol in `tool_calls_json`. Backend: extend ModuleAgent base with a `None`-by-default `render_hint_for_field` hook, route the hint through `_agent_node_factory` → AIMessage `additional_kwargs` → SSE `tool_calls` event → `messages.tool_calls_json` JSONB column. Frontend: `MessageBubble` reads the column, renders `WidgetRenderer` which dispatches on `widget_type`. SP3 ships one variant (`card_grid`) consumed by two M1 fields; future M3/M4/M5 widgets add new variants without touching existing code.

**Tech Stack:** Python 3.10+, Pydantic v2, FastAPI, SQLAlchemy 2.0, LangChain 1.x, LangGraph 1.2+, React 19, Next.js 16, TypeScript, Tailwind 3, lucide-react, Vitest 2, MSW 2.

**Spec:** `docs/superpowers/specs/2026-05-27-sp3-m1-card-grid-design.md`
**Depends on:** Sub-projects 1, 2, 7 (all on master).

---

## File map

### NEW backend files

```
orchestrator/agents/widgets.py                          # Pydantic CardOption + CardGridHint + WidgetHint union
orchestrator/prompts/m1/_options_field.json             # 8 academic-field options
orchestrator/prompts/m1/_options_research_type.json     # 3 research-type options
orchestrator/tests/agents/test_module_agent_render_hint.py
orchestrator/tests/agents/test_m1_widgets.py
api/tests/test_chat_messages_widgets.py
```

### MODIFIED backend files

```
orchestrator/agents/base.py                             # ModuleStepResult.tool_calls_json + render_hint_for_field hook + _ask_next_question wiring
orchestrator/agents/m1_topic.py                         # override render_hint_for_field
orchestrator/graph.py                                   # thread tool_calls_json through AIMessage.additional_kwargs
orchestrator/prompts/m1.md                              # one paragraph: invite picking when widget present
api/app/routers/chat.py                                 # emit tool_calls SSE event + persist tool_calls_json column
```

### NEW frontend files

```
web/app/components/chat/widgets/types.ts
web/app/components/chat/widgets/types.test.ts           # schema-drift guard
web/app/components/chat/widgets/synthesize.ts
web/app/components/chat/widgets/synthesize.test.ts
web/app/components/chat/widgets/CardGridWidget.tsx
web/app/components/chat/widgets/CardGridWidget.test.tsx
web/app/components/chat/widgets/WidgetRenderer.tsx
web/app/components/chat/widgets/WidgetRenderer.test.tsx
```

### MODIFIED frontend files

```
web/app/components/chat/hooks/useChat.ts                # +streamingToolCalls, +Message.tool_calls_json
web/app/components/chat/hooks/useChat.test.tsx          # +collect-tool_calls test
web/app/components/chat/MessageBubble.tsx               # render WidgetRenderer when toolCallsJson present
web/app/components/chat/MessageBubble.test.tsx          # +3 widget-render tests
web/app/components/chat/MessageList.tsx                 # forward onWidgetSelect + widgetDisabled
web/app/components/chat/ChatPane.tsx                    # wire onWidgetSelect → synthesize + send
web/app/components/chat/ChatPane.test.tsx               # +click → POST body integration test
```

### MODIFIED docs

```
docs/superpowers/2026-05-26-platform-pivot-roadmap.md   # flip SP3 to ✅
```

---

## Task index (17 tasks)

| Phase | Tasks |
|---|---|
| A. Backend widget primitive | 1. widgets.py + tests · 2. ModuleAgent base extension · 3. graph.py wiring |
| B. M1 hint emission | 4. option JSON files · 5. M1Agent override + tests |
| C. API streaming + persistence | 6. chat router emits tool_calls + persists |
| D. Frontend widget primitive | 7. types.ts + schema-drift test · 8. synthesize.ts + test · 9. CardGridWidget + tests · 10. WidgetRenderer + tests |
| E. Frontend integration | 11. useChat updates · 12. MessageBubble updates · 13. MessageList updates · 14. ChatPane wiring |
| F. Integration | 15. ChatPane click-to-send integration · 16. Round-trip test (synthesized → extract) |
| G. Wrap-up | 17. Prompt update + regression + roadmap flip |

---

## Phase A — Backend widget primitive

### Task 1: orchestrator/agents/widgets.py + tests

**Files:**
- Create: `orchestrator/agents/widgets.py`
- Create: `orchestrator/tests/agents/test_widgets.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_widgets.py`:

```python
"""Tests for Pydantic widget hint models."""
import pytest
from pydantic import ValidationError

from orchestrator.agents.widgets import CardOption, CardGridHint


def test_card_option_minimal_fields():
    o = CardOption(value="x", label="X")
    assert o.value == "x"
    assert o.label == "X"
    assert o.description == ""
    assert o.icon is None


def test_card_option_with_all_fields():
    o = CardOption(value="x", label="X", description="desc", icon="zap")
    assert o.description == "desc"
    assert o.icon == "zap"


def test_card_grid_hint_minimal():
    h = CardGridHint(
        field_name="field",
        title="Pick",
        options=[CardOption(value="x", label="X")],
    )
    assert h.widget_type == "card_grid"
    assert h.columns == 3      # default


def test_card_grid_hint_model_dump_includes_widget_type():
    """Backend serializes to JSON via model_dump(); widget_type must survive."""
    h = CardGridHint(
        field_name="research_type",
        title="Approach",
        options=[CardOption(value="quantitative", label="Quantitative")],
        columns=3,
    )
    blob = h.model_dump()
    assert blob["widget_type"] == "card_grid"
    assert blob["field_name"] == "research_type"
    assert blob["options"][0]["value"] == "quantitative"


def test_card_grid_hint_rejects_empty_options():
    """Pydantic should not allow building a card grid with zero options
    (widget would be unusable). Pydantic doesn't reject empty lists by
    default; ensure the test documents current behavior."""
    h = CardGridHint(field_name="x", title="t", options=[])
    assert h.options == []  # accepted today; if we tighten later, update.
```

- [ ] **Step 2: Run — should fail**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/agents/test_widgets.py -v
```
Expected: FAIL (`ModuleNotFoundError: No module named 'orchestrator.agents.widgets'`).

- [ ] **Step 3: Implement**

Create `orchestrator/agents/widgets.py`:

```python
"""Pydantic models for module-agent widget render hints.

Each `WidgetHint` variant is serialized via `.model_dump()` into the
`messages.tool_calls_json` JSONB column. The frontend's WidgetRenderer
dispatches on `widget_type` to pick the right React component.

Future sub-projects (SP4-SP6) add new variants (e.g. `model_builder`,
`outline_editor`) to the discriminated union below — existing variants
and consumers are unaffected.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


class CardOption(BaseModel):
    value: str               # The schema value the click sends back
    label: str               # Display name
    description: str = ""    # Optional secondary line
    icon: str | None = None  # lucide-react icon name; SP3 ignores it


class CardGridHint(BaseModel):
    """Card grid: a labeled set of clickable cards. One click = one value."""
    widget_type: Literal["card_grid"] = "card_grid"
    field_name: str          # Which schema field this widget fills
    title: str               # Header above the grid
    options: list[CardOption]
    columns: int = 3         # Visual columns (frontend may collapse on narrow screens)


# Discriminated union — future variants land here.
WidgetHint = Annotated[Union[CardGridHint], Field(discriminator="widget_type")]
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_widgets.py -v
git add orchestrator/agents/widgets.py orchestrator/tests/agents/test_widgets.py
git commit -m "feat(orchestrator): widgets.py — CardOption + CardGridHint + WidgetHint union"
```
Expected: 5 PASS.

---

### Task 2: ModuleAgent base extension

**Files:**
- Modify: `orchestrator/agents/base.py`
- Create: `orchestrator/tests/agents/test_module_agent_render_hint.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_module_agent_render_hint.py`:

```python
"""Tests for ModuleAgent.render_hint_for_field hook + ModuleStepResult.tool_calls_json."""
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleAgent
from orchestrator.state import ContextStore


class _ToyOutput(BaseModel):
    color: str = Field(..., min_length=1)
    shape: str = Field(..., min_length=1)


class _PlainAgent(ModuleAgent):
    schema = _ToyOutput
    module_key = "M1"
    tools = []
    system_prompt = "toy"


class _HintingAgent(_PlainAgent):
    def render_hint_for_field(self, field_name):
        if field_name == "color":
            return {
                "widget_type": "card_grid",
                "field_name": "color",
                "title": "Pick a color",
                "options": [{"value": "red", "label": "Red"}],
                "columns": 3,
            }
        return None


def _state(messages, partial=None):
    cs = ContextStore()
    if partial:
        cs.m1_topic = partial
    return {
        "project_id": None, "thread_id": None, "messages": messages,
        "current_module": "M1", "context_store": cs, "mode": "interactive",
        "user_intent": None, "pending_confirmations": [],
    }


def test_default_hook_returns_none(monkeypatch):
    """Base class default → ModuleStepResult.tool_calls_json is None."""
    fake = MagicMock()
    fake.invoke.return_value.content = "What color?"
    monkeypatch.setattr(_PlainAgent, "_get_llm", lambda self: fake)
    result = _PlainAgent().step(_state([HumanMessage("start")]))
    assert result.tool_calls_json is None


def test_subclass_override_attaches_hint(monkeypatch):
    """Subclass that overrides → hint flows into ModuleStepResult."""
    fake = MagicMock()
    fake.invoke.return_value.content = "What color?"
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    result = _HintingAgent().step(_state([HumanMessage("start")]))
    assert result.tool_calls_json is not None
    assert result.tool_calls_json["widget_type"] == "card_grid"
    assert result.tool_calls_json["field_name"] == "color"


def test_no_hint_when_summary_phase(monkeypatch):
    """When all fields filled, summary path emits no hint."""
    fake = MagicMock()
    fake.invoke.return_value.content = "Summary..."
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    result = _HintingAgent().step(_state(
        [HumanMessage("yes")],
        partial={"color": "red", "shape": "circle"},
    ))
    assert result.tool_calls_json is None


def test_no_hint_in_auto_mode(monkeypatch):
    """Auto-mode skips _ask_next_question entirely; tool_calls_json stays None."""
    fake = MagicMock()
    fake.invoke.return_value.content = '{"color": "red", "shape": "circle"}'
    monkeypatch.setattr(_HintingAgent, "_get_llm", lambda self: fake)
    state = _state([HumanMessage("topic")])
    state["mode"] = "auto"
    result = _HintingAgent().step(state)
    assert result.tool_calls_json is None
```

- [ ] **Step 2: Run — should fail**

```bash
python -m pytest orchestrator/tests/agents/test_module_agent_render_hint.py -v
```
Expected: FAIL (`'ModuleStepResult' object has no attribute 'tool_calls_json'`).

- [ ] **Step 3: Extend ModuleStepResult**

Find the `@dataclass` block in `orchestrator/agents/base.py` and add the field:

```python
@dataclass
class ModuleStepResult:
    """What a module's step() returns to the graph runner."""
    assistant_message: str
    context_patch: dict
    transition: bool                 # True → done; supervisor takes over
    needs_user_reply: bool = False
    tool_calls_json: dict | None = None    # NEW — widget render hint, or None
```

- [ ] **Step 4: Add render_hint_for_field hook**

In the `ModuleAgent` class body (around the `_get_llm` method), add:

```python
    def render_hint_for_field(self, field_name: str) -> dict | None:
        """Optional override: return a widget render hint when asking the user
        to fill `field_name`. Default returns None (plain-text input).

        Subclasses should return a dict matching one of the WidgetHint
        variants in orchestrator/agents/widgets.py (e.g. CardGridHint).
        Use `<HintClass>(...).model_dump()` to produce the dict.
        """
        return None
```

- [ ] **Step 5: Wire the hint into _ask_next_question**

Find `_ask_next_question` in `orchestrator/agents/base.py`. The current return for the "ask next field" branch looks roughly like:

```python
        msg = self._get_llm().invoke(prompt).content.strip()
        return ModuleStepResult(
            assistant_message=msg, context_patch=partial,
            transition=False, needs_user_reply=True,
        )
```

Change it to:

```python
        msg = self._get_llm().invoke(prompt).content.strip()
        hint = self.render_hint_for_field(missing)
        return ModuleStepResult(
            assistant_message=msg, context_patch=partial,
            transition=False, needs_user_reply=True,
            tool_calls_json=hint,
        )
```

Leave the summary-phase return path (where `missing is None`) untouched — it defaults to `tool_calls_json=None`.

- [ ] **Step 6: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_module_agent_render_hint.py -v
git add orchestrator/agents/base.py orchestrator/tests/agents/test_module_agent_render_hint.py
git commit -m "feat(orchestrator): ModuleAgent.render_hint_for_field hook + tool_calls_json on result"
```
Expected: 4 PASS.

---

### Task 3: orchestrator/graph.py — thread tool_calls_json through the graph

**Files:**
- Modify: `orchestrator/graph.py`
- Modify: `orchestrator/tests/test_graph.py` (extend an existing test)

- [ ] **Step 1: Write a new test verifying additional_kwargs propagation**

Append to `orchestrator/tests/test_graph.py`:

```python
def test_graph_node_attaches_tool_calls_json_to_ai_message(monkeypatch):
    """When ModuleStepResult.tool_calls_json is set, the emitted AIMessage
    should carry the same dict in additional_kwargs['tool_calls_json']."""
    from langchain_core.messages import HumanMessage
    from langgraph.checkpoint.memory import MemorySaver
    from unittest.mock import MagicMock

    from orchestrator.agents.m1_topic import M1Agent
    from orchestrator.graph import build_graph
    from orchestrator.state import ContextStore

    # Stub M1Agent.step to return a result with tool_calls_json set.
    hint = {"widget_type": "card_grid", "field_name": "field",
            "title": "Pick", "options": [], "columns": 3}
    from orchestrator.agents.base import ModuleStepResult

    def fake_step(self, state):
        return ModuleStepResult(
            assistant_message="Pick a field",
            context_patch={"field": None},
            transition=False, needs_user_reply=True,
            tool_calls_json=hint,
        )
    monkeypatch.setattr(M1Agent, "step", fake_step)

    # Also stub M2-M5 + supervisor to never get hit (we only test M1 once).
    g = build_graph(interactive=True, checkpointer=MemorySaver())
    state = {
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "interactive",
        "user_intent": None,
        "pending_confirmations": [],
    }
    # Run one step; interrupt_before=["supervisor"] gives us a snapshot after M1.
    config = {"configurable": {"thread_id": "test-tc"}}
    g.invoke(state, config=config)
    snapshot = g.get_state(config)
    last_ai = next(
        m for m in reversed(snapshot.values["messages"])
        if m.__class__.__name__ == "AIMessage"
    )
    assert last_ai.additional_kwargs.get("tool_calls_json") == hint
```

- [ ] **Step 2: Run — should fail**

```bash
python -m pytest orchestrator/tests/test_graph.py::test_graph_node_attaches_tool_calls_json_to_ai_message -v
```
Expected: FAIL (the existing `_agent_node_factory` doesn't attach `additional_kwargs`).

- [ ] **Step 3: Update _agent_node_factory**

In `orchestrator/graph.py`, find `_agent_node_factory`. The existing implementation looks roughly like:

```python
def _agent_node_factory(module_key: str):
    def _node(state: OrchestratorState) -> dict:
        from langchain_core.messages import AIMessage
        agent = _AGENT_BY_KEY[module_key]
        result = agent.step(state)
        cs = state["context_store"].model_copy(deep=True)
        setattr(cs, _MODULE_FIELD[module_key], result.context_patch)
        return {
            "messages": [AIMessage(content=result.assistant_message)],
            "context_store": cs,
        }
    return _node
```

Change to attach `additional_kwargs` when the hint is present:

```python
def _agent_node_factory(module_key: str):
    def _node(state: OrchestratorState) -> dict:
        from langchain_core.messages import AIMessage
        agent = _AGENT_BY_KEY[module_key]
        result = agent.step(state)
        cs = state["context_store"].model_copy(deep=True)
        setattr(cs, _MODULE_FIELD[module_key], result.context_patch)
        ai = AIMessage(content=result.assistant_message)
        if result.tool_calls_json:
            ai.additional_kwargs["tool_calls_json"] = result.tool_calls_json
        return {"messages": [ai], "context_store": cs}
    return _node
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/test_graph.py -v 2>&1 | tail -10
git add orchestrator/graph.py orchestrator/tests/test_graph.py
git commit -m "feat(orchestrator): graph passes tool_calls_json through AIMessage.additional_kwargs"
```
Expected: PASS (new test + all existing graph tests).

---

## Phase B — M1 hint emission

### Task 4: Option JSON files

**Files:**
- Create: `orchestrator/prompts/m1/_options_field.json`
- Create: `orchestrator/prompts/m1/_options_research_type.json`

- [ ] **Step 1: Create the field options file**

```bash
mkdir -p /Users/caonguyenvan/project/dothesis/orchestrator/prompts/m1
```

Create `orchestrator/prompts/m1/_options_field.json`:

```json
[
  {"value": "Marketing",         "label": "Marketing",          "description": "Consumer behavior, branding, advertising"},
  {"value": "Management",        "label": "Management",         "description": "Leadership, strategy, organizational behavior"},
  {"value": "Economics",         "label": "Economics",          "description": "Macro/micro economics, finance, development"},
  {"value": "Psychology",        "label": "Psychology",         "description": "Cognitive, social, organizational psychology"},
  {"value": "Sociology",         "label": "Sociology",          "description": "Social structures, culture, change"},
  {"value": "Education",         "label": "Education",          "description": "Pedagogy, learning theory, policy"},
  {"value": "Accounting-Finance","label": "Accounting & Finance","description": "Corporate finance, accounting, audit"},
  {"value": "Other",             "label": "Other / Specify",    "description": "Type your field below"}
]
```

- [ ] **Step 2: Create the research-type options file**

Create `orchestrator/prompts/m1/_options_research_type.json`:

```json
[
  {"value": "quantitative", "label": "Quantitative",  "description": "Test relationships between variables; statistical analysis"},
  {"value": "qualitative",  "label": "Qualitative",   "description": "Explore experiences, meanings, themes; interpretive analysis"},
  {"value": "mixed",        "label": "Mixed methods", "description": "Combine both for breadth and depth"}
]
```

- [ ] **Step 3: Validate the files parse as JSON**

```bash
python -c "import json; json.load(open('orchestrator/prompts/m1/_options_field.json'))"
python -c "import json; json.load(open('orchestrator/prompts/m1/_options_research_type.json'))"
```
Expected: no output (silent success).

- [ ] **Step 4: Commit**

```bash
git add orchestrator/prompts/m1/_options_field.json orchestrator/prompts/m1/_options_research_type.json
git commit -m "feat(orchestrator): M1 card-grid option JSON files (field + research_type)"
```

---

### Task 5: M1Agent override + tests

**Files:**
- Modify: `orchestrator/agents/m1_topic.py`
- Create: `orchestrator/tests/agents/test_m1_widgets.py`

- [ ] **Step 1: Write the failing tests**

Create `orchestrator/tests/agents/test_m1_widgets.py`:

```python
"""Tests for M1Agent.render_hint_for_field overrides."""
from orchestrator.agents.m1_topic import M1Agent


def test_field_returns_card_grid_hint():
    hint = M1Agent().render_hint_for_field("field")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "field"
    assert len(hint["options"]) >= 7
    assert any(o["value"] == "Marketing" for o in hint["options"])
    assert any(o["value"] == "Other" for o in hint["options"])


def test_research_type_returns_card_grid_hint():
    hint = M1Agent().render_hint_for_field("research_type")
    assert hint is not None
    assert hint["widget_type"] == "card_grid"
    assert hint["field_name"] == "research_type"
    values = {o["value"] for o in hint["options"]}
    assert values == {"quantitative", "qualitative", "mixed"}


def test_text_fields_return_none():
    """Free-text M1 fields get no widget."""
    agent = M1Agent()
    for f in ("research_title", "target_population", "scope", "objectives", "research_questions"):
        assert agent.render_hint_for_field(f) is None, f"Expected None for {f}"


def test_hint_options_carry_description():
    """Description field is populated; helps the UI show secondary text."""
    hint = M1Agent().render_hint_for_field("field")
    marketing = next(o for o in hint["options"] if o["value"] == "Marketing")
    assert marketing["description"] != ""
```

- [ ] **Step 2: Run — should fail**

```bash
python -m pytest orchestrator/tests/agents/test_m1_widgets.py -v
```
Expected: FAIL (`render_hint_for_field` returns None by default).

- [ ] **Step 3: Override the hook in M1Agent**

Replace `orchestrator/agents/m1_topic.py`:

```python
"""M1 — Topic Discovery agent."""
import json
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.agents.widgets import CardGridHint, CardOption
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics


_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"
_PROMPT = (_PROMPT_DIR / "m1.md").read_text()
_FIELD_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_field.json").read_text())
_RESEARCH_TYPE_OPTIONS = json.loads((_PROMPT_DIR / "m1" / "_options_research_type.json").read_text())


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]

    def render_hint_for_field(self, field_name: str) -> dict | None:
        if field_name == "field":
            return CardGridHint(
                field_name="field",
                title="Which academic field is your research in?",
                options=[CardOption(**o) for o in _FIELD_OPTIONS],
                columns=3,
            ).model_dump()
        if field_name == "research_type":
            return CardGridHint(
                field_name="research_type",
                title="Which research approach fits your question?",
                options=[CardOption(**o) for o in _RESEARCH_TYPE_OPTIONS],
                columns=3,
            ).model_dump()
        return None
```

- [ ] **Step 4: Run + commit**

```bash
python -m pytest orchestrator/tests/agents/test_m1_widgets.py orchestrator/tests/agents/test_agents_m1.py -v
git add orchestrator/agents/m1_topic.py orchestrator/tests/agents/test_m1_widgets.py
git commit -m "feat(orchestrator): M1Agent emits card_grid hints for field + research_type"
```
Expected: 4 NEW + existing PASS.

---

## Phase C — API streaming + persistence

### Task 6: chat router emits tool_calls + persists

**Files:**
- Modify: `api/app/routers/chat.py`
- Create: `api/tests/test_chat_messages_widgets.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_chat_messages_widgets.py`:

```python
"""Tests that the chat message endpoint emits tool_calls SSE events
and persists the payload to messages.tool_calls_json."""
import asyncio
import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Message, User
from app.security import create_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_ENABLED", "true")
    return TestClient(create_app())


def _setup(client) -> tuple[uuid.UUID, uuid.UUID]:
    sf = get_session_factory()
    with sf() as db:
        u = User(email=f"u{uuid.uuid4().hex[:6]}@x",
                 username=f"u{uuid.uuid4().hex[:6]}",
                 password_hash="x", email_verified=True)
        db.add(u); db.commit()
        client.cookies.set("dothesis_session", create_session(db, u))
    pid = client.post("/api/v1/projects", json={"name": "T"}).json()["id"]
    tid = client.get(f"/api/v1/projects/{pid}/threads").json()[0]["id"]
    return uuid.UUID(pid), uuid.UUID(tid)


def _async_iter(items):
    async def _it():
        for x in items:
            yield x
    return _it()


def test_stream_emits_tool_calls_event_and_persists(client, monkeypatch):
    pid, tid = _setup(client)

    # Stub the interactive graph to emit ONE update with an assistant message
    # carrying tool_calls_json in additional_kwargs, then 'done'.
    from langchain_core.messages import AIMessage
    ai = AIMessage(content="Pick a field")
    ai.additional_kwargs["tool_calls_json"] = {
        "widget_type": "card_grid", "field_name": "field",
        "title": "Pick", "options": [], "columns": 3,
    }

    fake_graph = MagicMock()
    fake_graph.astream.return_value = _async_iter([
        {"M1": {"messages": [ai]}},
    ])
    monkeypatch.setattr(
        "orchestrator.graph.get_interactive_graph", lambda: fake_graph
    )

    resp = client.post(
        f"/api/v1/threads/{tid}/messages",
        json={"text": "hi"},
    )
    assert resp.status_code == 200
    body = resp.text
    # SSE body contains a tool_calls event with the payload
    assert '"type": "tool_calls"' in body or '"type":"tool_calls"' in body
    assert "card_grid" in body

    # Persisted Message row carries the JSONB payload
    sf = get_session_factory()
    with sf() as db:
        msgs = db.query(Message).filter_by(thread_id=tid).order_by(Message.id).all()
        # 1 user msg + 1 assistant msg
        assistant = [m for m in msgs if m.role == "assistant"][0]
        assert assistant.tool_calls_json is not None
        assert assistant.tool_calls_json["widget_type"] == "card_grid"
        assert assistant.tool_calls_json["field_name"] == "field"
```

- [ ] **Step 2: Run — should fail**

```bash
cd api && source .venv/bin/activate
python -m pytest tests/test_chat_messages_widgets.py -v
```
Expected: FAIL (router doesn't emit tool_calls events yet).

- [ ] **Step 3: Update the chat router**

In `api/app/routers/chat.py`, find the `send_message` endpoint's `gen()` async generator. The existing implementation looks roughly like:

```python
    async def gen():
        nonlocal final_module_tag
        async for event in graph.astream(
            {"messages": [HumanMessage(content=body.text)], "mode": "interactive"},
            config=config,
            stream_mode="updates",
        ):
            for node_name, payload in event.items():
                if node_name in {"M1", "M2", "M3", "M4", "M5"}:
                    final_module_tag = node_name
                msgs = payload.get("messages") or []
                for m in msgs:
                    chunk = getattr(m, "content", "")
                    if chunk:
                        assistant_chunks.append(chunk)
                        yield sse_pack({
                            "type": "token",
                            "module": node_name if node_name != "supervisor" else None,
                            "text": chunk,
                        })

        full = "".join(assistant_chunks)
        if full:
            with db.bind.connect() as conn:
                conn.execute(
                    Message.__table__.insert().values(
                        thread_id=thread_id, role="assistant",
                        content=full, module_tag=final_module_tag,
                    )
                )
                conn.commit()
        yield sse_pack({"type": "done"})
```

Add a `final_tool_calls` collector and the tool_calls emit + persist:

```python
    async def gen():
        nonlocal final_module_tag
        final_tool_calls: dict | None = None       # NEW
        async for event in graph.astream(
            {"messages": [HumanMessage(content=body.text)], "mode": "interactive"},
            config=config,
            stream_mode="updates",
        ):
            for node_name, payload in event.items():
                if node_name in {"M1", "M2", "M3", "M4", "M5"}:
                    final_module_tag = node_name
                msgs = payload.get("messages") or []
                for m in msgs:
                    chunk = getattr(m, "content", "")
                    if chunk:
                        assistant_chunks.append(chunk)
                        yield sse_pack({
                            "type": "token",
                            "module": node_name if node_name != "supervisor" else None,
                            "text": chunk,
                        })

                    # NEW: emit tool_calls when present
                    tc = getattr(m, "additional_kwargs", {}).get("tool_calls_json")
                    if tc:
                        final_tool_calls = tc
                        yield sse_pack({"type": "tool_calls", "payload": tc})

        full = "".join(assistant_chunks)
        if full:
            with db.bind.connect() as conn:
                conn.execute(
                    Message.__table__.insert().values(
                        thread_id=thread_id, role="assistant",
                        content=full, module_tag=final_module_tag,
                        tool_calls_json=final_tool_calls,         # NEW
                    )
                )
                conn.commit()
        yield sse_pack({"type": "done"})
```

- [ ] **Step 4: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/api && source .venv/bin/activate
python -m pytest tests/test_chat_messages_widgets.py -v
cd /Users/caonguyenvan/project/dothesis
git add api/app/routers/chat.py api/tests/test_chat_messages_widgets.py
git commit -m "feat(api): chat router emits tool_calls SSE event + persists tool_calls_json"
```
Expected: PASS.

---

## Phase D — Frontend widget primitive

### Task 7: widgets/types.ts + schema-drift guard

**Files:**
- Create: `web/app/components/chat/widgets/types.ts`
- Create: `web/app/components/chat/widgets/types.test.ts`

- [ ] **Step 1: Create types.ts**

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

// Discriminated union — future variants (model_builder, outline_editor, ...) land here.
export type WidgetHint = CardGridHint;

export type WidgetSelectHandler = (
  fieldName: string,
  value: string,
  label: string,
) => void;
```

- [ ] **Step 2: Create the schema-drift guard test**

```typescript
// web/app/components/chat/widgets/types.test.ts
import { describe, expect, test } from "vitest";
import type { CardGridHint } from "./types";

/**
 * Fixture matching exactly what backend's orchestrator/agents/widgets.py
 * CardGridHint.model_dump() produces. If backend schema changes, the
 * fixture below stops parsing cleanly into the TS type and the build fails
 * — surfacing the drift before it ships.
 */
const FIXTURE: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [
    { value: "Marketing", label: "Marketing", description: "x", icon: null },
  ],
  columns: 3,
};

describe("CardGridHint schema parity", () => {
  test("matches backend Pydantic output shape", () => {
    expect(FIXTURE.widget_type).toBe("card_grid");
    expect(FIXTURE.options[0]).toHaveProperty("value");
    expect(FIXTURE.options[0]).toHaveProperty("label");
    expect(FIXTURE.options[0]).toHaveProperty("description");
    expect(FIXTURE.options[0]).toHaveProperty("icon");
  });
});
```

- [ ] **Step 3: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis/web && npm test -- widgets/types
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/types.ts web/app/components/chat/widgets/types.test.ts
git commit -m "feat(web): widget hint TypeScript types + schema-drift guard"
```
Expected: 1 PASS.

---

### Task 8: synthesize.ts + test

**Files:**
- Create: `web/app/components/chat/widgets/synthesize.ts`
- Create: `web/app/components/chat/widgets/synthesize.test.ts`

- [ ] **Step 1: Write the failing tests**

```typescript
// web/app/components/chat/widgets/synthesize.test.ts
import { describe, expect, test } from "vitest";
import { synthesizeWidgetSelection } from "./synthesize";

describe("synthesizeWidgetSelection", () => {
  test("field synthesizes 'I'd like to study X.'", () => {
    expect(synthesizeWidgetSelection("field", "Marketing", "Marketing"))
      .toBe("I'd like to study Marketing.");
  });

  test("research_type synthesizes 'I'll use a X approach.'", () => {
    expect(synthesizeWidgetSelection("research_type", "qualitative", "Qualitative"))
      .toBe("I'll use a qualitative approach.");
  });

  test("unknown field falls back to label", () => {
    expect(synthesizeWidgetSelection("unknown_field", "x", "X")).toBe("X");
  });

  test("research_type uses lowercase label inside the sentence", () => {
    expect(synthesizeWidgetSelection("research_type", "mixed", "Mixed methods"))
      .toBe("I'll use a mixed methods approach.");
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/widgets/synthesize.ts
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
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- widgets/synthesize
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/synthesize.ts web/app/components/chat/widgets/synthesize.test.ts
git commit -m "feat(web): synthesize click → natural-language message helper"
```
Expected: 4 PASS.

---

### Task 9: CardGridWidget + tests

**Files:**
- Create: `web/app/components/chat/widgets/CardGridWidget.tsx`
- Create: `web/app/components/chat/widgets/CardGridWidget.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// web/app/components/chat/widgets/CardGridWidget.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { CardGridWidget } from "./CardGridWidget";
import type { CardGridHint } from "./types";


const hint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick a field",
  options: [
    { value: "Marketing", label: "Marketing", description: "Brand & ads" },
    { value: "Economics", label: "Economics" },
  ],
};


describe("CardGridWidget", () => {
  test("renders title and option cards", () => {
    render(<CardGridWidget hint={hint} onSelect={() => {}} />);
    expect(screen.getByText("Pick a field")).toBeTruthy();
    expect(screen.getByText("Marketing")).toBeTruthy();
    expect(screen.getByText("Brand & ads")).toBeTruthy();
    expect(screen.getByText("Economics")).toBeTruthy();
  });

  test("clicking an option fires onSelect with field_name/value/label", () => {
    const onSelect = vi.fn();
    render(<CardGridWidget hint={hint} onSelect={onSelect} />);
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).toHaveBeenCalledWith("field", "Marketing", "Marketing");
  });

  test("disabled prevents click", () => {
    const onSelect = vi.fn();
    render(<CardGridWidget hint={hint} onSelect={onSelect} disabled />);
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).not.toHaveBeenCalled();
  });

  test("data-testid uses field_name", () => {
    render(<CardGridWidget hint={hint} onSelect={() => {}} />);
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/widgets/CardGridWidget.tsx
"use client";

import { CardGridHint, WidgetSelectHandler } from "./types";


// Map columns count to static Tailwind class strings. Tailwind's JIT doesn't
// pick up dynamically-computed class names, so we enumerate the supported values.
const COLUMN_CLASSES: Record<number, string> = {
  2: "grid-cols-1 sm:grid-cols-2",
  3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3",
  4: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4",
};


export function CardGridWidget({
  hint,
  onSelect,
  disabled,
}: {
  hint: CardGridHint;
  onSelect: WidgetSelectHandler;
  disabled?: boolean;
}) {
  const columnClass = COLUMN_CLASSES[hint.columns ?? 3] ?? COLUMN_CLASSES[3];
  return (
    <div
      className="mt-3 rounded-lg border border-gray-200 bg-white p-3"
      data-testid={`card-grid-${hint.field_name}`}
    >
      <div className="text-xs font-semibold text-gray-700 mb-2">{hint.title}</div>
      <div className={`grid gap-2 ${columnClass}`}>
        {hint.options.map(opt => (
          <button
            key={opt.value}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(hint.field_name, opt.value, opt.label)}
            data-testid={`card-${opt.value}`}
            className="text-left rounded-md border border-gray-200 px-3 py-2 hover:border-purple-400 hover:bg-purple-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <div className="text-sm font-medium text-gray-900">{opt.label}</div>
            {opt.description && (
              <div className="text-xs text-gray-500 mt-0.5 line-clamp-2">{opt.description}</div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- widgets/CardGridWidget
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/CardGridWidget.tsx web/app/components/chat/widgets/CardGridWidget.test.tsx
git commit -m "feat(web): CardGridWidget component"
```
Expected: 4 PASS.

---

### Task 10: WidgetRenderer + tests

**Files:**
- Create: `web/app/components/chat/widgets/WidgetRenderer.tsx`
- Create: `web/app/components/chat/widgets/WidgetRenderer.test.tsx`

- [ ] **Step 1: Write the failing tests**

```typescript
// web/app/components/chat/widgets/WidgetRenderer.test.tsx
import { describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";
import { WidgetRenderer } from "./WidgetRenderer";
import type { CardGridHint } from "./types";


const cardGridHint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "x", label: "X" }],
};


describe("WidgetRenderer", () => {
  test("dispatches card_grid to CardGridWidget", () => {
    render(<WidgetRenderer hint={cardGridHint} onSelect={() => {}} />);
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });

  test("returns null for unknown widget_type (forward-compat)", () => {
    const { container } = render(
      <WidgetRenderer
        hint={{ widget_type: "future_widget" } as never}
        onSelect={() => {}}
      />,
    );
    expect(container.innerHTML).toBe("");
  });

  test("forwards disabled prop", () => {
    render(<WidgetRenderer hint={cardGridHint} onSelect={() => {}} disabled />);
    const btn = screen.getByTestId("card-x");
    expect(btn).toBeDisabled();
  });
});
```

- [ ] **Step 2: Implement**

```typescript
// web/app/components/chat/widgets/WidgetRenderer.tsx
"use client";

import { CardGridWidget } from "./CardGridWidget";
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
    default:
      return null;
  }
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- widgets/WidgetRenderer
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/widgets/WidgetRenderer.tsx web/app/components/chat/widgets/WidgetRenderer.test.tsx
git commit -m "feat(web): WidgetRenderer dispatch component"
```
Expected: 3 PASS.

---

## Phase E — Frontend integration

### Task 11: useChat — collect tool_calls events

**Files:**
- Modify: `web/app/components/chat/hooks/useChat.ts`
- Modify: `web/app/components/chat/hooks/useChat.test.tsx`

- [ ] **Step 1: Add the failing test**

Append to `web/app/components/chat/hooks/useChat.test.tsx`:

```typescript
test("collects tool_calls SSE event into streamingToolCalls", async () => {
  server.use(
    http.get("/api/v1/threads/t1/messages", () => HttpResponse.json([])),
    http.post("/api/v1/threads/t1/messages", () => streamResponse([
      'data: {"type":"token","text":"Pick a field"}\n\n',
      'data: {"type":"tool_calls","payload":{"widget_type":"card_grid","field_name":"field","title":"Pick","options":[],"columns":3}}\n\n',
      'data: {"type":"done"}\n\n',
    ])),
  );

  const { result } = renderHook(() => useChat("t1"), { wrapper });
  await waitFor(() => expect(result.current.messages).toEqual([]));

  await act(async () => {
    await result.current.send("hello");
  });

  expect(result.current.streamingToolCalls).toMatchObject({
    widget_type: "card_grid",
    field_name: "field",
  });
});
```

- [ ] **Step 2: Run — should fail**

```bash
cd web && npm test -- useChat
```
Expected: FAIL (`streamingToolCalls` doesn't exist).

- [ ] **Step 3: Update useChat.ts**

Modify `web/app/components/chat/hooks/useChat.ts`. Add the import + update Message type + return value:

```typescript
import type { WidgetHint } from "../widgets/types";


export type Message = {
  id: number;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  module_tag?: string | null;
  tool_calls_json?: WidgetHint | null;   // NEW
  created_at: string;
};


export function useChat(threadId: string) {
  const stream = useStream();
  const { data: messages, mutate } = useSWR<Message[]>(
    `/threads/${threadId}/messages`,
    fetcher,
  );

  const streamingText = stream.state.events
    .filter(e => e.type === "token")
    .map(e => (e as unknown as { text: string }).text)
    .join("");

  // NEW: pull the latest tool_calls event (backend should only emit one per turn)
  const streamingToolCalls = (stream.state.events
    .filter(e => e.type === "tool_calls")
    .map(e => (e as unknown as { payload: WidgetHint }).payload)
    .at(-1)) ?? null;

  const send = async (text: string) => {
    const optimistic: Message = {
      id: -Date.now(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    void mutate([...(messages ?? []), optimistic], false);

    await stream.start(`/api/v1/threads/${threadId}/messages`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });

    void mutate();
  };

  return {
    messages: messages ?? [],
    streamingText,
    streamingToolCalls,                  // NEW
    inflight: stream.state.inflight,
    error: stream.state.error,
    send,
  };
}
```

- [ ] **Step 4: Run + commit**

```bash
cd web && npm test -- useChat
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/hooks/useChat.ts web/app/components/chat/hooks/useChat.test.tsx
git commit -m "feat(web): useChat exposes streamingToolCalls + tool_calls_json on Message"
```
Expected: existing + new PASS.

---

### Task 12: MessageBubble — render WidgetRenderer when toolCallsJson present

**Files:**
- Modify: `web/app/components/chat/MessageBubble.tsx`
- Modify: `web/app/components/chat/MessageBubble.test.tsx`

- [ ] **Step 1: Add the failing tests**

Append to `web/app/components/chat/MessageBubble.test.tsx`:

```typescript
import type { CardGridHint } from "./widgets/types";

const cardGridHint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick a field",
  options: [{ value: "Marketing", label: "Marketing" }],
};


describe("MessageBubble widget rendering", () => {
  test("renders widget when toolCallsJson present and onWidgetSelect provided", () => {
    render(
      <MessageBubble
        role="assistant"
        content="Pick a field"
        toolCallsJson={cardGridHint}
        onWidgetSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("card-grid-field")).toBeTruthy();
  });

  test("does not render widget when toolCallsJson absent", () => {
    render(<MessageBubble role="assistant" content="Hi" />);
    expect(screen.queryByTestId(/card-grid/)).toBeNull();
  });

  test("widgetDisabled prevents card clicks", () => {
    const onSelect = vi.fn();
    render(
      <MessageBubble
        role="assistant"
        content="Pick a field"
        toolCallsJson={cardGridHint}
        onWidgetSelect={onSelect}
        widgetDisabled
      />,
    );
    fireEvent.click(screen.getByTestId("card-Marketing"));
    expect(onSelect).not.toHaveBeenCalled();
  });
});
```

Also add `vi` and `fireEvent` to the existing imports at the top of the file if not already present.

- [ ] **Step 2: Run — should fail**

```bash
cd web && npm test -- MessageBubble
```
Expected: FAIL.

- [ ] **Step 3: Update MessageBubble.tsx**

Replace the existing component definition:

```typescript
// web/app/components/chat/MessageBubble.tsx
import { ReactNode } from "react";
import { WidgetRenderer } from "./widgets/WidgetRenderer";
import type { WidgetHint, WidgetSelectHandler } from "./widgets/types";


export type MessageBubbleProps = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  moduleTag?: string | null;
  toolCallsJson?: WidgetHint | null;     // NEW
  onWidgetSelect?: WidgetSelectHandler;  // NEW
  widgetDisabled?: boolean;              // NEW
  children?: ReactNode;
};


export function MessageBubble({
  role,
  content,
  moduleTag,
  toolCallsJson,
  onWidgetSelect,
  widgetDisabled,
  children,
}: MessageBubbleProps) {
  const isUser = role === "user";
  const isSystem = role === "system";

  return (
    <div data-role={role} className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={
          isUser
            ? "max-w-[70%] rounded-2xl rounded-br-sm bg-purple-600 text-white px-4 py-2"
            : isSystem
            ? "max-w-[70%] rounded-md bg-gray-100 text-gray-600 px-3 py-1 text-sm italic"
            : "max-w-[70%] rounded-2xl rounded-bl-sm bg-gray-50 text-gray-900 px-4 py-2 border border-gray-200"
        }
      >
        {moduleTag && !isUser && !isSystem && (
          <div className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">{moduleTag}</div>
        )}
        <div className="whitespace-pre-wrap">{content}</div>
        {toolCallsJson && onWidgetSelect && (
          <WidgetRenderer hint={toolCallsJson} onSelect={onWidgetSelect} disabled={widgetDisabled} />
        )}
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run + commit**

```bash
cd web && npm test -- MessageBubble
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/MessageBubble.tsx web/app/components/chat/MessageBubble.test.tsx
git commit -m "feat(web): MessageBubble renders WidgetRenderer when toolCallsJson present"
```
Expected: existing + 3 new PASS.

---

### Task 13: MessageList — forward onWidgetSelect + widgetDisabled

**Files:**
- Modify: `web/app/components/chat/MessageList.tsx`
- Modify: `web/app/components/chat/MessageList.test.tsx`

- [ ] **Step 1: Add the failing test**

Append to `web/app/components/chat/MessageList.test.tsx`:

```typescript
import type { CardGridHint } from "./widgets/types";

const hint: CardGridHint = {
  widget_type: "card_grid",
  field_name: "field",
  title: "Pick",
  options: [{ value: "Marketing", label: "Marketing" }],
};


describe("MessageList widget integration", () => {
  test("widget on the LAST assistant message is enabled", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
    ];
    const onWidgetSelect = vi.fn();
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} onWidgetSelect={onWidgetSelect} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).not.toBeDisabled();
  });

  test("widget on a NON-last message is disabled", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
      { id: 2, role: "user" as const, content: "I'd like to study Marketing.", created_at: "2026-05-27" },
    ];
    render(<MessageList messages={messages} streamingText="" streamingModuleTag={null} onWidgetSelect={() => {}} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).toBeDisabled();
  });

  test("widget on last message is disabled while streaming", () => {
    const messages = [
      { id: 1, role: "assistant" as const, content: "Pick", created_at: "2026-05-27",
        tool_calls_json: hint },
    ];
    render(<MessageList messages={messages} streamingText="thinking…" streamingModuleTag={null} onWidgetSelect={() => {}} />);
    const card = screen.getByTestId("card-Marketing");
    expect(card).toBeDisabled();
  });
});
```

- [ ] **Step 2: Update MessageList.tsx**

```typescript
// web/app/components/chat/MessageList.tsx
"use client";

import { useEffect, useRef } from "react";
import { MessageBubble } from "./MessageBubble";
import { StreamingBubble } from "./StreamingBubble";
import type { Message } from "./hooks/useChat";
import type { WidgetSelectHandler } from "./widgets/types";


export function MessageList({
  messages,
  streamingText,
  streamingModuleTag,
  onWidgetSelect,                          // NEW (optional)
}: {
  messages: Message[];
  streamingText: string;
  streamingModuleTag: string | null;
  onWidgetSelect?: WidgetSelectHandler;
}) {
  const endRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth" });
  }, [messages.length, streamingText]);

  const isStreaming = Boolean(streamingText);

  return (
    <div className="flex-1 overflow-y-auto px-6 py-4 bg-white">
      {messages.map((m, idx) => {
        const isLast = idx === messages.length - 1;
        const widgetDisabled = !isLast || isStreaming;
        return (
          <MessageBubble
            key={m.id}
            role={m.role}
            content={m.content}
            moduleTag={m.module_tag}
            toolCallsJson={m.tool_calls_json}
            onWidgetSelect={onWidgetSelect}
            widgetDisabled={widgetDisabled}
          />
        );
      })}
      {streamingText && (
        <StreamingBubble text={streamingText} moduleTag={streamingModuleTag} />
      )}
      <div ref={endRef} />
    </div>
  );
}
```

- [ ] **Step 3: Run + commit**

```bash
cd web && npm test -- MessageList
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/MessageList.tsx web/app/components/chat/MessageList.test.tsx
git commit -m "feat(web): MessageList forwards onWidgetSelect + computes widgetDisabled"
```
Expected: existing + 3 new PASS.

---

### Task 14: ChatPane — wire onWidgetSelect

**Files:**
- Modify: `web/app/components/chat/ChatPane.tsx`

- [ ] **Step 1: Update ChatPane.tsx**

Inside the existing `ChatPane` component, add the handler and pass it to `MessageList`. The relevant additions:

Top of the file, in imports:
```typescript
import { synthesizeWidgetSelection } from "./widgets/synthesize";
import type { WidgetSelectHandler } from "./widgets/types";
```

Inside the component (before the `return`):
```typescript
  const onWidgetSelect: WidgetSelectHandler = (fieldName, value, label) => {
    const text = synthesizeWidgetSelection(fieldName, value, label);
    void send(text);
  };
```

Update the existing `<MessageList ...>` JSX to include the new prop:
```typescript
      <MessageList
        messages={messages}
        streamingText={inflight ? streamingText : ""}
        streamingModuleTag={null}
        onWidgetSelect={onWidgetSelect}    /* NEW */
      />
```

- [ ] **Step 2: Smoke-test the build**

```bash
cd web && npm run build 2>&1 | tail -10
```
Expected: build succeeds with no TS errors.

- [ ] **Step 3: Run the full chat test surface to verify no regressions**

```bash
cd web && npm test -- ChatPane MessageList MessageBubble useChat
```
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add web/app/components/chat/ChatPane.tsx
git commit -m "feat(web): ChatPane wires onWidgetSelect through to MessageList"
```

---

## Phase F — Integration

### Task 15: ChatPane click-to-send integration test

**Files:**
- Modify: `web/app/components/chat/ChatPane.test.tsx`

- [ ] **Step 1: Append the integration test**

Append to `web/app/components/chat/ChatPane.test.tsx`:

```typescript
describe("ChatPane widget click integration", () => {
  test("clicking a card synthesizes message and POSTs it", async () => {
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
          content: "Which field is your research in?",
          created_at: "2026-05-27T00:00:00Z",
          tool_calls_json: {
            widget_type: "card_grid",
            field_name: "field",
            title: "Pick a field",
            options: [
              { value: "Marketing", label: "Marketing", description: "" },
              { value: "Economics", label: "Economics", description: "" },
            ],
            columns: 3,
          },
        },
      ])),
      http.post("/api/v1/threads/t1/messages", async ({ request }) => {
        capturedBody = await request.json();
        return streamResponse([
          'data: {"type":"token","text":"Got it."}\n\n',
          'data: {"type":"done"}\n\n',
        ]);
      }),
    );

    render(<ChatPane projectId="p1" threadId="t1" />);

    // The widget renders from the existing message
    await waitFor(() => expect(screen.getByTestId("card-Marketing")).toBeTruthy());

    fireEvent.click(screen.getByTestId("card-Marketing"));

    // The frontend should POST with the synthesized message
    await waitFor(() => expect(capturedBody?.text).toBe("I'd like to study Marketing."));
  });
});
```

- [ ] **Step 2: Run + commit**

```bash
cd web && npm test -- ChatPane
cd /Users/caonguyenvan/project/dothesis
git add web/app/components/chat/ChatPane.test.tsx
git commit -m "test(web): ChatPane widget integration — click → synthesized POST body"
```
Expected: PASS.

---

### Task 16: Backend round-trip — synthesized sentence → _extract_answer

**Files:**
- Modify: `orchestrator/tests/agents/test_m1_widgets.py` (append a round-trip test)

- [ ] **Step 1: Append the round-trip test**

Append to `orchestrator/tests/agents/test_m1_widgets.py`:

```python
def test_synthesized_field_sentence_extracts_to_value(monkeypatch):
    """The synthesized sentence 'I'd like to study Marketing.' should
    extract to the value 'Marketing' via ModuleAgent._extract_answer."""
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    from orchestrator.agents.m1_topic import M1Agent

    # Stub the LLM to behave like the real extractor: respond with
    # {"field": "field", "value": "Marketing"} when fed the synthesized text.
    fake = MagicMock()
    fake.invoke.return_value.content = '{"field": "field", "value": "Marketing"}'
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    state = {
        "messages": [HumanMessage(content="I'd like to study Marketing.")],
        "current_module": "M1",
        "mode": "interactive",
    }
    extracted = agent._extract_answer(state, "field")
    assert extracted == "Marketing"


def test_synthesized_research_type_extracts_to_value(monkeypatch):
    """'I'll use a qualitative approach.' → 'qualitative'."""
    from unittest.mock import MagicMock
    from langchain_core.messages import HumanMessage
    from orchestrator.agents.m1_topic import M1Agent

    fake = MagicMock()
    fake.invoke.return_value.content = '{"field": "research_type", "value": "qualitative"}'
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    state = {
        "messages": [HumanMessage(content="I'll use a qualitative approach.")],
        "current_module": "M1",
        "mode": "interactive",
    }
    extracted = agent._extract_answer(state, "research_type")
    assert extracted == "qualitative"
```

- [ ] **Step 2: Run + commit**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate
python -m pytest orchestrator/tests/agents/test_m1_widgets.py -v
git add orchestrator/tests/agents/test_m1_widgets.py
git commit -m "test(orchestrator): round-trip — synthesized sentence → _extract_answer"
```
Expected: all PASS.

---

## Phase G — Wrap-up

### Task 17: M1 prompt update + regression + roadmap flip

**Files:**
- Modify: `orchestrator/prompts/m1.md`
- Modify: `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`

- [ ] **Step 1: Update M1 prompt**

Read the existing `orchestrator/prompts/m1.md`. Append (or insert near the bottom, before any "Tools" section) a short paragraph:

```markdown

## When a card-grid widget appears

When the next field you're asking about (`field` or `research_type`) is shown to the user as clickable cards, your text should invite picking — for example: *"Which field is your research in? Pick one of the cards below, or type your own."* — rather than asking the user to type the answer.
```

- [ ] **Step 2: Run all three test suites to verify no regressions**

```bash
cd /Users/caonguyenvan/project/dothesis && source api/.venv/bin/activate

# Orchestrator
echo "=== orchestrator ==="
python -m pytest orchestrator/tests/ -m "integration or not integration" -q --no-header 2>&1 | tail -3

# API
echo "=== api ==="
cd api && python -m pytest tests/ -q --no-header 2>&1 | tail -3
cd ..

# Web
echo "=== web ==="
cd web && npm test 2>&1 | tail -3
```

Expected:
- Orchestrator: same as baseline (117+ from SP2 era), no NEW failures.
- API: same baseline failures (52ish) + new tests passing, no NEW failures.
- Web: SP7 baseline + ~15 new tests, all passing.

If any new failures surface that aren't in the baseline, document them and fix before continuing.

- [ ] **Step 3: Flip roadmap status**

Edit `docs/superpowers/2026-05-26-platform-pivot-roadmap.md`. Find:

```
## Sub-project 3 — M1 Topic Discovery card-grid UX ⬜
```

Replace with:

```
## Sub-project 3 — M1 Topic Discovery card-grid UX ✅

**Status:** Shipped 2026-05-27 (branch `feat/sp3-m1-card-grid`; widget infra + FieldPicker + ResearchTypePicker)
```

Find the ASCII sub-project map. Update the "3. M1 topic" label to add "✅":

```
3. M1 topic ✅
   (card-grid UX)
```

Find the Status log section. Append:

```
| 2026-05-27 | 3 | ⬜ → ✅ | M1 card-grid widgets shipped — widget infra + FieldPicker + ResearchTypePicker; pattern ready for SP4-SP6 |
```

- [ ] **Step 4: Commit**

```bash
cd /Users/caonguyenvan/project/dothesis
git add orchestrator/prompts/m1.md docs/superpowers/2026-05-26-platform-pivot-roadmap.md
git commit -m "docs+orchestrator: SP3 shipped — M1 prompt invites picking + roadmap flip to ✅"
```

---

## Done criteria checklist

- [ ] All 17 tasks committed in order
- [ ] All web tests pass (`cd web && npm test`)
- [ ] All orchestrator tests pass (no regressions vs baseline)
- [ ] API tests show only baseline failures + new tests passing
- [ ] `npm run build` succeeds in `web/`
- [ ] End-to-end manual smoke (optional): start `./dev.sh`, hit `/chat`, click a card, verify the synthesized message appears and the next widget renders
- [ ] Roadmap flipped to ✅ for SP3
- [ ] Schema-drift test (`widgets/types.test.ts`) catches a deliberately-broken Pydantic↔TS mismatch (try removing a field from the backend Pydantic model; assert the TS build fails; revert)

## What's next after SP3 ships

SP4 (M3 Research Design multi-method) is next. SP4 adds new variants to the `WidgetHint` discriminated union (e.g. `methodology_picker`, `model_builder`) following the exact pattern this plan established. The card_grid variant from SP3 is reused for one-or-more M3 fields (paradigm choice, design type within paradigm); new variants land alongside without touching SP3 code.
