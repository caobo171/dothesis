"""F11 Task 4 — the between-session weekly nudge runner. Deps are injected so no
test touches a live DB or sends a real email (F0 boundary rule)."""
from datetime import datetime, timezone, timedelta

from app.jobs.weekly_nudge import run_weekly_nudge


class _Proj:
    def __init__(self, pid, state, owner, last=None, opt=True):
        self.id, self._state, self.owner_id = pid, state, owner
        self.last_nudge_at, self._opt = last, opt


def test_sends_to_due_optedin_only(monkeypatch):
    now = datetime(2026, 7, 10, tzinfo=timezone.utc)
    due = _Proj("p1", {"contextStore": {"thesis_timeline": {"milestones":
        [{"module": "M4", "label": "Data analysis", "start": "2026-07-01", "end": "2026-07-15"}]}},
        "focus": "M2", "status": {}}, owner="u1", last=None)
    recent = _Proj("p2", due._state, owner="u2", last=now - timedelta(days=1))
    sent = []
    res = run_weekly_nudge(
        db=None, mail_send=lambda to, subject, html: sent.append(to) or True, now=now,
        _projects=lambda db: [due, recent],
        _email_for=lambda db, uid: f"{uid}@x.com",
        _opted_in=lambda db, uid: True,
        _mark=lambda db, p, ts: setattr(p, "last_nudge_at", ts))
    assert res["sent"] == 1 and sent == ["u1@x.com"]
