"""Route-independent token accounting (F10 Task 3).

The credit ledger (chat_v3) debits per token, so usage must read the same whether
the model is native (LangChain usage_metadata) or OpenAI-compatible
(usage.prompt_tokens/completion_tokens). No network — pure shape mapping."""
from agent.usage import extract_usage


def test_openai_shaped_usage():
    assert extract_usage({"usage": {"prompt_tokens": 100, "completion_tokens": 40}}) == {"in": 100, "out": 40}


def test_anthropic_langchain_usage_metadata():
    class Msg:
        usage_metadata = {"input_tokens": 12, "output_tokens": 7}
    assert extract_usage(Msg()) == {"in": 12, "out": 7}


def test_openai_usage_object_attribute():
    # An OpenAI-compatible chunk may carry usage as an attribute, not a dict key.
    class Chunk:
        usage = {"prompt_tokens": 5, "completion_tokens": 3}
    assert extract_usage(Chunk()) == {"in": 5, "out": 3}


def test_missing_usage_is_zero():
    assert extract_usage({}) == {"in": 0, "out": 0}


def test_none_is_zero():
    assert extract_usage(None) == {"in": 0, "out": 0}
