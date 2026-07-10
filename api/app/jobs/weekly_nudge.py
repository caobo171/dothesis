"""Weekly thesis nudge — the between-session accompaniment. Runnable via
`python -m app.jobs.weekly_nudge` from the deploy's cron (no in-app scheduler).
Idempotent (6-day window). Best-effort per project; opt-in honored at send time.

Layering: this is app-side, so importing agent.timeline (pure) is fine — the
forbidden direction is agent -> app, not app -> agent. The DB/mail wiring lives
in swappable `_default_*` helpers so the injected-deps signature is fully
testable without a live DB or a real email (F0 boundary rule).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)
_NUDGE_WINDOW = timedelta(days=6)


def run_weekly_nudge(db, mail_send, now=None, *, _projects=None, _email_for=None,
                     _opted_in=None, _mark=None) -> dict:
    """Send one nudge per due, opted-in project. Injectable deps for tests.

    Due = no nudge in the last 6 days (idempotent). Opt-in honored at send time.
    A project with no timeline (timeline_status -> {}) is skipped — nothing to say.
    """
    from agent.timeline import timeline_status  # noqa: PLC0415
    now = now or datetime.now(timezone.utc)
    projects = (_projects or _default_projects)(db)
    sent = skipped = 0
    for p in projects:
        try:
            # 6-day idempotency window: a crash-and-rerun or a double cron tick
            # never double-sends.
            if p.last_nudge_at and (now - p.last_nudge_at) < _NUDGE_WINDOW:
                skipped += 1
                continue
            if not (_opted_in or _default_opted_in)(db, p.owner_id):
                skipped += 1
                continue
            state = p._state if hasattr(p, "_state") else _load_state(db, p)
            st = timeline_status(state, now.date())
            if not st:
                skipped += 1
                continue
            behind = (f"You're about {st['weeks_behind']} week(s) behind."
                      if not st["on_track"] else "You're on track — keep going.")
            html = (f"<p>This week: <b>{st['this_week']}</b>.</p><p>{behind}</p>"
                    f"<p><a href='https://dothesis.app'>Open your thesis</a></p>")
            to = (_email_for or _default_email_for)(db, p.owner_id)
            if mail_send(to, "Your thesis this week", html):
                (_mark or _default_mark)(db, p, now)
                sent += 1
        except Exception:
            # One bad project must never sink the whole cron run.
            logger.exception("weekly_nudge: project %s failed", getattr(p, "id", "?"))
            skipped += 1
    return {"sent": sent, "skipped": skipped}


# --- real DB-backed defaults (thin; tests inject stubs) ----------------------
# Only exercised by the __main__ cron path; the test drives the injected deps.
def _default_projects(db):
    """Projects that have a coaching store (where thesis_timeline lives), so we
    don't load state for every project that never set a defense date."""
    from sqlalchemy import select  # noqa: PLC0415

    from ..models import ContextStore, Project  # noqa: PLC0415
    return db.execute(
        select(Project)
        .join(ContextStore, ContextStore.project_id == Project.id)
        .where(ContextStore.coaching.isnot(None))
    ).scalars().all()


def _default_opted_in(db, uid) -> bool:
    """Opt-in defaults to True (the nudge is gentle + one/week); a user opts OUT
    by flipping the nudge_opt_in preference."""
    from ..user_memory import load_user_prefs  # noqa: PLC0415
    return bool(load_user_prefs(db, uid).get("nudge_opt_in", True))


def _default_email_for(db, uid) -> str:
    from ..models import User  # noqa: PLC0415
    user = db.get(User, uid)
    return user.email if user else ""


def _default_mark(db, p, ts) -> None:
    p.last_nudge_at = ts
    db.add(p)


def _load_state(db, p) -> dict:
    """Load a project's full state (contextStore includes the lifted coaching
    keys, so thesis_timeline is visible to timeline_status)."""
    from ..agent_state import DbProjectStateStore  # noqa: PLC0415
    from ..db import get_engine  # noqa: PLC0415
    from ..routers.chat_v3 import _workspace_dir  # noqa: PLC0415
    store = DbProjectStateStore(get_engine(), p.id, _workspace_dir(p.id))
    return store.load()


if __name__ == "__main__":  # pragma: no cover
    # F0 correction: app.db exposes get_session_factory(), NOT SessionLocal.
    from app.db import get_session_factory
    from app.mail import send_html
    Session = get_session_factory()
    with Session() as db:
        print(run_weekly_nudge(db, send_html))
        db.commit()
