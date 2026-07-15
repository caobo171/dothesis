"""Route-independent token accounting (F10 Task 3).

The credit ledger (chat_v3) debits per token, so usage must read the same whether
the model is native (LangChain usage_metadata) or OpenAI-compatible
(usage.prompt_tokens/completion_tokens). No network — pure shape mapping.

The strict-equality asserts below now include `cached_in`: the extractor stopped
throwing the cached-token count away (Ofox caches ~96% of our prefix — measured
2026-07-16). Equality is kept rather than loosened to subset checks on purpose —
this dict IS the billing contract, so an unnoticed new key is exactly what these
tests should fail on."""
from agent.usage import extract_usage


def test_openai_shaped_usage():
    assert extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 40}}) == {"in": 100, "out": 40, "cached_in": 0}


def test_anthropic_langchain_usage_metadata():
    class Msg:
        usage_metadata = {"input_tokens": 12, "output_tokens": 7}
    assert extract_usage(Msg()) == {"in": 12, "out": 7, "cached_in": 0}


def test_openai_usage_object_attribute():
    # An OpenAI-compatible chunk may carry usage as an attribute, not a dict key.
    class Chunk:
        usage = {"prompt_tokens": 5, "completion_tokens": 3}
    assert extract_usage(Chunk()) == {"in": 5, "out": 3, "cached_in": 0}


def test_missing_usage_is_zero():
    assert extract_usage({}) == {"in": 0, "out": 0, "cached_in": 0}


def test_none_is_zero():
    assert extract_usage(None) == {"in": 0, "out": 0, "cached_in": 0}


# -- Cached input tokens (measured real on Ofox/qwen-plus, 2026-07-16) --------
# `cached_in` is a SUBSET of `in`, never additional to it: OpenAI-compat reports
# prompt_tokens=3456 with prompt_tokens_details.cached_tokens=3328, and LangChain
# defines input_tokens as the sum of all input token types (cache_read included).
# Extracting it does not change billing — it makes the discount measurable.
def test_openai_compat_cached_tokens():
    u = extract_usage({"usage": {"prompt_tokens": 3456, "completion_tokens": 16,
                                 "prompt_tokens_details": {"cached_tokens": 3328}}})
    assert u == {"in": 3456, "out": 16, "cached_in": 3328}


def test_native_langchain_cache_read():
    class Msg:
        usage_metadata = {"input_tokens": 3456, "output_tokens": 16,
                          "input_token_details": {"cache_read": 3328}}
    assert extract_usage(Msg()) == {"in": 3456, "out": 16, "cached_in": 3328}


def test_cached_in_defaults_to_zero_when_absent():
    # Every provider that reports no cache stat must read as 0, not None — the
    # ledger/metrics arithmetic downstream must never see a non-int here.
    assert extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 40}})["cached_in"] == 0
    class Msg:
        usage_metadata = {"input_tokens": 12, "output_tokens": 7}
    assert extract_usage(Msg())["cached_in"] == 0
    assert extract_usage(None)["cached_in"] == 0
    assert extract_usage({})["cached_in"] == 0


def test_cached_in_never_exceeds_in():
    # Guards the subset semantic against a provider echoing a bogus count.
    u = extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 5,
                                 "prompt_tokens_details": {"cached_tokens": 9999}}})
    assert u["cached_in"] <= u["in"]
