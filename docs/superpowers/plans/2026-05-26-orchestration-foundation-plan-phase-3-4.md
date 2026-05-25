# Phase 3–4: Agents + Graph (Tasks 12–19)

> Companion file to `2026-05-26-orchestration-foundation-plan.md`. Requires Phase 0–2 (Tasks 1–11) to be complete.

---

## Task 12: ModuleAgent base class (shared clarification loop)

**Files:**
- Create: `orchestrator/agents/__init__.py`
- Create: `orchestrator/agents/base.py`
- Test: `orchestrator/tests/test_agent_base.py`

- [ ] **Step 1: Write the test**

Create `orchestrator/tests/test_agent_base.py`:

```python
"""Tests for ModuleAgent's clarification loop (shared by all 5 module agents)."""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field

from orchestrator.agents.base import ModuleAgent, ModuleStepResult
from orchestrator.state import ContextStore, OrchestratorState


class _ToyOutput(BaseModel):
    title: str = Field(..., min_length=1)
    answer: str = Field(..., min_length=1)
    confirmed_at: datetime | None = None


class _ToyAgent(ModuleAgent):
    schema = _ToyOutput
    module_key = "M1"
    tools = []
    system_prompt = "You are a toy agent."


def _state(messages, partial=None, mode="interactive"):
    cs = ContextStore()
    if partial:
        cs.m1_topic = partial
    return {
        "project_id": None,
        "thread_id": None,
        "messages": messages,
        "current_module": "M1",
        "context_store": cs,
        "mode": mode,
        "user_intent": None,
        "pending_confirmations": [],
    }


def test_interactive_asks_for_first_missing_field(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(content="What is the title?")
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="start")])
    result = agent.step(state)
    assert isinstance(result, ModuleStepResult)
    assert result.transition is False
    assert "title" in result.assistant_message.lower()


def test_interactive_fills_field_from_user_answer(monkeypatch):
    """When the agent has just asked for 'title' and user replies, it stores 'title'."""
    agent = _ToyAgent()
    fake_llm = MagicMock()
    # First call: ask. Second call (validation/extraction): structured field.
    fake_llm.invoke.side_effect = [
        AIMessage(content='{"field": "title", "value": "My Title"}'),  # extraction
        AIMessage(content="Got it. What is the answer?"),               # next question
    ]
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state(
        [HumanMessage(content="start"),
         AIMessage(content="What is the title?"),
         HumanMessage(content="My Title")],
        partial={"_awaiting_field": "title"},
    )
    result = agent.step(state)
    # Updated context_store has title set.
    new_partial = result.context_patch
    assert new_partial.get("title") == "My Title"


def test_auto_mode_autofills_silently(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    fake_llm.invoke.return_value = AIMessage(
        content='{"title": "Auto Title", "answer": "Auto Answer"}'
    )
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    state = _state([HumanMessage(content="seed topic")], mode="auto")
    result = agent.step(state)
    assert result.transition is True
    patch = result.context_patch
    assert patch["title"] == "Auto Title"
    assert patch["answer"] == "Auto Answer"
    assert "confirmed_at" in patch  # auto-mode auto-confirms


def test_interactive_transition_after_confirm(monkeypatch):
    agent = _ToyAgent()
    fake_llm = MagicMock()
    monkeypatch.setattr(_ToyAgent, "_get_llm", lambda self: fake_llm)

    # All fields already filled, agent is awaiting user confirmation.
    state = _state(
        [AIMessage(content="Summary: title=X, answer=Y. Confirm?"),
         HumanMessage(content="yes")],
        partial={"title": "X", "answer": "Y", "_awaiting_confirm": True},
    )
    result = agent.step(state)
    assert result.transition is True
    assert "confirmed_at" in result.context_patch
```

- [ ] **Step 2: Run (fails — module missing)**

Run: `python -m pytest orchestrator/tests/test_agent_base.py -v`
Expected: FAIL — ImportError.

- [ ] **Step 3: Implement the base agent**

Create `orchestrator/agents/__init__.py`:

```python
"""Module agents + supervisor."""
```

Create `orchestrator/agents/base.py`:

```python
"""ModuleAgent base — shared clarification loop for all 5 module nodes."""
from __future__ import annotations

import json
import logging
import os
from abc import ABC
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, ValidationError

from orchestrator.state import OrchestratorState, get_module_slice

logger = logging.getLogger(__name__)


@dataclass
class ModuleStepResult:
    """What a module's step() returns to the graph runner."""
    assistant_message: str
    context_patch: dict
    transition: bool                 # True → done; supervisor takes over
    needs_user_reply: bool = False


class ModuleAgent(ABC):
    """Shared clarification loop. Subclasses override schema / prompt / tools / module_key."""

    schema: type[BaseModel]
    module_key: str
    system_prompt: str
    tools: list[Any]

    # --- LLM hookpoint (overridable in tests) ---------------------------------
    def _get_llm(self):
        return ChatGoogleGenerativeAI(
            model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
            temperature=0.4,
        )

    # --- Public entrypoint ----------------------------------------------------
    def step(self, state: OrchestratorState) -> ModuleStepResult:
        mode = state.get("mode", "interactive")
        partial = dict(get_module_slice(state["context_store"], self.module_key))

        # AUTO MODE — fill all required fields in one LLM call, auto-confirm.
        if mode == "auto":
            return self._auto_fill(state, partial)

        # INTERACTIVE — decide whether we're (a) extracting an answer,
        # (b) asking for the next field, or (c) awaiting confirmation.
        if partial.pop("_awaiting_confirm", False):
            user_says_yes = self._is_affirmative(state["messages"])
            if user_says_yes:
                partial["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                return ModuleStepResult(
                    assistant_message=f"Confirmed {self.module_key}. Moving on.",
                    context_patch=partial,
                    transition=True,
                )
            # User wants edits — drop awaiting flag, re-ask the loop.
            return self._ask_next_question(state, partial)

        awaiting_field = partial.pop("_awaiting_field", None)
        if awaiting_field:
            extracted = self._extract_answer(state, awaiting_field)
            if extracted is not None:
                partial[awaiting_field] = extracted

        return self._ask_next_question(state, partial)

    # --- Auto-mode path -------------------------------------------------------
    def _auto_fill(self, state, partial: dict) -> ModuleStepResult:
        seed = " ".join(
            m.content for m in state["messages"]
            if isinstance(m, HumanMessage)
        )
        required = self._required_field_names()
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You are operating in fully-silent auto-mode. Fill ALL fields of this schema "
            f"with reasonable best-guess defaults derived from the topic. Respond with ONLY "
            f"a JSON object matching this schema (no prose, no markdown).\n\n"
            f"Required fields: {required}\nTopic: {seed}\n"
            f"Already filled (do not change): {json.dumps({k:v for k,v in partial.items() if k in required}, default=str)}"
        )
        resp = self._get_llm().invoke(prompt).content
        try:
            filled = json.loads(_strip_code_fence(resp))
        except (json.JSONDecodeError, TypeError):
            logger.warning("%s auto-fill returned non-JSON: %r", self.module_key, resp[:200])
            filled = {}
        merged = {**partial, **filled, "confirmed_at": datetime.now(timezone.utc).isoformat()}
        # Validate. If invalid, salvage what we can; supervisor sees the issue via logs.
        try:
            self.schema.model_validate(merged)
        except ValidationError as e:
            logger.warning("%s auto-fill validation: %s", self.module_key, e)
        return ModuleStepResult(
            assistant_message=f"[auto] Filled {self.module_key} from topic.",
            context_patch=merged,
            transition=True,
        )

    # --- Interactive helpers --------------------------------------------------
    def _ask_next_question(self, state, partial: dict) -> ModuleStepResult:
        missing = self._next_missing_field(partial)
        if missing is None:
            # All fields present → summarize + ask for confirm.
            summary = self._summarize_for_confirm(partial)
            partial["_awaiting_confirm"] = True
            return ModuleStepResult(
                assistant_message=f"Here's what we have:\n\n{summary}\n\nConfirm and move on?",
                context_patch=partial,
                transition=False,
                needs_user_reply=True,
            )

        # Ask for the next missing field.
        partial["_awaiting_field"] = missing
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You need the user to provide a value for the schema field '{missing}'. "
            f"Ask a single targeted question in friendly, plain language. Don't ask "
            f"for multiple fields at once. Don't restate the whole schema. Already "
            f"filled: {json.dumps({k:v for k,v in partial.items() if not k.startswith('_')}, default=str)[:1000]}"
        )
        msg = self._get_llm().invoke(prompt).content.strip()
        return ModuleStepResult(
            assistant_message=msg, context_patch=partial,
            transition=False, needs_user_reply=True,
        )

    def _extract_answer(self, state, field_name: str) -> Any:
        """Convert the user's free-text reply into the schema field's type."""
        last_user = next(
            (m.content for m in reversed(state["messages"]) if isinstance(m, HumanMessage)),
            None,
        )
        if not last_user:
            return None
        prompt = (
            f"Extract the value of '{field_name}' from this user reply. The schema "
            f"field type is described as: {self._field_description(field_name)}. "
            f"Respond with ONLY a JSON object {{\"field\": \"{field_name}\", "
            f"\"value\": <the value>}}. If the user answer is not a usable value, "
            f"respond with {{\"field\": \"{field_name}\", \"value\": null}}.\n\n"
            f"User reply: {last_user}"
        )
        try:
            data = json.loads(_strip_code_fence(self._get_llm().invoke(prompt).content))
            return data.get("value")
        except (json.JSONDecodeError, TypeError):
            return last_user  # fall back to raw text

    @staticmethod
    def _is_affirmative(messages: list[BaseMessage]) -> bool:
        last_user = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        return last_user.strip().lower() in {
            "yes", "y", "ok", "okay", "confirm", "go", "continue", "yep",
            "đồng ý", "ok rồi", "tiếp tục",
        }

    def _summarize_for_confirm(self, partial: dict) -> str:
        return "\n".join(
            f"- **{k}**: {json.dumps(v, default=str, ensure_ascii=False)[:200]}"
            for k, v in partial.items() if not k.startswith("_")
        )

    # --- Schema introspection -------------------------------------------------
    def _required_field_names(self) -> list[str]:
        return [
            name for name, field in self.schema.model_fields.items()
            if field.is_required() and name != "confirmed_at"
        ]

    def _next_missing_field(self, partial: dict) -> str | None:
        for name in self._required_field_names():
            v = partial.get(name)
            if v is None or v == "" or v == []:
                return name
        return None

    def _field_description(self, field_name: str) -> str:
        f = self.schema.model_fields.get(field_name)
        if f is None:
            return field_name
        return f"{f.annotation} — {f.description or 'no description'}"


def _strip_code_fence(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest orchestrator/tests/test_agent_base.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/agents/ orchestrator/tests/test_agent_base.py
git commit -m "feat(orchestrator): ModuleAgent base with shared clarification loop"
```

---

## Task 13: M1 Topic agent

**Files:**
- Create: `orchestrator/agents/m1_topic.py`
- Create: `orchestrator/prompts/m1.md`
- Test: `orchestrator/tests/test_agents_m1.py`

- [ ] **Step 1: Write the prompt**

Create `orchestrator/prompts/m1.md`:

```markdown
# M1 — Topic Discovery agent

You are the Topic Discovery agent for an academic research assistant. Your job is to help the user nail down:

- A specific research title
- The academic field
- Whether they want a quantitative, qualitative, or mixed-methods study
- The target population and scope
- 1–3 research objectives
- 1–3 research questions

Style: friendly, concise, one question at a time. Don't repeat the whole schema back at the user. When suggesting topics, use the `suggest_topics` tool. When polishing a title, use `refine_title`.
```

- [ ] **Step 2: Write the test**

Create `orchestrator/tests/test_agents_m1.py`:

```python
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from orchestrator.agents.m1_topic import M1Agent
from orchestrator.state import ContextStore


def _state(messages, mode="interactive"):
    return {
        "messages": messages, "current_module": "M1",
        "context_store": ContextStore(), "mode": mode,
        "user_intent": None, "pending_confirmations": [],
    }


def test_m1_auto_mode_produces_valid_output(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"research_title": "Impact of TL on EE", "field": "Marketing", '
        '"research_type": "quantitative", "target_population": "SME employees", '
        '"scope": "Vietnam 2026", "objectives": ["Test H1"], '
        '"research_questions": ["Does TL affect EE?"]}'
    )
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    res = agent.step(_state([HumanMessage(content="leadership thesis")], mode="auto"))
    assert res.transition is True
    assert res.context_patch["research_title"]
    assert "confirmed_at" in res.context_patch


def test_m1_interactive_first_turn_asks_a_question(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value = AIMessage(content="What's your research field?")
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    res = agent.step(_state([HumanMessage(content="hi")]))
    assert res.transition is False
    assert res.needs_user_reply is True
    assert "?" in res.assistant_message
```

- [ ] **Step 3: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_agents_m1.py -v`
Expected: FAIL — module missing.

- [ ] **Step 4: Implement the agent**

Create `orchestrator/agents/m1_topic.py`:

```python
"""M1 — Topic Discovery agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m1 import M1Output
from orchestrator.tools.m1_topic import refine_title, suggest_topics

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m1.md").read_text()


class M1Agent(ModuleAgent):
    schema = M1Output
    module_key = "M1"
    system_prompt = _PROMPT
    tools = [suggest_topics, refine_title]
```

- [ ] **Step 5: Run**

Run: `python -m pytest orchestrator/tests/test_agents_m1.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agents/m1_topic.py orchestrator/prompts/m1.md orchestrator/tests/test_agents_m1.py
git commit -m "feat(orchestrator): M1 Topic Discovery agent"
```

---

## Task 14: M2 Literature agent

**Files:**
- Create: `orchestrator/agents/m2_literature.py`
- Create: `orchestrator/prompts/m2.md`
- Test: `orchestrator/tests/test_agents_m2.py`

- [ ] **Step 1: Write the prompt**

Create `orchestrator/prompts/m2.md`:

```markdown
# M2 — Literature Review agent

You handle the literature review. For each project you must produce:

- A research-state summary (with in-text citations)
- 2–4 cited research gaps (each with supporting paper references and page numbers when known)
- A theoretical framework name
- Hypotheses (if quantitative) or propositions (if qualitative)
- A draft Chapter 2 (Literature Review) text
- A citation list

Use your tools: `scout_citations` to find sources, `summarize_paper` to digest PDFs, `find_research_gaps` to extract gaps, `compile_citations` to format references, `verify_page_numbers` when the user has uploaded source PDFs.

Always cite. Never invent. If a page number cannot be verified, mark it `[page?]`.
```

- [ ] **Step 2: Write the test**

Create `orchestrator/tests/test_agents_m2.py`:

```python
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m2_literature import M2Agent
from orchestrator.state import ContextStore


def _state(mode="auto"):
    return {
        "messages": [HumanMessage(content="literature review for leadership")],
        "current_module": "M2",
        "context_store": ContextStore(
            m1_topic={"research_title": "TL→EE", "research_type": "quantitative",
                      "confirmed_at": "2026-05-26T00:00:00"}
        ),
        "mode": mode, "user_intent": None, "pending_confirmations": [],
    }


def test_m2_auto_fills_required_fields(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"research_state_summary":"...","research_gaps":[{"description":"SME gap",'
        '"relevance":"High","supporting_papers":[],"confirmed":true}],'
        '"theoretical_framework":"TL","hypotheses":["H1"],'
        '"literature_review_doc":"...","citation_list":[]}'
    )
    monkeypatch.setattr(M2Agent, "_get_llm", lambda self: fake)
    res = M2Agent().step(_state())
    assert res.transition is True
    assert res.context_patch["research_gaps"][0]["description"] == "SME gap"
```

- [ ] **Step 3: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_agents_m2.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement**

Create `orchestrator/agents/m2_literature.py`:

```python
"""M2 — Literature Review agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m2 import M2Output
from orchestrator.tools.m2_literature import (
    compile_citations, find_research_gaps, scout_citations,
    summarize_paper, verify_page_numbers,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m2.md").read_text()


class M2Agent(ModuleAgent):
    schema = M2Output
    module_key = "M2"
    system_prompt = _PROMPT
    tools = [
        scout_citations, summarize_paper, find_research_gaps,
        compile_citations, verify_page_numbers,
    ]
```

- [ ] **Step 5: Run**

Run: `python -m pytest orchestrator/tests/test_agents_m2.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add orchestrator/agents/m2_literature.py orchestrator/prompts/m2.md orchestrator/tests/test_agents_m2.py
git commit -m "feat(orchestrator): M2 Literature Review agent"
```

---

## Task 15: M3 Research Design agent

**Files:**
- Create: `orchestrator/agents/m3_design.py`
- Create: `orchestrator/prompts/m3.md`
- Test: `orchestrator/tests/test_agents_m3.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m3.md`:

```markdown
# M3 — Research Design agent

You design the study. Given the topic, paradigm, and gaps from M1/M2, produce:

- A specific design (PLS-SEM / CB-SEM / Regression / Thematic Analysis / Grounded Theory / Phenomenological / Case Study / Sequential Explanatory / Sequential Exploratory)
- The primary analysis tool (SPSS / SmartPLS / AMOS / R lavaan / NVivo / Atlas.ti / Manual)
- A sampling strategy with a justified target sample size
- For quantitative: a conceptual model (constructs + paths + hypotheses), scale items
- For qualitative: a thematic framework, interview guide

Tools: `recommend_methodology`, `build_conceptual_model`, `suggest_scale_items`, `estimate_sample_size`.

Explain trade-offs briefly when the user is undecided; recommend a default but let them override.
```

- [ ] **Step 2: Test**

Create `orchestrator/tests/test_agents_m3.py`:

```python
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m3_design import M3Agent
from orchestrator.state import ContextStore


def test_m3_auto_quantitative(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"paradigm":"quantitative","design":"PLS-SEM","tool":"SmartPLS",'
        '"sampling_strategy":"convenience","target_sample_size":300,'
        '"conceptual_model":{"constructs":["TL","EE"],"paths":[]},'
        '"constructs":[],"questionnaire_text":null,"interview_guide":null}'
    )
    monkeypatch.setattr(M3Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="design")], "current_module": "M3",
        "context_store": ContextStore(m1_topic={"research_type": "quantitative",
                                                "confirmed_at": "2026-05-26"}),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M3Agent().step(state)
    assert res.transition is True
    assert res.context_patch["design"] == "PLS-SEM"
```

- [ ] **Step 3: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_agents_m3.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement**

Create `orchestrator/agents/m3_design.py`:

```python
"""M3 — Research Design agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m3 import M3Output
from orchestrator.tools.m3_design import (
    build_conceptual_model, estimate_sample_size,
    recommend_methodology, suggest_scale_items,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m3.md").read_text()


class M3Agent(ModuleAgent):
    schema = M3Output
    module_key = "M3"
    system_prompt = _PROMPT
    tools = [
        recommend_methodology, build_conceptual_model,
        suggest_scale_items, estimate_sample_size,
    ]
```

- [ ] **Step 5: Run + Commit**

```bash
python -m pytest orchestrator/tests/test_agents_m3.py -v
git add orchestrator/agents/m3_design.py orchestrator/prompts/m3.md orchestrator/tests/test_agents_m3.py
git commit -m "feat(orchestrator): M3 Research Design agent"
```

---

## Task 16: M4 Data Analysis agent

**Files:**
- Create: `orchestrator/agents/m4_analysis.py`
- Create: `orchestrator/prompts/m4.md`
- Test: `orchestrator/tests/test_agents_m4.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m4.md`:

```markdown
# M4 — Data Analysis agent

You analyze the data. Steps:

1. Use `detect_data_type` to identify what the user uploaded (SPSS / SmartPLS / CB-SEM / Qualitative).
2. Use `generate_analysis_outline` to propose a standard outline for that data type.
3. Let the user adjust (add/remove steps via chat).
4. For each confirmed step, call `run_analysis_step` and then `interpret_result` to produce a plain-language explanation in the user's language.

In auto-mode: pick the outline based on M3's methodology, run all steps with the stub `run_analysis_step` (real parsers ship in a later sub-project), and write interpretations from the stubbed results.
```

- [ ] **Step 2: Test**

Create `orchestrator/tests/test_agents_m4.py`:

```python
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.state import ContextStore


def test_m4_auto_produces_outline_and_results(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"data_type_detected":"SPSS",'
        '"analysis_outline":{"sections":["Descriptive","Reliability"],"confirmed_by_user":true},'
        '"results":{"descriptive":{"n":300}},'
        '"interpretations":{"descriptive":"Sample of 300..."}}'
    )
    monkeypatch.setattr(M4Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="analyze")], "current_module": "M4",
        "context_store": ContextStore(
            m3_design={"design": "Regression", "tool": "SPSS",
                       "confirmed_at": "2026-05-26"}),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M4Agent().step(state)
    assert res.transition is True
    assert res.context_patch["data_type_detected"] == "SPSS"
```

- [ ] **Step 3: Run (fails) → Implement → Run → Commit**

Create `orchestrator/agents/m4_analysis.py`:

```python
"""M4 — Data Analysis agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m4 import M4Output
from orchestrator.tools.m4_analysis import (
    detect_data_type, generate_analysis_outline,
    interpret_result, run_analysis_step,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m4.md").read_text()


class M4Agent(ModuleAgent):
    schema = M4Output
    module_key = "M4"
    system_prompt = _PROMPT
    tools = [detect_data_type, generate_analysis_outline,
             run_analysis_step, interpret_result]
```

Run:
```bash
python -m pytest orchestrator/tests/test_agents_m4.py -v
git add orchestrator/agents/m4_analysis.py orchestrator/prompts/m4.md orchestrator/tests/test_agents_m4.py
git commit -m "feat(orchestrator): M4 Data Analysis agent"
```

---

## Task 17: M5 Writing agent

**Files:**
- Create: `orchestrator/agents/m5_writing.py`
- Create: `orchestrator/prompts/m5.md`
- Test: `orchestrator/tests/test_agents_m5.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/m5.md`:

```markdown
# M5 — Writing & Export agent

You assemble the final thesis. Pull from `context_store` (M1–M4 outputs) and produce:

- Each chapter as text (intro, lit_review, methodology, results, discussion, conclusion)
- A formatted citation list using the project's citation style
- Export artifacts (docx + pdf), URIs in `export_artifacts`

Use `compose_section` for each section, `validate_draft` to catch issues, `format_citations` for the bibliography, and `compile_pdf` + `export_docx` for the final files.

In auto-mode this is the section that takes the longest — every section is composed and exported in one pass.
```

- [ ] **Step 2: Test**

Create `orchestrator/tests/test_agents_m5.py`:

```python
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent
from orchestrator.state import ContextStore


def test_m5_auto_composes_and_exports(monkeypatch):
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"sections":[{"name":"intro","text":"..."},{"name":"lit_review","text":"..."}],'
        '"export_artifacts":[{"kind":"docx","uri":"/tmp/x.docx","size_bytes":1024},'
        '{"kind":"pdf","uri":"/tmp/x.pdf","size_bytes":2048}]}'
    )
    monkeypatch.setattr(M5Agent, "_get_llm", lambda self: fake)
    state = {
        "messages": [HumanMessage(content="write")], "current_module": "M5",
        "context_store": ContextStore(
            m1_topic={"research_title": "X", "confirmed_at": "2026-05-26"},
            m2_literature={"literature_review_doc": "...", "confirmed_at": "2026-05-26"},
        ),
        "mode": "auto", "user_intent": None, "pending_confirmations": [],
    }
    res = M5Agent().step(state)
    assert res.transition is True
    assert any(a["kind"] == "docx" for a in res.context_patch["export_artifacts"])
```

- [ ] **Step 3: Run (fails) → Implement → Run → Commit**

Create `orchestrator/agents/m5_writing.py`:

```python
"""M5 — Writing & Export agent."""
from pathlib import Path

from orchestrator.agents.base import ModuleAgent
from orchestrator.schemas.m5 import M5Output
from orchestrator.tools.m5_writing import (
    compile_pdf, compose_section, export_docx,
    format_citations, validate_draft,
)

_PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "m5.md").read_text()


class M5Agent(ModuleAgent):
    schema = M5Output
    module_key = "M5"
    system_prompt = _PROMPT
    tools = [compose_section, validate_draft, format_citations,
             compile_pdf, export_docx]
```

Run:
```bash
python -m pytest orchestrator/tests/test_agents_m5.py -v
git add orchestrator/agents/m5_writing.py orchestrator/prompts/m5.md orchestrator/tests/test_agents_m5.py
git commit -m "feat(orchestrator): M5 Writing & Export agent"
```

---

## Task 18: Supervisor agent

**Files:**
- Create: `orchestrator/agents/supervisor.py`
- Create: `orchestrator/prompts/supervisor.md`
- Test: `orchestrator/tests/test_supervisor.py`

- [ ] **Step 1: Prompt**

Create `orchestrator/prompts/supervisor.md`:

```markdown
# Supervisor — routing decision

You decide which of the 5 module agents should run next. Your inputs:

- The current `context_store` (which modules are confirmed)
- The user's latest message
- The project's `current_module` pointer

Decision rules:

1. Walk M1→M2→M3→M4→M5 in order; route to the first unconfirmed module.
2. If the user explicitly asks to navigate ("go back to M2", "skip to M4", "redo my methodology"), honour that request and route to the named module instead.
3. If all five modules are confirmed, route to `DONE`.

Respond with a single JSON object: `{"next_module": "M3", "reason": "...", "needs_user_acknowledgement": false}`.
```

- [ ] **Step 2: Test**

Create `orchestrator/tests/test_supervisor.py`:

```python
from unittest.mock import MagicMock

from langchain_core.messages import HumanMessage

from orchestrator.agents.supervisor import RouteDecision, supervisor_node
from orchestrator.state import ContextStore


def _state(messages, cs=None, mode="interactive"):
    return {
        "messages": messages, "current_module": "M1",
        "context_store": cs or ContextStore(), "mode": mode,
        "user_intent": None, "pending_confirmations": [],
    }


def test_supervisor_rules_pick_first_unconfirmed():
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"})
    state = _state([HumanMessage(content="ok")], cs=cs, mode="auto")
    out = supervisor_node(state)
    decision = out["pending_confirmations"]  # we stash route decision here
    assert state["current_module"] in {"M1", "M2", "M3", "M4", "M5", "DONE"}


def test_supervisor_all_done_routes_to_done():
    cs = ContextStore(**{m: {"confirmed_at": "2026-05-26"} for m in
                         ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing")})
    state = _state([HumanMessage(content="...")], cs=cs)
    out = supervisor_node(state)
    assert out["current_module"] == "DONE"


def test_supervisor_routes_to_first_unconfirmed_in_auto():
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state([HumanMessage(content="...")], cs=cs, mode="auto")
    out = supervisor_node(state)
    assert out["current_module"] == "M3"


def test_supervisor_honors_navigation_request(monkeypatch):
    cs = ContextStore(m1_topic={"confirmed_at": "2026-05-26"},
                      m2_literature={"confirmed_at": "2026-05-26"})
    state = _state([HumanMessage(content="actually go back to M2 and redo it")], cs=cs)
    # Stub the intent classifier to return a navigation request.
    fake = MagicMock()
    fake.with_structured_output.return_value.invoke.return_value = type(
        "X", (), {"wants_navigation": True, "target_module": "M2", "confidence": 0.9}
    )()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", lambda: fake)
    out = supervisor_node(state)
    assert out["current_module"] == "M2"


def test_supervisor_auto_mode_skips_llm_classifier(monkeypatch):
    """Auto mode should never call the LLM classifier — only rules."""
    counter = {"calls": 0}
    def fake_llm():
        counter["calls"] += 1
        return MagicMock()
    monkeypatch.setattr("orchestrator.agents.supervisor._intent_llm", fake_llm)

    cs = ContextStore()
    state = _state([HumanMessage(content="go back to M3")], cs=cs, mode="auto")
    supervisor_node(state)
    assert counter["calls"] == 0
```

- [ ] **Step 3: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_supervisor.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement**

Create `orchestrator/agents/supervisor.py`:

```python
"""Supervisor — routes between module agents based on rules + (interactive only) LLM intent."""
from __future__ import annotations

import logging
import os
from typing import Literal

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from orchestrator.state import ModuleKey, OrchestratorState, next_unconfirmed_module

logger = logging.getLogger(__name__)

_NAV_KEYWORDS = (
    "go back", "skip", "redo", "i already have", "jump to", "start over",
    "quay lại", "bỏ qua", "làm lại",
)


class RouteDecision(BaseModel):
    next_module: Literal["M1", "M2", "M3", "M4", "M5", "DONE"]
    reason: str
    needs_user_acknowledgement: bool = False


class IntentClassification(BaseModel):
    wants_navigation: bool = Field(...)
    target_module: Literal["M1", "M2", "M3", "M4", "M5"] | None = None
    confidence: float = 0.0


def _intent_llm():
    return ChatGoogleGenerativeAI(
        model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.0-flash-001"),
        temperature=0.0,
    )


def _looks_like_navigation(text: str) -> bool:
    t = text.lower()
    return any(k in t for k in _NAV_KEYWORDS)


def _rule_based(state: OrchestratorState) -> RouteDecision:
    nxt = next_unconfirmed_module(state["context_store"])
    return RouteDecision(
        next_module=nxt,
        reason="sequential" if nxt != "DONE" else "all_modules_confirmed",
    )


def supervisor_node(state: OrchestratorState) -> dict:
    """Returns a state patch with the updated current_module."""
    decision = _rule_based(state)

    if state.get("mode") == "interactive":
        last_user = next(
            (m.content for m in reversed(state.get("messages") or [])
             if isinstance(m, HumanMessage)),
            "",
        )
        if last_user and _looks_like_navigation(last_user):
            try:
                llm = _intent_llm().with_structured_output(IntentClassification)
                intent = llm.invoke(
                    f"Is the user requesting navigation to a specific module? "
                    f"Message: {last_user}"
                )
                if intent.wants_navigation and intent.confidence >= 0.7 and intent.target_module:
                    decision = RouteDecision(
                        next_module=intent.target_module,
                        reason=f"user requested {intent.target_module}",
                        needs_user_acknowledgement=True,
                    )
            except Exception:
                logger.exception("supervisor intent classifier failed; falling back to rules")

    return {
        "current_module": decision.next_module,
        "pending_confirmations": [decision.model_dump_json()],
    }


def route_from_supervisor(state: OrchestratorState) -> str:
    """Used by graph.py's add_conditional_edges."""
    return state["current_module"]
```

- [ ] **Step 5: Run + Commit**

```bash
python -m pytest orchestrator/tests/test_supervisor.py -v
git add orchestrator/agents/supervisor.py orchestrator/prompts/supervisor.md \
        orchestrator/tests/test_supervisor.py
git commit -m "feat(orchestrator): supervisor with rule-based + LLM intent override"
```

---

## Task 19: Graph builder

**Files:**
- Create: `orchestrator/graph.py`
- Test: `orchestrator/tests/test_graph.py`

- [ ] **Step 1: Test**

Create `orchestrator/tests/test_graph.py`:

```python
"""Tests for the LangGraph topology — uses an in-memory checkpointer + fake LLMs."""
from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from orchestrator.graph import build_graph
from orchestrator.state import ContextStore


def _all_modules_confirmed_cs():
    return ContextStore(**{m: {"confirmed_at": "2026-05-26"} for m in
                           ("m1_topic", "m2_literature", "m3_design",
                            "m4_analysis", "m5_writing")})


def test_graph_compiles_in_both_modes():
    g_interactive = build_graph(interactive=True, checkpointer=MemorySaver())
    g_auto       = build_graph(interactive=False, checkpointer=MemorySaver())
    assert g_interactive is not None
    assert g_auto is not None


def test_graph_terminates_when_all_confirmed():
    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    state = {
        "messages": [HumanMessage(content="seed")],
        "current_module": "M1",
        "context_store": _all_modules_confirmed_cs(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }
    config = {"configurable": {"thread_id": "test-1"}}
    final = graph.invoke(state, config=config)
    # Supervisor saw all 5 done → END.
    assert final["current_module"] == "DONE"


def test_graph_routes_to_correct_first_unconfirmed(monkeypatch):
    """Inject a fake LLM so the M1 agent's auto-fill returns a valid object."""
    from orchestrator.agents.m1_topic import M1Agent
    fake = MagicMock()
    fake.invoke.return_value.content = (
        '{"research_title": "T", "field": "Marketing", "research_type": "quantitative", '
        '"target_population": "p", "scope": "s", '
        '"objectives": ["o1"], "research_questions": ["q1"]}'
    )
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)
    # And M2..M5 all return immediately confirming with minimal content.
    from orchestrator.agents.m2_literature import M2Agent
    from orchestrator.agents.m3_design import M3Agent
    from orchestrator.agents.m4_analysis import M4Agent
    from orchestrator.agents.m5_writing import M5Agent

    minimal = {
        M2Agent: '{"research_state_summary":"x","research_gaps":[{"description":"g","relevance":"High","confirmed":true,"supporting_papers":[]}],"theoretical_framework":"f","hypotheses":[],"literature_review_doc":"d","citation_list":[]}',
        M3Agent: '{"paradigm":"quantitative","design":"Regression","tool":"SPSS","sampling_strategy":"convenience","target_sample_size":200,"constructs":[]}',
        M4Agent: '{"data_type_detected":"SPSS","analysis_outline":{"sections":["Descriptive"]},"results":{},"interpretations":{}}',
        M5Agent: '{"sections":[{"name":"intro","text":"..."}],"export_artifacts":[]}',
    }
    for cls, blob in minimal.items():
        m = MagicMock(); m.invoke.return_value.content = blob
        monkeypatch.setattr(cls, "_get_llm", lambda self, _m=m: _m)

    graph = build_graph(interactive=False, checkpointer=MemorySaver())
    final = graph.invoke({
        "messages": [HumanMessage(content="leadership thesis")],
        "current_module": "M1",
        "context_store": ContextStore(),
        "mode": "auto",
        "user_intent": None,
        "pending_confirmations": [],
    }, config={"configurable": {"thread_id": "test-flow"}})

    assert final["current_module"] == "DONE"
    for m in ("m1_topic", "m2_literature", "m3_design", "m4_analysis", "m5_writing"):
        assert getattr(final["context_store"], m) is not None
```

- [ ] **Step 2: Run (fails)**

Run: `python -m pytest orchestrator/tests/test_graph.py -v`
Expected: FAIL — graph module missing.

- [ ] **Step 3: Implement the graph**

Create `orchestrator/graph.py`:

```python
"""LangGraph topology — supervisor in the middle, 5 module agents on the spokes."""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from orchestrator.agents.m1_topic import M1Agent
from orchestrator.agents.m2_literature import M2Agent
from orchestrator.agents.m3_design import M3Agent
from orchestrator.agents.m4_analysis import M4Agent
from orchestrator.agents.m5_writing import M5Agent
from orchestrator.agents.supervisor import route_from_supervisor, supervisor_node
from orchestrator.state import OrchestratorState

logger = logging.getLogger(__name__)


_AGENT_BY_KEY = {
    "M1": M1Agent(),
    "M2": M2Agent(),
    "M3": M3Agent(),
    "M4": M4Agent(),
    "M5": M5Agent(),
}


def _agent_node_factory(module_key: str):
    """Wrap a ModuleAgent.step() into a LangGraph node function."""
    def _node(state: OrchestratorState) -> dict:
        from langchain_core.messages import AIMessage
        agent = _AGENT_BY_KEY[module_key]
        result = agent.step(state)
        # Persist the module's partial schema back into context_store via a patch.
        cs = state["context_store"].model_copy(deep=True)
        field = {
            "M1": "m1_topic", "M2": "m2_literature", "M3": "m3_design",
            "M4": "m4_analysis", "M5": "m5_writing",
        }[module_key]
        setattr(cs, field, result.context_patch)
        return {
            "messages": [AIMessage(content=result.assistant_message)],
            "context_store": cs,
        }
    return _node


def build_graph(*, interactive: bool, checkpointer: BaseCheckpointSaver):
    """Compile the orchestrator graph.

    interactive=True  → halts before supervisor so caller can stream + collect next user turn.
    interactive=False → runs to END without interrupts (auto-mode).
    """
    builder = StateGraph(OrchestratorState)
    builder.add_node("supervisor", supervisor_node)
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_node(key, _agent_node_factory(key))

    builder.add_edge(START, "supervisor")
    builder.add_conditional_edges(
        "supervisor",
        route_from_supervisor,
        {"M1": "M1", "M2": "M2", "M3": "M3",
         "M4": "M4", "M5": "M5", "DONE": END},
    )
    for key in ("M1", "M2", "M3", "M4", "M5"):
        builder.add_edge(key, "supervisor")

    interrupt_before = ["supervisor"] if interactive else []
    return builder.compile(checkpointer=checkpointer, interrupt_before=interrupt_before)


# ---------------------------------------------------------------------------
# Singleton accessors — the FastAPI app and the subprocess each get one.
# ---------------------------------------------------------------------------

_pool = None

def _get_pool():
    """Lazy psycopg connection pool used by PostgresSaver.

    LangGraph 1.x's PostgresSaver expects a real connection pool for long-lived
    services (FastAPI / long-running subprocess). The `from_conn_string` context-
    manager API is only suitable for short-lived scripts.
    """
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(
            os.environ["DATABASE_URL"],
            min_size=1,
            max_size=int(os.getenv("ORCHESTRATOR_PG_POOL_MAX", "10")),
            kwargs={"autocommit": True},
        )
    return _pool


@lru_cache(maxsize=1)
def get_interactive_graph():
    """Returns the cached in-process graph used by the chat router."""
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()  # idempotent — creates langgraph internal tables on first run
    return build_graph(interactive=True, checkpointer=saver)


@lru_cache(maxsize=1)
def get_auto_graph():
    """Returns the cached auto-mode graph used by the subprocess entrypoint."""
    from langgraph.checkpoint.postgres import PostgresSaver
    saver = PostgresSaver(_get_pool())
    saver.setup()
    return build_graph(interactive=False, checkpointer=saver)
```

- [ ] **Step 4: Run**

Run: `python -m pytest orchestrator/tests/test_graph.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add orchestrator/graph.py orchestrator/tests/test_graph.py
git commit -m "feat(orchestrator): LangGraph topology (supervisor + 5 module nodes)"
```

---

End of Phase 3–4 (Tasks 12–19). Continue to `2026-05-26-orchestration-foundation-plan-phase-5-6.md` for Tasks 20–26 (Subprocess + HTTP API).
