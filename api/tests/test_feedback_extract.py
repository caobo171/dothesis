"""extract_directives (F4 Task 2). The LLM is stubbed at its orchestrator source
so these assert the two contract points: a well-formed JSON reply becomes typed
directives, and any bad output falls back to one raw-text directive (never drop a
professor comment)."""
import orchestrator.tools.m5_writing as m5
from agent.feedback import extract_directives


def test_extract_parses_directives(monkeypatch):
    payload = ('{"directives": [{"chapter": "results", "issue": "no effect sizes", '
               '"required_change": "add Cohen f2"}]}')
    monkeypatch.setattr(m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p:
                        type("R", (), {"content": payload})()})())
    out = extract_directives("Prof: please add effect sizes to chapter 4")
    assert out[0]["chapter"] == "results" and out[0]["required_change"] == "add Cohen f2"


def test_extract_falls_back_to_raw_on_bad_json(monkeypatch):
    monkeypatch.setattr(m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p:
                        type("R", (), {"content": "not json"})()})())
    out = extract_directives("some professor comment")
    assert len(out) == 1 and "some professor comment" in out[0]["issue"]
