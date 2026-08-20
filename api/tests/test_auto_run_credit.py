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


# The default model must be a REAL id that quality/model_prices.py prices. It used
# to be a bare "gemini", which no ledger row ever carries (token_meter writes the id
# that actually served the call) — it only billed 1.0 because the old substring
# matcher fell through to 1.0 for anything it didn't recognize. Under table-based
# pricing an unpriced id correctly hits the unknown-model fallback, so the fixture's
# fake id would have silently changed what these tests measure.
def _ledger(db, project_id, prompt, completion, model="gemini-2.5-flash"):
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
        _ledger(db, p.id, 2000, 2000, model="gemini-2.5-flash")   # 4000 tok @ 1.0  → 4.0
        _ledger(db, p.id, 1000, 1000, model="gemini-3.5-flash")   # 2000 tok @ 12.9 → 25.7
        db.commit()

        _charge_auto_run(db, run); db.commit()
        db.refresh(u)
        # ⚠️ REPRICED, not re-derived: 3.5-flash was 4.0 here (total 12) because the
        # old multiplier read engine/utils/model_config.py's $0.50/$3.00. That row is
        # stale (Feb-2026, inferred by analogy from the 3-flash-preview anchor). Both
        # of quality/model_prices.py's independent sources — July-2026 provider
        # research AND the live Ofox gateway pull — say $1.50/$9.00, so the honest
        # rate is 12.86x and 4.0 was a ~3.2x UNDERCHARGE on the production default.
        # This number is a business decision, not arithmetic: see
        # .superpowers/sdd/fix-credit-multiplier-report.md before deploying.
        # Derived from the table, not hardcoded: this assertion exists to prove the
        # ENV VAR doesn't leak into the charge, and that property must survive a
        # repricing. The literal used to be 30 (4.0 + 25.7) when the baseline row
        # was 3.24x too cheap; after the 2026-08-02 baseline correction it is 12 —
        # which is exactly the total this test's own comment records it having
        # BEFORE the stale row landed. A hardcoded number here just re-breaks on
        # the next price move.
        from app.pricing import credit_multiplier as _cm
        expected = round(4000 / 1000 * _cm("gemini-2.5-flash")
                         + 2000 / 1000 * _cm("gemini-3.5-flash"))
        assert expected == 12, f"baseline sanity: expected 12 credits, got {expected}"
        assert u.credit == 10000 - expected


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


def test_headless_meter_event_bills_the_run_at_the_priced_rate(monkeypatch):
    """Spec §Testing item 4, end to end: a `_UsageMeter`-produced event lands in
    token_ledger and `_charge_auto_run` debits > 0 at the RIGHT price.

    The test below drives `_ingest_event` from a hand-written payload, so nothing
    crossed from the runner's own emitter into billing — which is exactly how the
    unpriced-model overcharge (C1) survived every earlier review. Here the meter
    builds the event, so the id it chooses is the id the student is charged for.
    """
    import asyncio

    from app.headless_entry import _UsageMeter
    from app.job_runner import _ingest_event
    from app.pricing import credit_multiplier, is_priced

    # Pin the CONFIGURED model: route=openai with no override resolves to
    # gpt-5.6-luna (agent/model_factory.spec_from_env).
    monkeypatch.setenv("DOTHESIS_MODEL_ROUTE", "openai")
    monkeypatch.delenv("DOTHESIS_AGENT_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    sf = get_session_factory()
    with sf() as db:
        u, p, run = _seed(db)
        db.commit()
        run_id, project_id, before = run.id, p.id, u.credit

    emitted = []

    class _Appender:
        def write(self, ev):
            emitted.append(ev)

    meter = _UsageMeter(project_id, _Appender())
    # A realistic turn: the main brain, plus a step whose served id the price
    # table does not carry (a dated snapshot — the C1 shape).
    meter.observe({"type": "usage", "input_tokens": 120_000,
                   "output_tokens": 40_000, "model": "gemini-2.5-flash"})
    meter.observe({"type": "usage", "input_tokens": 30_000,
                   "output_tokens": 10_000, "model": "gpt-5.6-luna-2026-05-13"})
    assert meter.flush() == 2

    for ev in emitted:
        assert asyncio.run(_ingest_event(run_id, ev)) is False

    with sf() as db:
        rows = db.query(TokenLedger).filter_by(project_id=project_id).all()
        assert len(rows) == 2
        # Every row the runner writes must be one the charge can actually price;
        # an unpriced label silently bills at UNKNOWN_MODEL_MULTIPLIER (4.0x).
        assert all(is_priced(r.model) for r in rows), [r.model for r in rows]

        job = db.get(Job, run_id)
        _charge_auto_run(db, job)
        db.commit()
        owner = db.get(User, db.get(Project, project_id).user_id)
        charged = before - owner.credit

    # Derived from the table, not hardcoded, so a repricing moves the assertion
    # with the product: 160k tokens at the baseline + 40k at the configured
    # model's rate (the snapshot id billed as gpt-5.6-luna, not as unknown).
    expected = round(160_000 / 1000 * credit_multiplier("gemini-2.5-flash")
                     + 40_000 / 1000 * credit_multiplier("gpt-5.6-luna"))
    assert charged == expected
    assert charged > 0, "a headless run that spent tokens must not be free"
    # The 4.0x-fallback bill for the same tokens, which C1 was producing.
    assert charged < round(160_000 / 1000 * credit_multiplier("gemini-2.5-flash")
                           + 40_000 / 1000 * 4.0)


def test_token_usage_event_becomes_ledger_row_and_gets_charged():
    """The gap this closes: the orchestrator runs as a SUBPROCESS with a no-op
    sink, so auto runs wrote zero token_ledger rows and _charge_auto_run billed
    nothing. Ledger entries now travel as `token_usage` events on the existing
    events.jsonl contract and are persisted API-side (the single DB writer)."""
    import asyncio

    from app.job_runner import _ingest_event

    sf = get_session_factory()
    with sf() as db:
        u, p, run = _seed(db)
        db.commit()
        run_id, project_id, before = run.id, p.id, u.credit
        events_before = run.events_processed

    payload = {
        "type": "token_usage",
        "action_kind": "m2_citation_planner",
        "model": "gemini-3-flash-preview",
        "prompt_tokens": 3000,
        "completion_tokens": 1000,
        "reserved": 0,
        "duration_ms": 1234,
        "project_id": str(project_id),
    }
    # asyncio.run, not get_event_loop(): the latter is deprecated and raises
    # "no current event loop" depending on what earlier tests left behind, which
    # made this pass alone and fail in a full run.
    terminal = asyncio.run(_ingest_event(run_id, payload))
    assert terminal is False

    with sf() as db:
        rows = db.query(TokenLedger).filter_by(project_id=project_id).all()
        assert len(rows) == 1
        assert rows[0].model == "gemini-3-flash-preview"
        assert rows[0].action_kind == "m2_citation_planner"
        assert rows[0].prompt_tokens + rows[0].completion_tokens == 4000

        # Bookkeeping still advances, or _monitor replays the line and double-bills.
        job = db.get(Job, run_id)
        assert job.events_processed == events_before + 1

        # And it actually bills: 4000 tokens at gemini-3-flash-preview's 4.286x.
        _charge_auto_run(db, job); db.commit()
        owner = db.get(User, db.get(Project, project_id).user_id)
        assert owner.credit < before, "auto run must now be charged"
