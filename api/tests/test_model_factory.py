"""Provider-routing factory (F10). No network: assert constructed client config only.

Task 1 covers the native route (Google default / Anthropic when a key is present); Task 2
adds the OpenRouter route. The native construction must match runtime._default_model
byte-for-byte at default settings (drop-in factory, no behavior change)."""
from agent.model_factory import ModelSpec, make_model, spec_from_env


def test_native_google_by_default(monkeypatch):
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # ChatGoogleGenerativeAI validates a key is present at construction (no
    # network). A dummy key keeps this offline while proving the config.
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    m = make_model(spec_from_env())
    assert m.__class__.__name__ == "ChatGoogleGenerativeAI"


def test_native_anthropic_when_key_present(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "native")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "claude-haiku-4-5")
    m = make_model(spec_from_env())
    assert m.__class__.__name__ == "ChatAnthropic"


def test_spec_from_env_defaults(monkeypatch):
    # Byte-for-byte with runtime._default_model: gemini-3.5-flash @ temp 0.4,
    # max_tokens 8000, native route, no fallbacks.
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_TEMPERATURE", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_MAX_TOKENS", raising=False)
    spec = spec_from_env()
    assert spec.route == "native"
    assert spec.model == "gemini-3.5-flash"
    assert spec.fallbacks == []
    assert spec.temperature == 0.4
    assert spec.max_tokens == 8000


def test_spec_anthropic_default_model_when_key(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "native")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    assert spec_from_env().model == "claude-sonnet-4-6"


def test_native_google_construction_matches_default(monkeypatch):
    # Gemini gets temperature but NOT max_tokens (matches runtime._default_model).
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    m = make_model(ModelSpec(route="native", model="gemini-3.5-flash"))
    assert m.temperature == 0.4


def test_unknown_route_raises():
    import pytest
    with pytest.raises(ValueError):
        make_model(ModelSpec(route="bogus"))


# -- Task 2: OpenRouter route ------------------------------------------------
# langchain_openai is an eval/openrouter-only dep and is NOT installed in the
# test env (the native route never touches it). Inject a fake module so we can
# assert the *config contract* the constructor receives without the dep / network.
def _install_fake_chatopenai(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            # Mirror the attributes the real ChatOpenAI stores, so asserts that
            # read them (openai_api_base/extra_body/model_kwargs) still work.
            self.model = kwargs.get("model")
            self.openai_api_base = kwargs.get("base_url")
            self.extra_body = kwargs.get("extra_body")
            self.model_kwargs = kwargs.get("model_kwargs")

    fake_mod = types.ModuleType("langchain_openai")
    fake_mod.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_mod)
    return captured


def test_openrouter_route_config(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.delenv("DOTHESIS_OPENROUTER_DATA_POLICY", raising=False)
    captured = _install_fake_chatopenai(monkeypatch)
    spec = ModelSpec(route="openrouter", model="qwen3.6-plus",
                     fallbacks=["gpt-5.4-mini", "gemini-3.5-flash"])
    m = make_model(spec)
    assert "openrouter.ai" in str(m.openai_api_base)
    body = m.extra_body or {}
    # Primary first, then the fallback cascade — OpenRouter fails over in order.
    assert body["models"] == ["qwen3.6-plus", "gpt-5.4-mini", "gemini-3.5-flash"]
    # Student PII must not be trained on / logged by downstream providers.
    assert body["provider"]["data_collection"] == "deny"
    assert body["provider"]["allow_fallbacks"] is True
    # OpenAI-compatible streaming reports usage only when asked — the ledger needs it.
    assert (m.model_kwargs.get("stream_options") or {}).get("include_usage") is True


def test_openrouter_data_policy_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setenv("DOTHESIS_OPENROUTER_DATA_POLICY", "allow")
    captured = _install_fake_chatopenai(monkeypatch)
    m = make_model(ModelSpec(route="openrouter", model="qwen"))
    assert m.extra_body["provider"]["data_collection"] == "allow"
    assert m.extra_body["models"] == ["qwen"]


def test_openrouter_requires_key(monkeypatch):
    import pytest
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # Fail fast at build time on a misconfigured route (missing key), before any
    # attempt to import/construct the client.
    with pytest.raises(RuntimeError):
        make_model(ModelSpec(route="openrouter", model="qwen"))


# -- Ofox gateway route (OpenAI-compatible; the cost/quality lever) ----------
def test_ofox_route_config(monkeypatch):
    monkeypatch.setenv("OFOX_API_KEY", "sk-of-test")
    captured = _install_fake_chatopenai(monkeypatch)
    m = make_model(ModelSpec(route="ofox", model="google/gemini-2.5-flash"))
    assert "api.ofox.ai/v1" in str(m.openai_api_base)
    assert captured["model"] == "google/gemini-2.5-flash"
    assert captured["api_key"] == "sk-of-test"
    # OpenAI-compatible streaming reports usage only when asked — the ledger needs it.
    assert (m.model_kwargs.get("stream_options") or {}).get("include_usage") is True


def test_ofox_requires_key(monkeypatch):
    monkeypatch.delenv("OFOX_API_KEY", raising=False)
    import pytest
    with pytest.raises(RuntimeError, match="OFOX_API_KEY"):
        make_model(ModelSpec(route="ofox", model="google/gemini-2.5-flash"))


def test_spec_from_env_ofox_default_model(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    spec = spec_from_env()
    assert spec.route == "ofox"
    assert spec.model == "google/gemini-2.5-flash"


# --- A: vision capability fields (headless convergence spec §2) -------------
from agent.model_factory import make_vision_model, model_supports_vision


def test_supports_vision_lookup_fail_closed():
    # FAIL-CLOSED is the load-bearing property: an unknown id must read as
    # text-only, so the worst drift outcome is a needless transcription —
    # never Gemini media blocks shipped into an OpenAI-compat endpoint
    # (design-doc defect 1's failure shape).
    assert model_supports_vision("gemini-3.5-flash") is True
    assert model_supports_vision("google/gemini-2.5-flash") is True
    assert model_supports_vision("claude-sonnet-4-6") is True
    assert model_supports_vision("qwen/qwen-plus") is False
    assert model_supports_vision("qwen-plus") is False
    assert model_supports_vision("some-future-model") is False
    assert model_supports_vision("") is False


def test_spec_from_env_derives_vision_fields(monkeypatch):
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.setenv("DOTHESIS_AGENT_MODEL", "qwen/qwen-plus")
    monkeypatch.delenv("DOTHESIS_VISION_MODEL", raising=False)
    spec = spec_from_env()
    assert spec.supports_vision is False
    assert spec.vision_model == ""  # "" = resolve at make_vision_model time


def test_make_vision_model_text_only_brain_defaults_to_gemini(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.delenv("OFOX_API_KEY", raising=False)
    spec = ModelSpec(route="native", model="qwen-plus", supports_vision=False)
    m = make_vision_model(spec)
    assert m.__class__.__name__ == "ChatGoogleGenerativeAI"
    assert "gemini-2.5-flash" in m.model


def test_make_vision_model_ofox_prefixes_and_points_at_gateway(monkeypatch):
    monkeypatch.setenv("OFOX_API_KEY", "ok-test")
    spec = ModelSpec(route="ofox", model="qwen/qwen-plus",
                     vision_model="gemini-2.5-flash", supports_vision=False)
    m = make_vision_model(spec)
    assert "google/gemini-2.5-flash" in m.model  # Ofox needs provider-prefixed ids
