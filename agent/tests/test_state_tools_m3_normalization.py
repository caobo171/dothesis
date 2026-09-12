"""Regression coverage for canonical M3 writes at the model-facing boundary."""

import json
import uuid

from agent.state import ProjectStateStore
from agent.tools.state_tools import make_state_tools


def test_m3_instrument_commit_normalizes_nested_construct_items(tmp_path):
    store = ProjectStateStore(tmp_path / f"p-{uuid.uuid4().hex}")
    tools = {tool.name: tool for tool in make_state_tools(store)}

    out = json.loads(tools["commit_slice"].func(
        module="M3",
        writes={"instrument": {
            "scale": "Likert 5",
            "constructs": {
                "EXP": {"items": [
                    {"id": "EXP_1", "text": "The influencer is knowledgeable."},
                ]},
            },
        }},
        reason="save questionnaire",
    ))

    assert "error" not in out
    assert store.load()["contextStore"]["instrument"]["items"] == [{
        "id": "EXP_1",
        "text": "The influencer is knowledgeable.",
        "construct": "EXP",
        "reverse_coded": False,
        "attention_check": False,
    }]
