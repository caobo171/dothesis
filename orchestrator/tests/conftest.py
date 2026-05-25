"""Shared pytest fixtures for orchestrator tests."""
import pytest


@pytest.fixture
def fake_llm_responses():
    """Override per-test to inject responses into FakeListChatModel."""
    return ["test response"]
