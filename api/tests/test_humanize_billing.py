"""humanize now meters its LLM cost and charges for it — routers/humanize.py.

Before this, humanize called the model directly: no `token_ledger` row, no
credit debit. That was a cost blind spot on the WEB path as much as over MCP —
the tokens were always real, only the accounting was missing.

The tests that matter are the ones about the edges, because the happy path is
arithmetic: a pass that FAILS still cost money, a user at zero must not lose a
rewrite they waited 30s for, and a billing bug must never eat a successful
result.
"""
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, TokenLedger, User
from tests.conftest import make_user


@pytest.fixture
def user():
    Session = get_session_factory()
    with Session() as s:
        u = make_user(s, email="h@e.com", credit=1000)
        s.commit(); s.refresh(u); s.expunge(u)
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app)


def _patch(monkeypatch, result):
    """Stand in for the real pass — these tests are about accounting, not prose."""
    import orchestrator.tools.humanize as h
    monkeypatch.setattr(h, "humanize_prose", lambda *a, **k: result)


USAGE_1K = [{"model": "gemini-2.5-flash", "prompt_tokens": 700, "completion_tokens": 300}]


def _ledger(user_id):
    Session = get_session_factory()
    with Session() as s:
        return s.query(TokenLedger).filter_by(user_id=user_id).all()


def _balance(user_id):
    Session = get_session_factory()
    with Session() as s:
        return s.get(User, user_id).credit


def test_a_successful_pass_writes_a_ledger_row_and_charges(user, monkeypatch):
    _patch(monkeypatch, {"ok": True, "text": "out", "changed": True, "usage": USAGE_1K})
    r = _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    assert r.status_code == 200
    assert r.json()["credits_charged"] > 0

    rows = _ledger(user.id)
    assert len(rows) == 1
    assert rows[0].action_kind == "humanize"
    assert rows[0].model == "gemini-2.5-flash"
    assert rows[0].prompt_tokens == 700 and rows[0].completion_tokens == 300
    # Project-less: humanize takes a passage, not a thesis. user_id is the only
    # attribution it can have, which is why the column was added.
    assert rows[0].project_id is None and rows[0].user_id == user.id
    assert _balance(user.id) < 1000


def test_a_failed_pass_is_still_billed(user, monkeypatch):
    """Three rounds that then fail the frozen gate cost exactly as much as three
    that succeed. Billing only successes would silently eat that."""
    _patch(monkeypatch, {"ok": False, "error": "frozen_violation", "text": "in",
                         "changed": False, "usage": USAGE_1K})
    r = _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    assert r.json()["ok"] is False
    assert r.json()["credits_charged"] > 0
    assert len(_ledger(user.id)) == 1


def test_each_model_in_a_pass_is_billed_at_its_own_rate(user, monkeypatch):
    """The anchor router and the rewrite are separately configurable, so one pass
    can span models. A single scalar multiplier cannot price that."""
    _patch(monkeypatch, {"ok": True, "text": "o", "usage": [
        {"model": "gemini-2.5-flash", "prompt_tokens": 1000, "completion_tokens": 0},
        {"model": "gemini-2.5-pro", "prompt_tokens": 1000, "completion_tokens": 0},
    ]})
    _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    rows = _ledger(user.id)
    assert {r.model for r in rows} == {"gemini-2.5-flash", "gemini-2.5-pro"}


def test_a_user_at_zero_is_undercharged_not_refused(user, monkeypatch):
    """Refusing here would fail a rewrite the student already waited 30s for.
    The under-charge is visible in token_ledger instead of silent."""
    Session = get_session_factory()
    with Session() as s:
        s.get(User, user.id).credit = 0
        s.commit()
    _patch(monkeypatch, {"ok": True, "text": "out", "usage": USAGE_1K})
    r = _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    assert r.status_code == 200
    assert r.json()["ok"] is True          # the rewrite is still delivered
    assert r.json()["credits_charged"] == 0
    assert _balance(user.id) == 0
    assert len(_ledger(user.id)) == 1      # ...and the real cost is still recorded


def test_a_provider_without_usage_metadata_records_the_call_but_charges_nothing(user, monkeypatch):
    """"Did we attempt N calls at $0 because the provider stopped reporting?" is
    a question the ledger should be able to answer."""
    _patch(monkeypatch, {"ok": True, "text": "out", "usage": [
        {"model": "mystery", "prompt_tokens": 0, "completion_tokens": 0}]})
    r = _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    assert r.json()["credits_charged"] == 0
    assert len(_ledger(user.id)) == 1
    assert _balance(user.id) == 1000


def test_a_billing_failure_never_eats_the_rewrite(user, monkeypatch):
    """The rewrite is the product; the invoice is bookkeeping. A dead credit
    ledger must not turn a 30-second successful humanize into an error."""
    _patch(monkeypatch, {"ok": True, "text": "precious output", "usage": USAGE_1K})

    def _boom(*a, **k):
        raise RuntimeError("credit ledger down")
    monkeypatch.setattr("app.credit_ledger.debit", _boom)

    r = _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    assert r.status_code == 200
    assert r.json()["text"] == "precious output"
    assert r.json()["credits_charged"] == 0
    # ...and the cost is STILL recorded, because metering commits separately
    # from billing. An unbillable call must not erase its own cost record.
    assert len(_ledger(user.id)) == 1


def test_a_charge_shows_up_on_the_transactions_page(user, monkeypatch):
    _patch(monkeypatch, {"ok": True, "text": "out", "usage": USAGE_1K})
    _as(user).post("/api/v1/humanize", json={"access_token": "x", "text": "in"})
    Session = get_session_factory()
    with Session() as s:
        tx = s.query(CreditTransaction).filter_by(user_id=user.id).all()
    assert [t.reason for t in tx] == ["humanize"]
    assert tx[0].delta < 0
