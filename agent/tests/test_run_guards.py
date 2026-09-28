"""Turn budget + tool-call hardening (agent/run_guards.py).

Ported from the Morgan runtime. Three failures they close:
- a model that keeps calling tools ran until deepagents' recursion_limit of
  9_999, billing the student for every step;
- one tool raising anything but a validation error killed the whole turn, and
  the student saw a bare ``ValueError: …``;
- ``writes='{"instrument": …}'`` (a JSON string for a dict parameter) failed
  validation, and the artifact router read it as "no keys" and misreported a
  routing mismatch.
"""
import asyncio
import json
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool
from langchain.agents.middleware.types import ToolCallRequest
from pydantic import PrivateAttr

from agent.run_guards import (
    TURN_BUDGET_MESSAGE_NAME,
    ToolCallGuardMiddleware,
    TurnBudget,
    TurnBudgetMiddleware,
    budget_stop_message,
    repair_string_encoded_args,
)
from agent.runtime import build_agent, stream_turn


class _LoopingModel(BaseChatModel):
    """Calls `tool_name` on every step and never answers: the runaway case."""

    tool_name: str = "ls"
    tool_args: dict = {}
    _calls: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "looping-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        self._calls += 1
        msg = AIMessage(content="", tool_calls=[{
            "name": self.tool_name, "args": dict(self.tool_args),
            "id": f"call-{self._calls}", "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=msg)])


class _CrashThenAnswerModel(BaseChatModel):
    """Calls the crashing tool once, then answers from whatever it got back."""

    _seen_tool_error: str = PrivateAttr(default="")

    @property
    def _llm_type(self) -> str:
        return "crash-fake"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        results = [m for m in messages if isinstance(m, ToolMessage)]
        if not results:
            msg = AIMessage(content="", tool_calls=[{
                "name": "render_model_diagram", "args": {"model": {}},
                "id": "call-1", "type": "tool_call"}])
        else:
            self._seen_tool_error = str(results[-1].content)
            msg = AIMessage(content="Không vẽ được sơ đồ, mình sẽ thử cách khác.")
        return ChatResult(generations=[ChatGeneration(message=msg)])


def _run(agent, text: str) -> list[dict]:
    async def go():
        return [ev async for ev in stream_turn(agent, "t-guard", text, store=None)]
    return asyncio.run(go())


def _reply(events: list[dict]) -> str:
    return "".join(e["text"] for e in events if e.get("type") == "token")


# --- turn budget -----------------------------------------------------------

def test_runaway_tool_loop_stops_at_the_model_call_budget(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver
    model = _LoopingModel()
    agent = build_agent(tmp_path, model=model, checkpointer=InMemorySaver(),
                        turn_budget=TurnBudget(max_model_calls=3, max_seconds=None))

    events = _run(agent, "Viết giúp mình chương 2")

    assert model._calls == 3
    assert not [e for e in events if e.get("type") == "error"]
    assert "tạm dừng" in _reply(events)
    grids = [e["payload"] for e in events
             if e.get("type") == "tool_calls" and e["payload"].get("widget_type") == "card_grid"]
    assert [o["label"] for o in grids[-1]["options"]] == ["Tiếp tục", "Dừng ở đây"]
    assert events[-1] == {"type": "done"}


def test_budget_resets_on_the_next_turn_so_continue_can_resume(tmp_path):
    from langgraph.checkpoint.memory import InMemorySaver
    model = _LoopingModel()
    agent = build_agent(tmp_path, model=model, checkpointer=InMemorySaver(),
                        turn_budget=TurnBudget(max_model_calls=2, max_seconds=None))

    _run(agent, "Write chapter 2")
    events = _run(agent, "Continue")

    assert model._calls == 4
    assert "paused" in _reply(events)


def test_wall_clock_budget_stops_before_the_next_model_call():
    mw = TurnBudgetMiddleware(TurnBudget(max_model_calls=None, max_seconds=5))
    state = {"messages": [HumanMessage("Write chapter 2")],
             "turn_model_calls": 1, "turn_started_at": 0.0}  # monotonic 0 = long ago

    update = mw.before_model(state, None)

    assert update["jump_to"] == "end"
    stop = update["messages"][0]
    assert stop.name == TURN_BUDGET_MESSAGE_NAME
    assert stop.additional_kwargs["termination_reason"] == "max_seconds"
    assert "time limit" in stop.content


def test_under_budget_does_nothing():
    import time
    mw = TurnBudgetMiddleware(TurnBudget(max_model_calls=10, max_seconds=60))
    state = {"messages": [], "turn_model_calls": 3, "turn_started_at": time.monotonic()}
    assert mw.before_model(state, None) is None


def test_budget_env_zero_disables(monkeypatch):
    monkeypatch.setenv("DOTHESIS_TURN_MAX_MODEL_CALLS", "0")
    monkeypatch.setenv("DOTHESIS_TURN_MAX_SECONDS", "90")
    assert TurnBudget.from_env() == TurnBudget(max_model_calls=None, max_seconds=90.0)


def test_budget_env_garbage_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("DOTHESIS_TURN_MAX_MODEL_CALLS", "lots")
    monkeypatch.delenv("DOTHESIS_TURN_MAX_SECONDS", raising=False)
    assert TurnBudget.from_env() == TurnBudget()


def test_stop_message_follows_the_student_language():
    assert "[OPTIONS] Continue | Stop here" in budget_stop_message("max_model_calls", "hi")
    assert "[OPTIONS] Tiếp tục | Dừng ở đây" in budget_stop_message(
        "max_seconds", "viết chương hai")


# --- tool failure containment ---------------------------------------------

def test_a_crashing_tool_is_returned_to_the_model_not_the_turn(tmp_path, monkeypatch):
    from langgraph.checkpoint.memory import InMemorySaver
    import agent.runtime as runtime_mod

    @tool("render_model_diagram")
    def exploding(model: dict) -> str:
        """Render the research model."""
        raise RuntimeError("graphviz binary missing")

    monkeypatch.setattr(runtime_mod, "render_model_diagram", exploding)
    model = _CrashThenAnswerModel()
    agent = build_agent(tmp_path, model=model, checkpointer=InMemorySaver())

    events = _run(agent, "Vẽ sơ đồ mô hình")

    assert not [e for e in events if e.get("type") == "error"]
    payload = json.loads(model._seen_tool_error)
    assert payload["error"].startswith("tool_failed: RuntimeError")
    assert "graphviz binary missing" in payload["error"]
    assert "Không vẽ được" in _reply(events)


def _request(tool_obj, args: dict) -> ToolCallRequest:
    return ToolCallRequest(
        tool_call={"name": tool_obj.name, "args": args, "id": "c1", "type": "tool_call"},
        tool=tool_obj, state={"messages": []}, runtime=None)


def test_graph_control_flow_is_not_swallowed():
    import pytest
    from langgraph.errors import GraphInterrupt

    @tool
    def ask(q: str) -> str:
        """Ask."""
        return q

    def handler(_req):
        raise GraphInterrupt(())

    with pytest.raises(GraphInterrupt):
        ToolCallGuardMiddleware().wrap_tool_call(_request(ask, {"q": "x"}), handler)


# --- argument repair --------------------------------------------------------

@tool
def _commit(module: str, writes: dict[str, Any], tags: list[str] | None = None,
            note: str | dict | None = None) -> str:
    """Stand-in with commit_slice's parameter shapes."""
    return "ok"


def test_json_string_for_a_dict_param_is_decoded():
    fixed = repair_string_encoded_args(
        {"module": "M3", "writes": '{"instrument": {"items": []}}'}, _commit.args)
    assert fixed == {"module": "M3", "writes": {"instrument": {"items": []}}}


def test_json_string_for_an_optional_list_param_is_decoded():
    fixed = repair_string_encoded_args({"tags": '["a", "b"]'}, _commit.args)
    assert fixed == {"tags": ["a", "b"]}


def test_string_params_and_unparseable_values_are_left_alone():
    # `module` is a plain string; `note` accepts a string, so a JSON-looking
    # value there may be intentional; `writes` is not valid JSON.
    assert repair_string_encoded_args(
        {"module": '{"x": 1}', "note": '{"y": 2}', "writes": "{not json"},
        _commit.args) is None


def test_decoded_type_must_match_the_schema():
    assert repair_string_encoded_args({"writes": '["a"]'}, _commit.args) is None


def test_repair_happens_before_the_tool_and_router_see_the_call():
    seen = {}

    def handler(req):
        seen.update(req.tool_call["args"])
        return ToolMessage(content="ok", tool_call_id="c1", name="_commit")

    ToolCallGuardMiddleware().wrap_tool_call(
        _request(_commit, {"module": "M3", "writes": '{"instrument": {}}'}), handler)

    assert seen["writes"] == {"instrument": {}}


def test_stop_message_does_not_trip_the_false_save_warning():
    # chat_v3._SAVED_CLAIM_RE appends "nothing was saved" to any reply that
    # claims a save; the pause notice makes no such claim in either language.
    import re
    saved_claim = re.compile(
        r"\b(?:đã\s+lưu|da\s+luu|đã\s+cập\s*nhật|da\s+cap\s*nhat|"
        r"đã\s+build|da\s+build|locked\s+in|committed\s+to|saved\s+to)\b", re.I)
    for text in ("viết chương hai", "write chapter two"):
        for reason in ("max_model_calls", "max_seconds"):
            assert not saved_claim.search(budget_stop_message(reason, text))
