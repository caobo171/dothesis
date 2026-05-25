"""Smoke tests for the auto-mode subprocess entrypoint."""
import json
import signal
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_help_flag_works():
    res = subprocess.run(
        [sys.executable, "-m", "orchestrator", "--help"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode == 0
    assert "--auto-draft" in res.stdout
    assert "--resume-run-id" in res.stdout


def test_missing_required_args_errors():
    res = subprocess.run(
        [sys.executable, "-m", "orchestrator", "--auto-draft"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    assert res.returncode != 0


def test_argparse_routes_auto_vs_resume(tmp_path):
    from orchestrator.__main__ import build_arg_parser
    p = build_arg_parser()
    args = p.parse_args([
        "--auto-draft", "--project-id", "x", "--user-id", "y",
        "--workdir", str(tmp_path), "--brief-json", str(tmp_path / "b.json"),
    ])
    assert args.auto_draft is True
    assert args.resume_run_id is None

    args = p.parse_args(["--resume-run-id", "abc", "--workdir", str(tmp_path)])
    assert args.resume_run_id == "abc"
    assert args.auto_draft is False


def test_sigterm_handler_writes_paused_event(tmp_path, monkeypatch):
    from orchestrator.__main__ import _install_sigterm_handler

    events = tmp_path / "events.jsonl"

    class _Appender:
        def __init__(self, p): self.p = p
        def write(self, obj):
            with self.p.open("a") as f:
                f.write(json.dumps(obj) + "\n")
        def close(self): pass

    current = {"module": "M3"}
    exits = []
    monkeypatch.setattr(sys, "exit", lambda code=0: exits.append(code))

    _install_sigterm_handler(_Appender(events), current)
    handler = signal.getsignal(signal.SIGTERM)
    handler(signal.SIGTERM, None)

    assert events.exists()
    line = json.loads(events.read_text().strip())
    assert line["type"] == "paused"
    assert line["module"] == "M3"
    assert exits == [0]
