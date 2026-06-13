# Admin + Announcements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the admin section's five pages (Users, Papers, Jobs, Announcements, Orders) and the user-facing announcement dialog system. Admin pages are gated by the `SUPER_ADMIN_EMAILS` allowlist already in place; announcements have two flavors (first-login dialog, login banner) with `localStorage` throttling.

**Architecture:** Backend grows an `Announcement` table and an `/api/v1/admin/*` namespace where every endpoint depends on `require_admin`. Cross-cutting listing endpoints use one shape: `{ items: [...], total: N, page: 1, page_size: 20 }`. Frontend adds a shared `AdminTable` component to keep the five pages consistent; the announcement dialog lives in the `(inapp)/layout.tsx` so it surfaces everywhere a logged-in user lands.

**Tech Stack:** FastAPI + SQLAlchemy 2 + Alembic, Pydantic 2; Next 16 / React 19, Tailwind, Headless UI, Heroicons, SWR.

---

## File structure

**API (`api/app/`):**
- Modify: `models.py` — add `Announcement` model.
- New migration: `migrations/versions/<rev>_announcements.py`.
- New: `routers/admin_users.py` — `GET /admin/users`, `GET /admin/users/{id}`, `POST /admin/users/{id}/credit`.
- New: `routers/admin_papers.py` — `GET /admin/papers`.
- New: `routers/admin_jobs.py` — `GET /admin/jobs`, `POST /admin/jobs/{id}/cancel`.
- New: `routers/admin_orders.py` — `GET /admin/orders`.
- New: `routers/admin_announcements.py` — `GET/POST /admin/announcements`, `PATCH/DELETE /admin/announcements/{id}`.
- New: `routers/announcements.py` — `GET /announcements/me` (user-facing).
- Modify: `main.py` — register all six new routers under `/api/v1`.

**API tests (`api/tests/`):**
- New: `test_admin_users.py`, `test_admin_papers.py`, `test_admin_jobs.py`, `test_admin_orders.py`, `test_admin_announcements.py`, `test_announcements_me.py`.

**Web (`web/`):**
- New: `app/components/admin/AdminTable.tsx` — generic paginated table.
- New: `app/components/admin/Drawer.tsx` — slide-over panel (Headless UI Dialog).
- New: `app/admin/users/_components/UsersTable.tsx`.
- Modify: `app/admin/users/page.tsx` — replace the stub.
- New: `app/admin/papers/page.tsx`, `app/admin/papers/_components/PapersTable.tsx`.
- New: `app/admin/jobs/page.tsx`, `app/admin/jobs/_components/JobsTable.tsx`.
- New: `app/admin/orders/page.tsx`, `app/admin/orders/_components/OrdersTable.tsx`.
- New: `app/admin/announcements/page.tsx`, `app/admin/announcements/_components/AnnouncementsAdmin.tsx`, `app/admin/announcements/_components/AnnouncementForm.tsx`.
- New: `app/components/announcements/AnnouncementDialog.tsx`.
- New: `app/components/announcements/AnnouncementProvider.tsx` — fetches `/announcements/me`, applies localStorage throttling, renders dialog(s).
- Modify: `app/(inapp)/layout.tsx` — wrap `SidebarLayout`'s `{children}` with `<AnnouncementProvider>`.

**Out of scope:** Real Polar account, affiliate, refund admin UI (use Users page credit-grant), exporting tables to CSV.

---

## Pre-flight

- [ ] **P1: Clean working tree**

`git status --short` returns nothing.

- [ ] **P2: Baseline test count**

From `api/`: `.\.venv\Scripts\python.exe -m pytest -q --tb=no 2>&1 | findstr "passed failed"`. Note the line (post-Plan 2 expect ~56 new passing + 15 pre-existing INET-failing).

---

## Task 1: Announcement model + migration

**Files:**
- Modify: `api/app/models.py`
- Create: `api/migrations/versions/<rev>_announcements.py`

- [ ] **Step 1: Append `Announcement` class to `models.py`**

```python


class Announcement(Base):
    __tablename__ = "announcements"

    id: Mapped[uuid.UUID] = _uuid_pk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # first_login | login_banner
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    cta_label: Mapped[str | None] = mapped_column(String(64))
    cta_url: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(default=True, server_default="true", nullable=False)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

Add `from sqlalchemy import Boolean` to imports if not already imported (the `Mapped[bool]` works without it but `Boolean` is conventional for explicit type). The default `Mapped[bool]` resolves to `Boolean`; no extra import needed.

- [ ] **Step 2: Generate migration**

From `api/`:
```
.\.venv\Scripts\python.exe -m alembic revision -m "announcements"
```
Note the new revision id. Note the current head before generation (likely `ffe6dccd65df` from Plan 2 — confirm with `alembic heads`).

- [ ] **Step 3: Write upgrade/downgrade**

In the generated file, set `down_revision = "ffe6dccd65df"` (or the actual current head). Add `from sqlalchemy.dialects import postgresql`. Replace upgrade/downgrade with:

```python
def upgrade() -> None:
    op.create_table(
        "announcements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("image_url", sa.Text),
        sa.Column("cta_label", sa.String(64)),
        sa.Column("cta_url", sa.Text),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_announcements_kind_active", "announcements", ["kind", "active"])


def downgrade() -> None:
    op.drop_index("ix_announcements_kind_active", table_name="announcements")
    op.drop_table("announcements")
```

- [ ] **Step 4: Verify head**

`alembic heads` → new revision marked `(head)`.

- [ ] **Step 5: Commit**

```
git add api/app/models.py api/migrations/versions/
git commit -m "feat(api): Announcement model + migration"
```

---

## Task 2: Admin Users router

**Files:**
- Create: `api/app/routers/admin_users.py`
- Modify: `api/app/main.py`
- Test: `api/tests/test_admin_users.py`

- [ ] **Step 1: Write failing tests**

`api/tests/test_admin_users.py`:

```python
import uuid
from sqlalchemy import select

import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import CreditTransaction, User


@pytest.fixture
def admin_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


@pytest.fixture
def non_admin_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="alice@example.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_non_admin_gets_403(non_admin_user):
    client, app = _as(non_admin_user)
    try:
        r = client.get("/api/v1/admin/users")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_list_users(admin_user):
    # Seed extra users
    Session = get_session_factory()
    with Session() as s:
        for i in range(3):
            s.add(User(email=f"u{i}@e.com", password_hash="x", credit=100*i))
        s.commit()

    client, app = _as(admin_user)
    try:
        r = client.get("/api/v1/admin/users?page=1&page_size=10")
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["total"] >= 4
        emails = {u["email"] for u in data["items"]}
        assert "cao.nv17@gmail.com" in emails
        assert "u1@e.com" in emails
    finally:
        app.dependency_overrides.clear()


def test_list_users_search(admin_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(User(email="findme@example.com", password_hash="x", credit=0))
        s.commit()

    client, app = _as(admin_user)
    try:
        r = client.get("/api/v1/admin/users?q=findme")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["email"] == "findme@example.com"
    finally:
        app.dependency_overrides.clear()


def test_grant_credit_appends_ledger_and_updates_balance(admin_user):
    Session = get_session_factory()
    with Session() as s:
        target = User(email="target@e.com", password_hash="x", credit=50)
        s.add(target)
        s.commit()
        target_id = target.id

    client, app = _as(admin_user)
    try:
        r = client.post(f"/api/v1/admin/users/{target_id}/credit", json={"delta": 500, "note": "bonus"})
        assert r.status_code == 200, r.text
        with Session() as s:
            u = s.get(User, target_id)
            assert u.credit == 550
            tx = s.scalars(select(CreditTransaction).where(CreditTransaction.user_id == target_id)).all()
            assert len(tx) == 1
            assert tx[0].delta == 500
            assert tx[0].reason == "admin_grant"
    finally:
        app.dependency_overrides.clear()


def test_get_user_returns_detail(admin_user):
    Session = get_session_factory()
    with Session() as s:
        target = User(email="detail@e.com", password_hash="x", credit=42, username="dtl")
        s.add(target)
        s.commit()
        target_id = target.id

    client, app = _as(admin_user)
    try:
        r = client.get(f"/api/v1/admin/users/{target_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == "detail@e.com"
        assert body["credit"] == 42
        assert body["username"] == "dtl"
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_users.py -v
```

- [ ] **Step 3: Implement `api/app/routers/admin_users.py`**

```python
"""Admin: users list, search, detail, grant credit."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, desc, or_
from sqlalchemy.orm import Session

from ..admin_config import is_super_admin
from ..auth_admin import require_admin
from ..credit_ledger import credit as ledger_credit, debit as ledger_debit, InsufficientCredit
from ..db import db_session
from ..models import User

router = APIRouter(prefix="/admin/users", tags=["admin"], dependencies=[Depends(require_admin)])


def _serialize(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "credit": u.credit,
        "is_super_admin": is_super_admin(u),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


@router.get("")
def list_users(
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    db: Session = Depends(db_session),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    stmt = select(User)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(User.email.ilike(like), User.username.ilike(like)))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(desc(User.created_at)).offset((page - 1) * page_size).limit(page_size)).all()
    return {
        "items": [_serialize(u) for u in rows],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.get("/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(db_session)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    return _serialize(u)


class CreditGrantRequest(BaseModel):
    delta: int = Field(description="Positive = grant, negative = debit")
    note: str | None = None  # accepted but not persisted; for future audit


@router.post("/{user_id}/credit")
def grant_credit(
    user_id: uuid.UUID,
    body: CreditGrantRequest,
    db: Session = Depends(db_session),
):
    if body.delta == 0:
        raise HTTPException(400, detail={"error": {"code": "zero_delta"}})
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if body.delta > 0:
        ledger_credit(db, u, delta=body.delta, reason="admin_grant", ref_type="user", ref_id=u.id)
    else:
        try:
            ledger_debit(db, u, delta=-body.delta, reason="admin_grant", ref_type="user", ref_id=u.id)
        except InsufficientCredit as e:
            raise HTTPException(400, detail={"error": {"code": "insufficient", "balance": e.balance, "required": e.required}})
    db.commit()
    db.refresh(u)
    return _serialize(u)
```

- [ ] **Step 4: Register in `main.py`**

```python
from .routers import admin_users as admin_users_router
# ...
    app.include_router(admin_users_router.router, prefix="/api/v1")
```

- [ ] **Step 5: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_users.py -v
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add api/app/routers/admin_users.py api/app/main.py api/tests/test_admin_users.py
git commit -m "feat(api): admin users router — list, search, detail, credit grant"
```

---

## Task 3: Admin Papers + Jobs + Orders routers

These three are structurally similar (paginated list, simple filter). One commit for all three to keep the diff small.

**Files:**
- Create: `api/app/routers/admin_papers.py`
- Create: `api/app/routers/admin_jobs.py`
- Create: `api/app/routers/admin_orders.py`
- Modify: `api/app/main.py`
- Test: `api/tests/test_admin_papers.py`, `api/tests/test_admin_jobs.py`, `api/tests/test_admin_orders.py`

- [ ] **Step 1: Write failing tests (one file)**

Create `api/tests/test_admin_papers.py`:

```python
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Paper, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_admin_papers_lists_all(admin):
    Session = get_session_factory()
    with Session() as s:
        owner = User(email="own@e.com", password_hash="x", credit=0)
        s.add(owner)
        s.flush()
        for i in range(3):
            s.add(Paper(
                user_id=owner.id, topic=f"T{i}", academic_level="master",
                language="en", citation_style="apa", model="gemini-flash",
                model_tier="standard", sources_json={}, status="done",
            ))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.get("/api/v1/admin/papers")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 3
        item = data["items"][0]
        assert "owner_email" in item
        assert "model_tier" in item
        assert "status" in item
    finally:
        app.dependency_overrides.clear()
```

`api/tests/test_admin_jobs.py`:

```python
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Job, Paper, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_admin_jobs_lists_recent(admin):
    Session = get_session_factory()
    with Session() as s:
        owner = User(email="o@e.com", password_hash="x", credit=0)
        s.add(owner)
        s.flush()
        paper = Paper(
            user_id=owner.id, topic="X", academic_level="research",
            language="en", citation_style="apa", model="gemini-flash",
            model_tier="standard", sources_json={}, status="running",
        )
        s.add(paper)
        s.flush()
        s.add(Job(paper_id=paper.id, status="running"))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.get("/api/v1/admin/jobs?status=running")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["status"] == "running"
        assert "paper_topic" in item
        assert "owner_email" in item
    finally:
        app.dependency_overrides.clear()
```

`api/tests/test_admin_orders.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Order, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_admin_orders_lists(admin):
    Session = get_session_factory()
    with Session() as s:
        buyer = User(email="b@e.com", password_hash="x", credit=0)
        s.add(buyer)
        s.flush()
        s.add(Order(
            user_id=buyer.id, package_id="standard_package",
            credits=700, amount_cents=1900, status="paid",
            polar_checkout_id="ck_xx",
        ))
        s.commit()

    client, app = _as(admin)
    try:
        r = client.get("/api/v1/admin/orders")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        item = data["items"][0]
        assert item["owner_email"] == "b@e.com"
        assert item["status"] == "paid"
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_papers.py tests/test_admin_jobs.py tests/test_admin_orders.py -v
```

- [ ] **Step 3: Implement `api/app/routers/admin_papers.py`**

```python
"""Admin: list all papers across users."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Paper, User

router = APIRouter(prefix="/admin/papers", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
def list_papers(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    user_id: str | None = None,
    db: Session = Depends(db_session),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    stmt = select(Paper, User).join(User, User.id == Paper.user_id)
    if status:
        stmt = stmt.where(Paper.status == status)
    if user_id:
        stmt = stmt.where(Paper.user_id == user_id)
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0
    rows = db.execute(
        stmt.order_by(desc(Paper.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(p.id), "owner_email": u.email, "owner_id": str(u.id),
                "topic": p.topic, "academic_level": p.academic_level,
                "model_tier": p.model_tier, "status": p.status,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "updated_at": p.updated_at.isoformat() if p.updated_at else None,
            }
            for p, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 4: Implement `api/app/routers/admin_jobs.py`**

```python
"""Admin: list and cancel jobs across users."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..job_runner import cancel_job
from ..models import Job, Paper, User

router = APIRouter(prefix="/admin/jobs", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
def list_jobs(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(db_session),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    stmt = select(Job, Paper, User).join(Paper, Paper.id == Job.paper_id).join(User, User.id == Paper.user_id)
    if status:
        stmt = stmt.where(Job.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Job.started_at).nullslast()).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(j.id), "paper_id": str(p.id), "paper_topic": p.topic,
                "owner_email": u.email, "status": j.status, "phase": j.phase,
                "progress": j.progress,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
                "error_text": j.error_text,
            }
            for j, p, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }


@router.post("/{job_id}/cancel", status_code=202)
def cancel(job_id: uuid.UUID, db: Session = Depends(db_session)):
    j = db.get(Job, job_id)
    if not j:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    if j.status in {"done", "failed", "canceled"}:
        return {"status": j.status}
    cancel_job(db, j)
    return {"status": "canceled"}
```

- [ ] **Step 5: Implement `api/app/routers/admin_orders.py`**

```python
"""Admin: credit-purchase audit."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, desc
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Order, User

router = APIRouter(prefix="/admin/orders", tags=["admin"], dependencies=[Depends(require_admin)])


@router.get("")
def list_orders(
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    db: Session = Depends(db_session),
):
    page = max(1, page)
    page_size = max(1, min(100, page_size))
    stmt = select(Order, User).join(User, User.id == Order.user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(
        stmt.order_by(desc(Order.created_at)).offset((page - 1) * page_size).limit(page_size)
    ).all()
    return {
        "items": [
            {
                "id": str(o.id), "owner_email": u.email, "owner_id": str(u.id),
                "package_id": o.package_id, "credits": o.credits,
                "amount_cents": o.amount_cents, "currency": o.currency,
                "status": o.status,
                "polar_checkout_id": o.polar_checkout_id,
                "polar_order_id": o.polar_order_id,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            }
            for o, u in rows
        ],
        "total": int(total),
        "page": page,
        "page_size": page_size,
    }
```

- [ ] **Step 6: Register all three in `main.py`**

```python
from .routers import admin_papers as admin_papers_router
from .routers import admin_jobs as admin_jobs_router
from .routers import admin_orders as admin_orders_router
# ...
    app.include_router(admin_papers_router.router, prefix="/api/v1")
    app.include_router(admin_jobs_router.router, prefix="/api/v1")
    app.include_router(admin_orders_router.router, prefix="/api/v1")
```

- [ ] **Step 7: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_papers.py tests/test_admin_jobs.py tests/test_admin_orders.py -v
```
Expected: 3 passed.

- [ ] **Step 8: Commit**

```
git add api/app/routers/admin_papers.py api/app/routers/admin_jobs.py api/app/routers/admin_orders.py api/app/main.py api/tests/test_admin_papers.py api/tests/test_admin_jobs.py api/tests/test_admin_orders.py
git commit -m "feat(api): admin papers, jobs, orders routers"
```

---

## Task 4: Announcements (admin CRUD + user-facing me-fetch)

**Files:**
- Create: `api/app/routers/admin_announcements.py`
- Create: `api/app/routers/announcements.py`
- Modify: `api/app/main.py`
- Test: `api/tests/test_admin_announcements.py`, `api/tests/test_announcements_me.py`

- [ ] **Step 1: Write failing tests**

`api/tests/test_admin_announcements.py`:

```python
import uuid
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Announcement, User


@pytest.fixture
def admin():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="cao.nv17@gmail.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_create_and_list_announcement(admin):
    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/announcements", json={
            "kind": "login_banner",
            "title": "Welcome",
            "body": "Hello world",
            "active": True,
        })
        assert r.status_code == 201, r.text
        ann = r.json()
        assert ann["kind"] == "login_banner"

        r2 = client.get("/api/v1/admin/announcements")
        assert r2.status_code == 200
        items = r2.json()["items"]
        assert any(a["id"] == ann["id"] for a in items)
    finally:
        app.dependency_overrides.clear()


def test_patch_announcement(admin):
    Session = get_session_factory()
    with Session() as s:
        ann = Announcement(kind="first_login", title="Original", body="x", active=True)
        s.add(ann)
        s.commit()
        ann_id = ann.id

    client, app = _as(admin)
    try:
        r = client.patch(f"/api/v1/admin/announcements/{ann_id}", json={"title": "Updated"})
        assert r.status_code == 200
        assert r.json()["title"] == "Updated"
    finally:
        app.dependency_overrides.clear()


def test_delete_announcement(admin):
    Session = get_session_factory()
    with Session() as s:
        ann = Announcement(kind="first_login", title="Doomed", body="x", active=True)
        s.add(ann)
        s.commit()
        ann_id = ann.id

    client, app = _as(admin)
    try:
        r = client.delete(f"/api/v1/admin/announcements/{ann_id}")
        assert r.status_code == 204
        with Session() as s:
            assert s.get(Announcement, ann_id) is None
    finally:
        app.dependency_overrides.clear()


def test_bad_kind_rejected(admin):
    client, app = _as(admin)
    try:
        r = client.post("/api/v1/admin/announcements", json={
            "kind": "nonsense", "title": "T", "body": "B", "active": True,
        })
        assert r.status_code == 422
    finally:
        app.dependency_overrides.clear()
```

`api/tests/test_announcements_me.py`:

```python
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from app.db import get_session_factory
from app.main import create_app
from app.models import Announcement, User


@pytest.fixture
def regular_user():
    Session = get_session_factory()
    with Session() as s:
        u = User(email="reader@e.com", password_hash="x", credit=0)
        s.add(u)
        s.commit()
        return u


def _as(user):
    app = create_app()
    from app.deps import current_user
    app.dependency_overrides[current_user] = lambda: user
    return TestClient(app), app


def test_me_returns_active_banner(regular_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Hi", body="x", active=True))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        data = r.json()
        assert data["login_banner"]["title"] == "Hi"
        assert data["first_login"] is None
    finally:
        app.dependency_overrides.clear()


def test_inactive_banner_not_returned(regular_user):
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Hidden", body="x", active=False))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        assert r.json()["login_banner"] is None
    finally:
        app.dependency_overrides.clear()


def test_expired_banner_not_returned(regular_user):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    Session = get_session_factory()
    with Session() as s:
        s.add(Announcement(kind="login_banner", title="Old", body="x", active=True, ends_at=past))
        s.commit()

    client, app = _as(regular_user)
    try:
        r = client.get("/api/v1/announcements/me")
        assert r.status_code == 200
        assert r.json()["login_banner"] is None
    finally:
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run, expect fail**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_announcements.py tests/test_announcements_me.py -v
```

- [ ] **Step 3: Implement `api/app/routers/admin_announcements.py`**

```python
"""Admin CRUD for announcements."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..auth_admin import require_admin
from ..db import db_session
from ..models import Announcement

router = APIRouter(prefix="/admin/announcements", tags=["admin"], dependencies=[Depends(require_admin)])

ALLOWED_KINDS = {"first_login", "login_banner"}


class AnnouncementIn(BaseModel):
    kind: str
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1)
    image_url: str | None = None
    cta_label: str | None = Field(default=None, max_length=64)
    cta_url: str | None = None
    active: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class AnnouncementPatch(BaseModel):
    kind: str | None = None
    title: str | None = None
    body: str | None = None
    image_url: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    active: bool | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


def _serialize(a: Announcement) -> dict:
    return {
        "id": str(a.id), "kind": a.kind, "title": a.title, "body": a.body,
        "image_url": a.image_url, "cta_label": a.cta_label, "cta_url": a.cta_url,
        "active": a.active,
        "starts_at": a.starts_at.isoformat() if a.starts_at else None,
        "ends_at": a.ends_at.isoformat() if a.ends_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.get("")
def list_all(db: Session = Depends(db_session)):
    rows = db.scalars(select(Announcement).order_by(desc(Announcement.created_at))).all()
    return {"items": [_serialize(a) for a in rows], "total": len(rows), "page": 1, "page_size": len(rows)}


@router.post("", status_code=201)
def create(body: AnnouncementIn, db: Session = Depends(db_session)):
    if body.kind not in ALLOWED_KINDS:
        raise HTTPException(422, detail={"error": {"code": "bad_kind"}})
    a = Announcement(**body.model_dump())
    db.add(a)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.patch("/{ann_id}")
def patch(ann_id: uuid.UUID, body: AnnouncementPatch, db: Session = Depends(db_session)):
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    for key, val in body.model_dump(exclude_unset=True).items():
        if key == "kind" and val not in ALLOWED_KINDS:
            raise HTTPException(422, detail={"error": {"code": "bad_kind"}})
        setattr(a, key, val)
    db.commit()
    db.refresh(a)
    return _serialize(a)


@router.delete("/{ann_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(ann_id: uuid.UUID, db: Session = Depends(db_session)):
    a = db.get(Announcement, ann_id)
    if not a:
        raise HTTPException(404, detail={"error": {"code": "not_found"}})
    db.delete(a)
    db.commit()
    return Response(status_code=204)
```

- [ ] **Step 4: Implement `api/app/routers/announcements.py`**

```python
"""User-facing announcement fetch."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import desc, or_, select
from sqlalchemy.orm import Session

from ..db import db_session
from ..deps import current_user
from ..models import Announcement, User

router = APIRouter(prefix="/announcements", tags=["announcements"])


def _serialize(a: Announcement) -> dict:
    return {
        "id": str(a.id), "kind": a.kind, "title": a.title, "body": a.body,
        "image_url": a.image_url, "cta_label": a.cta_label, "cta_url": a.cta_url,
    }


def _pick_one(db: Session, kind: str) -> Announcement | None:
    now = datetime.now(timezone.utc)
    stmt = (
        select(Announcement)
        .where(
            Announcement.kind == kind,
            Announcement.active.is_(True),
            or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
            or_(Announcement.ends_at.is_(None), Announcement.ends_at > now),
        )
        .order_by(desc(Announcement.created_at))
        .limit(1)
    )
    return db.scalar(stmt)


@router.get("/me")
def announcements_for_me(
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
):
    return {
        "first_login": (lambda a: _serialize(a) if a else None)(_pick_one(db, "first_login")),
        "login_banner": (lambda a: _serialize(a) if a else None)(_pick_one(db, "login_banner")),
    }
```

- [ ] **Step 5: Register both routers**

In `main.py`:

```python
from .routers import admin_announcements as admin_announcements_router
from .routers import announcements as announcements_router
# ...
    app.include_router(admin_announcements_router.router, prefix="/api/v1")
    app.include_router(announcements_router.router, prefix="/api/v1")
```

- [ ] **Step 6: Run tests, expect pass**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_announcements.py tests/test_announcements_me.py -v
```
Expected: 7 passed.

- [ ] **Step 7: Commit**

```
git add api/app/routers/admin_announcements.py api/app/routers/announcements.py api/app/main.py api/tests/test_admin_announcements.py api/tests/test_announcements_me.py
git commit -m "feat(api): announcements admin CRUD + user-facing /announcements/me"
```

---

## Task 5: Shared admin UI primitives

**Files:**
- Create: `web/app/components/admin/AdminTable.tsx`
- Create: `web/app/components/admin/Drawer.tsx`

- [ ] **Step 1: Create `AdminTable.tsx`**

```tsx
"use client";

import clsx from "clsx";
import { useState, type ReactNode } from "react";

export type AdminColumn<T> = {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  className?: string;
};

type AdminTableProps<T> = {
  columns: AdminColumn<T>[];
  rows: T[];
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onRowClick?: (row: T) => void;
  isLoading?: boolean;
  emptyMessage?: string;
};

export function AdminTable<T extends { id: string }>(props: AdminTableProps<T>) {
  const { columns, rows, total, page, pageSize, onPageChange, onRowClick, isLoading, emptyMessage } = props;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="overflow-hidden rounded-2xl border border-ink-100 bg-white shadow-sm">
      <table className="min-w-full text-sm">
        <thead className="bg-ink-50">
          <tr>
            {columns.map((c) => (
              <th
                key={c.key}
                className={clsx("px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500", c.className)}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {isLoading && (
            <tr><td colSpan={columns.length} className="px-4 py-8 text-center text-ink-500">Loading…</td></tr>
          )}
          {!isLoading && rows.length === 0 && (
            <tr><td colSpan={columns.length} className="px-4 py-8 text-center text-ink-500">
              {emptyMessage || "No results"}
            </td></tr>
          )}
          {!isLoading && rows.map((row) => (
            <tr
              key={row.id}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              className={clsx(onRowClick && "cursor-pointer hover:bg-ink-50/60", "transition-colors")}
            >
              {columns.map((c) => (
                <td key={c.key} className={clsx("px-4 py-3 text-ink-900", c.className)}>
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center justify-between border-t border-ink-100 bg-white px-4 py-3 text-sm">
        <div className="text-ink-500">{total.toLocaleString()} total</div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => onPageChange(page - 1)}
            className="rounded-md border border-ink-200 px-3 py-1 text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Prev
          </button>
          <span className="text-ink-500">
            {page} / {totalPages}
          </span>
          <button
            type="button"
            disabled={page >= totalPages}
            onClick={() => onPageChange(page + 1)}
            className="rounded-md border border-ink-200 px-3 py-1 text-ink-700 hover:bg-ink-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create `Drawer.tsx`**

```tsx
"use client";

import { Dialog, DialogPanel, Transition, TransitionChild } from "@headlessui/react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { Fragment, type ReactNode } from "react";

export function Drawer({
  open, onClose, title, children,
}: {
  open: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Transition show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-ink-900/40" />
        </TransitionChild>
        <div className="fixed inset-y-0 right-0 flex max-w-full">
          <TransitionChild
            as={Fragment}
            enter="transform transition ease-out duration-300"
            enterFrom="translate-x-full"
            enterTo="translate-x-0"
            leave="transform transition ease-in duration-200"
            leaveFrom="translate-x-0"
            leaveTo="translate-x-full"
          >
            <DialogPanel className="w-screen max-w-md bg-white shadow-xl flex flex-col">
              <div className="flex items-center justify-between border-b border-ink-100 px-5 py-4">
                <div className="text-sm font-semibold text-ink-900">{title}</div>
                <button type="button" onClick={onClose} className="text-ink-500 hover:text-ink-900">
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto p-5">{children}</div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </Transition>
  );
}
```

- [ ] **Step 3: Type-check**

`npx tsc --noEmit` from `web/`. Expected: clean.

- [ ] **Step 4: Commit**

```
git add web/app/components/admin/
git commit -m "feat(web): shared AdminTable + Drawer primitives"
```

---

## Task 6: Admin Users page

**Files:**
- Modify: `web/app/admin/users/page.tsx`
- Create: `web/app/admin/users/_components/UsersTable.tsx`

- [ ] **Step 1: Replace `users/page.tsx` body**

```tsx
import UsersTable from "./_components/UsersTable";

export default function UsersPage() {
  return <UsersTable />;
}
```

- [ ] **Step 2: Create `users/_components/UsersTable.tsx`**

```tsx
"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { Drawer } from "@/app/components/admin/Drawer";
import { apiFetch, swrFetcher } from "@/app/lib/api";

type AdminUserRow = {
  id: string;
  email: string;
  username: string | null;
  credit: number;
  is_super_admin: boolean;
  created_at: string | null;
};

type ListResponse = {
  items: AdminUserRow[];
  total: number;
  page: number;
  page_size: number;
};

export default function UsersTable() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState("");
  const [active, setActive] = useState<AdminUserRow | null>(null);
  const [delta, setDelta] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (q.trim()) params.set("q", q.trim());
  const key = `/admin/users?${params.toString()}`;
  const { data, isLoading } = useSWR<ListResponse>(key, swrFetcher);

  async function grant() {
    if (!active) return;
    const n = parseInt(delta, 10);
    if (!n) { setErr("Enter a non-zero integer"); return; }
    setBusy(true);
    setErr(null);
    try {
      await apiFetch(`/admin/users/${active.id}/credit`, {
        method: "POST",
        body: { delta: n },
      });
      setDelta("");
      globalMutate(key);
      setActive(null);
    } catch (e: any) {
      setErr(e?.body?.detail?.error?.code === "insufficient"
        ? "Cannot debit beyond current balance."
        : e?.message || "Grant failed.");
    } finally {
      setBusy(false);
    }
  }

  const columns: AdminColumn<AdminUserRow>[] = [
    { key: "email", header: "Email", render: (r) => <span className="font-medium">{r.email}</span> },
    { key: "username", header: "Username", render: (r) => r.username || "—" },
    { key: "credit", header: "Credit", render: (r) => r.credit.toLocaleString(), className: "tabular-nums" },
    {
      key: "admin",
      header: "Admin",
      render: (r) => r.is_super_admin
        ? <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-600">Yes</span>
        : <span className="text-ink-400">—</span>,
    },
    {
      key: "created",
      header: "Joined",
      render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
      className: "text-ink-500 text-xs",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Users</h1>
        <input
          type="search"
          placeholder="Search email or username…"
          value={q}
          onChange={(e) => { setQ(e.target.value); setPage(1); }}
          className="w-72 rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm focus:border-primary-500 focus:outline-none"
        />
      </div>
      <AdminTable<AdminUserRow>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        onRowClick={(r) => { setActive(r); setDelta(""); setErr(null); }}
        isLoading={isLoading}
      />
      <Drawer open={!!active} onClose={() => setActive(null)} title={active?.email}>
        {active && (
          <div className="space-y-4">
            <div className="rounded-xl bg-ink-50 p-3 text-sm">
              <div className="text-ink-500">Balance</div>
              <div className="text-2xl font-bold text-ink-900">{active.credit.toLocaleString()} credits</div>
            </div>
            <div>
              <label className="text-xs font-medium text-ink-500">Grant or debit (negative = debit)</label>
              <div className="mt-1 flex gap-2">
                <input
                  type="number"
                  value={delta}
                  onChange={(e) => setDelta(e.target.value)}
                  placeholder="e.g. 500 or -100"
                  className="flex-1 rounded-xl border border-ink-200 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={grant}
                  disabled={busy}
                  className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
                >
                  {busy ? "Applying…" : "Apply"}
                </button>
              </div>
              {err && <div className="mt-2 text-xs text-red-700">{err}</div>}
            </div>
            <div className="text-xs text-ink-500">
              Admin status is managed in code (`SUPER_ADMIN_EMAILS` constant); not editable here.
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 4: Commit**

```
git add web/app/admin/users/
git commit -m "feat(web): admin Users page with search and credit-grant drawer"
```

---

## Task 7: Admin Papers, Jobs, Orders pages

Three pages in one commit — they share the AdminTable shape.

- [ ] **Step 1: Create `web/app/admin/papers/page.tsx`**

```tsx
import PapersTable from "./_components/PapersTable";

export default function PapersPage() {
  return <PapersTable />;
}
```

- [ ] **Step 2: Create `web/app/admin/papers/_components/PapersTable.tsx`**

```tsx
"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; owner_email: string; owner_id: string;
  topic: string; academic_level: string; model_tier: string;
  status: string; created_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "draft", "running", "done", "failed", "canceled"];

export default function PapersTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const { data, isLoading } = useSWR<ListResp>(`/admin/papers?${params.toString()}`, swrFetcher);

  const columns: AdminColumn<Row>[] = [
    { key: "topic", header: "Topic", render: (r) => <span className="font-medium truncate block max-w-md">{r.topic}</span> },
    { key: "owner", header: "Owner", render: (r) => r.owner_email },
    { key: "level", header: "Level", render: (r) => r.academic_level },
    { key: "tier", header: "Tier", render: (r) => r.model_tier },
    {
      key: "status",
      header: "Status",
      render: (r) => <StatusPill status={r.status} />,
    },
    {
      key: "created",
      header: "Created",
      render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
      className: "text-ink-500 text-xs",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Papers</h1>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>
      <AdminTable<Row>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        isLoading={isLoading}
      />
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const map: Record<string, string> = {
    done: "bg-green-50 text-green-700",
    running: "bg-blue-50 text-blue-700",
    failed: "bg-red-50 text-red-700",
    canceled: "bg-ink-100 text-ink-700",
    draft: "bg-ink-50 text-ink-500",
  };
  const cls = map[status] || "bg-ink-100 text-ink-700";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${cls}`}>{status}</span>;
}
```

- [ ] **Step 3: Create `web/app/admin/jobs/page.tsx`**

```tsx
import JobsTable from "./_components/JobsTable";

export default function JobsPage() {
  return <JobsTable />;
}
```

- [ ] **Step 4: Create `web/app/admin/jobs/_components/JobsTable.tsx`**

```tsx
"use client";

import { useState } from "react";
import useSWR, { mutate } from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { apiFetch, swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; paper_id: string; paper_topic: string;
  owner_email: string; status: string; phase: string | null;
  progress: number;
  started_at: string | null; finished_at: string | null;
  error_text: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "queued", "running", "done", "failed", "canceled"];

export default function JobsTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("running");
  const [cancelling, setCancelling] = useState<string | null>(null);
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const key = `/admin/jobs?${params.toString()}`;
  const { data, isLoading } = useSWR<ListResp>(key, swrFetcher);

  async function doCancel(jobId: string) {
    setCancelling(jobId);
    try {
      await apiFetch(`/admin/jobs/${jobId}/cancel`, { method: "POST" });
      mutate(key);
    } finally {
      setCancelling(null);
    }
  }

  const columns: AdminColumn<Row>[] = [
    { key: "topic", header: "Topic", render: (r) => <span className="font-medium truncate block max-w-md">{r.paper_topic}</span> },
    { key: "owner", header: "Owner", render: (r) => r.owner_email },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "phase", header: "Phase", render: (r) => r.phase || "—" },
    { key: "progress", header: "Progress", render: (r) => `${Math.round((r.progress || 0) * 100)}%`, className: "tabular-nums" },
    {
      key: "actions",
      header: "",
      render: (r) => r.status === "running" || r.status === "queued"
        ? (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); doCancel(r.id); }}
            disabled={cancelling === r.id}
            className="rounded-md border border-red-200 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {cancelling === r.id ? "Cancelling…" : "Cancel"}
          </button>
        )
        : <span className="text-ink-400">—</span>,
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Jobs</h1>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>
      <AdminTable<Row>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        isLoading={isLoading}
      />
    </div>
  );
}
```

- [ ] **Step 5: Create `web/app/admin/orders/page.tsx`**

```tsx
import OrdersTable from "./_components/OrdersTable";

export default function OrdersPage() {
  return <OrdersTable />;
}
```

- [ ] **Step 6: Create `web/app/admin/orders/_components/OrdersTable.tsx`**

```tsx
"use client";

import { useState } from "react";
import useSWR from "swr";

import { AdminTable, type AdminColumn } from "@/app/components/admin/AdminTable";
import { swrFetcher } from "@/app/lib/api";

type Row = {
  id: string; owner_email: string; package_id: string;
  credits: number; amount_cents: number; currency: string;
  status: string;
  polar_checkout_id: string | null; polar_order_id: string | null;
  created_at: string | null; paid_at: string | null;
};

type ListResp = { items: Row[]; total: number; page: number; page_size: number };

const STATUSES = ["", "pending", "paid", "refunded", "failed"];

export default function OrdersTable() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const params = new URLSearchParams({ page: String(page), page_size: "20" });
  if (status) params.set("status", status);
  const { data, isLoading } = useSWR<ListResp>(`/admin/orders?${params.toString()}`, swrFetcher);

  const columns: AdminColumn<Row>[] = [
    { key: "owner", header: "Owner", render: (r) => <span className="font-medium">{r.owner_email}</span> },
    { key: "package", header: "Package", render: (r) => r.package_id },
    { key: "credits", header: "Credits", render: (r) => r.credits.toLocaleString(), className: "tabular-nums" },
    { key: "amount", header: "Amount", render: (r) => `$${(r.amount_cents / 100).toFixed(2)} ${r.currency}`, className: "tabular-nums" },
    { key: "status", header: "Status", render: (r) => r.status },
    { key: "polar", header: "Polar ID", render: (r) => r.polar_order_id || r.polar_checkout_id || "—", className: "font-mono text-xs text-ink-500" },
    {
      key: "created",
      header: "Created",
      render: (r) => r.created_at ? new Date(r.created_at).toLocaleDateString() : "—",
      className: "text-ink-500 text-xs",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold text-ink-900">Orders</h1>
        <select
          value={status}
          onChange={(e) => { setStatus(e.target.value); setPage(1); }}
          className="rounded-xl border border-ink-200 bg-white px-3 py-2 text-sm shadow-sm"
        >
          {STATUSES.map((s) => <option key={s} value={s}>{s || "All statuses"}</option>)}
        </select>
      </div>
      <AdminTable<Row>
        columns={columns}
        rows={data?.items || []}
        total={data?.total || 0}
        page={page}
        pageSize={20}
        onPageChange={setPage}
        isLoading={isLoading}
      />
    </div>
  );
}
```

- [ ] **Step 7: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 8: Commit**

```
git add web/app/admin/papers/ web/app/admin/jobs/ web/app/admin/orders/
git commit -m "feat(web): admin Papers + Jobs + Orders pages"
```

---

## Task 8: Admin Announcements page (CRUD)

**Files:**
- Create: `web/app/admin/announcements/page.tsx`
- Create: `web/app/admin/announcements/_components/AnnouncementsAdmin.tsx`
- Create: `web/app/admin/announcements/_components/AnnouncementForm.tsx`

- [ ] **Step 1: Create `page.tsx`**

```tsx
import AnnouncementsAdmin from "./_components/AnnouncementsAdmin";

export default function AnnouncementsPage() {
  return <AnnouncementsAdmin />;
}
```

- [ ] **Step 2: Create `AnnouncementForm.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";

export type AnnouncementInput = {
  kind: "first_login" | "login_banner";
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
};

export function AnnouncementForm({
  initial, onSubmit, submitting,
}: {
  initial?: Partial<AnnouncementInput>;
  onSubmit: (data: AnnouncementInput) => void;
  submitting: boolean;
}) {
  const [form, setForm] = useState<AnnouncementInput>({
    kind: (initial?.kind as AnnouncementInput["kind"]) || "login_banner",
    title: initial?.title || "",
    body: initial?.body || "",
    image_url: initial?.image_url || null,
    cta_label: initial?.cta_label || null,
    cta_url: initial?.cta_url || null,
    active: initial?.active ?? true,
    starts_at: initial?.starts_at || null,
    ends_at: initial?.ends_at || null,
  });

  useEffect(() => {
    if (initial) {
      setForm((f) => ({ ...f, ...(initial as any) }));
    }
  }, [initial]);

  const set = <K extends keyof AnnouncementInput>(k: K, v: AnnouncementInput[K]) =>
    setForm((f) => ({ ...f, [k]: v }));

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(form); }}
      className="space-y-3"
    >
      <Field label="Kind">
        <select
          value={form.kind}
          onChange={(e) => set("kind", e.target.value as AnnouncementInput["kind"])}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        >
          <option value="first_login">first_login</option>
          <option value="login_banner">login_banner</option>
        </select>
      </Field>
      <Field label="Title">
        <input
          required
          value={form.title}
          onChange={(e) => set("title", e.target.value)}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <Field label="Body">
        <textarea
          required
          value={form.body}
          onChange={(e) => set("body", e.target.value)}
          rows={6}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <Field label="Image URL (optional)">
        <input
          value={form.image_url || ""}
          onChange={(e) => set("image_url", e.target.value || null)}
          className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
        />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="CTA label">
          <input
            value={form.cta_label || ""}
            onChange={(e) => set("cta_label", e.target.value || null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
        <Field label="CTA URL">
          <input
            value={form.cta_url || ""}
            onChange={(e) => set("cta_url", e.target.value || null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Starts at (ISO)">
          <input
            type="datetime-local"
            value={form.starts_at?.slice(0, 16) || ""}
            onChange={(e) => set("starts_at", e.target.value ? new Date(e.target.value).toISOString() : null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
        <Field label="Ends at (ISO)">
          <input
            type="datetime-local"
            value={form.ends_at?.slice(0, 16) || ""}
            onChange={(e) => set("ends_at", e.target.value ? new Date(e.target.value).toISOString() : null)}
            className="w-full rounded-xl border border-ink-200 px-3 py-2 text-sm"
          />
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={form.active} onChange={(e) => set("active", e.target.checked)} />
        Active
      </label>
      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700 disabled:opacity-50"
      >
        {submitting ? "Saving…" : "Save"}
      </button>
    </form>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-ink-500">{label}</span>
      <div className="mt-1">{children}</div>
    </label>
  );
}
```

- [ ] **Step 3: Create `AnnouncementsAdmin.tsx`**

```tsx
"use client";

import { useState } from "react";
import useSWR, { mutate as globalMutate } from "swr";

import { Drawer } from "@/app/components/admin/Drawer";
import { apiFetch, swrFetcher } from "@/app/lib/api";

import { AnnouncementForm, type AnnouncementInput } from "./AnnouncementForm";

type AnnouncementRow = {
  id: string;
  kind: string;
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
  created_at: string | null;
};

type ListResp = { items: AnnouncementRow[]; total: number };

const KEY = "/admin/announcements";

export default function AnnouncementsAdmin() {
  const { data } = useSWR<ListResp>(KEY, swrFetcher);
  const [editing, setEditing] = useState<AnnouncementRow | "new" | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function save(form: AnnouncementInput) {
    setSubmitting(true);
    try {
      if (editing === "new") {
        await apiFetch(KEY, { method: "POST", body: form });
      } else if (editing) {
        await apiFetch(`${KEY}/${editing.id}`, { method: "PATCH", body: form });
      }
      setEditing(null);
      globalMutate(KEY);
    } finally {
      setSubmitting(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this announcement?")) return;
    await apiFetch(`${KEY}/${id}`, { method: "DELETE" });
    globalMutate(KEY);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-ink-900">Announcements</h1>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
        >
          + New
        </button>
      </div>

      <div className="grid gap-3">
        {(data?.items || []).map((a) => (
          <div key={a.id} className="rounded-2xl border border-ink-100 bg-white p-4 shadow-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-semibold text-primary-600">{a.kind}</span>
                  {!a.active && <span className="rounded-full bg-ink-100 px-2 py-0.5 text-xs text-ink-500">inactive</span>}
                </div>
                <h3 className="mt-2 text-base font-semibold text-ink-900">{a.title}</h3>
                <p className="mt-1 text-sm text-ink-500 line-clamp-2">{a.body}</p>
              </div>
              <div className="flex gap-2 flex-shrink-0">
                <button type="button" onClick={() => setEditing(a)} className="text-sm text-primary-600 hover:underline">
                  Edit
                </button>
                <button type="button" onClick={() => remove(a.id)} className="text-sm text-red-600 hover:underline">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
        {data?.items?.length === 0 && (
          <div className="rounded-2xl border border-dashed border-ink-200 p-8 text-center text-sm text-ink-500">
            No announcements yet.
          </div>
        )}
      </div>

      <Drawer
        open={editing !== null}
        onClose={() => setEditing(null)}
        title={editing === "new" ? "New announcement" : "Edit announcement"}
      >
        {editing && (
          <AnnouncementForm
            initial={editing === "new" ? undefined : editing}
            onSubmit={save}
            submitting={submitting}
          />
        )}
      </Drawer>
    </div>
  );
}
```

- [ ] **Step 4: Type-check**

`npx tsc --noEmit`. Expected: clean.

- [ ] **Step 5: Commit**

```
git add web/app/admin/announcements/
git commit -m "feat(web): admin Announcements page with CRUD drawer"
```

---

## Task 9: User-facing announcement dialog + provider

**Files:**
- Create: `web/app/components/announcements/AnnouncementDialog.tsx`
- Create: `web/app/components/announcements/AnnouncementProvider.tsx`
- Modify: `web/app/(inapp)/layout.tsx`

- [ ] **Step 1: Create `AnnouncementDialog.tsx`**

```tsx
"use client";

import { Dialog, DialogPanel, DialogTitle, Transition, TransitionChild } from "@headlessui/react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { Fragment } from "react";

export type AnnouncementShape = {
  id: string;
  kind: string;
  title: string;
  body: string;
  image_url: string | null;
  cta_label: string | null;
  cta_url: string | null;
};

export function AnnouncementDialog({
  announcement, open, onClose,
}: {
  announcement: AnnouncementShape;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Transition show={open} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <TransitionChild
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-ink-900/60" />
        </TransitionChild>
        <div className="fixed inset-0 flex items-center justify-center p-4">
          <TransitionChild
            as={Fragment}
            enter="ease-out duration-200"
            enterFrom="opacity-0 scale-95"
            enterTo="opacity-100 scale-100"
            leave="ease-in duration-150"
            leaveFrom="opacity-100 scale-100"
            leaveTo="opacity-0 scale-95"
          >
            <DialogPanel className="w-full max-w-md overflow-hidden rounded-2xl bg-white shadow-xl">
              {announcement.image_url && (
                <img src={announcement.image_url} alt="" className="h-40 w-full object-cover" />
              )}
              <div className="relative p-6">
                <button
                  type="button"
                  onClick={onClose}
                  className="absolute right-4 top-4 text-ink-400 hover:text-ink-700"
                  aria-label="Close"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
                <DialogTitle as="h3" className="text-lg font-bold text-ink-900">
                  {announcement.title}
                </DialogTitle>
                <div className="mt-2 whitespace-pre-wrap text-sm text-ink-700">
                  {announcement.body}
                </div>
                {announcement.cta_label && announcement.cta_url && (
                  <a
                    href={announcement.cta_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-5 block w-full rounded-xl bg-primary-600 px-4 py-2.5 text-center text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
                  >
                    {announcement.cta_label}
                  </a>
                )}
              </div>
            </DialogPanel>
          </TransitionChild>
        </div>
      </Dialog>
    </Transition>
  );
}
```

- [ ] **Step 2: Create `AnnouncementProvider.tsx`**

```tsx
"use client";

import { useEffect, useState, type ReactNode } from "react";
import useSWR from "swr";

import { swrFetcher } from "@/app/lib/api";
import { useMe } from "@/app/lib/use-me";

import { AnnouncementDialog, type AnnouncementShape } from "./AnnouncementDialog";

type MeAnnouncements = {
  first_login: AnnouncementShape | null;
  login_banner: AnnouncementShape | null;
};

const FIRST_LOGIN_TTL_HOURS = 48; // Only show first_login if account is < 48h old

export function AnnouncementProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const { data } = useSWR<MeAnnouncements>(me.data ? "/announcements/me" : null, swrFetcher);
  const [showFirstLogin, setShowFirstLogin] = useState(false);
  const [showBanner, setShowBanner] = useState(false);

  // first_login: once per user, only within 48h of signup
  useEffect(() => {
    if (!data?.first_login || !me.data) return;
    const created = (me.data as any).created_at;
    if (created) {
      const ageMs = Date.now() - new Date(created).getTime();
      if (ageMs > FIRST_LOGIN_TTL_HOURS * 3600 * 1000) return;
    }
    const key = `dothesis_first_announcement_${me.data.id}`;
    if (window.localStorage.getItem(key)) return;
    window.localStorage.setItem(key, "1");
    setShowFirstLogin(true);
  }, [data?.first_login, me.data]);

  // login_banner: once per day per user per announcement id
  useEffect(() => {
    if (!data?.login_banner || !me.data) return;
    const key = `dothesis_login_banner_${me.data.id}_${data.login_banner.id}`;
    const stored = window.localStorage.getItem(key);
    const startOfToday = new Date().setHours(0, 0, 0, 0);
    if (stored && parseInt(stored, 10) >= startOfToday) return;
    window.localStorage.setItem(key, String(Date.now()));
    setShowBanner(true);
  }, [data?.login_banner, me.data]);

  return (
    <>
      {children}
      {data?.first_login && (
        <AnnouncementDialog
          announcement={data.first_login}
          open={showFirstLogin}
          onClose={() => setShowFirstLogin(false)}
        />
      )}
      {data?.login_banner && (
        <AnnouncementDialog
          announcement={data.login_banner}
          open={showBanner}
          onClose={() => setShowBanner(false)}
        />
      )}
    </>
  );
}
```

- [ ] **Step 3: Update `(inapp)/layout.tsx`** to wrap children

Replace the existing return statement of `InAppLayout`:

```tsx
import { AnnouncementProvider } from "@/app/components/announcements/AnnouncementProvider";
// ...
export default function InAppLayout({ children }: { children: ReactNode }) {
  return (
    <SidebarLayout sections={SECTIONS}>
      <AnnouncementProvider>{children}</AnnouncementProvider>
    </SidebarLayout>
  );
}
```

- [ ] **Step 4: Extend `Me` type with `created_at`**

Edit `web/app/lib/types.ts` to add `created_at: string | null` to `Me`. Backend already returns `created_at` from `/me`? **Check** — if `_to_out` does NOT include `created_at`, add it in `api/app/routers/auth.py`'s `_to_out` and `UserOut`:

```python
class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    credit: int = 0
    is_super_admin: bool = False
    created_at: str | None = None


def _to_out(u: User) -> UserOut:
    from ..admin_config import is_super_admin as _is_admin
    return UserOut(
        id=str(u.id),
        email=u.email,
        username=u.username,
        credit=u.credit,
        is_super_admin=_is_admin(u),
        created_at=u.created_at.isoformat() if u.created_at else None,
    )
```

(If `created_at` was already there, just add to the TS type.)

- [ ] **Step 5: Type-check**

`npx tsc --noEmit` from `web/`. Expected: clean.

- [ ] **Step 6: Commit**

```
git add web/app/components/announcements/ web/app/(inapp)/layout.tsx web/app/lib/types.ts api/app/routers/auth.py
git commit -m "feat(web): user-facing announcement dialog + provider with localStorage throttling"
```

---

## Task 10: End-to-end verification

- [ ] **Step 1: Run full new test suite**

```
.\.venv\Scripts\python.exe -m pytest tests/test_admin_users.py tests/test_admin_papers.py tests/test_admin_jobs.py tests/test_admin_orders.py tests/test_admin_announcements.py tests/test_announcements_me.py tests/test_pricing.py tests/test_credit_ledger.py tests/test_credit_routes.py tests/test_papers_credit.py tests/test_admin_config.py tests/test_require_admin.py tests/test_auth_me_extended.py tests/test_health.py -v
```
Expected: all pass.

- [ ] **Step 2: Type-check web**

`cd web && npx tsc --noEmit`. Expected: clean.

- [ ] **Step 3: Manual click-through**

Boot API + web. Sign in as `cao.nv17@gmail.com`. Visit each admin page:
- `/admin/users` — see the user list, click yourself, grant +100 credits via drawer, balance updates.
- `/admin/papers` — see any papers from earlier sessions.
- `/admin/jobs` — filter for running, none yet (unless mid-job).
- `/admin/orders` — see any orders.
- `/admin/announcements` — click "+ New", create a `login_banner` with title "Welcome to DoThesis" and a body. Save. Reload `/` (or any inapp page) — banner dialog appears. Close. Reload — no dialog (one-per-day throttle).
- Sign out, sign up as `bob@example.com` (non-admin). `/admin` 403s. Banner still appears (it's user-facing, not admin-gated).

- [ ] **Step 4: Commit any tweaks**

If anything was patched during click-through, commit.

## Done criteria

- API: `/api/v1/admin/{users,papers,jobs,orders,announcements}` all live and gated by `require_admin`. `/api/v1/announcements/me` returns `{ first_login, login_banner }` based on activity windows. All new tests pass.
- Web: All five admin pages render with the shared `AdminTable`. Users page supports search + credit grant via drawer. Announcements page supports CRUD. User-facing announcement dialog appears with correct localStorage throttling.

## Out of scope

- Real Polar account wiring (already supported via env vars; just flip `DOTHESIS_PAYMENTS` to `polar` and set tokens).
- Affiliate program.
- CSV exports.
- Migration of legacy `.jsx` pages to TS+Tailwind internals.
