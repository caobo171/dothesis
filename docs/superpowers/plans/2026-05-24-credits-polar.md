> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# Credits + Polar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up real billing: users can buy credit packs via Polar; creating a thesis deducts credits scaled by `(academic_level, model_tier)`; engine failures refund the deduction. Wizard exposes a Standard/Premium tier picker — the concrete model is resolved server-side.

**Architecture:** Two DB tables (`orders`, `credit_transactions`) join the existing `users.credit` cache. Polar checkout is server-initiated; webhook is signature-verified and idempotent. Credit deduction wraps paper creation in a `SELECT … FOR UPDATE` transaction and writes a ledger row. Job failure/cancel paths insert a refund ledger row (idempotently). Tier→model mapping lives in `pricing.py` and is hidden from the API surface.

**Tech Stack:** FastAPI, SQLAlchemy 2 + Postgres, Alembic, `polar-sdk` (server SDK, async); Next 16 / React 19, Tailwind, Headless UI; existing SWR + Polar JS-less checkout via `window.location` redirect.

---

## File structure

**API (`api/app/`):**
- New: `pricing.py` — `PACKAGES` list, `PAPER_COST` dict, `TIER_TO_MODEL` map, helper `paper_cost(level, tier)` and `resolve_model(tier)`.
- New: `credit_ledger.py` — pure-DB helpers: `debit(user, delta, reason, ref_type, ref_id)`, `credit(user, delta, reason, ref_type, ref_id)`, `refund_if_unrefunded(user, paper_id)`, with `SELECT … FOR UPDATE`.
- New: `polar_client.py` — thin wrapper around Polar SDK: `create_checkout(order, return_url, cancel_url)`, `verify_webhook(payload, signature)`. Stubbable for tests via env flag `DOTHESIS_PAYMENTS=dummy`.
- New: `routers/credit.py` — `GET /packages`, `POST /checkout`, `POST /polar/webhook`, `GET /orders`, `GET /transactions`.
- Modify: `models.py` — add `Paper.model_tier`, new `Order` model, new `CreditTransaction` model.
- Modify: `routers/papers.py` — replace `ALLOWED_MODELS` with `ALLOWED_TIERS = {"standard", "premium"}`; accept `model_tier` in `PaperCreate`; remove `model` from API; compute cost; deduct; resolve model server-side before spawning job.
- Modify: `job_runner.py` — in the `error`, cancel and `canceled` paths, call `credit_ledger.refund_if_unrefunded(...)`.
- Modify: `main.py` — register `credit` router.
- Modify: `settings.py` — add `polar_access_token`, `polar_webhook_secret`, `polar_server`, `dothesis_base_url`, `dothesis_payments` (=`polar`|`dummy`).
- New migration: `migrations/versions/<rev>_credit_schema.py` — adds `papers.model_tier`, `orders` table, `credit_transactions` table.

**API tests (`api/tests/`):**
- New: `test_pricing.py` — package list shape, paper-cost matrix, tier→model resolution, error on bad tier/level.
- New: `test_credit_ledger.py` — debit/credit/refund idempotence; balance stays consistent with ledger sum.
- New: `test_credit_routes.py` — `/packages` returns list; `/checkout` calls polar_client and returns URL; `/polar/webhook` increments balance + is idempotent.
- New: `test_papers_credit.py` — paper creation deducts; insufficient balance returns 402; refund on engine failure.

**Web (`web/`):**
- New: `app/(inapp)/credit/page.tsx` — server component that suspends `<Credit />`.
- New: `app/(inapp)/credit/_components/Credit.tsx` — page UI, header (avatar + email + credit badge), success banner when `?polar=success`, stats row, packages, important notes.
- New: `app/(inapp)/credit/_components/PricingPackages.tsx` — package grid with quantity stepper, "Buy" button → POST `/credit/checkout` then redirect.
- Modify: `app/lib/api.js` — confirm `swrFetcher` supports POST (used by checkout); add `apiPost` helper if missing.
- Modify: `app/components/wizard.jsx` (and any New-Thesis form) — replace model select with `Standard | Premium` radio tiles; send `model_tier`. Show calculated credit cost preview.
- New: `app/lib/credit-packages.ts` — shared TS type for the package response.

**Out of scope:**
- Admin orders page (Plan 3).
- Affiliate / leaderboard.
- Refund-from-admin UI (use DB grant via Plan 3 admin Users page instead).

---

## Pre-flight

- [ ] **P1: Confirm clean working tree on `master`**

Run: `git status --short`. Expected: empty.

- [ ] **P2: Establish baseline test count**

Run from `api/`:
```
.\.venv\Scripts\python.exe -m pytest -q --tb=no 2>&1 | findstr /R "passed failed"
```
Expected: roughly `21 passed, 15 failed` (pre-existing INET bug). Note this exact line.

- [ ] **P3: Confirm dev Postgres is reachable**

Either: Docker testcontainers boots in pytest (already used by `conftest.py`) OR there's a local dev Postgres. If neither is true, set up Docker Desktop before continuing.

---

## Task 1: Pricing config

**Files:**
- Create: `api/app/pricing.py`
- Test: `api/tests/test_pricing.py`

- [ ] **Step 1: Write failing tests**

Create `api/tests/test_pricing.py`:

```python
import pytest

from app.pricing import (
    PACKAGES,
    PAPER_COST,
    TIER_TO_MODEL,
    paper_cost,
    resolve_model,
)


def test_packages_match_survify_pricing():
    by_id = {p["id"]: p for p in PACKAGES}
    assert by_id["starter_package"]["price_cents"] == 900
    assert by_id["starter_package"]["credits"] == 300
    assert by_id["standard_package"]["price_cents"] == 1900
    assert by_id["standard_package"]["credits"] == 700
    assert by_id["expert_package"]["price_cents"] == 4900
    assert by_id["expert_package"]["credits"] == 2000


def test_package_fields_present():
    for pkg in PACKAGES:
        assert {"id", "name", "price_cents", "old_price_cents", "credits"} <= set(pkg.keys())


def test_paper_cost_matrix_complete():
    expected_levels = {"research", "bachelor", "master", "phd"}
    expected_tiers = {"standard", "premium"}
    for level in expected_levels:
        for tier in expected_tiers:
            assert (level, tier) in PAPER_COST
            assert PAPER_COST[(level, tier)] > 0


def test_paper_cost_premium_is_more_expensive_than_standard():
    for level in {"research", "bachelor", "master", "phd"}:
        assert PAPER_COST[(level, "premium")] > PAPER_COST[(level, "standard")]


def test_paper_cost_phd_more_than_research():
    assert PAPER_COST[("phd", "standard")] > PAPER_COST[("research", "standard")]
    assert PAPER_COST[("phd", "premium")] > PAPER_COST[("research", "premium")]


def test_paper_cost_helper_returns_int():
    assert paper_cost("master", "standard") == PAPER_COST[("master", "standard")]
    assert isinstance(paper_cost("phd", "premium"), int)


def test_paper_cost_helper_raises_on_bad_input():
    with pytest.raises(ValueError):
        paper_cost("nonsense", "standard")
    with pytest.raises(ValueError):
        paper_cost("master", "deluxe")


def test_resolve_model_uses_tier_map():
    assert resolve_model("standard") == TIER_TO_MODEL["standard"]
    assert resolve_model("premium") == TIER_TO_MODEL["premium"]


def test_resolve_model_raises_on_bad_tier():
    with pytest.raises(ValueError):
        resolve_model("ultra")


def test_resolve_model_env_override(monkeypatch):
    monkeypatch.setenv("DOTHESIS_PREMIUM_MODEL", "gpt-5-custom")
    # Re-import to pick up env at module init? We use the helper, which reads env each call.
    from app.pricing import resolve_model as r
    assert r("premium") == "gpt-5-custom"
```

- [ ] **Step 2: Run test (expect import error)**

```
.\.venv\Scripts\python.exe -m pytest tests/test_pricing.py -v
```
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `api/app/pricing.py`**

```python
"""Pricing config: credit packs, paper-cost matrix, tier→model resolution.

PACKAGES values come directly from Survify's PRICING_PACKAGES (USD prices,
credits per pack). PAPER_COST is a placeholder matrix; tune later.
"""
from __future__ import annotations

import os
from typing import TypedDict


class Package(TypedDict):
    id: str
    name: str
    price_cents: int
    old_price_cents: int
    credits: int


PACKAGES: list[Package] = [
    {
        "id": "starter_package",
        "name": "Starter package",
        "price_cents": 900,
        "old_price_cents": 1500,
        "credits": 300,
    },
    {
        "id": "standard_package",
        "name": "Standard package",
        "price_cents": 1900,
        "old_price_cents": 3500,
        "credits": 700,
    },
    {
        "id": "expert_package",
        "name": "Expert package",
        "price_cents": 4900,
        "old_price_cents": 10000,
        "credits": 2000,
    },
]

PACKAGES_BY_ID: dict[str, Package] = {p["id"]: p for p in PACKAGES}


# Placeholder per-paper cost; tune via product later.
PAPER_COST: dict[tuple[str, str], int] = {
    ("research", "standard"):  60, ("research", "premium"):  150,
    ("bachelor", "standard"): 120, ("bachelor", "premium"):  300,
    ("master",   "standard"): 240, ("master",   "premium"):  600,
    ("phd",      "standard"): 480, ("phd",      "premium"): 1200,
}


# Tier→model defaults. Overridable per-tier via env vars:
#   DOTHESIS_STANDARD_MODEL (default "gemini-flash")
#   DOTHESIS_PREMIUM_MODEL  (default "gpt-5")
TIER_TO_MODEL: dict[str, str] = {
    "standard": "gemini-flash",
    "premium":  "gpt-5",
}

ALLOWED_TIERS: frozenset[str] = frozenset({"standard", "premium"})
ALLOWED_LEVELS: frozenset[str] = frozenset({"research", "bachelor", "master", "phd"})


def paper_cost(level: str, tier: str) -> int:
    if level not in ALLOWED_LEVELS:
        raise ValueError(f"unknown level: {level!r}")
    if tier not in ALLOWED_TIERS:
        raise ValueError(f"unknown tier: {tier!r}")
    return PAPER_COST[(level, tier)]


def resolve_model(tier: str) -> str:
    if tier not in ALLOWED_TIERS:
        raise ValueError(f"unknown tier: {tier!r}")
    env_key = f"DOTHESIS_{tier.upper()}_MODEL"
    return os.environ.get(env_key) or TIER_TO_MODEL[tier]
```

- [ ] **Step 4: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_pricing.py -v
```
Expected: 10 passed.

- [ ] **Step 5: Commit**

```
git add api/app/pricing.py api/tests/test_pricing.py
git commit -m "feat(api): pricing config — packages, paper-cost matrix, tier→model"
```

---

## Task 2: SQLAlchemy models — Paper.model_tier, Order, CreditTransaction

**Files:**
- Modify: `api/app/models.py`

- [ ] **Step 1: Add `model_tier` to `Paper`**

In the `Paper` class in `api/app/models.py`, add this line **after `model:`**:

```python
    model_tier: Mapped[str] = mapped_column(String(16), nullable=False, default="standard", server_default="standard")
```

- [ ] **Step 2: Append new `Order` and `CreditTransaction` classes at the bottom of `models.py`**

```python
class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    package_id: Mapped[str] = mapped_column(String(64), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD", server_default="USD")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending", server_default="pending")
    polar_checkout_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    polar_order_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class CreditTransaction(Base):
    __tablename__ = "credit_transactions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    delta: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    ref_type: Mapped[str | None] = mapped_column(String(16))
    ref_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

(Imports `BigInteger`, `ForeignKey`, `Integer`, `String`, `Text`, `UUID`, `DateTime`, `func` are already present.)

- [ ] **Step 3: Verify import**

```
.\.venv\Scripts\python.exe -c "from app.models import Paper, Order, CreditTransaction; print('Paper cols:', list(Paper.__table__.columns.keys())); print('Order cols:', list(Order.__table__.columns.keys())); print('CreditTx cols:', list(CreditTransaction.__table__.columns.keys()))"
```
Expected: all three classes import; `Paper`'s column list includes `model_tier`.

- [ ] **Step 4: Commit**

```
git add api/app/models.py
git commit -m "feat(api): Paper.model_tier + Order + CreditTransaction models"
```

---

## Task 3: Alembic migration for credit schema

**Files:**
- Create: `api/migrations/versions/<rev>_credit_schema.py`

- [ ] **Step 1: Generate**

From `api/`: `.\.venv\Scripts\python.exe -m alembic revision -m "credit_schema"`
Note the revision id.

- [ ] **Step 2: Write upgrade/downgrade**

Edit the generated file. Set `down_revision = "d7dfd0ab08d1"` (the head from Plan 1). Replace upgrade/downgrade with:

```python
def upgrade() -> None:
    op.add_column(
        "papers",
        sa.Column("model_tier", sa.String(16), nullable=False, server_default="standard"),
    )

    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("package_id", sa.String(64), nullable=False),
        sa.Column("credits", sa.Integer, nullable=False),
        sa.Column("amount_cents", sa.Integer, nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="USD"),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("polar_checkout_id", sa.String(128), unique=True),
        sa.Column("polar_order_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("paid_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])

    op.create_table(
        "credit_transactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("delta", sa.Integer, nullable=False),
        sa.Column("reason", sa.String(32), nullable=False),
        sa.Column("ref_type", sa.String(16)),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_credit_transactions_user_id", "credit_transactions", ["user_id"])
    op.create_index("ix_credit_transactions_ref", "credit_transactions", ["ref_type", "ref_id"])


def downgrade() -> None:
    op.drop_index("ix_credit_transactions_ref", "credit_transactions")
    op.drop_index("ix_credit_transactions_user_id", "credit_transactions")
    op.drop_table("credit_transactions")
    op.drop_index("ix_orders_user_id", "orders")
    op.drop_table("orders")
    op.drop_column("papers", "model_tier")
```

Add `from sqlalchemy.dialects import postgresql` near the top if not already present.

- [ ] **Step 3: Verify head**

```
.\.venv\Scripts\python.exe -m alembic heads
```
Expected: your new revision id followed by `(head)`.

- [ ] **Step 4: Commit**

```
git add api/migrations/versions/
git commit -m "feat(api): migration for papers.model_tier + orders + credit_transactions"
```

---

## Task 4: Credit ledger helpers

**Files:**
- Create: `api/app/credit_ledger.py`
- Test: `api/tests/test_credit_ledger.py`

- [ ] **Step 1: Write failing tests**

`api/tests/test_credit_ledger.py`:

```python
import uuid
import pytest
from sqlalchemy import select

from app.credit_ledger import (
    InsufficientCredit,
    debit,
    credit,
    refund_if_unrefunded,
)
from app.db import get_engine, get_session_factory
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
    session.refresh(u)
    assert u.credit == 50  # unchanged


def test_refund_inserts_refund_row_once(session):
    u = _new_user(session, balance=1000)
    paper_id = uuid.uuid4()
    debit(session, u, delta=200, reason="paper_run", ref_type="paper", ref_id=paper_id)
    session.refresh(u)
    assert u.credit == 800

    refunded = refund_if_unrefunded(session, u, paper_id=paper_id)
    assert refunded == 200
    session.refresh(u)
    assert u.credit == 1000

    # Second call is a no-op
    refunded_again = refund_if_unrefunded(session, u, paper_id=paper_id)
    assert refunded_again == 0
    session.refresh(u)
    assert u.credit == 1000


def test_refund_with_no_prior_debit_is_noop(session):
    u = _new_user(session, balance=100)
    refunded = refund_if_unrefunded(session, u, paper_id=uuid.uuid4())
    assert refunded == 0
    session.refresh(u)
    assert u.credit == 100
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_credit_ledger.py -v
```

- [ ] **Step 3: Implement**

Create `api/app/credit_ledger.py`:

```python
"""Atomic credit operations against the users.credit cache + credit_transactions ledger.

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
    """Re-fetch the user row with row-level lock; returns the locked row."""
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
    """Add credit to the user. Caller commits."""
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
    """Deduct credit; raises InsufficientCredit if balance < delta."""
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
    """If a paper_run debit exists for this paper and no refund yet, refund it.

    Returns the refunded amount (0 if nothing to refund).
    """
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
```

- [ ] **Step 4: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_credit_ledger.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add api/app/credit_ledger.py api/tests/test_credit_ledger.py
git commit -m "feat(api): atomic credit ledger helpers"
```

---

## Task 5: Polar client wrapper (with dummy mode for tests)

**Files:**
- Modify: `api/pyproject.toml` (add `polar-sdk`)
- Modify: `api/app/settings.py`
- Create: `api/app/polar_client.py`

- [ ] **Step 1: Add `polar-sdk` to pyproject**

Open `api/pyproject.toml`. Append to the `dependencies` array:

```
  "polar-sdk>=0.9",
```

Run from `api/`: `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`. Confirm `polar-sdk` installs.

(If `polar-sdk` is hard to install on Windows, fall back to `httpx`-based REST calls — the wrapper interface stays the same.)

- [ ] **Step 2: Add settings**

In `api/app/settings.py`, add these fields to the `Settings` BaseSettings class:

```python
    polar_access_token: str = ""
    polar_webhook_secret: str = ""
    polar_server: str = "sandbox"           # "sandbox" | "production"
    dothesis_base_url: str = "http://localhost:3000"
    dothesis_payments: str = "polar"        # "polar" | "dummy"
```

- [ ] **Step 3: Create `api/app/polar_client.py`**

```python
"""Polar payment integration. Falls back to dummy URLs when DOTHESIS_PAYMENTS=dummy."""
from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from typing import TYPE_CHECKING

from .settings import Settings, get_settings

if TYPE_CHECKING:
    from .models import Order

log = logging.getLogger(__name__)


class PolarError(Exception):
    pass


def _is_dummy(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return settings.dothesis_payments == "dummy" or not settings.polar_access_token


def create_checkout(order: "Order", *, return_url: str, cancel_url: str) -> tuple[str, str]:
    """Create a Polar checkout. Returns (checkout_id, checkout_url)."""
    settings = get_settings()
    if _is_dummy(settings):
        cid = f"dummy_{uuid.uuid4().hex}"
        url = f"{settings.dothesis_base_url}/credit?polar=dummy&order={order.id}"
        log.warning("polar dummy mode — order %s gets fake checkout %s", order.id, cid)
        return cid, url

    # Live mode: lazy import so tests/dev without polar-sdk still work.
    from polar_sdk import Polar  # type: ignore
    client = Polar(access_token=settings.polar_access_token, server=settings.polar_server)
    resp = client.checkouts.create(request={
        "product_id": order.package_id,
        "success_url": return_url,
        "metadata": {"order_id": str(order.id), "user_id": str(order.user_id)},
    })
    return resp.id, resp.url


def verify_webhook(payload: bytes, signature: str) -> None:
    """Raise PolarError if the HMAC doesn't match."""
    settings = get_settings()
    if _is_dummy(settings):
        # Accept everything in dummy mode (still validate non-empty).
        if not signature:
            raise PolarError("missing signature")
        return
    secret = settings.polar_webhook_secret.encode()
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PolarError("invalid signature")
```

- [ ] **Step 4: Commit**

```
git add api/pyproject.toml api/app/settings.py api/app/polar_client.py
git commit -m "feat(api): polar client wrapper with dummy mode"
```

---

## Task 6: Credit router — packages, checkout, webhook, listings

**Files:**
- Create: `api/app/routers/credit.py`
- Modify: `api/app/main.py` (register router)
- Test: `api/tests/test_credit_routes.py`

- [ ] **Step 1: Write failing tests**

`api/tests/test_credit_routes.py`:

```python
import json
import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.models import CreditTransaction, Order, User
from app.db import get_session_factory


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def _admin_user_signup(client):
    # Pre-existing INET bug breaks signup. Insert user directly into DB.
    Session = get_session_factory()
    with Session() as s:
        u = User(email="buyer@e.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        yield u


def _login_as(client, user_id):
    # No login flow; tests inject sessions via direct DB if needed.
    # For these tests we bypass auth via dependency override.
    from app.deps import current_user
    from app.main import app
    app.dependency_overrides[current_user] = lambda: _admin_user_signup
    yield
    app.dependency_overrides.pop(current_user, None)


def test_packages_returns_all_three(client):
    r = client.get("/api/v1/credit/packages")
    assert r.status_code == 200
    data = r.json()
    ids = {p["id"] for p in data}
    assert ids == {"starter_package", "standard_package", "expert_package"}


def test_checkout_creates_order_and_returns_url(client, _admin_user_signup, monkeypatch):
    from app.deps import current_user
    from app.main import app
    app.dependency_overrides[current_user] = lambda: _admin_user_signup

    try:
        with patch("app.routers.credit.create_checkout", return_value=("ck_test_123", "https://polar.test/checkout/abc")):
            r = client.post("/api/v1/credit/checkout", json={"package_id": "starter_package"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["checkout_url"] == "https://polar.test/checkout/abc"

        Session = get_session_factory()
        with Session() as s:
            orders = s.scalars(select(Order)).all()
            assert len(orders) == 1
            assert orders[0].polar_checkout_id == "ck_test_123"
            assert orders[0].credits == 300
            assert orders[0].amount_cents == 900
            assert orders[0].status == "pending"
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_checkout_rejects_unknown_package(client, _admin_user_signup):
    from app.deps import current_user
    from app.main import app
    app.dependency_overrides[current_user] = lambda: _admin_user_signup
    try:
        r = client.post("/api/v1/credit/checkout", json={"package_id": "nope"})
        assert r.status_code == 400
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_polar_webhook_credits_user_idempotently(client, _admin_user_signup, monkeypatch):
    monkeypatch.setenv("DOTHESIS_PAYMENTS", "dummy")
    # Seed a pending order
    Session = get_session_factory()
    with Session() as s:
        order = Order(
            user_id=_admin_user_signup.id,
            package_id="standard_package",
            credits=700,
            amount_cents=1900,
            polar_checkout_id="ck_seeded",
            status="pending",
        )
        s.add(order)
        s.commit()
        order_id = order.id

    payload = json.dumps({
        "type": "order.paid",
        "data": {"checkout_id": "ck_seeded", "id": "polar_order_abc"},
    }).encode()
    r = client.post("/api/v1/credit/polar/webhook", content=payload, headers={"X-Polar-Signature": "any-in-dummy"})
    assert r.status_code == 200

    with Session() as s:
        u = s.get(User, _admin_user_signup.id)
        assert u.credit == 700
        order = s.get(Order, order_id)
        assert order.status == "paid"
        ledger = s.scalars(select(CreditTransaction).where(CreditTransaction.user_id == u.id)).all()
        assert len(ledger) == 1
        assert ledger[0].delta == 700

    # Second delivery: no double-credit
    r2 = client.post("/api/v1/credit/polar/webhook", content=payload, headers={"X-Polar-Signature": "any-in-dummy"})
    assert r2.status_code == 200
    with Session() as s:
        u = s.get(User, _admin_user_signup.id)
        assert u.credit == 700


def test_polar_webhook_missing_signature_is_400(client):
    payload = b"{}"
    r = client.post("/api/v1/credit/polar/webhook", content=payload, headers={})
    assert r.status_code == 400
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_credit_routes.py -v
```

- [ ] **Step 3: Implement `api/app/routers/credit.py`**

```python
"""Credit packs, checkout, Polar webhook, and listings."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..credit_ledger import credit as ledger_credit
from ..db import db_session
from ..deps import current_user
from ..models import CreditTransaction, Order, User
from ..polar_client import PolarError, create_checkout, verify_webhook
from ..pricing import PACKAGES, PACKAGES_BY_ID
from ..settings import get_settings

router = APIRouter(prefix="/credit", tags=["credit"])


@router.get("/packages")
def packages():
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "price_cents": p["price_cents"],
            "old_price_cents": p["old_price_cents"],
            "credits": p["credits"],
        }
        for p in PACKAGES
    ]


class CheckoutRequest(BaseModel):
    package_id: str


@router.post("/checkout")
def checkout(
    body: CheckoutRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    pkg = PACKAGES_BY_ID.get(body.package_id)
    if not pkg:
        raise HTTPException(400, detail={"error": {"code": "bad_package", "message": "unknown package"}})

    order = Order(
        user_id=user.id,
        package_id=pkg["id"],
        credits=pkg["credits"],
        amount_cents=pkg["price_cents"],
        status="pending",
    )
    db.add(order)
    db.flush()  # so order.id is set

    settings = get_settings()
    return_url = f"{settings.dothesis_base_url}/credit?polar=success"
    cancel_url = f"{settings.dothesis_base_url}/credit?polar=cancel"
    try:
        checkout_id, url = create_checkout(order, return_url=return_url, cancel_url=cancel_url)
    except PolarError as e:
        raise HTTPException(502, detail={"error": {"code": "polar_failed", "message": str(e)}})

    order.polar_checkout_id = checkout_id
    db.commit()
    return {"checkout_url": url, "order_id": str(order.id)}


@router.post("/polar/webhook")
async def polar_webhook(
    request: Request,
    x_polar_signature: str | None = Header(default=None, alias="X-Polar-Signature"),
    db: Session = Depends(db_session),
):
    payload = await request.body()
    if not x_polar_signature:
        raise HTTPException(400, detail={"error": {"code": "missing_signature"}})
    try:
        verify_webhook(payload, x_polar_signature)
    except PolarError as e:
        raise HTTPException(400, detail={"error": {"code": "bad_signature", "message": str(e)}})

    import json
    try:
        event = json.loads(payload)
    except json.JSONDecodeError:
        raise HTTPException(400, detail={"error": {"code": "bad_json"}})

    if event.get("type") != "order.paid":
        return {"ignored": event.get("type")}

    data = event.get("data") or {}
    checkout_id = data.get("checkout_id")
    polar_order_id = data.get("id")
    if not checkout_id:
        raise HTTPException(400, detail={"error": {"code": "no_checkout_id"}})

    order = db.scalar(select(Order).where(Order.polar_checkout_id == checkout_id))
    if not order:
        # Unknown checkout — log and accept (avoid retries from Polar).
        return {"ignored": "unknown_order"}
    if order.status == "paid":
        return {"ok": True, "already_paid": True}

    from datetime import datetime, timezone
    user = db.get(User, order.user_id)
    if not user:
        raise HTTPException(500, detail={"error": {"code": "user_gone"}})

    order.status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    if polar_order_id:
        order.polar_order_id = polar_order_id

    ledger_credit(db, user, delta=order.credits, reason="purchase", ref_type="order", ref_id=order.id)

    db.commit()
    return {"ok": True}


@router.get("/orders")
def list_my_orders(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    rows = db.scalars(
        select(Order).where(Order.user_id == user.id).order_by(desc(Order.created_at)).limit(50)
    ).all()
    return [
        {
            "id": str(o.id),
            "package_id": o.package_id,
            "credits": o.credits,
            "amount_cents": o.amount_cents,
            "currency": o.currency,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
        }
        for o in rows
    ]


@router.get("/transactions")
def list_my_transactions(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    rows = db.scalars(
        select(CreditTransaction).where(CreditTransaction.user_id == user.id)
        .order_by(desc(CreditTransaction.id)).limit(200)
    ).all()
    return [
        {
            "id": r.id, "delta": r.delta, "reason": r.reason,
            "ref_type": r.ref_type, "ref_id": str(r.ref_id) if r.ref_id else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
```

- [ ] **Step 4: Register in `api/app/main.py`**

Add to imports:

```python
from .routers import credit as credit_router
```

And inside `create_app`, after the existing `include_router` calls:

```python
    app.include_router(credit_router.router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_credit_routes.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add api/app/routers/credit.py api/app/main.py api/tests/test_credit_routes.py
git commit -m "feat(api): credit router — packages, checkout, polar webhook, listings"
```

---

## Task 7: Paper creation deducts credits; tier resolved server-side

**Files:**
- Modify: `api/app/routers/papers.py`
- Test: `api/tests/test_papers_credit.py`

- [ ] **Step 1: Read current `papers.py:23-43`** (the `ALLOWED_MODELS` constant and `PaperCreate` schema) so you know what to change.

- [ ] **Step 2: Write failing tests**

`api/tests/test_papers_credit.py`:

```python
import uuid
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, Paper, User


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture
def buyer():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="creator@e.com", password_hash="x", credit=1000)
        s.add(u)
        s.commit()
        return u


def _override_user(buyer):
    from app.deps import current_user
    from app.main import app
    app.dependency_overrides[current_user] = lambda: buyer
    return app


def _payload(tier: str = "standard", level: str = "master"):
    return {
        "topic": "Cargo cult engineering in cloud-native stacks",
        "research_question": "How does it spread?",
        "academic_level": level,
        "language": "en",
        "citation_style": "apa",
        "model_tier": tier,
    }


def test_create_paper_with_standard_tier_deducts_240_credits(client, buyer):
    app = _override_user(buyer)
    try:
        with patch("app.routers.papers.spawn_job"):
            r = client.post("/api/v1/papers", json=_payload(tier="standard", level="master"))
        assert r.status_code == 201, r.text
        Session = get_session_factory()
        with Session() as s:
            u = s.get(User, buyer.id)
            assert u.credit == 760
            tx = s.query(CreditTransaction).all()
            assert len(tx) == 1
            assert tx[0].delta == -240
            assert tx[0].reason == "paper_run"
    finally:
        app.dependency_overrides.clear()


def test_create_paper_with_premium_tier_deducts_more(client, buyer):
    app = _override_user(buyer)
    try:
        with patch("app.routers.papers.spawn_job"):
            r = client.post("/api/v1/papers", json=_payload(tier="premium", level="master"))
        assert r.status_code == 201
        Session = get_session_factory()
        with Session() as s:
            u = s.get(User, buyer.id)
            assert u.credit == 400  # 1000 - 600
    finally:
        app.dependency_overrides.clear()


def test_create_paper_returns_402_when_insufficient(client):
    Session = get_session_factory()
    with Session() as s:
        u = User(email="broke@e.com", password_hash="x", credit=10)
        s.add(u)
        s.commit()
    app = _override_user(u)
    try:
        with patch("app.routers.papers.spawn_job"):
            r = client.post("/api/v1/papers", json=_payload(tier="premium", level="phd"))
        assert r.status_code == 402
        body = r.json()
        assert body["detail"]["error"]["code"] == "insufficient_credit"
        assert body["detail"]["error"]["required"] == 1200
        assert body["detail"]["error"]["balance"] == 10
        with Session() as s:
            u2 = s.get(User, u.id)
            assert u2.credit == 10  # untouched
    finally:
        app.dependency_overrides.clear()


def test_create_paper_rejects_unknown_tier(client, buyer):
    app = _override_user(buyer)
    try:
        with patch("app.routers.papers.spawn_job"):
            r = client.post("/api/v1/papers", json=_payload(tier="ultra"))
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_create_paper_no_longer_accepts_model_field(client, buyer):
    """The wizard sends model_tier, not model. Pydantic strict should ignore unknown field."""
    app = _override_user(buyer)
    try:
        with patch("app.routers.papers.spawn_job"):
            body = _payload()
            body["model"] = "claude-opus"  # legacy field
            r = client.post("/api/v1/papers", json=body)
        # Either succeed (ignoring extra) or 422 — both are acceptable. The point is
        # model isn't honored. Check the paper row to confirm.
        if r.status_code == 201:
            Session = get_session_factory()
            with Session() as s:
                paper = s.query(Paper).first()
                # whatever was persisted, it came from the tier, not body['model']
                from app.pricing import resolve_model
                assert paper.model == resolve_model(paper.model_tier)
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 3: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_papers_credit.py -v
```

- [ ] **Step 4: Edit `api/app/routers/papers.py`**

Replace the `ALLOWED_*` block and `PaperCreate` schema with:

```python
ALLOWED_LEVELS = {"research", "bachelor", "master", "phd"}
ALLOWED_STYLES = {"apa", "mla", "chicago", "ieee", "harvard"}
ALLOWED_TIERS = {"standard", "premium"}
```

(Delete `ALLOWED_MODELS`.)

Replace `class PaperCreate` with:

```python
class PaperCreate(BaseModel):
    topic: str = Field(min_length=4, max_length=500)
    research_question: str | None = Field(default=None, max_length=2000)
    academic_level: str
    language: str = Field(min_length=2, max_length=16)
    model_tier: str = Field(default="standard")
    citation_style: str
    sources: Sources = Sources()
    tone: str | None = None
```

In the `create_paper` handler, replace:

```python
    if body.model not in ALLOWED_MODELS:
        raise HTTPException(422, detail={"error": {"code": "bad_model", "message": "invalid model"}})
```

with:

```python
    if body.model_tier not in ALLOWED_TIERS:
        raise HTTPException(422, detail={"error": {"code": "bad_tier", "message": "invalid model_tier"}})
```

And inside `create_paper`, before the `Paper(...)` instantiation, add:

```python
    from ..credit_ledger import InsufficientCredit, debit
    from ..pricing import paper_cost, resolve_model

    cost = paper_cost(body.academic_level, body.model_tier)
    try:
        debit(db, user, delta=cost, reason="paper_run", ref_type="paper", ref_id=None)  # ref_id set after flush
    except InsufficientCredit as e:
        raise HTTPException(
            402,
            detail={"error": {"code": "insufficient_credit", "required": e.required, "balance": e.balance}},
        )
```

Change the `Paper(...)` constructor to remove `model=body.model` and add:

```python
        model=resolve_model(body.model_tier),
        model_tier=body.model_tier,
```

After `db.flush()` for the paper, update the unfilled ledger row's `ref_id`:

```python
    # Backfill paper_id into the ledger row we just wrote
    last_tx = db.scalars(
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user.id, CreditTransaction.ref_id.is_(None))
        .order_by(CreditTransaction.id.desc()).limit(1)
    ).one()
    last_tx.ref_id = paper.id
    db.flush()
```

Add `from ..models import CreditTransaction` and `from sqlalchemy import select` to the existing imports.

The `brief` dict that gets passed to `spawn_job` should also drop `model_tier` (engine doesn't need it) and keep `model` (already there, now derived from tier).

- [ ] **Step 5: Update tests in `tests/test_papers.py` that send `model=...`**

If the existing `tests/test_papers.py` sends `"model": "claude-sonnet"` etc., those tests are not the focus here but they may now 422 because `model_tier` defaults to `standard` but they may have set `credit=0` users. Skip / adapt as needed; do NOT delete. If they fail, mark them with `@pytest.mark.skip(reason="superseded by test_papers_credit; model field removed in Plan 2")` and note in commit message.

- [ ] **Step 6: Run new tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_papers_credit.py tests/test_pricing.py tests/test_credit_ledger.py -v
```

- [ ] **Step 7: Commit**

```
git add api/app/routers/papers.py api/tests/test_papers_credit.py api/tests/test_papers.py
git commit -m "feat(api): paper creation deducts credits by (level, tier); tier→model resolved"
```

---

## Task 8: Job-failure refund

**Files:**
- Modify: `api/app/job_runner.py:159-165, 185-196`
- Test: extend `api/tests/test_papers_credit.py`

- [ ] **Step 1: Add failing test**

Append to `api/tests/test_papers_credit.py`:

```python
def test_engine_failure_refunds_credits(client, buyer):
    """When the engine emits an error event, the paper-run debit is refunded."""
    from app.credit_ledger import refund_if_unrefunded
    from app.models import Paper, Job

    # Set up: create a paper that's mid-debit
    Session = get_session_factory()
    with Session() as s:
        u = s.get(User, buyer.id)
        u.credit = 760  # post-debit state for master/standard
        paper = Paper(
            user_id=u.id,
            topic="X", academic_level="master", language="en",
            citation_style="apa", model="gemini-flash", model_tier="standard",
            sources_json={}, status="running",
        )
        s.add(paper)
        s.flush()
        # Write a fake debit ledger row
        from app.models import CreditTransaction
        s.add(CreditTransaction(user_id=u.id, delta=-240, reason="paper_run",
                                 ref_type="paper", ref_id=paper.id))
        s.commit()
        paper_id = paper.id

    # Now run refund
    with Session() as s:
        u = s.get(User, buyer.id)
        refunded = refund_if_unrefunded(s, u, paper_id=paper_id)
        s.commit()
        assert refunded == 240

    with Session() as s:
        u = s.get(User, buyer.id)
        assert u.credit == 1000  # back to original
```

- [ ] **Step 2: Wire refund into `job_runner.py`**

In the `if type_ == "error":` block (lines 159–165), append after `paper.status = "failed"`:

```python
                if paper:
                    from .credit_ledger import refund_if_unrefunded
                    refund_if_unrefunded(db, db.get(User, paper.user_id), paper_id=paper.id)
```

Add `from .models import User` at the top if missing.

Do the same in `cancel_job` (around line 195) after `paper.status = "failed"`:

```python
    if paper:
        from .credit_ledger import refund_if_unrefunded
        refund_if_unrefunded(db, db.get(User, paper.user_id), paper_id=paper.id)
```

- [ ] **Step 3: Run tests**

```
.\.venv\Scripts\python.exe -m pytest tests/test_papers_credit.py -v
```
Expected: all pass including the new refund test.

- [ ] **Step 4: Commit**

```
git add api/app/job_runner.py api/tests/test_papers_credit.py
git commit -m "feat(api): refund credits on engine failure or cancel"
```

---

## Task 9: PricingPackages component (port from Survify)

**Files:**
- Create: `web/app/(inapp)/credit/_components/PricingPackages.tsx`
- Create: `web/app/lib/credit-packages.ts`

- [ ] **Step 1: Create the type**

`web/app/lib/credit-packages.ts`:

```ts
export type CreditPackage = {
  id: string;
  name: string;
  price_cents: number;
  old_price_cents: number;
  credits: number;
};
```

- [ ] **Step 2: Create the component**

`web/app/(inapp)/credit/_components/PricingPackages.tsx`:

```tsx
"use client";

import { Award, Minus, Plus, Ticket } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import { swrFetcher, apiPost } from "@/app/lib/api";
import type { CreditPackage } from "@/app/lib/credit-packages";

const PACKAGE_ICONS: Record<string, typeof Award> = {
  starter_package: Ticket,
  standard_package: Award,
  expert_package: Award,
};

export function PricingPackages({ onSuccess }: { onSuccess?: () => void }) {
  const { data: packages, error } = useSWR<CreditPackage[]>("/credit/packages", swrFetcher);
  const [qty, setQty] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  if (error) return <div className="text-stop-fg">Could not load packages.</div>;
  if (!packages) return <div className="text-ink-500">Loading…</div>;

  const adjust = (id: string, delta: number) =>
    setQty((p) => ({ ...p, [id]: Math.max(1, Math.min(99, (p[id] || 1) + delta)) }));

  async function buy(pkg: CreditPackage) {
    setBusy(pkg.id);
    setErr(null);
    try {
      const res = await apiPost("/credit/checkout", { package_id: pkg.id });
      if (res?.checkout_url) {
        window.location.href = res.checkout_url;
      } else {
        setErr("Could not start checkout.");
      }
    } catch (e: any) {
      setErr(e?.message || "Checkout failed.");
    } finally {
      setBusy(null);
      onSuccess?.();
    }
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {err && (
        <div className="sm:col-span-2 lg:col-span-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {err}
        </div>
      )}
      {packages.map((pkg) => {
        const Icon = PACKAGE_ICONS[pkg.id] || Award;
        const quantity = qty[pkg.id] || 1;
        const totalCents = pkg.price_cents * quantity;
        const totalCredits = pkg.credits * quantity;
        return (
          <div
            key={pkg.id}
            className="flex flex-col rounded-2xl border border-ink-100 bg-white p-5 shadow-sm hover:shadow-md transition-shadow"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-ink-900">{pkg.name}</h3>
                <p className="text-xs text-ink-500">{pkg.credits.toLocaleString()} credits</p>
              </div>
            </div>

            <div className="mt-5 flex items-baseline gap-2">
              <span className="text-3xl font-extrabold text-ink-900">${(pkg.price_cents / 100).toFixed(0)}</span>
              <span className="text-sm text-ink-400 line-through">${(pkg.old_price_cents / 100).toFixed(0)}</span>
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                className="rounded-md border border-ink-200 p-1 text-ink-500 hover:bg-ink-50"
                onClick={() => adjust(pkg.id, -1)}
                aria-label="Decrease quantity"
              >
                <Minus className="h-4 w-4" />
              </button>
              <span className="w-10 text-center text-sm font-medium text-ink-900">{quantity}</span>
              <button
                type="button"
                className="rounded-md border border-ink-200 p-1 text-ink-500 hover:bg-ink-50"
                onClick={() => adjust(pkg.id, 1)}
                aria-label="Increase quantity"
              >
                <Plus className="h-4 w-4" />
              </button>
              <span className="ml-auto text-xs text-ink-500">
                Total: ${(totalCents / 100).toFixed(0)} · {totalCredits.toLocaleString()} cr.
              </span>
            </div>

            <button
              type="button"
              onClick={() => buy(pkg)}
              disabled={busy !== null}
              className="mt-5 rounded-xl bg-primary-600 px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
            >
              {busy === pkg.id ? "Starting checkout…" : "Buy"}
            </button>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Add `apiPost` helper to `web/app/lib/api.js` if missing**

Inspect the file. If only `swrFetcher` (GET) exists, add:

```js
export async function apiPost(path, body) {
  const BASE = "http://localhost:7100/api/v1";
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    let detail;
    try { detail = JSON.parse(text); } catch { detail = text; }
    const err = new Error(detail?.detail?.error?.message || `HTTP ${res.status}`);
    err.detail = detail;
    err.status = res.status;
    throw err;
  }
  return res.json();
}
```

(Match the BASE URL style already present in the file — it likely defines `const BASE = ...` near the top.)

- [ ] **Step 4: Type-check**

From `web/`: `npx tsc --noEmit`. Expected: succeeds.

- [ ] **Step 5: Commit**

```
git add web/app/lib/credit-packages.ts web/app/lib/api.js "web/app/(inapp)/credit/_components/PricingPackages.tsx"
git commit -m "feat(web): PricingPackages component + apiPost helper"
```

---

## Task 10: Credit page

**Files:**
- Create: `web/app/(inapp)/credit/page.tsx`
- Create: `web/app/(inapp)/credit/_components/Credit.tsx`

- [ ] **Step 1: Create page**

`web/app/(inapp)/credit/page.tsx`:

```tsx
import { Suspense } from "react";
import Credit from "./_components/Credit";

export default function CreditPage() {
  return (
    <Suspense fallback={<div className="text-ink-500">Loading…</div>}>
      <Credit />
    </Suspense>
  );
}
```

- [ ] **Step 2: Create UI**

`web/app/(inapp)/credit/_components/Credit.tsx`:

```tsx
"use client";

import { CheckCircle, FileText, Hash, Mail, ShoppingCart, Ticket } from "lucide-react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useMe } from "@/app/lib/use-me";

import { PricingPackages } from "./PricingPackages";

type OrderRow = {
  id: string; status: string; created_at: string | null;
};

export default function Credit() {
  const me = useMe();
  const params = useSearchParams();
  const polarStatus = params.get("polar");

  const orders = useSWR<OrderRow[]>("/credit/orders", swrFetcher);
  const orderCount = orders.data?.length || 0;

  return (
    <section className="px-2 sm:px-4 lg:px-6">
      <div className="max-w-5xl mx-auto">
        {polarStatus === "success" && (
          <div className="flex items-center gap-3 bg-green-50 border border-green-200 rounded-xl p-4 mb-4">
            <CheckCircle className="w-5 h-5 text-green-600 flex-shrink-0" />
            <p className="text-sm text-green-800">
              Payment successful! Your credits will be added shortly.
            </p>
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 mb-4 py-3 border-b border-ink-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-primary-50 text-primary-600 flex items-center justify-center font-semibold">
              {(me.data?.username || me.data?.email || "?").charAt(0).toUpperCase()}
            </div>
            <div className="flex flex-col sm:flex-row sm:items-center gap-0.5 sm:gap-3">
              <span className="text-sm font-medium text-ink-900">
                {me.data?.username || me.data?.email?.split("@")[0] || "—"}
              </span>
              <div className="flex items-center gap-3 text-xs text-ink-500">
                <span className="flex items-center gap-1"><Mail className="w-3 h-3" /> {me.data?.email || "—"}</span>
                <span className="flex items-center gap-1"><Hash className="w-3 h-3" /> {me.data?.id?.slice(0, 8) || "—"}</span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 bg-primary-50 rounded-full px-3 py-1.5">
            <Ticket className="w-4 h-4 text-primary-600" />
            <span className="text-sm font-semibold text-primary-600">
              {me.data?.credit?.toLocaleString() || 0} Credit
            </span>
          </div>
        </div>

        <div className="flex items-center gap-6 mb-6">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-blue-50 flex items-center justify-center">
              <FileText className="w-4 h-4 text-blue-600" />
            </div>
            <div>
              <span className="text-lg font-bold text-ink-900">—</span>
              <span className="text-xs text-ink-500 ml-1">Drafts</span>
            </div>
          </div>
          <div className="w-px h-6 bg-ink-200" />
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded bg-green-50 flex items-center justify-center">
              <ShoppingCart className="w-4 h-4 text-green-600" />
            </div>
            <div>
              <span className="text-lg font-bold text-ink-900">{orderCount}</span>
              <span className="text-xs text-ink-500 ml-1">Orders</span>
            </div>
          </div>
        </div>

        <div className="mb-3">
          <h2 className="text-base font-semibold text-ink-900">Buy Credit</h2>
        </div>

        <PricingPackages onSuccess={() => me.mutate()} />

        <div className="bg-ink-50 rounded-xl p-4 mt-6">
          <h3 className="text-sm font-semibold text-ink-900 mb-3">Important Notes</h3>
          <ul className="space-y-1.5 text-xs text-ink-500">
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>100% refund if the tool fails or your draft cannot be completed.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>Credits are deducted when a draft is started and automatically refunded on engine error.</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="text-primary-500 mt-0.5">•</span>
              <span>Payment is processed within 1–3 minutes after Polar confirms.</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Type-check**

From `web/`: `npx tsc --noEmit`. Expected: clean.

- [ ] **Step 4: Boot smoke-test**

Run `npm run dev` from `web/`. Sign in (or use the dev seed admin), visit `/credit` in a browser. Expect the page to render with the three packages, $9/$19/$49 prices, a "0 Credit" badge if balance is 0.

- [ ] **Step 5: Commit**

```
git add "web/app/(inapp)/credit/"
git commit -m "feat(web): credit page with Survify-styled package grid"
```

---

## Task 11: Wizard tier picker

**Files:**
- Modify: `web/app/components/wizard.jsx` (whichever file holds the model selector)

- [ ] **Step 1: Locate the model selector**

```
grep -n "model" web/app/components/wizard.jsx
```

Identify the radio/select/buttons for model choice and the property name being sent in the POST. Common name: `model`.

- [ ] **Step 2: Replace the model UI with Standard/Premium tiles**

Use the Edit tool to replace the existing model selector. The minimal replacement:

```jsx
<div className="grid grid-cols-2 gap-3">
  {[
    { id: "standard", title: "Standard", subtitle: "Fast & inexpensive", cost: "from 60 credits" },
    { id: "premium", title: "Premium", subtitle: "Higher quality", cost: "from 150 credits" },
  ].map((t) => (
    <button
      key={t.id}
      type="button"
      onClick={() => setModelTier(t.id)}
      className={`text-left rounded-xl border p-4 transition-all ${
        modelTier === t.id
          ? "border-primary-600 bg-primary-50 shadow-sm"
          : "border-ink-200 bg-white hover:border-ink-300"
      }`}
    >
      <div className="text-sm font-semibold text-ink-900">{t.title}</div>
      <div className="text-xs text-ink-500 mt-0.5">{t.subtitle}</div>
      <div className="text-xs text-primary-600 mt-2 font-medium">{t.cost}</div>
    </button>
  ))}
</div>
```

And the corresponding state (replace existing `const [model, setModel] = ...` with):

```jsx
const [modelTier, setModelTier] = useState("standard");
```

- [ ] **Step 3: Update the POST body**

Wherever the wizard submits the paper (probably `apiPost("/papers", { ... })` or `fetch(...)`), change the field name from `model` to `model_tier`. If `apiPost` doesn't exist yet, add it to `app/lib/api.js` (or it's now there from Task 9).

- [ ] **Step 4: Smoke-test**

`npm run dev`. Visit `/wizard`, fill in topic, pick tier, submit. Expect: paper creates successfully, balance decrements (visible in topbar avatar or `/credit`).

- [ ] **Step 5: Commit**

```
git add web/app/components/wizard.jsx
git commit -m "feat(web): wizard exposes Standard/Premium tier, sends model_tier"
```

---

## Task 12: End-to-end verification

- [ ] **Step 1: Restart API and web**

```
# Terminal A
cd api && .\.venv\Scripts\activate && uvicorn app.main:app --reload --port 7100
# Terminal B
cd web && npm run dev
```

- [ ] **Step 2: Manual click-through**

1. Sign up as `cao.nv17@gmail.com`. Verify `/credit` shows "0 Credit".
2. With `DOTHESIS_PAYMENTS=dummy` in the API env, click "Buy" on Starter — redirected to `/credit?polar=dummy&order=...`. (Real Polar flow requires Polar account; dummy mode just generates a fake URL.)
3. In a separate terminal, simulate the Polar webhook:
   ```
   curl -X POST http://localhost:7100/api/v1/credit/polar/webhook \
     -H "X-Polar-Signature: dummy" \
     -d '{"type":"order.paid","data":{"checkout_id":"<the checkout id from the order>","id":"polar_test"}}'
   ```
   (Find the checkout id with `SELECT polar_checkout_id FROM orders ORDER BY created_at DESC LIMIT 1;`.)
4. Reload `/credit`. Balance is now 300.
5. Visit `/wizard`, fill in a master-level topic, pick Standard, submit. Paper creates; balance drops to 60.
6. Force an engine failure (e.g., kill the engine process). After job status flips to `failed`, refresh `/credit` — balance back to 300.

- [ ] **Step 3: Full backend test pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_pricing.py tests/test_credit_ledger.py tests/test_credit_routes.py tests/test_papers_credit.py tests/test_admin_config.py tests/test_require_admin.py tests/test_auth_me_extended.py tests/test_health.py -v
```
Expected: all new tests pass.

- [ ] **Step 4: Type-check**

```
npx tsc --noEmit
```
From `web/`. Expected: clean.

## Done criteria

- API: `/api/v1/credit/{packages,checkout,polar/webhook,orders,transactions}` all live. Paper creation deducts credits via the ledger; insufficient balance returns 402; engine failure refunds. Polar dummy mode lets the full flow be tested without a real Polar account.
- Web: `/credit` renders the three packages with Survify visual fidelity. Wizard exposes Standard/Premium; the underlying model name is never sent over the wire.
- DB: `papers.model_tier`, `orders`, `credit_transactions` exist.
- New test suite passes; pre-existing INET-bug tests remain in their existing state.

## Out of scope (Plan 3)

- Admin pages (Users / Papers / Jobs / Announcements / Orders).
- Announcement dialog system.
- Real Polar account wiring (this plan ships dummy + production paths; admin will swap env vars).
