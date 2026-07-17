"""score_thesis(include_judge=False) — the deterministic spine for the certificate."""
import pytest


def test_include_judge_false_skips_judge_dims():
    from quality.rubric import score_thesis
    r = score_thesis({}, include_judge=False)
    names = {d["name"] for d in r["dimensions"]}
    assert "methodology" not in names and "writing" not in names
    # deterministic dims still present
    assert {"structure", "citations", "stats_validity", "coherence", "similarity",
            "source_verification"} <= names


def test_include_judge_false_constructs_no_llm(monkeypatch):
    import orchestrator.tools.m5_writing as _m5
    monkeypatch.setattr(_m5, "_get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no LLM allowed")))
    from quality.rubric import score_thesis
    r = score_thesis({"m1_topic": {"research_title": "X"}}, include_judge=False)
    assert "blocking" in r  # succeeded without touching the judge


def test_include_judge_default_true_has_judge(monkeypatch):
    import orchestrator.tools.m5_writing as _m5
    monkeypatch.setattr(_m5, "_get_llm",
                        lambda: type("L", (), {"invoke": lambda self, p: type("R", (), {"content": '{"score":0.8,"findings":[]}'})()})())
    from quality.rubric import score_thesis
    names = {d["name"] for d in score_thesis({})["dimensions"]}
    assert "methodology" in names and "writing" in names
