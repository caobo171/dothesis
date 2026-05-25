from orchestrator.tools.m1_topic import suggest_topics, refine_title


class _FakeLLM:
    """Returns deterministic strings — no network call."""
    def __init__(self, response: str):
        self._response = response

    def invoke(self, prompt):
        from langchain_core.messages import AIMessage
        return AIMessage(content=self._response)


def test_suggest_topics_returns_list(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _FakeLLM('["Topic A", "Topic B", "Topic C"]'),
    )
    out = suggest_topics.invoke({"field": "Marketing"})
    assert out == ["Topic A", "Topic B", "Topic C"]


def test_suggest_topics_handles_malformed_response(monkeypatch):
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _FakeLLM("not json"),
    )
    out = suggest_topics.invoke({"field": "Marketing"})
    assert out == []


def test_refine_title_passes_seed_to_llm(monkeypatch):
    captured = {}
    class _Capture(_FakeLLM):
        def invoke(self, prompt):
            captured["prompt"] = str(prompt)
            return super().invoke(prompt)
    monkeypatch.setattr(
        "orchestrator.tools.m1_topic._get_llm",
        lambda: _Capture("The Impact of X on Y at Z"),
    )
    out = refine_title.invoke({"seed": "X and Y in Vietnam"})
    assert out == "The Impact of X on Y at Z"
    assert "X and Y in Vietnam" in captured["prompt"]
