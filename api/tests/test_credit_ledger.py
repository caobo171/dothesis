import uuid
import pytest
from sqlalchemy import select

from app.credit_ledger import (
    InsufficientCredit,
    debit,
    credit,
    refund_if_unrefunded,
)
from app.db import get_session_factory
from app.models import CreditTransaction, User


@pytest.fixture
def session():
    Session = get_session_factory()
    with Session() as s:
        yield s


def _new_user(session, *, balance: int = 0) -> User:
    u = User(email=f"u{uuid.uuid4().hex[:8]}@e.com", password_hash="x", credit=balance)
    session.add(u)
    session.commit()
    return u


def test_credit_adds_balance_and_writes_ledger(session):
    u = _new_user(session, balance=0)
    credit(session, u, delta=100, reason="purchase", ref_type="order", ref_id=uuid.uuid4())
    session.commit()
    session.refresh(u)
    assert u.credit == 100
    rows = session.scalars(select(CreditTransaction).where(CreditTransaction.user_id == u.id)).all()
    assert len(rows) == 1
    assert rows[0].delta == 100
    assert rows[0].reason == "purchase"


def test_debit_deducts_balance_and_writes_ledger(session):
    u = _new_user(session, balance=500)
    paper_id = uuid.uuid4()
    debit(session, u, delta=120, reason="paper_run", ref_type="paper", ref_id=paper_id)
    session.commit()
    session.refresh(u)
    assert u.credit == 380
    rows = session.scalars(select(CreditTransaction).where(CreditTransaction.user_id == u.id)).all()
    assert rows[0].delta == -120


def test_debit_raises_when_insufficient(session):
    u = _new_user(session, balance=50)
    with pytest.raises(InsufficientCredit) as exc:
        debit(session, u, delta=120, reason="paper_run", ref_type="paper", ref_id=uuid.uuid4())
    assert exc.value.required == 120
    assert exc.value.balance == 50
    session.rollback()
    session.refresh(u)
    assert u.credit == 50  # unchanged


def test_refund_inserts_refund_row_once(session):
    u = _new_user(session, balance=1000)
    paper_id = uuid.uuid4()
    debit(session, u, delta=200, reason="paper_run", ref_type="paper", ref_id=paper_id)
    session.commit()
    session.refresh(u)
    assert u.credit == 800

    refunded = refund_if_unrefunded(session, u, paper_id=paper_id)
    session.commit()
    assert refunded == 200
    session.refresh(u)
    assert u.credit == 1000

    # Second call is a no-op
    refunded_again = refund_if_unrefunded(session, u, paper_id=paper_id)
    session.commit()
    assert refunded_again == 0
    session.refresh(u)
    assert u.credit == 1000


def test_refund_with_no_prior_debit_is_noop(session):
    u = _new_user(session, balance=100)
    refunded = refund_if_unrefunded(session, u, paper_id=uuid.uuid4())
    session.commit()
    assert refunded == 0
    session.refresh(u)
    assert u.credit == 100
