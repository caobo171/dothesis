"""Auto-approve runs charge actual token usage (from token_ledger) on completion."""
import uuid
from datetime import datetime, timedelta, timezone

from app.db import get_session_factory
from app.job_runner import _charge_auto_run
from app.models import CreditTransaction, Job, Project, TokenLedger, User


def _seed(db):
    u = User(email=f"u{uuid.uuid4().hex[:6]}@x", username=f"u{uuid.uuid4().hex[:6]}",
             password_hash="x", email_verified=True, credit=10000)
    db.add(u); db.flush()
    p = Project(user_id=u.id, name="T")
    db.add(p); db.flush()
    run = Job(project_id=p.id, paper_id=None, mode="auto", status="running",
              started_at=datetime.now(timezone.utc) - timedelta(minutes=1),
              langgraph_thread_id=str(uuid.uuid4()))
    db.add(run); db.flush()
    return u, p, run


def _ledger(db, project_id, prompt, completion, model="gemini"):
    db.add(TokenLedger(project_id=project_id, action_kind="m1_extract", model=model,
                       prompt_tokens=prompt, completion_tokens=completion,
                       reserved=0, duration_ms=10))


def test_auto_run_charges_actual_tokens_and_is_idempotent():
    sf = get_session_factory()
    with sf() as db:
        u, p, run = _seed(db)
        _ledger(db, p.id, 2500, 3500)  # 6000 tokens → round(6.0) = 6 credits
        db.commit()

        _charge_auto_run(db, run); db.commit()
        db.refresh(u)
        assert u.credit == 10000 - 6
        txns = (db.query(CreditTransaction)
                  .filter_by(ref_type="run", ref_id=run.id, reason="auto_run").all())
        assert len(txns) == 1 and txns[0].delta == -6

        # Second call must not double-charge.
        _charge_auto_run(db, run); db.commit()
        db.refresh(u)
        assert u.credit == 10000 - 6
        assert (db.query(CreditTransaction)
                  .filter_by(ref_type="run", ref_id=run.id, reason="auto_run").count() == 1)


def test_auto_run_bills_each_model_at_its_own_rate(monkeypatch):
    """A run spanning two models is billed per-model, from the ledger.

    Regression: billing used to scale total tokens by
    credit_multiplier(getenv("ORCHESTRATOR_LLM_MODEL", "gemini-3.5-flash")) — one
    scalar for the whole run, re-derived from env. That silently overcharged 4x
    when the engine defaulted to 2.5-flash, and cannot express a run that used
    more than one model (the citation planner runs a different model from the
    main brain). The env var must not influence the charge at all.
    """
    # Set the env var to the priciest tier: if it still leaks into the charge,
    # the numbers below come out ~5x too high and this test fails loudly.
    monkeypatch.setenv("ORCHESTRATOR_LLM_MODEL", "gemini-2.5-pro")
    sf = get_session_factory()
    with sf() as db:
        u, p, run = _seed(db)
        _ledger(db, p.id, 2000, 2000, model="gemini-2.5-flash")   # 4000 tok @ 1.0 → 4
        _ledger(db, p.id, 1000, 1000, model="gemini-3.5-flash")   # 2000 tok @ 4.0 → 8
        db.commit()

        _charge_auto_run(db, run); db.commit()
        db.refresh(u)
        assert u.credit == 10000 - 12  # 4 + 8, not 6000/1000 * one_scalar


def test_auto_run_ignores_tokens_from_before_it_started():
    sf = get_session_factory()
    with sf() as db:
        u, p, run = _seed(db)
        # A ledger row from BEFORE this run started must not be billed to it.
        old = TokenLedger(project_id=p.id, action_kind="prev", model="gemini",
                          prompt_tokens=9000, completion_tokens=9000,
                          reserved=0, duration_ms=10)
        db.add(old); db.flush()
        old.created_at = run.started_at - timedelta(minutes=5)
        db.commit()

        _charge_auto_run(db, run); db.commit()
        db.refresh(u)
        assert u.credit == 10000  # nothing to charge for this run
        assert (db.query(CreditTransaction)
                  .filter_by(ref_type="run", ref_id=run.id).count() == 0)
