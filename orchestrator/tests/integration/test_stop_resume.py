"""SIGTERM handler writes paused event; verify the contract."""
import json
import signal
import sys

import pytest

pytestmark = pytest.mark.integration


def test_sigterm_handler_writes_paused_event_and_exits(tmp_path, monkeypatch):
    from orchestrator.__main__ import _install_sigterm_handler

    events_file = tmp_path / "events.jsonl"

    class _Appender:
        def __init__(self, p): self.p = p; self._closed = False
        def write(self, obj):
            with self.p.open("a") as f:
                f.write(json.dumps(obj) + "\n")
        def close(self): self._closed = True

    appender = _Appender(events_file)
    current = {"module": "M3"}

    exited = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exited.append(code))

    _install_sigterm_handler(appender, current)
    handler = signal.getsignal(signal.SIGTERM)
    handler(signal.SIGTERM, None)

    lines = events_file.read_text().splitlines()
    assert len(lines) == 1
    paused = json.loads(lines[0])
    assert paused["type"] == "paused"
    assert paused["module"] == "M3"
    assert paused["reason"] == "user_stop"
    assert exited == [0]
    assert appender._closed is True
