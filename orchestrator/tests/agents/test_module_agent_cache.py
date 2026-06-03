"""Cache tests for ModuleAgent._generate_card_options and _generate_list_items.

Motivation: a live Gemini stall on `research_type` cards (12s timeout, see
production log) blocked a whole turn — AND the next turn would have done
the same call again because nothing in the partial state had changed. The
cache kills the repeat cost and removes a chance to hit an unhealthy
upstream at all.

These tests pin the cache contract:
  - identical (module, field, partial) → second call MUST NOT hit the LLM
  - different partial state → cache miss, LLM fires again
  - empty result NOT cached (caching [] would lock in a transient failure)
  - cache is isolated per (module, field) — M1's `field` doesn't poison M3's
"""
import json
from unittest.mock import MagicMock

import pytest

from orchestrator.agents import base as agent_base
from orchestrator.agents.m1_topic import M1Agent


@pytest.fixture(autouse=True)
def _clear_caches():
    """Each test starts with empty caches so order doesn't matter."""
    agent_base._card_cache.clear()
    agent_base._list_cache.clear()


def _stub_llm_returning(monkeypatch, cards: list[dict]) -> MagicMock:
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(cards)
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)
    return fake


def test_repeat_call_same_partial_does_not_hit_llm(monkeypatch):
    """The core promise: same (module, field, partial) twice → ONE LLM call.

    This is what fixes the live 12s-stall replay: even if the first call
    was slow, the cached options short-circuit every subsequent identical
    request."""
    cards = [{"value": "v1", "label": "L1", "description": "d1"}]
    fake = _stub_llm_returning(monkeypatch, cards)

    agent = M1Agent()
    partial = {"research_title": "AI in EdTech"}

    first = agent._generate_card_options("field", partial)
    second = agent._generate_card_options("field", partial)

    assert fake.invoke.call_count == 1
    # Same identity / content on the cached path.
    assert first == second
    assert len(first) == 1 and first[0].value == "v1"


def test_different_partial_state_misses_cache(monkeypatch):
    """When the user fills in another field, the seed context changes and
    we want fresh suggestions — the cache key MUST reflect the partial."""
    cards = [{"value": "v", "label": "L", "description": "d"}]
    fake = _stub_llm_returning(monkeypatch, cards)

    agent = M1Agent()
    agent._generate_card_options("field", {"research_title": "A"})
    agent._generate_card_options("field", {"research_title": "B"})

    assert fake.invoke.call_count == 2


def test_underscore_keys_in_partial_do_not_affect_cache_key(monkeypatch):
    """`_awaiting_field` and other underscore-prefixed bookkeeping fields
    change every turn but aren't part of the prompt context — they must
    be EXCLUDED from the cache key so otherwise-identical calls hit cache.
    """
    cards = [{"value": "v", "label": "L", "description": "d"}]
    fake = _stub_llm_returning(monkeypatch, cards)

    agent = M1Agent()
    agent._generate_card_options(
        "field", {"research_title": "X", "_awaiting_field": "field"})
    agent._generate_card_options(
        "field", {"research_title": "X", "_awaiting_field": "scope"})

    assert fake.invoke.call_count == 1


def test_empty_result_not_cached(monkeypatch):
    """If the LLM returns non-JSON or zero valid cards, the next call MUST
    retry (otherwise one transient parse failure would lock in [] forever
    for that field/partial pair)."""
    fake = MagicMock()
    fake.invoke.return_value.content = "not json at all"
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    agent._generate_card_options("field", {"research_title": "X"})
    agent._generate_card_options("field", {"research_title": "X"})

    assert fake.invoke.call_count == 2


def test_different_fields_have_separate_cache(monkeypatch):
    """`field` and `scope` are different cache entries even with the same
    partial. Regression guard: a too-loose key would return scope cards
    when the user is being asked about field."""
    cards = [{"value": "v", "label": "L", "description": "d"}]
    fake = _stub_llm_returning(monkeypatch, cards)

    agent = M1Agent()
    agent._generate_card_options("field", {"research_title": "X"})
    agent._generate_card_options("scope", {"research_title": "X"})

    assert fake.invoke.call_count == 2


def test_list_items_cache_works_independently(monkeypatch):
    """_generate_list_items shares the same caching mechanic but a
    separate dict (so a card cache eviction doesn't drop list seeds and
    vice versa)."""
    fake = MagicMock()
    fake.invoke.return_value.content = json.dumps(["item one", "item two"])
    monkeypatch.setattr(M1Agent, "_get_llm", lambda self: fake)

    agent = M1Agent()
    partial = {"research_title": "X", "research_type": "quantitative"}
    a = agent._generate_list_items("objectives", partial)
    b = agent._generate_list_items("objectives", partial)

    assert fake.invoke.call_count == 1
    assert a == b == ["item one", "item two"]
