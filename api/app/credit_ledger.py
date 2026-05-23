"""Atomic credit operations against users.credit + credit_transactions ledger.

Rules:
 - Every balance change has a matching ledger row.
 - debit() takes a row-level lock on the user to prevent races.
 - refund_if_unrefunded() is idempotent — second call returns 0 and does nothing.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CreditTransaction, User


@dataclass
class InsufficientCredit(Exception):
    required: int
    balance: int

    def __post_init__(self) -> None:
        super().__init__(f"insufficient credit: need {self.required}, have {self.balance}")


def _lock_user(session: Session, user: User) -> User:
    locked = session.scalar(
        select(User).where(User.id == user.id).with_for_update()
    )
    if locked is None:
        raise RuntimeError("user vanished")
    return locked


def credit(
    session: Session,
    user: User,
    *,
    delta: int,
    reason: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> None:
    if delta <= 0:
        raise ValueError("credit() requires positive delta; use debit() for the other direction")
    locked = _lock_user(session, user)
    locked.credit = (locked.credit or 0) + delta
    session.add(CreditTransaction(
        user_id=locked.id, delta=delta, reason=reason,
        ref_type=ref_type, ref_id=ref_id,
    ))
    session.flush()


def debit(
    session: Session,
    user: User,
    *,
    delta: int,
    reason: str,
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> None:
    if delta <= 0:
        raise ValueError("debit() requires positive delta")
    locked = _lock_user(session, user)
    if (locked.credit or 0) < delta:
        raise InsufficientCredit(required=delta, balance=locked.credit or 0)
    locked.credit = locked.credit - delta
    session.add(CreditTransaction(
        user_id=locked.id, delta=-delta, reason=reason,
        ref_type=ref_type, ref_id=ref_id,
    ))
    session.flush()


def refund_if_unrefunded(session: Session, user: User, *, paper_id: uuid.UUID) -> int:
    rows = session.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.ref_type == "paper", CreditTransaction.ref_id == paper_id)
        .order_by(CreditTransaction.id)
    ).all()
    debits = [r for r in rows if r.reason == "paper_run" and r.delta < 0]
    refunds = [r for r in rows if r.reason == "refund" and r.delta > 0]
    if not debits or refunds:
        return 0
    total_debited = sum(-r.delta for r in debits)
    locked = _lock_user(session, user)
    locked.credit = (locked.credit or 0) + total_debited
    session.add(CreditTransaction(
        user_id=locked.id, delta=total_debited, reason="refund",
        ref_type="paper", ref_id=paper_id,
    ))
    session.flush()
    return total_debited
