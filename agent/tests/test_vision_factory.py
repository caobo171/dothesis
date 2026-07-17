"""make_vision_capable_model dispatch (sidecar vs brain) — no client construction."""
import agent.model_factory as mf
from agent.model_factory import ModelSpec, make_vision_capable_model


def test_sidecar_delegates_to_vision_model(monkeypatch):
    monkeypatch.setattr(mf, "make_vision_model", lambda spec=None: "SIDECAR")
    monkeypatch.setattr(mf, "make_model", lambda spec=None: "BRAIN")
    assert make_vision_capable_model(ModelSpec(route="native"), use_sidecar=True) == "SIDECAR"


def test_brain_delegates_to_make_model(monkeypatch):
    monkeypatch.setattr(mf, "make_vision_model", lambda spec=None: "SIDECAR")
    monkeypatch.setattr(mf, "make_model", lambda spec=None: "BRAIN")
    assert make_vision_capable_model(ModelSpec(route="native", model="claude-sonnet-4-6"),
                                     use_sidecar=False) == "BRAIN"
