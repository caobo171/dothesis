"""Consumer auto-draft runs the deep agent over ALL five modules.

The partner report path scopes a run to the chapters it ordered; a thesis
cannot be scoped that way, so mode=full_thesis must clear required_modules
and must not apply the report-only chapter/grounding context vars.
"""
from app.headless_entry import _build_profile, _is_full_thesis


def test_full_thesis_requires_every_module():
    profile = _build_profile({"mode": "full_thesis", "topic": "X"})
    assert profile.required_modules is None
    assert profile.interactive is False


def test_full_thesis_gets_a_bigger_budget_than_a_report():
    full = _build_profile({"mode": "full_thesis", "topic": "X"})
    report = _build_profile({"depth": "analysis_report"})
    assert full.max_turns > report.max_turns
    assert full.wall_clock_s > report.wall_clock_s


def test_explicit_params_still_win_over_the_mode_default():
    profile = _build_profile({"mode": "full_thesis", "max_turns": 7,
                              "wall_clock_s": 60})
    assert profile.max_turns == 7 and profile.wall_clock_s == 60


def test_report_mode_is_unchanged():
    profile = _build_profile({"depth": "analysis_report"})
    assert profile.required_modules is not None


def test_mode_predicate():
    assert _is_full_thesis({"mode": "full_thesis"}) is True
    assert _is_full_thesis({"depth": "analysis_report"}) is False
    assert _is_full_thesis({}) is False


def test_seed_brief_writes_topic_and_language(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "AI in SMEs",
                                "language": "vi", "citation_style": "APA"})
    assert wrote is True
    m1 = store.load()["contextStore"]
    assert m1["research_title"] == "AI in SMEs"
    assert m1["language"] == "vi"
    # The raw brief is kept for audit under the seeding-only key.
    assert m1["user_context"]["citation_style"] == "APA"


def test_seed_brief_does_not_overwrite_an_existing_topic(tmp_path):
    from agent.state import ProjectStateStore
    from app.headless_entry import _seed_brief

    store = ProjectStateStore(tmp_path / "proj")
    store.commit_slice("M1", {"research_title": "Student's own title"},
                       reason="prior work")
    wrote = _seed_brief(store, {"mode": "full_thesis", "topic": "Something else"})
    assert wrote is False
    assert store.load()["contextStore"]["research_title"] == "Student's own title"


class _FakeStore:
    """Enough ProjectStateStore surface for main(): the seed write and the
    per-turn progress read. The real one is DB-backed and is not the unit here."""

    def __init__(self):
        self.commits = []
        self.state = {"contextStore": {}, "status": {}, "focus": "M1"}

    def load(self):
        return self.state

    def load_full_context_store(self):
        return {}

    def commit_slice(self, module, writes, reason=""):
        self.commits.append((module, writes, reason))


def _run_main(tmp_path, monkeypatch, params, *, exports=None):
    """Drive headless_entry.main() end to end with the DB and the agent stubbed.

    Everything main() needs is imported INSIDE the function, so patching the
    source modules is enough to keep the subprocess entrypoint off the database
    and off a real model."""
    import json
    import signal
    import sys
    import uuid

    from agent.headless import RunResult
    from app import headless_entry

    workdir = tmp_path / "wd"
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps(params), encoding="utf-8")

    monkeypatch.setattr("app.db.get_engine", lambda: None)
    monkeypatch.setattr("app.agent_state.DbProjectStateStore",
                        lambda *a, **k: _FakeStore())
    monkeypatch.setattr("agent.runtime.build_agent", lambda *a, **k: object())

    async def _fake_run(*a, **k):
        return RunResult(status="done", reason="roadmap_done", turns=3)

    monkeypatch.setattr("agent.headless.run_headless", _fake_run)
    monkeypatch.setattr(
        "app.partner_run.run_partner_export",
        lambda store, pid, p: (exports.append(p), {"sections": ["Intro"]})[1]
        if exports is not None else {"sections": ["Intro"]})

    monkeypatch.setattr(sys, "argv", [
        "headless_entry", "--project-id", str(uuid.uuid4()),
        "--job-id", str(uuid.uuid4()), "--workdir", str(workdir),
        "--params-json", str(params_path)])

    # main() installs a process-global SIGTERM handler; leaving it behind would
    # make every later test in this process exit(0) on SIGTERM.
    previous = signal.getsignal(signal.SIGTERM)
    try:
        rc = headless_entry.main()
    finally:
        signal.signal(signal.SIGTERM, previous)

    events = [json.loads(line) for line in
              (workdir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    return rc, events


def test_full_thesis_does_not_run_the_partner_export(tmp_path, monkeypatch):
    """C2: run_partner_export gates on assess_export_readiness against the
    4-chapter analysis_report default, so an EMPTY M4 turned a finished thesis
    into {"type": "error"} → Job failed → _charge_auto_run never reached: the
    student got the whole thesis free. The real full-thesis export is already
    written by the M5 done-hook (agent_state._auto_export_m5)."""
    exports = []
    rc, events = _run_main(tmp_path, monkeypatch,
                           {"mode": "full_thesis", "topic": "X",
                            "strict_gates": False},
                           exports=exports)
    assert exports == [], "the partner export must not run on consumer auto-draft"
    assert rc == 0
    types = [e["type"] for e in events]
    assert "job_done" in types and "error" not in types


def test_the_partner_path_still_exports(tmp_path, monkeypatch):
    """The guard is scoped to full_thesis: a partner report still composes the
    requested chapter subset through run_partner_export."""
    exports = []
    rc, events = _run_main(tmp_path, monkeypatch,
                           {"depth": "analysis_report", "language": "en",
                            "strict_gates": False},
                           exports=exports)
    assert rc == 0
    assert len(exports) == 1 and exports[0]["depth"] == "analysis_report"
    assert any(e["type"] == "job_done" and e.get("sections") == ["Intro"]
               for e in events)


def test_sigterm_writes_a_paused_event(tmp_path):
    """The monitor reads `paused` to mark a run resumable (job_runner.py:300).
    Without it, pausing an auto-draft leaves the Job stuck at `running`."""
    import signal

    from app.headless_entry import _install_pause_handler

    written = []

    class _Appender:
        def write(self, ev):
            written.append(ev)

    raised = []
    # signal.signal is process-global: leaving the runner's handler installed
    # would make every later test in this process exit(0) on SIGTERM, and that
    # failure would surface nowhere near its cause.
    previous = signal.getsignal(signal.SIGTERM)
    try:
        _install_pause_handler(_Appender())
        handler = signal.getsignal(signal.SIGTERM)
        assert handler is not previous, "handler was not installed"
        try:
            handler(signal.SIGTERM, None)
        except SystemExit as e:
            raised.append(e.code)
    finally:
        signal.signal(signal.SIGTERM, previous)

    assert written and written[0]["type"] == "paused"
    assert raised == [0]
