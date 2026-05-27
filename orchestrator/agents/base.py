"""ModuleAgent base — shared clarification loop for all 5 module nodes."""
from __future__ import annotations

import json
import logging
import os
from abc import ABC
from dataclasses import dataclass, field
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
    tool_calls_json: dict | None = None    # SP3 — widget render hint, or None
    # SP5: additional AIMessages the graph node should emit after the primary
    # assistant_message. Used by M4 to stream per-step execution results.
    # Default empty list keeps SP3/SP4 callers untouched.
    extra_messages: list = field(default_factory=list)


class ModuleAgent(ABC):
    """Shared clarification loop. Subclasses override schema/prompt/tools/module_key."""

    schema: type[BaseModel]
    module_key: str
    system_prompt: str
    tools: list[Any]

    def _get_llm(self):
        return ChatGoogleGenerativeAI(
            model=os.getenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-flash"),
            temperature=0.4,
        )

    def render_hint_for_field(self, field_name: str) -> dict | None:
        """Optional override: return a widget render hint when asking the user
        to fill `field_name`. Default returns None (plain-text input).

        Subclasses should return a dict matching one of the WidgetHint
        variants in orchestrator/agents/widgets.py (e.g. CardGridHint).
        Use `<HintClass>(...).model_dump()` to produce the dict.
        """
        # SP3: hook point for card-grid UX — subclasses override per-field
        return None

    def step(self, state: OrchestratorState) -> ModuleStepResult:
        mode = state.get("mode", "interactive")
        partial = dict(get_module_slice(state["context_store"], self.module_key))

        if mode == "auto":
            return self._auto_fill(state, partial)

        # Interactive: check if we're awaiting a final confirmation from the user.
        if partial.pop("_awaiting_confirm", False):
            if self._is_affirmative(state["messages"]):
                # User confirmed — stamp confirmed_at and transition to next module.
                partial["confirmed_at"] = datetime.now(timezone.utc).isoformat()
                return ModuleStepResult(
                    assistant_message=f"Confirmed {self.module_key}. Moving on.",
                    context_patch=partial,
                    transition=True,
                )
            # User did not confirm — treat as a correction and re-ask missing fields.
            return self._ask_next_question(state, partial)

        # Interactive: check if we were waiting for the user to fill a specific field.
        awaiting_field = partial.pop("_awaiting_field", None)
        if awaiting_field:
            # Extract the field value from the latest user message.
            extracted = self._extract_answer(state, awaiting_field)
            if extracted is not None:
                partial[awaiting_field] = extracted

        # Continue clarification: find the next missing field or summarize for confirm.
        return self._ask_next_question(state, partial)

    def _auto_fill(self, state, partial: dict) -> ModuleStepResult:
        """In auto mode, ask the LLM to fill all required fields at once silently."""
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
            f"Already filled (do not change): "
            f"{json.dumps({k:v for k,v in partial.items() if k in required}, default=str)}"
        )
        resp = self._get_llm().invoke(prompt).content
        try:
            filled = json.loads(_strip_code_fence(resp))
        except (json.JSONDecodeError, TypeError):
            logger.warning("%s auto-fill returned non-JSON: %r", self.module_key, resp[:200])
            filled = {}
        merged = {**partial, **filled,
                  "confirmed_at": datetime.now(timezone.utc).isoformat()}
        try:
            self.schema.model_validate(merged)
        except ValidationError as e:
            logger.warning("%s auto-fill validation: %s", self.module_key, e)
        return ModuleStepResult(
            assistant_message=f"[auto] Filled {self.module_key} from topic.",
            context_patch=merged,
            transition=True,
        )

    def _ask_next_question(self, state, partial: dict) -> ModuleStepResult:
        """Find the next missing required field and ask for it, or summarize for confirm."""
        missing = self._next_missing_field(partial)
        if missing is None:
            # All required fields filled — summarize and ask for user confirmation.
            summary = self._summarize_for_confirm(partial)
            partial["_awaiting_confirm"] = True
            return ModuleStepResult(
                assistant_message=f"Here's what we have:\n\n{summary}\n\nConfirm and move on?",
                context_patch=partial,
                transition=False,
                needs_user_reply=True,
            )

        # Mark which field we're waiting on so the next step can extract the answer.
        partial["_awaiting_field"] = missing
        prompt = (
            f"{self.system_prompt}\n\n"
            f"You need the user to provide a value for the schema field '{missing}'. "
            f"Ask a single targeted question in friendly, plain language. Don't ask "
            f"for multiple fields at once. Don't restate the whole schema. Already "
            f"filled: {json.dumps({k:v for k,v in partial.items() if not k.startswith('_')}, default=str)[:1000]}"
        )
        msg = self._get_llm().invoke(prompt).content.strip()
        # SP3: call the hook so subclasses can attach a widget render hint
        hint = self.render_hint_for_field(missing)
        return ModuleStepResult(
            assistant_message=msg, context_patch=partial,
            transition=False, needs_user_reply=True,
            tool_calls_json=hint,
        )

    def _extract_answer(self, state, field_name: str) -> Any:
        """Ask the LLM to extract the field value from the user's latest message."""
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
            # Fall back to using the raw user message as the value.
            return last_user

    @staticmethod
    def _is_affirmative(messages: list[BaseMessage]) -> bool:
        """Return True if the last user message is a confirmation word."""
        last_user = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            "",
        )
        return last_user.strip().lower() in {
            "yes", "y", "ok", "okay", "confirm", "go", "continue", "yep",
            "đồng ý", "ok rồi", "tiếp tục",
        }

    def _summarize_for_confirm(self, partial: dict) -> str:
        """Build a human-readable bullet list of filled fields for the confirm prompt."""
        return "\n".join(
            f"- **{k}**: {json.dumps(v, default=str, ensure_ascii=False)[:200]}"
            for k, v in partial.items() if not k.startswith("_")
        )

    def _required_field_names(self) -> list[str]:
        """Return schema field names that are required, excluding confirmed_at (has a default)."""
        return [
            name for name, field in self.schema.model_fields.items()
            if field.is_required() and name != "confirmed_at"
        ]

    def _next_missing_field(self, partial: dict) -> str | None:
        """Return the first required field that is not yet filled, or None if all filled."""
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
    """Remove leading/trailing markdown code fences from LLM responses."""
    s = s.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()
