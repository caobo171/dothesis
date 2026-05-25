"""Shared fixtures for orchestrator integration tests.

Uses MemorySaver (no Postgres) so individual integration tests don't need
testcontainers. Concurrency & migration tests still use the real DB.
"""
from unittest.mock import MagicMock

import pytest
from langgraph.checkpoint.memory import MemorySaver


@pytest.fixture
def memory_checkpointer():
    return MemorySaver()


@pytest.fixture
def fake_llm_factory():
    def _make(*responses: str):
        llm = MagicMock()
        if len(responses) == 1:
            llm.invoke.return_value.content = responses[0]
        else:
            llm.invoke.side_effect = [_msg(r) for r in responses]
        return llm
    return _make


def _msg(content: str):
    from langchain_core.messages import AIMessage
    return AIMessage(content=content)
