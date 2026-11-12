"""route=anthropic: every LLM surface runs on one ANTHROPIC_API_KEY.

No network anywhere — client construction is asserted on the langchain objects,
and the raw-SDK surfaces (draft adapter, citation planner, blog writer) get a
fake client whose messages.stream() returns a canned final message.
"""
from types import SimpleNamespace

import pytest

from agent.model_factory import (
    DEFAULT_CLAUDE_MODEL, ModelSpec, claude_accepts_temperature, make_model,
    make_vision_model, spec_from_env,
)


# -- fakes for the raw anthropic SDK ------------------------------------------

def _message(text="hello", stop_reason="end_turn", input_tokens=100, output_tokens=20,
             cache_read=0, cache_write=0, model="claude-haiku-4-5-20251001"):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        stop_reason=stop_reason,
        model=model,
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
def anthropic_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "anthropic")
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "anthropic")
    for var in ("DOTHESIS_AGENT_MODEL", "ORCHESTRATOR_LLM_MODEL", "DOTHESIS_VISION_MODEL",
                "DRAFT_LLM_ROUTE", "DRAFT_MODEL", "CITATION_PLANNER_MODEL", "BLOG_LLM_MODEL",
                "BLOG_LLM_PRICE_IN", "BLOG_LLM_PRICE_OUT", "DOTHESIS_VISION_FORCE_SIDECAR"):
        monkeypatch.delenv(var, raising=False)


# -- chat brain ---------------------------------------------------------------

def test_brain_defaults_to_cheapest_claude_with_vision(anthropic_env):
    spec = spec_from_env()
    assert spec.route == "anthropic"
    assert spec.model == DEFAULT_CLAUDE_MODEL == "claude-haiku-4-5"
    assert spec.supports_vision is True


def test_brain_builds_chat_anthropic_with_timeout_and_temperature(anthropic_env):
    m = make_model()
    assert m.__class__.__name__ == "ChatAnthropic"
    assert m.model == "claude-haiku-4-5"
    assert m.max_tokens == 8000
    # Haiku honours temperature, so the spec's 0.4 must reach it.
    assert m.temperature == 0.4
    # An explicit timeout: langchain's None default means "no timeout at all".
    assert m.default_request_timeout == 90.0


def test_brain_drops_temperature_on_tiers_that_reject_it(anthropic_env, monkeypatch):
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "claude-sonnet-5-5")
    m = make_model()
    assert m.model == "claude-sonnet-5-5"
    assert m.temperature is None


def test_brain_without_key_fails_at_construction(anthropic_env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        make_model()


@pytest.mark.parametrize("model,ok", [
    ("claude-haiku-4-5", True), ("claude-sonnet-4-6", True), ("claude-opus-4-5", True),
    ("claude-sonnet-5-5", False), ("claude-opus-5-5", False), ("claude-opus-4-7", False),
    ("claude-fable-5-1", False), ("claude-something-new", False),
])
def test_temperature_allow_list(model, ok):
    assert claude_accepts_temperature(model) is ok


# -- vision -------------------------------------------------------------------

def test_vision_goes_to_the_claude_brain_not_the_gemini_sidecar(anthropic_env):
    from agent.multimodal import detect_provider, resolve_vision

    assert detect_provider() == "anthropic"
    res = resolve_vision()
    assert (res.provider, res.use_sidecar) == ("anthropic", False)


def test_vision_sidecar_is_claude_even_with_a_leftover_gemini_vision_model(anthropic_env, monkeypatch):
    # A Claude-only box has no Google key; a stale DOTHESIS_VISION_MODEL=gemini-*
    # must not be sent to the Anthropic API either.
    monkeypatch.setenv("DOTHESIS_VISION_MODEL", "gemini-3.5-flash-lite")
    m = make_vision_model()
    assert m.__class__.__name__ == "ChatAnthropic"
    assert m.model == "claude-haiku-4-5"
    assert m.temperature == 0.2


def test_orchestrator_get_vision_llm_on_anthropic_route(anthropic_env):
    from orchestrator.llm import get_vision_llm

    m = get_vision_llm()
    assert m.__class__.__name__ == "ChatAnthropic"
    assert "claude" in m.model


def test_transcription_builds_anthropic_blocks(anthropic_env, monkeypatch):
    import agent.model_factory as mf
    from agent.multimodal import Attachment, _transcribe_via_vision

    seen = {}

    class _Vision:
        def invoke(self, msgs):
            seen["content"] = msgs[0].content
            return SimpleNamespace(content="| a | b |")

    monkeypatch.setattr(mf, "make_vision_model", lambda *a, **k: _Vision())
    att = Attachment(filename="loadings.png", mime_type="image/png", bytes=b"\x89PNG\r\n\x1a\nxx")
    assert _transcribe_via_vision(att) == "| a | b |"
    image = [b for b in seen["content"] if b.get("type") == "image"]
    assert image and image[0]["source"]["media_type"] == "image/png"


# -- orchestrator engine ------------------------------------------------------

def test_orchestrator_default_matches_the_brain(anthropic_env):
    from orchestrator.llm import resolve_orchestrator_model

    # Literal in orchestrator/llm.py (import-cycle), so pin it to the brain's.
    assert resolve_orchestrator_model() == DEFAULT_CLAUDE_MODEL


def test_orchestrator_builds_chat_anthropic(anthropic_env):
    from orchestrator.llm import get_orchestrator_llm

    m = get_orchestrator_llm(temperature=0.2)
    assert m.__class__.__name__ == "ChatAnthropic"
    assert m.temperature == 0.2  # m4_analysis's determinism is honoured on Haiku
    # Always a timeout — else the SDK refuses large non-streaming invoke()s.
    assert m.default_request_timeout == 600.0
    assert get_orchestrator_llm(timeout=20).default_request_timeout == 20.0


def test_orchestrator_drops_temperature_for_newer_tiers(anthropic_env, monkeypatch):
    from orchestrator.llm import get_orchestrator_llm

    monkeypatch.setenv("ORCHESTRATOR_LLM_MODEL", "claude-sonnet-5-5")
    assert get_orchestrator_llm(temperature=0.2).temperature is None


def test_orchestrator_without_key_fails_fast(anthropic_env, monkeypatch):
    from orchestrator.llm import get_orchestrator_llm

    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_orchestrator_llm()


def test_research_cache_key_separates_anthropic_proxies(anthropic_env, monkeypatch):
    from orchestrator.tools.research_cache import model_cache_key

    direct = model_cache_key("p")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example")
    proxied = model_cache_key("p")
    assert direct["route"] == "anthropic"
    assert direct["endpoint_sha256"] != proxied["endpoint_sha256"]


# -- draft engine adapter: engine/tests/test_anthropic_adapter.py (engine is not
#    importable as a package from this suite's path) ---------------------------


# -- M2 citation planner ------------------------------------------------------

def test_planner_defaults_to_claude_on_anthropic_route(anthropic_env):
    from orchestrator.tools.m2_literature import _AnthropicPlannerClient, _engine_model

    wrapped = _engine_model()
    assert isinstance(wrapped._inner, _AnthropicPlannerClient)
    assert wrapped.model_name == "claude-haiku-4-5"


def test_planner_refusal_reads_as_blocked(anthropic_env):
    from orchestrator.tools.m2_literature import _AnthropicPlannerClient

    planner = _AnthropicPlannerClient("claude-haiku-4-5", "sk-ant-test")
    planner._client = _FakeClient(_message(text="", stop_reason="refusal"))
    assert planner.generate_content("plan").candidates == []

    planner._client = _FakeClient(_message(text='```json\n{"q": []}\n```', input_tokens=7, cache_read=3))
    r = planner.generate_content("plan", generation_config={"response_mime_type": "application/json"})
    assert r.text == '{"q": []}'
    assert r.usage_metadata.prompt_token_count == 10


# -- blog writer --------------------------------------------------------------

def test_blog_writer_runs_on_claude_and_prices_at_haiku(anthropic_env):
    from app.blog.content.llm import LunaClient, default_model, usd_for

    assert default_model() == "claude-haiku-4-5"
    client = LunaClient(client=_FakeClient(_message(text='{"title": "x"}', input_tokens=1_000_000,
                                                    output_tokens=1_000_000)))
    c = client.complete_json("write a post as json")
    assert c.text == '{"title": "x"}'
    assert c.usd == pytest.approx(6.00)  # $1 in + $5 out per 1M
    assert usd_for(1_000_000, 0) == pytest.approx(1.00)


def test_blog_writer_still_defaults_to_luna_off_route(monkeypatch):
    from app.blog.content.llm import default_model, usd_for

    monkeypatch.delenv("ORCHESTRATOR_LLM_ROUTE", raising=False)
    monkeypatch.delenv("BLOG_LLM_MODEL", raising=False)
    monkeypatch.delenv("BLOG_LLM_PRICE_IN", raising=False)
    assert default_model() == "gpt-6-luna"
    assert usd_for(1_000_000, 0) == pytest.approx(0.10)


# -- billing ------------------------------------------------------------------

def test_claude_ids_bill_at_their_real_rate():
    from app.pricing import UNKNOWN_MODEL_MULTIPLIER, credit_multiplier

    for model in ("claude-haiku-4-5", "claude-haiku-4-5-20251001",
                  "claude-sonnet-5-5", "claude-opus-5-5"):
        assert credit_multiplier(model) != UNKNOWN_MODEL_MULTIPLIER, model
    assert credit_multiplier("claude-haiku-4-5") > credit_multiplier("gpt-6-luna")
