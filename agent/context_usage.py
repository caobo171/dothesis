"""Context-window accounting shared by runtime streaming and the chat UI.

Billing adds every model call in a turn. Context occupancy does not: it is the
input size of the latest call. This module only owns the stable compaction
threshold attached to each compiled deep agent.
"""

from __future__ import annotations

from threading import Lock


DEFAULT_COMPACT_AT_TOKENS = 170_000
_PROFILE_TRIGGER_FRACTION = 0.85
_THRESHOLDS_BY_AGENT_ID: dict[int, int] = {}
_REGISTRY_LOCK = Lock()


def compact_at_tokens(model: object) -> int:
    """Return the automatic summarization trigger used by deepagents."""
    profile = getattr(model, "profile", None)
    max_input = (
        profile.get("max_input_tokens")
        if isinstance(profile, dict)
        else None
    )
    # bool is an int subclass but cannot describe a context window.
    if isinstance(max_input, int) and not isinstance(max_input, bool) and max_input > 0:
        return int(max_input * _PROFILE_TRIGGER_FRACTION)
    return DEFAULT_COMPACT_AT_TOKENS


def register_agent_compact_threshold(agent: object, tokens: int) -> None:
    """Associate a compiled agent with the threshold of its resolved model."""
    threshold = tokens if isinstance(tokens, int) and tokens > 0 else DEFAULT_COMPACT_AT_TOKENS
    with _REGISTRY_LOCK:
        _THRESHOLDS_BY_AGENT_ID[id(agent)] = threshold


def agent_compact_at_tokens(agent: object) -> int:
    """Read a compiled agent threshold, falling back exactly like deepagents."""
    with _REGISTRY_LOCK:
        return _THRESHOLDS_BY_AGENT_ID.get(id(agent), DEFAULT_COMPACT_AT_TOKENS)
