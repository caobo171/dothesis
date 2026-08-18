import json

from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


def _commit_tool(store):
    return {tool.name: tool for tool in make_state_tools(store)}["commit_slice"]


def test_methodology_cannot_land_without_a_real_model(tmp_path):
    store = ProjectStateStore(str(tmp_path))
    result = json.loads(_commit_tool(store).func(
        module="M3",
        writes={"methodology": {"design": "quantitative"}},
        reason="draft methodology",
    ))
    assert result["error"].startswith("m3_model_required")
    assert store.load()["contextStore"].get("methodology") is None


def test_methodology_can_use_an_existing_structured_model(tmp_path):
    store = ProjectStateStore(str(tmp_path))
    model = {
        "nodes": [{"id": "X", "label": "X"}, {"id": "Y", "label": "Y"}],
        "edges": [{"source": "X", "target": "Y", "hypothesis": "H1"}],
    }
    first = json.loads(_commit_tool(store).func(
        module="M3", writes={"conceptual_model": model}, reason="build model"))
    assert "error" not in first
    second = json.loads(_commit_tool(store).func(
        module="M3",
        writes={"methodology": {"design": "quantitative"}},
        reason="write methodology",
        confirm_done=True,
    ))
    assert "error" not in second
    assert store.load()["status"]["M3"] == "done"
