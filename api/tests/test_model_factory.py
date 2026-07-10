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
