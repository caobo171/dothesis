"""Provider-routing factory (F10). No network: assert constructed client config only.

Task 1 covers the native route (Google default / Anthropic when a key is present); Task 2
adds the OpenRouter route. The native construction must match runtime._default_model
byte-for-byte at default settings (drop-in factory, no behavior change)."""
from agent.model_factory import ModelSpec, make_model, spec_from_env


def test_native_google_when_route_requested(monkeypatch):
    # Was "…by_default". The default route moved to openai on 2026-08-03, so
    # native is now an explicitly-chosen route rather than the fallback. What it
    # BUILDS is unchanged, which is what this still pins.
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "native")
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
    # The no-env default is openai/gpt-5.6-luna (2026-08-03). It was
    # native/gemini-3.5-flash, which no deployment had run since the OpenAI
    # cutover — a default nobody exercised while looking like the blessed path.
    # temp 0.4 / max_tokens 8000 / no fallbacks are unchanged.
    monkeypatch.delenv("DOTHESIS_MODEL_ROUTE", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_TEMPERATURE", raising=False)
    monkeypatch.delenv("DOTHESIS_MODEL_MAX_TOKENS", raising=False)
    spec = spec_from_env()
    assert spec.route == "openai"
    assert spec.model == "gpt-5.6-luna"
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
    assert spec.model == "bailian/qwen-plus"


def test_ofox_default_is_cheaper_than_the_credit_baseline():
    """The PROPERTY this default exists for: the ofox default must bill BELOW 1.0.

    PACKAGES in api/app/pricing.py are sized on "1 pack ≈ 1 run". Once
    credit_multiplier reads quality/model_prices.py instead of substring-matching
    names (f64bf79), the old defaults price far above that assumption:
    gemini-3.5-flash → ~12.9x (a Starter pack buys ~1/13 of a run) and the previous
    ofox default google/gemini-2.5-flash → ~3.2x (the gateway RESELLS 2.5-flash at
    0.30/2.50, not Google's native 0.15/0.60 baseline). qwen-plus at 0.12/0.29 is
    the only default that keeps the packs honest without re-tuning them.

    Asserted as an inequality against the baseline, not a literal: if a future price
    update pushes the default above baseline, the packs are wrong again and this
    must fail — that is the whole point of the model choice.
    """
    from app.pricing import credit_multiplier

    assert credit_multiplier("bailian/qwen-plus") < 1.0
    # The two defaults this one replaces, pinned so the reason stays legible.
    # Rebased 2026-08-02 with the BASELINE_MODEL price correction:
    #   - google/gemini-2.5-flash was >3.0 ONLY because the baseline row was
    #     3.24x too cheap. Google publishes 0.30/2.50, so the gateway id and the
    #     native id now price identically at ~1.0x and the ">3.0" premise (a
    #     resale markup over native) describes a gap that no longer exists.
    #   - gemini-3.5-flash 12.86x -> 3.97x by the same 3.24x rescale.
    # The inequality that carries the actual meaning — the default must stay
    # BELOW baseline or the packs are wrong — is the first assert, unchanged.
    assert credit_multiplier("google/gemini-2.5-flash") >= 1.0
    assert credit_multiplier("gemini-3.5-flash") > 3.0


def test_ofox_default_is_text_only_so_vision_routes_to_the_sidecar(monkeypatch):
    """qwen-plus is a text-only brain: image turns MUST go to the Gemini vision
    sidecar (make_vision_model), never ship media blocks at qwen. Making it the
    default is what puts the sidecar on the production path, so pin it here."""
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "ofox")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("DOTHESIS_VISION_MODEL", raising=False)
    spec = spec_from_env()
    assert spec.supports_vision is False
    assert spec.vision_model == ""  # "" = resolve the Gemini sidecar at call time


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


def test_make_vision_model_never_hands_a_claude_id_to_the_gemini_client(monkeypatch):
    # supports_vision=True must NOT make the sidecar echo the brain's own id:
    # make_vision_model always returns ChatGoogleGenerativeAI, so a Claude id
    # here would construct fine and then fail at invoke. A brain that can see
    # skips this factory entirely (build_user_message sends native blocks).
    monkeypatch.setenv("GOOGLE_API_KEY", "test")
    monkeypatch.delenv("OFOX_API_KEY", raising=False)
    spec = ModelSpec(route="native", model="claude-sonnet-4-6", supports_vision=True)
    m = make_vision_model(spec)
    assert "claude" not in m.model.lower()
    assert "gemini" in m.model.lower()


def test_make_vision_model_ofox_prefixes_and_points_at_gateway(monkeypatch):
    monkeypatch.setenv("OFOX_API_KEY", "ok-test")
    spec = ModelSpec(route="ofox", model="qwen/qwen-plus",
                     vision_model="gemini-2.5-flash", supports_vision=False)
    m = make_vision_model(spec)
    assert "google/gemini-2.5-flash" in m.model  # Ofox needs provider-prefixed ids


def test_ofox_docstring_does_not_carry_the_disproven_cache_caveat():
    # Measured live 2026-07-16 via scripts/probe_prompt_cache.py against the real
    # agent.runtime.SYSTEM_PROMPT: 3328/3456 input tokens cached on turn 2. The old
    # docstring's "may NOT get the ~90% input cache discount here / use route=native
    # if input caching matters" argued against the route the project is adopting, on
    # a premise that is now false. This test pins the correction so it can't regress.
    from agent.model_factory import _ofox
    doc = _ofox.__doc__ or ""
    assert "may NOT get" not in doc
    assert "use route=native for that provider instead" not in doc
    # It must cite the reproduction, not just drop the claim.
    assert "probe_prompt_cache" in doc
    assert "3328" in doc


def test_openai_route_disables_reasoning_so_function_tools_work(monkeypatch):
    """gpt-5.6-* reasons by default, and OpenAI rejects reasoning + function
    tools on /v1/chat/completions:

        400 "Function tools with reasoning_effort are not supported for
             gpt-5.6-luna in /v1/chat/completions. To use function tools, use
             /v1/responses or set reasoning_effort to 'none'."

    We never send reasoning_effort — langchain omits it when None — so the value
    being rejected is the model's server-side default. That makes this invisible
    on text-only calls and fatal on every tool-using one, i.e. every agent turn.
    Verified live: with this set the same bind_tools call succeeds.
    """
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    captured = _install_fake_chatopenai(monkeypatch)
    make_model(ModelSpec(route="openai", model="gpt-5.6-luna"))
    assert captured["reasoning_effort"] == "none"
    # Guard the other two route incompatibilities at the same time — all three
    # are "params the Ofox gateway was silently normalising away".
    assert "max_tokens" not in captured
    assert "temperature" not in captured
