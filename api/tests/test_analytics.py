"""Unit tests for the best-effort PostHog emit layer (F5 Task 1).

These assert the three invariants that keep analytics from ever breaking a turn:
no-op when unconfigured, swallow SDK errors, and forward to capture() when a
client exists. All three stub `analytics._client` so no real PostHog is touched.
"""
from app import analytics


def test_emit_noop_without_key(monkeypatch):
    monkeypatch.setattr(analytics, "_client", lambda: None)  # unconfigured
    analytics.emit("x", "u", {"a": 1})   # must not raise


def test_emit_swallows_sdk_errors(monkeypatch):
    class _Boom:
        def capture(self, *a, **k):
            raise RuntimeError("posthog down")

    monkeypatch.setattr(analytics, "_client", lambda: _Boom())
    analytics.emit("x", "u", {"a": 1})   # must not raise


def test_emit_calls_capture_when_configured(monkeypatch):
    seen = {}

    class _Ok:
        def capture(self, distinct_id=None, event=None, properties=None, **k):
            seen.update(distinct_id=distinct_id, event=event, properties=properties)

    monkeypatch.setattr(analytics, "_client", lambda: _Ok())
    analytics.emit("module_status_changed", "user-1", {"module": "M1"})
    assert seen["event"] == "module_status_changed" and seen["distinct_id"] == "user-1"
