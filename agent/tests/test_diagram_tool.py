"""render_model_diagram — promoted from partner_report_service._render_model_diagram
(spec §3): the hardcoded nvm node path (_NODE_BIN) whose failure was swallowed
meant every partner report silently shipped without its diagram. As an agent
tool all three surfaces get it, with node discovered via shutil.which."""
import json

from agent.tools.diagram import _mermaid_source, render_model_diagram


def test_mermaid_source_from_model():
    src = _mermaid_source(
        constructs=[{"id": "TR", "label": "Trust"}, {"id": "PI", "label": "Intention"}],
        paths=[{"from": "TR", "to": "PI"}],
    )
    assert src.startswith("flowchart LR")
    assert 'TR["Trust"]' in src and "TR --> PI" in src


def test_mermaid_source_rejects_dangling_paths():
    # A path to an undeclared construct is model noise, not a diagram edge.
    assert _mermaid_source(constructs=[{"id": "A", "label": "A"}],
                           paths=[{"from": "A", "to": "GHOST"}]) is None
    assert _mermaid_source(constructs=[], paths=[]) is None


def test_tool_fails_soft_without_mmdc(tmp_path, monkeypatch):
    # No mermaid CLI installed → a recovery-hint JSON, never a crashed turn.
    import agent.tools.diagram as mod
    monkeypatch.setattr(mod, "_MERMAID_DIR", tmp_path)  # empty dir: no mmdc
    out = json.loads(render_model_diagram.func(
        constructs=[{"id": "A", "label": "A"}, {"id": "B", "label": "B"}],
        paths=[{"from": "A", "to": "B"}]))
    assert out["error"] == "mmdc_unavailable"


def test_tool_reports_empty_model():
    # An empty/dangling model returns an actionable code, not a silent None —
    # the swallowed-failure lesson: the agent must be able to fix its input.
    out = json.loads(render_model_diagram.func(constructs=[], paths=[]))
    assert out["error"] == "empty_model"
    assert "hint" in out


def test_render_model_diagram_registered_in_build_agent():
    # The tool only reaches the three surfaces if build_agent binds it.
    import inspect

    import agent.runtime as runtime
    assert runtime.render_model_diagram is not None
    assert "render_model_diagram," in inspect.getsource(runtime.build_agent)
