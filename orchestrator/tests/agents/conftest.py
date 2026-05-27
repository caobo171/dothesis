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
