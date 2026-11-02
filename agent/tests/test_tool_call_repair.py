"""Malformed tool-call arguments must neither brick a thread nor end a turn.

Prod 2026-11-02 (thread 16095f19…): qwen-plus emitted a commit_slice call whose
arguments closed the object one brace early. LangChain kept it as an
invalid_tool_call, the turn ended silently, and every later turn replayed the
raw string as `function.arguments` — DashScope refuses non-JSON there with a
400, so the thread could never answer again.
"""
from __future__ import annotations

import json
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai.chat_models.base import _convert_message_to_dict

from agent.run_guards import (
    InvalidToolCallMiddleware,
    MAX_RETRIES_PER_TURN,
    repair_invalid_tool_call_args,
)

# The exact arguments string from the prod thread: one `}` too many before "reason".
BROKEN_ARGS = (
    '{"module": "M1", "writes": {"topic": "Gen Z và TikTok", "language": "vi"}}, '
    '"reason": "Đặt chủ đề nghiên cứu"}'
)


def _broken_ai(call_id: str = "call_bad") -> AIMessage:
    return AIMessage(
        content="Let me commit the initial project state.",
        invalid_tool_calls=[{
            "type": "invalid_tool_call", "id": call_id, "name": "commit_slice",
            "args": BROKEN_ARGS, "error": None,
        }],
    )


def test_replayed_invalid_call_serialises_to_json_arguments():
    repaired = repair_invalid_tool_call_args([HumanMessage("hi"), _broken_ai()])

    wire = _convert_message_to_dict(repaired[1])
    args = wire["tool_calls"][0]["function"]["arguments"]
    # What DashScope checks: the arguments string parses as JSON.
    assert isinstance(json.loads(args), dict)
    # The model can still see what it sent, so a retry can fix it.
    assert "Gen Z và TikTok" in args


def test_repair_leaves_history_untouched_and_reuses_clean_messages():
    human, broken = HumanMessage("hi"), _broken_ai()
    good = AIMessage(content="", tool_calls=[
        {"type": "tool_call", "id": "c1", "name": "quick_sources", "args": {"query": "x"}}])

    repaired = repair_invalid_tool_call_args([human, good, broken])

    assert repaired[0] is human and repaired[1] is good
    # The checkpointed message is not mutated; only the outgoing copy changes.
    assert broken.invalid_tool_calls[0]["args"] == BROKEN_ARGS


def test_already_json_invalid_call_is_left_alone():
    # Invalid for a reason other than JSON (e.g. schema) — nothing to repair.
    ai = AIMessage(content="", invalid_tool_calls=[{
        "type": "invalid_tool_call", "id": "c", "name": "x", "args": '{"a": 1}', "error": None}])
    assert repair_invalid_tool_call_args([ai])[0] is ai


def test_after_model_answers_only_invalid_call_and_reruns_model():
    update = InvalidToolCallMiddleware().after_model({"messages": [HumanMessage("hi"), _broken_ai()]}, None)

    assert update["jump_to"] == "model"
    [reply] = update["messages"]
    assert isinstance(reply, ToolMessage)
    assert reply.tool_call_id == "call_bad" and reply.status == "error"
    assert "not valid JSON" in reply.content


def test_after_model_lets_valid_calls_run_without_jumping():
    ai = _broken_ai()
    ai.tool_calls = [{"type": "tool_call", "id": "ok", "name": "quick_sources", "args": {}}]

    update = InvalidToolCallMiddleware().after_model({"messages": [HumanMessage("hi"), ai]}, None)

    assert "jump_to" not in update
    assert [m.tool_call_id for m in update["messages"]] == ["call_bad"]


def test_after_model_stops_retrying_after_the_cap():
    mw = InvalidToolCallMiddleware()
    history: list[Any] = [HumanMessage("hi")]
    for i in range(MAX_RETRIES_PER_TURN):
        history.append(_broken_ai(f"c{i}"))
        history.extend(mw.after_model({"messages": history}, None)["messages"])
    history.append(_broken_ai("last"))

    update = mw.after_model({"messages": history}, None)

    # Still answered (history stays well-formed), but the turn is allowed to end.
    assert "jump_to" not in update
    assert [m.tool_call_id for m in update["messages"]] == ["last"]


def test_cap_counts_only_the_current_turn():
    mw = InvalidToolCallMiddleware()
    history: list[Any] = [HumanMessage("old")]
    for i in range(MAX_RETRIES_PER_TURN):
        history.append(_broken_ai(f"old{i}"))
        history.extend(mw.after_model({"messages": history}, None)["messages"])
    history += [HumanMessage("new"), _broken_ai("fresh")]

    assert mw.after_model({"messages": history}, None)["jump_to"] == "model"


class _RecordingFake(GenericFakeChatModel):
    seen: list[list[Any]] = []

    def bind_tools(self, tools, **kwargs):  # noqa: ARG002 - create_agent binds tools
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        type(self).seen.append(list(messages))
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


@tool
def commit_slice(module: str, writes: dict, reason: str) -> str:
    """Save a slice."""
    return f"saved {module}"


def test_agent_retries_within_the_turn_with_repaired_history():
    _RecordingFake.seen = []
    fake = _RecordingFake(messages=iter([
        _broken_ai(),
        AIMessage(content="", tool_calls=[{
            "type": "tool_call", "id": "good", "name": "commit_slice",
            "args": {"module": "M1", "writes": {}, "reason": "r"}}]),
        AIMessage(content="Saved."),
    ]))
    agent = create_agent(model=fake, tools=[commit_slice], middleware=[InvalidToolCallMiddleware()])

    result = agent.invoke({"messages": [HumanMessage("save my topic")]})

    assert result["messages"][-1].content == "Saved."
    assert any(isinstance(m, ToolMessage) and m.content == "saved M1" for m in result["messages"])
    # The retry call saw the broken call with JSON-parseable arguments.
    retry_input = _RecordingFake.seen[1]
    broken_on_wire = next(_convert_message_to_dict(m) for m in retry_input
                          if isinstance(m, AIMessage) and m.invalid_tool_calls)
    json.loads(broken_on_wire["tool_calls"][0]["function"]["arguments"])


def test_turn_budget_still_counts_calls_across_retries():
    from agent.run_guards import TURN_BUDGET_MESSAGE_NAME, TurnBudget, TurnBudgetMiddleware

    _RecordingFake.seen = []
    fake = _RecordingFake(messages=iter([_broken_ai("a"), _broken_ai("b"), _broken_ai("c")]))
    # Same relative order as build_agent.
    agent = create_agent(model=fake, tools=[commit_slice], middleware=[
        InvalidToolCallMiddleware(),
        TurnBudgetMiddleware(TurnBudget(max_model_calls=2, max_seconds=None)),
    ])

    result = agent.invoke({"messages": [HumanMessage("save my topic")]})

    assert len(_RecordingFake.seen) == 2
    assert result["messages"][-1].name == TURN_BUDGET_MESSAGE_NAME
