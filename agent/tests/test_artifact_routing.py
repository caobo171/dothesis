import pytest

from agent.artifact_routing import (
    ArtifactRoutingMiddleware,
    WriteTarget,
    parse_write_target,
    resolve_write_target,
    validate_tool_call,
    write_target_marker,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import HumanMessage, ToolMessage


QUESTIONNAIRE = WriteTarget(
    module="M3", key="instrument", artifact="questionnaire")


def test_explicit_questionnaire_routes_to_m3_not_current_focus():
    assert resolve_write_target(
        "Build and save the questionnaire", recent_messages=()
    ) == QUESTIONNAIRE


def test_terse_save_inherits_nearest_artifact_from_dialogue():
    assert resolve_write_target(
        "thì lưu đi ...",
        recent_messages=(
            "Build lại bộ câu hỏi khảo sát",
            "Bộ câu hỏi gồm EXP_1 đến DEC_5.",
        ),
    ) == QUESTIONNAIRE


def test_explicit_new_artifact_overrides_questionnaire_history():
    assert resolve_write_target(
        "Save chapter 5 now",
        recent_messages=("The questionnaire contains 40 items.",),
    ) == WriteTarget(module="M5", key="final_sections", artifact="chapters")


def test_ambiguous_save_without_artifact_remains_agent_directed():
    assert resolve_write_target("save it", recent_messages=()) is None


def test_write_target_marker_round_trips():
    assert parse_write_target(write_target_marker(QUESTIONNAIRE)) == QUESTIONNAIRE


def test_non_state_tools_are_never_restricted():
    assert validate_tool_call(
        QUESTIONNAIRE,
        "audit_instrument",
        {"items": []},
    ) is None


def test_wrong_module_commit_is_rejected():
    error = validate_tool_call(
        QUESTIONNAIRE,
        "commit_slice",
        {"module": "M5", "writes": {"final_sections": [{"title": "Questionnaire"}]}},
    )
    assert error is not None
    assert "M3" in error
    assert "instrument" in error


def test_matching_commit_is_allowed():
    assert validate_tool_call(
        QUESTIONNAIRE,
        "commit_slice",
        {"module": "M3", "writes": {"instrument": {"items": []}}},
    ) is None


def test_right_module_without_required_key_is_rejected():
    error = validate_tool_call(
        QUESTIONNAIRE,
        "commit_slice",
        {"module": "M3", "writes": {"methodology": {}}},
    )
    assert error is not None
    assert "instrument" in error


def _request(name: str, args: dict):
    return ToolCallRequest(
        tool_call={"name": name, "args": args, "id": "call-1", "type": "tool_call"},
        tool=None,
        state={"messages": [HumanMessage(content=write_target_marker(QUESTIONNAIRE))]},
        runtime=None,
    )


def test_middleware_does_not_execute_misrouted_commit():
    called = False

    def handler(_request):
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1")

    result = ArtifactRoutingMiddleware().wrap_tool_call(
        _request("commit_slice", {
            "module": "M5",
            "writes": {"final_sections": [{"title": "Questionnaire"}]},
        }),
        handler,
    )

    assert called is False
    assert result.status == "error"
    assert "M3.instrument" in result.content


def test_middleware_leaves_arbitrary_tool_choice_untouched():
    expected = ToolMessage(content="audited", tool_call_id="call-1")

    def handler(_request):
        return expected

    result = ArtifactRoutingMiddleware().wrap_tool_call(
        _request("audit_instrument", {"items": []}),
        handler,
    )

    assert result is expected


@pytest.mark.asyncio
async def test_async_middleware_rejects_misrouted_commit():
    called = False

    async def handler(_request):
        nonlocal called
        called = True
        return ToolMessage(content="ok", tool_call_id="call-1")

    result = await ArtifactRoutingMiddleware().awrap_tool_call(
        _request("commit_slice", {
            "module": "M5",
            "writes": {"final_sections": [{"title": "Questionnaire"}]},
        }),
        handler,
    )

    assert called is False
    assert result.status == "error"
