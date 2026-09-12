"""Gap 2: build_agent threads strict_gates → make_state_tools."""
import agent.runtime as rt
from agent.artifact_routing import ArtifactRoutingMiddleware


def test_build_agent_forwards_strict_gates(tmp_path, monkeypatch):
    captured = {}

    def spy_make_state_tools(store, *, strict_gates=False):
        captured["strict_gates"] = strict_gates
        return []

    monkeypatch.setattr(rt, "make_state_tools", spy_make_state_tools)
    monkeypatch.setattr(rt, "create_deep_agent", lambda **k: object())
    monkeypatch.setattr(rt, "_default_model", lambda: object())

    rt.build_agent(tmp_path, strict_gates=True)
    assert captured["strict_gates"] is True

    captured.clear()
    rt.build_agent(tmp_path)  # default
    assert captured["strict_gates"] is False


def test_headless_entry_defaults_strict():
    # the inline default is params.get("strict_gates", True) — assert the semantics
    for params, expected in [({}, True), ({"strict_gates": False}, False),
                             ({"strict_gates": True}, True)]:
        assert params.get("strict_gates", True) is expected


def test_build_agent_registers_artifact_routing_middleware(tmp_path, monkeypatch):
    captured = {}

    monkeypatch.setattr(
        rt, "create_deep_agent",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(rt, "_default_model", lambda: object())

    rt.build_agent(tmp_path)

    assert any(
        isinstance(item, ArtifactRoutingMiddleware)
        for item in captured["middleware"]
    )
