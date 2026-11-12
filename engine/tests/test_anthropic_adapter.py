#!/usr/bin/env python3
"""Claude draft adapter (utils/anthropic_adapter.py) and the anthropic draft route.

No network: the SDK client is swapped for a fake whose messages.stream()
returns a canned final message.
"""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import default_draft_model, draft_llm_route  # noqa: E402
from utils.anthropic_adapter import AnthropicChatModel  # noqa: E402


def _message(text="hello", stop_reason="end_turn", input_tokens=100, output_tokens=20,
             cache_read=0, cache_write=0):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model="claude-haiku-4-5-20251001",
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens,
                              cache_read_input_tokens=cache_read,
                              cache_creation_input_tokens=cache_write),
    )


class _FakeStream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class _FakeClient:
    def __init__(self, message):
        self.requests = []
        self.messages = SimpleNamespace(stream=self._stream)
        self._msg = message

    def _stream(self, **request):
        self.requests.append(request)
        return _FakeStream(self._msg)


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DOTHESIS_LLM_CACHE", "0")
    monkeypatch.delenv("DRAFT_LLM_ROUTE", raising=False)
    monkeypatch.delenv("DRAFT_MODEL", raising=False)
    monkeypatch.delenv("DRAFT_MAX_OUTPUT_TOKENS", raising=False)


def _adapter(message):
    model = AnthropicChatModel("claude-haiku-4-5")
    model.client = _FakeClient(message)
    return model


def test_draft_route_inherits_the_orchestrator_route(env, monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "anthropic")
    assert draft_llm_route() == "anthropic"
    assert default_draft_model() == "claude-haiku-4-5"


def test_missing_key_fails_at_construction(env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        AnthropicChatModel("claude-haiku-4-5")


def test_returns_gemini_shape_with_summed_prompt_tokens(env):
    model = _adapter(_message(text="Chapter text", input_tokens=50, cache_read=900, cache_write=10))
    r = model.generate_content("write", generation_config={"max_output_tokens": 4000})
    assert r.text == "Chapter text"
    assert r.candidates[0].content.parts[0].text == "Chapter text"
    assert r.candidates[0].finish_reason == "STOP"
    # Anthropic's input_tokens excludes cache traffic; the meter wants the total.
    assert r.usage_metadata.prompt_token_count == 960
    assert r.usage_metadata.cached_content_token_count == 900
    req = model.client.requests[0]
    assert req["max_tokens"] == 4000 and "temperature" not in req


def test_default_budget_is_the_chapter_budget(env):
    model = _adapter(_message())
    model.generate_content("write")
    assert model.client.requests[0]["max_tokens"] == 32768


def test_json_mode_strips_fences_and_flags_truncation(env):
    model = _adapter(_message(text='```json\n{"a": 1}\n```', stop_reason="max_tokens"))
    r = model.generate_content("give json", generation_config={"response_mime_type": "application/json"})
    assert r.text == '{"a": 1}'
    assert r.finish_reason == "MAX_TOKENS"
    assert "JSON" in model.client.requests[0]["system"]


def test_refusal_maps_to_safety(env):
    r = _adapter(_message(text="", stop_reason="refusal")).generate_content("x")
    assert r.finish_reason == "SAFETY"
