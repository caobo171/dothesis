"""SP6.5: chat NL-rewrite no longer overwrites prose — it appends a
PendingEdit so the editor's unified accept/reject flow owns the resolution."""
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage

from orchestrator.agents.m5_writing import M5Agent


@pytest.fixture(autouse=True)
def _mock_m5_llm(monkeypatch):
    """M5Agent.step() routes through _is_rewrite_request (LLM-based since the
    keyword purge). Every test in this file expects rewrite=true → dispatch
    to _handle_rewrite, so default to that. Individual tests can override.
    """
    fake = MagicMock()
    fake.invoke.return_value.content = '{"rewrite": true}'
    monkeypatch.setattr(M5Agent, "_get_llm", lambda self: fake)
    return fake


def _make_state(user_msg: str, partial: dict, project_id: str = "p1") -> dict:
    class _CS:
        m1_topic = {"language": "en", "research_title": "X"}
        m2_literature = {"research_gaps": []}
        m3_design = {"paradigm": "quantitative"}
        m4_analysis = {}
        m5_writing = partial
    return {
        "messages": [HumanMessage(content=user_msg)],
        "context_store": _CS(),
        "project_id": project_id,
    }


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_appends_pending_edit_not_prose(mock_rewrite):
    """A chat rewrite must not mutate chapters[i].prose directly anymore."""
    mock_rewrite.invoke.return_value = "REWRITTEN INTRO TEXT"
    partial = {
        "chapters": {
            "intro": {"name": "intro", "prose": "OLD INTRO", "pending_edits": []},
        },
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite chapter 1 to be less formal", partial)
    agent = M5Agent()
    result = agent.step(state)
    patch_data = result.context_patch
    intro = patch_data["chapters"]["intro"]
    assert intro["prose"] == "OLD INTRO"                        # unchanged
    assert len(intro["pending_edits"]) == 1
    edit = intro["pending_edits"][0]
    assert edit["source"] == "chat_rewrite"
    assert edit["new_text"] == "REWRITTEN INTRO TEXT"
    assert edit["old_text"] == "OLD INTRO"
    assert edit["from_offset"] == 0
    assert edit["to_offset"] == len("OLD INTRO")


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_emits_bubble_with_editor_link(mock_rewrite):
    mock_rewrite.invoke.return_value = "REWRITTEN"
    partial = {
        "chapters": {
            "intro": {"name": "intro", "prose": "OLD", "pending_edits": []},
        },
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite intro", partial, project_id="proj-abc")
    agent = M5Agent()
    result = agent.step(state)
    bubble_text = "\n".join(m.content for m in (result.extra_messages or []))
    assert "/editor" in bubble_text or "Open in editor" in bubble_text


@patch("orchestrator.agents.m5_writing.rewrite_chapter")
def test_handle_rewrite_stacks_multiple_pending_edits(mock_rewrite):
    """Two rewrites of the same chapter produce two PendingEdits."""
    mock_rewrite.invoke.side_effect = ["FIRST REWRITE", "SECOND REWRITE"]
    partial = {
        "chapters": {"intro": {"name": "intro", "prose": "OLD", "pending_edits": []}},
        "_compose_chapters_done": True,
        "_awaiting_confirm": True,
    }
    state = _make_state("rewrite intro", partial)
    agent = M5Agent()
    first = agent.step(state)
    # Apply the patch back into partial to simulate context-store persistence
    partial["chapters"] = first.context_patch["chapters"]
    second = agent.step(_make_state("rewrite intro more concise", partial))
    edits = second.context_patch["chapters"]["intro"]["pending_edits"]
    assert len(edits) == 2
    assert edits[0]["new_text"] == "FIRST REWRITE"
    assert edits[1]["new_text"] == "SECOND REWRITE"
