"""Run guards for the chat agent: a per-turn budget and tool-call hardening.

Ported from the Morgan agent runtime (ai-agent-autogen), where every run has a
max-iteration cap and a wall-clock budget, a failing tool becomes an error
message instead of an exception, and string-encoded JSON arguments are repaired
before a schema check rejects them.

Without these, deepagents runs a turn with ``recursion_limit=9_999``: a model
that keeps calling tools spends the student's credits until the provider gives
up. One tool that raises (anything other than an argument-validation error)
aborts the whole turn, so the student sees ``ValueError: …`` and any work done
earlier in that turn goes unreported.

Layering: agent/ must never import app/ — stdlib + langchain only.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Annotated, Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, PrivateStateAttr, hook_config
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.channels.untracked_value import UntrackedValue
from langgraph.errors import GraphBubbleUp
from typing_extensions import NotRequired

# Name on the injected stop message so stream_turn can recognise it without
# parsing prose.
TURN_BUDGET_MESSAGE_NAME = "dothesis_turn_budget"

_VIETNAMESE_RE = re.compile(
    r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợ"
    r"úùủũụứừửữựýỳỷỹỵ]",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TurnBudget:
    """Limits for ONE user turn. ``None`` disables that limit."""

    max_model_calls: int | None = 40
    max_seconds: float | None = 1200.0

    @classmethod
    def from_env(cls) -> "TurnBudget":
        """``DOTHESIS_TURN_MAX_MODEL_CALLS`` / ``DOTHESIS_TURN_MAX_SECONDS``; 0 = off."""
        def _read(name: str, default: float) -> float | None:
            raw = os.getenv(name)
            try:
                value = float(raw) if raw not in (None, "") else default
            except ValueError:
                value = default
            return value if value > 0 else None

        calls = _read("DOTHESIS_TURN_MAX_MODEL_CALLS", cls.max_model_calls or 0)
        return cls(
            max_model_calls=int(calls) if calls is not None else None,
            max_seconds=_read("DOTHESIS_TURN_MAX_SECONDS", cls.max_seconds or 0),
        )


class _TurnBudgetState(AgentState):
    # UntrackedValue: never checkpointed, so every new turn starts from zero.
    turn_model_calls: NotRequired[Annotated[int, UntrackedValue, PrivateStateAttr]]
    turn_started_at: NotRequired[Annotated[float, UntrackedValue, PrivateStateAttr]]


def _last_human_text(messages: list) -> str:
    for message in reversed(messages or []):
        if getattr(message, "type", None) == "human":
            content = getattr(message, "content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    b.get("text", "") for b in content
                    if isinstance(b, dict) and b.get("type") == "text")
    return ""


def budget_stop_message(reason: str, user_text: str) -> str:
    """Localized pause notice with a continue/stop choice (Morgan's run continuation)."""
    if _VIETNAMESE_RE.search(user_text or ""):
        cause = ("đã dùng hết số bước xử lý cho một lượt"
                 if reason == "max_model_calls" else "đã chạy quá thời gian cho một lượt")
        # Wording avoids "đã lưu": chat_v3's save-claim check would otherwise
        # append a false "nothing was saved" warning to this notice.
        return (f"Mình tạm dừng ở đây vì {cause}. Phần việc hoàn tất trong lượt này vẫn "
                "được giữ nguyên. Bạn muốn mình làm tiếp phần còn lại không?\n\n"
                "[OPTIONS] Tiếp tục | Dừng ở đây")
    cause = ("used the step limit for one turn"
             if reason == "max_model_calls" else "ran past the time limit for one turn")
    return (f"I paused here because this request {cause}. Anything saved during this "
            "turn is kept. Do you want me to carry on with the rest?\n\n"
            "[OPTIONS] Continue | Stop here")


class TurnBudgetMiddleware(AgentMiddleware):
    """End a turn cleanly when it exceeds its model-call or wall-clock budget.

    Checked before each model call, so a running tool is never cut off halfway
    (Morgan consumes its steering signals at the same boundary). The stop
    message lands in the checkpoint, so the next turn's model knows it was
    interrupted, and its ``[OPTIONS]`` line lets the student resume with one click.
    """

    state_schema = _TurnBudgetState

    def __init__(self, budget: TurnBudget) -> None:
        super().__init__()
        self.budget = budget

    def before_agent(self, state, runtime) -> dict[str, Any] | None:
        return {"turn_model_calls": 0, "turn_started_at": time.monotonic()}

    async def abefore_agent(self, state, runtime) -> dict[str, Any] | None:
        return self.before_agent(state, runtime)

    def _exceeded(self, state) -> str | None:
        calls = state.get("turn_model_calls", 0)
        if self.budget.max_model_calls is not None and calls >= self.budget.max_model_calls:
            return "max_model_calls"
        started = state.get("turn_started_at")
        if (self.budget.max_seconds is not None and started is not None
                and time.monotonic() - started >= self.budget.max_seconds):
            return "max_seconds"
        return None

    @hook_config(can_jump_to=["end"])
    def before_model(self, state, runtime) -> dict[str, Any] | None:
        reason = self._exceeded(state)
        if reason is None:
            return None
        print(f"[agent.budget] turn stopped reason={reason} "
              f"model_calls={state.get('turn_model_calls', 0)}",
              file=sys.stderr, flush=True)
        text = budget_stop_message(reason, _last_human_text(state.get("messages", [])))
        return {
            "jump_to": "end",
            "messages": [AIMessage(content=text, name=TURN_BUDGET_MESSAGE_NAME,
                                   additional_kwargs={"termination_reason": reason})],
        }

    @hook_config(can_jump_to=["end"])
    async def abefore_model(self, state, runtime) -> dict[str, Any] | None:
        return self.before_model(state, runtime)

    def after_model(self, state, runtime) -> dict[str, Any] | None:
        return {"turn_model_calls": state.get("turn_model_calls", 0) + 1}

    async def aafter_model(self, state, runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)


# ---------------------------------------------------------------------------
# Tool-call hardening
# ---------------------------------------------------------------------------

_STRUCTURED = {"object", "array"}


def _schema_types(prop: dict) -> set[str]:
    types: set[str] = set()
    raw = prop.get("type")
    if isinstance(raw, str):
        types.add(raw)
    elif isinstance(raw, list):
        types.update(t for t in raw if isinstance(t, str))
    for key in ("anyOf", "oneOf"):
        for sub in prop.get(key) or []:
            if isinstance(sub, dict):
                types |= _schema_types(sub)
    if "properties" in prop or "additionalProperties" in prop:
        types.add("object")
    if "items" in prop:
        types.add("array")
    return types


def repair_string_encoded_args(args: dict, properties: dict) -> dict | None:
    """Decode JSON strings sent where the schema wants an object/array.

    Models on OpenAI-compatible routes regularly send ``writes="{\\"x\\": 1}"``
    for a dict parameter. Pydantic then rejects the call, which costs a whole
    model round-trip, and the artifact router sees no keys and misreports a
    routing mismatch. Returns the repaired args, or None when nothing changed.
    A parameter that also accepts a string is left alone.
    """
    repaired = dict(args)
    changed = False
    for name, value in args.items():
        prop = properties.get(name)
        if not isinstance(value, str) or not isinstance(prop, dict):
            continue
        types = _schema_types(prop)
        if not (types & _STRUCTURED) or "string" in types:
            continue
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            continue
        try:
            decoded = json.loads(stripped)
        except (ValueError, TypeError):
            continue
        expected = "object" if isinstance(decoded, dict) else (
            "array" if isinstance(decoded, list) else None)
        if expected in types:
            repaired[name] = decoded
            changed = True
    return repaired if changed else None


def _tool_properties(tool) -> dict:
    try:
        props = getattr(tool, "args", None)
    except Exception:  # pragma: no cover - a broken schema must not block the call
        return {}
    return props if isinstance(props, dict) else {}


def tool_failure_content(exc: Exception, tool_name: str) -> str:
    detail = str(exc).strip().replace("\n", " ")[:300]
    return json.dumps({
        "error": f"tool_failed: {type(exc).__name__}" + (f": {detail}" if detail else ""),
        "hint": (f"{tool_name} failed unexpectedly. Do not retry it with the same "
                 "arguments; change the input or take another approach, and tell the "
                 "student plainly if the step cannot be completed."),
    }, ensure_ascii=False)


class ToolCallGuardMiddleware(AgentMiddleware):
    """Repair malformed arguments, and return tool crashes to the model as errors.

    Tools in this repo already return ``{"error", "hint"}`` for failures they
    expect. This catches the ones they don't, so one crash costs one tool call
    instead of the turn. Control-flow signals (interrupts, parent commands) and
    cancellation still propagate.

    Place it FIRST in the middleware list so repaired arguments are what the
    artifact router validates.
    """

    @staticmethod
    def _repair(request):
        call = request.tool_call
        args = call.get("args")
        if not isinstance(args, dict) or request.tool is None:
            return request
        repaired = repair_string_encoded_args(args, _tool_properties(request.tool))
        if repaired is None:
            return request
        print(f"[agent.tool] repaired string-encoded args for {call.get('name')}",
              file=sys.stderr, flush=True)
        return request.override(tool_call={**call, "args": repaired})

    @staticmethod
    def _failure(request, exc: Exception) -> ToolMessage:
        name = str(request.tool_call.get("name") or "")
        print(f"[agent.tool] {name} raised {type(exc).__name__}; returned as tool error",
              file=sys.stderr, flush=True)
        traceback.print_exception(exc, file=sys.stderr)
        return ToolMessage(
            content=tool_failure_content(exc, name),
            tool_call_id=str(request.tool_call.get("id") or ""),
            name=name,
            status="error",
        )

    def wrap_tool_call(self, request, handler):
        request = self._repair(request)
        try:
            return handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return self._failure(request, exc)

    async def awrap_tool_call(self, request, handler):
        request = self._repair(request)
        try:
            return await handler(request)
        except GraphBubbleUp:
            raise
        except Exception as exc:
            return self._failure(request, exc)


# ---------------------------------------------------------------------------
# Unparseable tool calls
# ---------------------------------------------------------------------------

# Name on the error reply, so it is recognisable in the history and logs.
INVALID_TOOL_CALL_MESSAGE_NAME = "dothesis_invalid_tool_call"
MAX_RETRIES_PER_TURN = 2
_RAW_ARGS_LIMIT = 4000


def _is_json(raw: Any) -> bool:
    if not isinstance(raw, str):
        return False
    try:
        json.loads(raw)
    except (ValueError, TypeError):
        return False
    return True


def repair_invalid_tool_call_args(messages: list) -> list:
    """Return ``messages`` with every unparseable tool-call argument string made JSON.

    A model can write arguments LangChain cannot parse (prod 2026-11-02: qwen
    closed the object one brace early). The call is kept as an
    ``invalid_tool_call`` and the OpenAI adapter replays its raw string as
    ``function.arguments`` on every later model call. DashScope refuses that
    with a 400, so one bad call made the thread unusable for good. The raw
    text is wrapped, not dropped, so the model can see what it sent and fix it.
    The checkpointed messages are never mutated; untouched ones are reused.
    """
    repaired: list = []
    for message in messages:
        calls = getattr(message, "invalid_tool_calls", None) or []
        if not isinstance(message, AIMessage) or all(_is_json(c.get("args")) for c in calls):
            repaired.append(message)
            continue
        fixed = [
            c if _is_json(c.get("args")) else {
                **c,
                "args": json.dumps(
                    {"unparseable_arguments": str(c.get("args") or "")[:_RAW_ARGS_LIMIT]},
                    ensure_ascii=False),
            }
            for c in calls
        ]
        repaired.append(message.model_copy(update={"invalid_tool_calls": fixed}))
    return repaired


def _invalid_call_reply(call: dict) -> ToolMessage:
    name = str(call.get("name") or "unknown")
    return ToolMessage(
        content=json.dumps({
            "error": f"invalid_tool_call: the arguments for {name} were not valid JSON, "
                     "so the tool did not run.",
            "hint": "Call it again now with one complete JSON object as the arguments.",
        }, ensure_ascii=False),
        tool_call_id=str(call.get("id") or ""),
        name=INVALID_TOOL_CALL_MESSAGE_NAME,
        status="error",
    )


class InvalidToolCallMiddleware(AgentMiddleware):
    """Keep an unparseable tool call from ending the turn or breaking the thread.

    Before: such a call ran nothing, the router saw no tool calls and ended the
    turn mid-sentence ("Let me save…"), and the raw arguments were replayed on
    every later turn. Now each one gets an error reply straight away and, when
    it was the only thing the model asked for, the model is called again in the
    same turn. Retries are capped per turn; TurnBudgetMiddleware bounds the rest.
    """

    @staticmethod
    def _replay_safe(request):
        messages = repair_invalid_tool_call_args(request.messages)
        if all(a is b for a, b in zip(messages, request.messages)):
            return request
        return request.override(messages=messages)

    def wrap_model_call(self, request, handler):
        return handler(self._replay_safe(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._replay_safe(request))

    @hook_config(can_jump_to=["model"])
    def after_model(self, state, runtime) -> dict[str, Any] | None:
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or not last.invalid_tool_calls:
            return None
        replies = [_invalid_call_reply(c) for c in last.invalid_tool_calls if c.get("id")]
        if not replies:
            return None
        # Earlier unparseable rounds in THIS turn (since the student's message).
        retries = 0
        for message in reversed(messages[:-1]):
            if getattr(message, "type", None) == "human":
                break
            if isinstance(message, AIMessage) and message.invalid_tool_calls:
                retries += 1
        names = ",".join(str(c.get("name")) for c in last.invalid_tool_calls)
        print(f"[agent.tool] unparseable tool call(s) {names}; retries_this_turn={retries}",
              file=sys.stderr, flush=True)
        update: dict[str, Any] = {"messages": replies}
        # With valid calls alongside, the tool node runs them and the model is
        # called again anyway. Past the cap the replies still go in, so the
        # history stays well-formed, and the turn ends.
        if not last.tool_calls and retries < MAX_RETRIES_PER_TURN:
            update["jump_to"] = "model"
        return update

    @hook_config(can_jump_to=["model"])
    async def aafter_model(self, state, runtime) -> dict[str, Any] | None:
        return self.after_model(state, runtime)
