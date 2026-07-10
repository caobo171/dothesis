"""Config-contract tests for the orchestrator ENGINE's shared LLM factory.

Mirrors agent/model_factory's provider routing (see test_model_factory.py) but
for the engine: ORCHESTRATOR_LLM_ROUTE picks native Gemini (default, unchanged)
vs the Ofox OpenAI-compatible gateway. No network — we assert the constructed
client config only.

The native construction MUST match the ~10 `_get_llm()` sites byte-for-byte
(Gemini gets model + temperature, nothing else) so flipping the route is the
only change; with no new env the engine behaves exactly as before.
"""
from orchestrator.llm import get_orchestrator_llm


def test_native_default_builds_gemini(monkeypatch):
    monkeypatch.delenv("ORCHESTRATOR_LLM_ROUTE", raising=False)
    monkeypatch.delenv("ORCHESTRATOR_LLM_MODEL", raising=False)
    # ChatGoogleGenerativeAI validates a key at construction (no network); a
    # dummy key keeps this offline while proving the native route is unchanged.
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    m = get_orchestrator_llm()
    assert m.__class__.__name__ == "ChatGoogleGenerativeAI"
    # Gemini gets temperature (default 0.4), NOT max_tokens — matches the sites.
    assert m.temperature == 0.4


def test_native_passes_through_per_site_temperature(monkeypatch):
    # Sites call get_orchestrator_llm(temperature=0.2) etc.; that must reach the
    # Gemini client so per-tool temperatures survive the refactor.
    monkeypatch.delenv("ORCHESTRATOR_LLM_ROUTE", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    m = get_orchestrator_llm(temperature=0.2)
    assert m.temperature == 0.2


# -- Ofox gateway route (OpenAI-compatible) ----------------------------------
# langchain_openai is a gateway-only dep and is NOT installed in the test env
# (the native route never touches it). Inject a fake module so we can assert the
# config contract the constructor receives, without the dep or a network call.
def _install_fake_chatopenai(monkeypatch):
    import sys
    import types

    captured: dict = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            # Mirror the attributes the real ChatOpenAI stores, so asserts that
            # read them (openai_api_base/model_kwargs) still work.
            self.model = kwargs.get("model")
            self.openai_api_base = kwargs.get("base_url")
            self.model_kwargs = kwargs.get("model_kwargs")

    fake_mod = types.ModuleType("langchain_openai")
    fake_mod.ChatOpenAI = FakeChatOpenAI
    monkeypatch.setitem(sys.modules, "langchain_openai", fake_mod)
    return captured


def test_ofox_route_config(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "ofox")
    monkeypatch.setenv("OFOX_API_KEY", "sk-of-test")
    captured = _install_fake_chatopenai(monkeypatch)
    m = get_orchestrator_llm(model="google/gemini-2.5-flash")
    assert "api.ofox.ai/v1" in str(m.openai_api_base)
    assert captured["model"] == "google/gemini-2.5-flash"
    assert captured["api_key"] == "sk-of-test"
    # OpenAI-compatible streaming reports usage only when asked — the ledger needs it.
    assert (m.model_kwargs.get("stream_options") or {}).get("include_usage") is True


def test_ofox_requires_key(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "ofox")
    monkeypatch.delenv("OFOX_API_KEY", raising=False)
    import pytest
    # Fail fast at build time on a misconfigured route (missing key), before any
    # attempt to import/construct the client.
    with pytest.raises(RuntimeError, match="OFOX_API_KEY"):
        get_orchestrator_llm(model="google/gemini-2.5-flash")


def test_unknown_route_raises(monkeypatch):
    monkeypatch.setenv("ORCHESTRATOR_LLM_ROUTE", "bogus")
    import pytest
    with pytest.raises(ValueError):
        get_orchestrator_llm()
