from agent.context_usage import (
    DEFAULT_COMPACT_AT_TOKENS,
    agent_compact_at_tokens,
    compact_at_tokens,
    register_agent_compact_threshold,
)


class _Model:
    def __init__(self, profile=None):
        self.profile = profile


def test_profile_context_window_uses_deepagents_85_percent_trigger():
    assert compact_at_tokens(_Model({"max_input_tokens": 1_000_000})) == 850_000


def test_missing_or_malformed_profile_uses_deepagents_fallback():
    assert compact_at_tokens(_Model()) == DEFAULT_COMPACT_AT_TOKENS == 170_000
    assert compact_at_tokens(_Model({"max_input_tokens": "1000000"})) == 170_000
    assert compact_at_tokens(object()) == 170_000


def test_compiled_agent_threshold_registry_defaults_then_round_trips():
    compiled_agent = object()
    assert agent_compact_at_tokens(compiled_agent) == DEFAULT_COMPACT_AT_TOKENS

    register_agent_compact_threshold(compiled_agent, 850_000)

    assert agent_compact_at_tokens(compiled_agent) == 850_000
