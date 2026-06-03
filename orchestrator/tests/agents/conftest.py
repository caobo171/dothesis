"""Overrides autouse fixtures for unit tests in orchestrator/tests/agents/.

The top-level conftest's _bind_db fixture requires the app module which isn't
needed for pure orchestrator.agents unit tests. Tests here use direct
monkeypatching instead.
"""
import pytest


@pytest.fixture(autouse=False)
def _bind_db(request, pg_url=None, monkeypatch=None):
    """Override the autouse fixture from parent conftest — make it opt-in.

    Tests in orchestrator/tests/agents/ are isolated unit tests using mocks,
    so they don't need a real DB. The parent conftest._bind_db is autouse=True,
    which forces it on all tests. By redefining it here with autouse=False,
    we shadow it for this subtree.
    """
    # No-op — tests that need the fixture can request it explicitly.
    pass


@pytest.fixture(autouse=True)
def _clear_agent_caches():
    """Reset the process-wide card / list-item caches before every test.

    The caches in orchestrator.agents.base persist across tests (module-
    level dicts), so a test that populates the cache for (M1, "field",
    partial={}) would cause a subsequent test using the same key to skip
    its LLM mock entirely and get the cached entry instead. Autouse-clear
    keeps each test deterministic without every test having to remember.
    """
    from orchestrator.agents import base as _agent_base
    _agent_base._card_cache.clear()
    _agent_base._list_cache.clear()
    yield
