"""FakeChatModel: the E2E harness's scripted LLM. No app/ imports here —
agent/ layering rule."""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from agent.testing.fake_model import FakeChatModel, FixtureError

FIXTURE = {
    "scenario": "demo",
    "entry": "start the demo",
    "steps": [
        {
            "expect_user": "start the demo",
            "response": "Committing.",
            "tool_calls": [{
                "name": "commit_slice",
                "args": {"module": "M1",
                         "writes": {"research_title": "T"},
                         "reason": "r", "confirm_done": True},
            }],
        },
        {
            "expect_user": '"module": "M1"',
            "response": "Done.\n\n[OPTIONS] Next | Stop",
        },
    ],
}


@pytest.fixture
def model(tmp_path):
    (tmp_path / "demo.json").write_text(json.dumps(FIXTURE), encoding="utf-8")
    return FakeChatModel.from_fixtures_dir(str(tmp_path))


def test_first_step_emits_real_tool_call(model):
    # The runtime prepends a [PROJECT STATE] header to user turns — entry
    # matching must be a search, not an anchored match.
    out = model.invoke([HumanMessage(content="[PROJECT STATE] focus=None\nstart the demo")])
    assert out.content == "Committing."
    assert out.tool_calls and out.tool_calls[0]["name"] == "commit_slice"
    assert out.tool_calls[0]["args"]["writes"] == {"research_title": "T"}
    assert out.tool_calls[0]["id"]  # deepagents needs ids to route ToolMessages


def test_step_index_counts_ai_messages(model):
    history = [
        HumanMessage(content="start the demo"),
        AIMessage(content="Committing.",
                  tool_calls=[{"name": "commit_slice", "args": {},
                               "id": "e2e-0-0", "type": "tool_call"}]),
        ToolMessage(content='{"module": "M1", "status": {"M1": "done"}}',
                    tool_call_id="e2e-0-0"),
    ]
    out = model.invoke(history)
    assert "[OPTIONS]" in out.content
    assert not out.tool_calls


def test_expect_user_mismatch_raises(model):
    history = [
        HumanMessage(content="start the demo"),
        AIMessage(content="Committing."),
        HumanMessage(content="something the script never expected"),
    ]
    with pytest.raises(FixtureError):
        model.invoke(history)


def test_exhausted_script_raises(model):
    history = [
        HumanMessage(content="start the demo"),
        AIMessage(content="a"),
        AIMessage(content="b"),
        HumanMessage(content="one turn too many"),
    ]
    with pytest.raises(FixtureError):
        model.invoke(history)


def test_unmatched_scenario_raises(model):
    with pytest.raises(FixtureError):
        model.invoke([HumanMessage(content="totally unrelated first message")])


def test_bind_tools_is_a_passthrough(model):
    # deepagents binds its tool set at agent build; the fixture decides which
    # calls to emit, so binding must be a no-op instead of the BaseChatModel
    # default NotImplementedError.
    assert model.bind_tools([]) is model


def test_astream_yields_text_then_tool_chunk(model):
    async def collect():
        return [c async for c in model.astream(
            [HumanMessage(content="start the demo")])]
    chunks = asyncio.run(collect())
    text = "".join(c.content for c in chunks if isinstance(c.content, str))
    assert "Committing." in text
    assert any(getattr(c, "tool_call_chunks", None) for c in chunks)


def test_default_model_hook(monkeypatch, tmp_path):
    monkeypatch.setenv("DOTHESIS_E2E_MOCK", "1")
    monkeypatch.setenv("DOTHESIS_E2E_FIXTURES_DIR", str(tmp_path))
    from agent.runtime import _default_model
    assert isinstance(_default_model(), FakeChatModel)
