> **📜 Historical record — superseded.** This document captured a plan / spec / design at a point in time and is kept for history. It does **not** describe the current system. For the live DoThesis method and architecture see `README.md`, `AGENTS.md`, `docs/ARCHITECTURE.md`, and `docs/PIPELINE.md`.

# Foundation: Tailwind/TS, DB, Admin Allowlist, Sidebar Shell — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Set up the foundational pieces (Tailwind + TS in the web app, DB columns and admin allowlist in the API, new sidebar/topbar shell wrapping existing pages) so subsequent plans for credits and admin pages can build on a working chrome.

**Architecture:** Two parallel tracks. Backend: extend the existing FastAPI `User` model with `credit` and `username` columns, add a `SUPER_ADMIN_EMAILS` constant + `require_admin` dependency, and extend `/api/v1/auth/me` to return derived `is_super_admin`. Frontend: add TypeScript, Tailwind, Headless UI, Heroicons, and `clsx` to `web/`; port Survify's `SidebarLayout` component into `web/app/components/layout/`; move existing pages into a new `(inapp)` route group; create an `admin` route group that 403s for non-admins. Existing `.jsx` pages keep working — only the wrapping chrome changes.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2, Alembic, Pydantic 2; Next.js 16, React 19, TypeScript 5, Tailwind CSS 3, Headless UI 2, Heroicons 2, Lucide React, clsx, SWR 2.

---

## File structure

**API (`api/app/`):**
- New: `admin_config.py` — `SUPER_ADMIN_EMAILS` frozenset + `is_super_admin(user)` helper + env-var loader.
- New: `auth_admin.py` — `require_admin` FastAPI dependency (kept separate from `deps.py` to avoid coupling auth/admin).
- Modify: `models.py:24-30` — add `credit` (int) and `username` (str | None) columns to `User`.
- Modify: `routers/auth.py:24-30,82-84` — extend `UserOut` with `username`, `credit`, `is_super_admin`; update `_to_out` and `/me`.
- New migration: `migrations/versions/<rev>_user_credit_username.py`.

**API tests (`api/tests/`):**
- New: `test_admin_config.py` — allowlist hits + misses, env-var extension.
- New: `test_require_admin.py` — 403 for non-admins, passes for admins.
- New: `test_auth_me_extended.py` — `/api/v1/auth/me` returns new fields.

**Web (`web/`):**
- New: `tsconfig.json`, `tailwind.config.ts`, `postcss.config.js`, `next-env.d.ts`.
- Modify: `package.json` — new dependencies.
- Modify: `app/globals.css` — prepend `@tailwind` directives.
- Modify: `app/layout.jsx` → `app/layout.tsx`.
- New: `app/components/layout/SidebarLayout.tsx` — ported Survify shell.
- New: `app/components/layout/sections.ts` — section/nav type definitions.
- New: `app/components/layout/Brand.tsx` — dothesis brand mark + wordmark.
- New: `app/lib/use-me.ts` — SWR hook for current user.
- New: `app/lib/types.ts` — shared `Me` type.
- New route group: `app/(inapp)/layout.tsx` — user-shell layout.
- Move: `app/page.jsx` → `app/(inapp)/page.jsx`.
- Move: `app/wizard/page.jsx` → `app/(inapp)/wizard/page.jsx`.
- Move: `app/paper/[id]/page.jsx` → `app/(inapp)/paper/[id]/page.jsx`.
- Edit moved pages: remove their inline `<Sidebar />` import — the shell now owns it.
- New route group: `app/admin/layout.tsx` — admin-shell layout with allowlist gate.
- New: `app/admin/page.tsx` — redirect to `/admin/users` placeholder (which doesn't exist yet; this plan just stubs it as a "Users — coming soon" panel).

**Out of scope for this plan:** credit packages UI, admin entity pages beyond a stub, announcements, paper-creation credit deduction. Those land in Plans 2 and 3.

---

## Pre-flight

- [ ] **P1: Confirm working tree is clean**

Run: `git status --short`
Expected: only the two spec/plan commits are present; no uncommitted changes from prior work.

- [ ] **P2: Confirm test infra works**

Run: `cd api && pytest -q`
Expected: existing test suite passes (or a known-passing subset). If failures pre-exist, note them so we don't blame this plan.

---

## Task 1: Add Python admin allowlist constant + helper

**Files:**
- Create: `api/app/admin_config.py`
- Test: `api/tests/test_admin_config.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_admin_config.py`:

```python
import os
from unittest.mock import MagicMock

import pytest

from app.admin_config import SUPER_ADMIN_EMAILS, is_super_admin, _load_extra_emails


def _user(email: str):
    u = MagicMock()
    u.email = email
    return u


def test_seeded_admin_is_recognised():
    assert "cao.nv17@gmail.com" in SUPER_ADMIN_EMAILS
    assert is_super_admin(_user("cao.nv17@gmail.com")) is True


def test_non_admin_email_rejected():
    assert is_super_admin(_user("alice@example.com")) is False


def test_admin_check_is_case_insensitive():
    assert is_super_admin(_user("CAO.NV17@GMAIL.COM")) is True


def test_env_var_extends_allowlist(monkeypatch):
    monkeypatch.setenv("DOTHESIS_SUPER_ADMIN_EMAILS", "extra1@x.com, EXTRA2@y.com")
    extras = _load_extra_emails()
    assert extras == frozenset({"extra1@x.com", "extra2@y.com"})


def test_env_var_empty_returns_empty_set(monkeypatch):
    monkeypatch.delenv("DOTHESIS_SUPER_ADMIN_EMAILS", raising=False)
    assert _load_extra_emails() == frozenset()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_admin_config.py -v`
Expected: `ModuleNotFoundError: No module named 'app.admin_config'`

- [ ] **Step 3: Write the implementation**

Create `api/app/admin_config.py`:

```python
"""Super-admin allowlist. Source of truth is this file; env var extends it."""
from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import User


_SEED: frozenset[str] = frozenset({
    "cao.nv17@gmail.com",
})


def _load_extra_emails() -> frozenset[str]:
    raw = os.environ.get("DOTHESIS_SUPER_ADMIN_EMAILS", "").strip()
    if not raw:
        return frozenset()
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


SUPER_ADMIN_EMAILS: frozenset[str] = _SEED | _load_extra_emails()


def is_super_admin(user: "User") -> bool:
    """True iff the user's email (case-insensitive) is in the allowlist."""
    if not user or not getattr(user, "email", None):
        return False
    return user.email.lower() in SUPER_ADMIN_EMAILS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_admin_config.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/admin_config.py api/tests/test_admin_config.py
git commit -m "feat(api): super-admin email allowlist constant"
```

---

## Task 2: Add `require_admin` FastAPI dependency

**Files:**
- Create: `api/app/auth_admin.py`
- Test: `api/tests/test_require_admin.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_require_admin.py`:

```python
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.auth_admin import require_admin


def _user(email: str):
    u = MagicMock()
    u.email = email
    return u


def test_admin_user_passes_through():
    user = _user("cao.nv17@gmail.com")
    assert require_admin(user=user) is user


def test_non_admin_raises_403():
    user = _user("alice@example.com")
    with pytest.raises(HTTPException) as exc:
        require_admin(user=user)
    assert exc.value.status_code == 403
    assert exc.value.detail["error"]["code"] == "forbidden"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_require_admin.py -v`
Expected: `ModuleNotFoundError: No module named 'app.auth_admin'`.

- [ ] **Step 3: Write the implementation**

Create `api/app/auth_admin.py`:

```python
from fastapi import Depends, HTTPException

from .admin_config import is_super_admin
from .deps import current_user
from .models import User


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "forbidden", "message": "admin only"}},
        )
    return user
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_require_admin.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add api/app/auth_admin.py api/tests/test_require_admin.py
git commit -m "feat(api): require_admin dependency using allowlist"
```

---

## Task 3: Add `credit` and `username` columns to `User`

**Files:**
- Modify: `api/app/models.py:24-30`

- [ ] **Step 1: Modify the User model**

Replace the body of the `User` class in `api/app/models.py` with:

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credit: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
```

(Note: `Integer` and `String` are already imported at the top of the file.)

- [ ] **Step 2: Verify model still imports cleanly**

Run: `cd api && python -c "from app.models import User; print(User.__table__.columns.keys())"`
Expected output: `['id', 'email', 'username', 'password_hash', 'credit', 'created_at']`

- [ ] **Step 3: Commit**

```bash
git add api/app/models.py
git commit -m "feat(api): add credit and username columns to User model"
```

---

## Task 4: Alembic migration for User columns

**Files:**
- Create: `api/migrations/versions/<rev>_user_credit_username.py`

- [ ] **Step 1: Generate the migration**

Run: `cd api && alembic revision -m "user_credit_username"`
Expected: prints the path to a newly created file under `migrations/versions/` with revision id `<rev>`. Note the revision id.

- [ ] **Step 2: Write the upgrade and downgrade**

Replace the body of the generated file with:

```python
"""user_credit_username

Revision ID: <rev>
Revises: a1c2d3e4f5
Create Date: 2026-05-23 ...

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<rev>"            # leave as the auto-generated id
down_revision: Union[str, None] = "a1c2d3e4f5"   # latest existing rev
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("username", sa.String(64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("credit", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("users", "credit")
    op.drop_column("users", "username")
```

(Confirm `down_revision` matches the head shown by `alembic heads` — `a1c2d3e4f5` is the existing latest from `jobs_checkpoint`.)

- [ ] **Step 3: Verify the migration**

Run: `cd api && alembic heads` — confirms the new revision is the head.
Run: `cd api && alembic upgrade head` against your dev DB.
Expected: no errors. `users` table has new `credit` and `username` columns.

- [ ] **Step 4: Commit**

```bash
git add api/migrations/versions/<filename>.py
git commit -m "feat(api): migration for user credit and username"
```

---

## Task 5: Extend `/api/v1/auth/me` with username, credit, is_super_admin

**Files:**
- Modify: `api/app/routers/auth.py:24-30, 82-84`
- Test: `api/tests/test_auth_me_extended.py`

- [ ] **Step 1: Write the failing test**

Create `api/tests/test_auth_me_extended.py`. (This test follows the pattern used by existing auth tests — check `api/tests/` for the existing fixtures and DB-session pattern, then adapt. If no auth test exists yet, write the minimum self-contained version below.)

```python
from fastapi.testclient import TestClient

from app.main import app


def test_me_includes_credit_username_and_is_super_admin_for_admin():
    client = TestClient(app)
    # Sign up an admin and check /me
    r = client.post("/api/v1/auth/signup", json={"email": "cao.nv17@gmail.com", "password": "supersecret"})
    assert r.status_code == 201
    me = client.get("/api/v1/auth/me").json()
    assert me["email"] == "cao.nv17@gmail.com"
    assert me["credit"] == 0
    assert me["username"] is None
    assert me["is_super_admin"] is True


def test_me_is_super_admin_false_for_regular_user():
    client = TestClient(app)
    r = client.post("/api/v1/auth/signup", json={"email": "alice@example.com", "password": "supersecret"})
    assert r.status_code == 201
    me = client.get("/api/v1/auth/me").json()
    assert me["is_super_admin"] is False
    assert me["credit"] == 0
```

(If a `conftest.py` with DB-isolation fixtures exists in `api/tests/`, this test must use it — otherwise tests will pollute the dev DB. Inspect the file first: `ls api/tests/ && cat api/tests/conftest.py 2>/dev/null`. If absent, this test should be marked skip and the test runner setup added in a separate task.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd api && pytest tests/test_auth_me_extended.py -v`
Expected: assertion errors — `credit`, `username`, and `is_super_admin` not in response.

- [ ] **Step 3: Update the `UserOut` schema and `/me` endpoint**

Edit `api/app/routers/auth.py`. Replace the `UserOut` class and `_to_out` helper with:

```python
class UserOut(BaseModel):
    id: str
    email: str
    username: str | None = None
    credit: int = 0
    is_super_admin: bool = False


def _to_out(u: User) -> UserOut:
    from ..admin_config import is_super_admin as _is_admin
    return UserOut(
        id=str(u.id),
        email=u.email,
        username=u.username,
        credit=u.credit,
        is_super_admin=_is_admin(u),
    )
```

(The `/me` endpoint at line 82-84 already uses `_to_out`, so it picks up the new fields automatically. `signup` and `login` also return `_to_out`, which is fine — they include the new fields too.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd api && pytest tests/test_auth_me_extended.py -v`
Expected: 2 passed.

- [ ] **Step 5: Run full backend test suite**

Run: `cd api && pytest -q`
Expected: no new failures vs. P2 baseline.

- [ ] **Step 6: Commit**

```bash
git add api/app/routers/auth.py api/tests/test_auth_me_extended.py
git commit -m "feat(api): /auth/me returns username, credit, is_super_admin"
```

---

## Task 6: Install web dev dependencies

**Files:**
- Modify: `web/package.json`

- [ ] **Step 1: Install runtime deps**

Run from `web/`:
```bash
npm install @headlessui/react@^2 @heroicons/react@^2 lucide-react@^0.453 clsx@^2
```

- [ ] **Step 2: Install dev deps**

Run from `web/`:
```bash
npm install -D typescript@^5 @types/react@^19 @types/react-dom@^19 @types/node@^22 \
  tailwindcss@^3 postcss@^8 autoprefixer@^10
```

- [ ] **Step 3: Verify `package.json` was updated**

Run: `cat web/package.json`
Expected: dependencies block includes the six runtime packages; devDependencies block includes the six dev packages.

- [ ] **Step 4: Commit**

```bash
git add web/package.json web/package-lock.json
git commit -m "build(web): add tailwind, typescript, headlessui, heroicons, lucide, clsx"
```

---

## Task 7: TypeScript scaffolding

**Files:**
- Create: `web/tsconfig.json`
- Create: `web/next-env.d.ts`

- [ ] **Step 1: Create `web/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 2: Create `web/next-env.d.ts`**

```ts
/// <reference types="next" />
/// <reference types="next/image-types/global" />

// NOTE: This file should not be edited. See https://nextjs.org/docs/basic-features/typescript for more information.
```

- [ ] **Step 3: Verify type-check passes on existing JSX**

Run from `web/`: `npx tsc --noEmit`
Expected: succeeds (no errors) because `allowJs: true` and `strict: true` together still let JSX through without annotations.

- [ ] **Step 4: Commit**

```bash
git add web/tsconfig.json web/next-env.d.ts
git commit -m "build(web): typescript scaffolding"
```

---

## Task 8: Tailwind scaffolding

**Files:**
- Create: `web/tailwind.config.ts`
- Create: `web/postcss.config.js`
- Modify: `web/app/globals.css:1-3`

- [ ] **Step 1: Create `web/tailwind.config.ts`**

```ts
import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          50:  "#f1f3ff",
          100: "#e7eaff",
          500: "#3a4dff",
          600: "#1c2eff",
          700: "#0a1ee0",
        },
        ink: {
          50:  "#f5f6fb",
          100: "#eef0f6",
          200: "#e2e4ee",
          300: "#c2c5d6",
          400: "#8a8fa8",
          500: "#5b5f7d",
          700: "#292c44",
          800: "#161827",
          900: "#0b0d1a",
        },
      },
      fontFamily: {
        sans: ["Manrope", "ui-sans-serif", "system-ui"],
        serif: ["Source Serif 4", "Georgia", "serif"],
        mono: ["JetBrains Mono", "ui-monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 2: Create `web/postcss.config.js`**

```js
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3: Prepend Tailwind directives to `web/app/globals.css`**

Insert at the very top of `app/globals.css` (before the existing `@import url(...)` for Google Fonts is fine — Tailwind layers don't interfere):

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- [ ] **Step 4: Verify the dev server boots and a Tailwind class works**

Run: `cd web && npm run dev`
Then in a separate shell: `curl -s http://localhost:3000/login | head -50`
Expected: HTML returns 200; no Tailwind-specific build errors in the dev-server stdout.

Add a temporary smoke check: add `<div className="bg-primary-600 text-white p-4">tw works</div>` to the bottom of `app/login/page.jsx`, reload http://localhost:3000/login in a browser, confirm it renders with the electric-blue background, then **revert that change before committing**.

- [ ] **Step 5: Commit**

```bash
git add web/tailwind.config.ts web/postcss.config.js web/app/globals.css
git commit -m "build(web): tailwind scaffolding with primary/ink palette"
```

---

## Task 9: Convert root layout to TSX

**Files:**
- Delete: `web/app/layout.jsx`
- Create: `web/app/layout.tsx`

- [ ] **Step 1: Create `web/app/layout.tsx`**

```tsx
import "./globals.css";
import type { ReactNode } from "react";
import { AuthProvider } from "./lib/auth-context";

export const metadata = {
  title: "DoThesis — AI Thesis Agent",
  description:
    "Draft master's theses and PhD dissertations with 19 specialized AI agents and 100% verified citations.",
  icons: { icon: "/favicon.png" },
};

export const viewport = {
  width: 1440,
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-white text-ink-900 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Delete the JSX version**

```bash
git rm web/app/layout.jsx
```

- [ ] **Step 3: Boot dev server to verify**

Run: `cd web && npm run dev`
Then in a browser: open http://localhost:3000/login — should render normally.

- [ ] **Step 4: Commit**

```bash
git add web/app/layout.tsx
git commit -m "build(web): convert root layout to tsx"
```

---

## Task 10: Define shared types and `useMe` hook

**Files:**
- Create: `web/app/lib/types.ts`
- Create: `web/app/lib/use-me.ts`

- [ ] **Step 1: Create the `Me` type**

`web/app/lib/types.ts`:

```ts
export type Me = {
  id: string;
  email: string;
  username: string | null;
  credit: number;
  is_super_admin: boolean;
};
```

- [ ] **Step 2: Create the SWR hook**

`web/app/lib/use-me.ts`:

```ts
"use client";

import useSWR from "swr";
import { swrFetcher } from "./api";
import type { Me } from "./types";

export function useMe() {
  return useSWR<Me>("/auth/me", swrFetcher);
}
```

(Note: `swrFetcher` already exists in `web/app/lib/api.js`. The path `/auth/me` is what its base-URL config produces — confirm by checking `api.js`. If the helper prefixes `/api/v1`, this URL is correct; otherwise, adjust.)

- [ ] **Step 3: Inspect `api.js` to confirm base URL**

Run: `cat web/app/lib/api.js`
If the fetcher prepends `/api/v1`, `"/auth/me"` is right. Otherwise change to `"/api/v1/auth/me"`.

- [ ] **Step 4: Commit**

```bash
git add web/app/lib/types.ts web/app/lib/use-me.ts
git commit -m "feat(web): Me type and useMe SWR hook"
```

---

## Task 11: Create Brand component

**Files:**
- Create: `web/app/components/layout/Brand.tsx`

- [ ] **Step 1: Create the component**

`web/app/components/layout/Brand.tsx`:

```tsx
import Link from "next/link";

type BrandProps = {
  collapsed?: boolean;
};

export function Brand({ collapsed = false }: BrandProps) {
  return (
    <Link href="/" className="flex items-center gap-3 no-underline">
      <div
        className="flex items-center justify-center rounded-xl bg-primary-600 text-white shadow-sm"
        style={{ width: 38, height: 38 }}
      >
        <svg width={22} height={22} viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M19 4c-7 0-13 6-13 13v3h3c7 0 13-6 13-13V4Z" fill="white" fillOpacity={0.95} />
          <path d="M16 8 5 19" stroke="#1c2eff" strokeWidth={2} strokeLinecap="round" />
          <path d="M14 14H8" stroke="#1c2eff" strokeWidth={2} strokeLinecap="round" />
        </svg>
      </div>
      {!collapsed && (
        <div className="flex flex-col leading-tight">
          <span className="text-base font-extrabold tracking-tight text-ink-900">
            Do<span className="text-primary-600">Thesis</span>
          </span>
          <span className="text-[11px] font-medium text-ink-500">Draft with conviction</span>
        </div>
      )}
    </Link>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/layout/Brand.tsx
git commit -m "feat(web): Brand component (sidebar logo)"
```

---

## Task 12: Define sidebar section type

**Files:**
- Create: `web/app/components/layout/sections.ts`

- [ ] **Step 1: Define the types**

```ts
import type { ComponentType, SVGProps } from "react";

export type SidebarItem = {
  name: string;
  href: string;
  icon?: ComponentType<SVGProps<SVGSVGElement>>;
  default?: boolean;
  count?: number;
  subitems?: SidebarItem[];
};

export type SidebarSection = {
  id: string;
  name: string;
  options: SidebarItem[];
};
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/layout/sections.ts
git commit -m "feat(web): sidebar section/item types"
```

---

## Task 13: Port `SidebarLayout` component

**Files:**
- Create: `web/app/components/layout/SidebarLayout.tsx`

This is the largest component in the plan. We copy Survify's `sidebar-layout.tsx` with three changes:
1. Use the new `Brand` component instead of `<Image src="/static/img/logo-...">`.
2. Replace `useMe` from `@/hooks/user` with our `useMe` from `@/app/lib/use-me`.
3. Replace `MeFunctions.logout()` with a simple call to `fetch('/api/v1/auth/logout', { method: 'POST' })` + redirect.

- [ ] **Step 1: Write the component**

Create `web/app/components/layout/SidebarLayout.tsx`:

```tsx
"use client";

import {
  Dialog,
  DialogPanel,
  Menu,
  MenuButton,
  MenuItem,
  MenuItems,
  Transition,
  TransitionChild,
} from "@headlessui/react";
import {
  Bars3Icon,
  BellIcon,
  ChevronDoubleLeftIcon,
  ChevronDoubleRightIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  XMarkIcon,
} from "@heroicons/react/24/outline";
import clsx from "clsx";
import Link from "next/link";
import { Fragment, type PropsWithChildren, useEffect, useState } from "react";

import { useMe } from "@/app/lib/use-me";

import { Brand } from "./Brand";
import type { SidebarSection } from "./sections";

const COLLAPSED_KEY = "dothesis_sidebar_collapsed";

async function logout() {
  await fetch("/api/v1/auth/logout", { method: "POST", credentials: "include" });
  window.location.href = "/login";
}

export function SidebarLayout({ sections, children }: PropsWithChildren<{ sections: SidebarSection[] }>) {
  const [selectedHref, setSelectedHref] = useState<string>("");
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const me = useMe();

  useEffect(() => {
    setSelectedHref(window.location.pathname + window.location.search);
    const stored = window.localStorage.getItem(COLLAPSED_KEY);
    if (stored === "true") setSidebarCollapsed(true);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(COLLAPSED_KEY, String(sidebarCollapsed));
  }, [sidebarCollapsed]);

  const toggleExpanded = (itemName: string) => {
    setExpandedItems((prev) => {
      const next = new Set(prev);
      if (next.has(itemName)) next.delete(itemName);
      else next.add(itemName);
      return next;
    });
  };

  function renderSections(collapsed = false) {
    return (
      <ul role="list" className="flex flex-1 flex-col gap-y-7 list-none p-0 m-0">
        {sections.map((section) => (
          <li key={section.id} className="space-y-2">
            {!collapsed && section.name && (
              <div className="text-xs font-semibold text-ink-500 uppercase tracking-wide">
                {section.name}
              </div>
            )}
            <ul role="list" className={clsx("mt-2 space-y-1 list-none p-0", collapsed ? "mx-0" : "-mx-2")}>
              {section.options.map((option) => {
                const hasSubitems = (option.subitems?.length ?? 0) > 0;
                const isExpanded = expandedItems.has(option.name);
                const active = selectedHref === option.href || option.default;
                const hasActiveSubitem =
                  hasSubitems && option.subitems!.some((s) => selectedHref === s.href);

                return (
                  <li key={option.name} className="relative group/item">
                    {hasSubitems ? (
                      <div>
                        <button
                          type="button"
                          onClick={() => {
                            if (collapsed) {
                              setSidebarCollapsed(false);
                              setExpandedItems(new Set([option.name]));
                            } else {
                              toggleExpanded(option.name);
                            }
                          }}
                          className={clsx(
                            active || hasActiveSubitem
                              ? "bg-primary-50 text-primary-600 font-medium shadow-sm"
                              : "text-ink-700 hover:bg-ink-50 hover:text-ink-900",
                            "group flex w-full items-center gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                            collapsed && "justify-center px-2",
                          )}
                        >
                          {option.icon && (
                            <option.icon
                              className={clsx(
                                active || hasActiveSubitem ? "text-primary-600" : "text-ink-500",
                                "h-5 w-5 shrink-0",
                              )}
                              aria-hidden="true"
                            />
                          )}
                          {!collapsed && (
                            <>
                              <span className="flex-1 text-left">{option.name}</span>
                              <ChevronRightIcon
                                className={clsx(
                                  "h-4 w-4 transition-transform",
                                  isExpanded ? "rotate-90" : "",
                                  active || hasActiveSubitem ? "text-primary-600" : "text-ink-500",
                                )}
                                aria-hidden="true"
                              />
                            </>
                          )}
                        </button>
                        {collapsed && (
                          <div className="absolute left-full top-1/2 -translate-y-1/2 ml-2 px-2 py-1 bg-ink-900 text-white text-xs rounded opacity-0 invisible group-hover/item:opacity-100 group-hover/item:visible transition-all whitespace-nowrap z-50">
                            {option.name}
                          </div>
                        )}
                        {isExpanded && !collapsed && (
                          <ul className="mt-1 space-y-1 list-none">
                            {option.subitems!.map((subitem) => {
                              const subActive = selectedHref === subitem.href;
                              return (
                                <li key={subitem.name}>
                                  <Link
                                    href={subitem.href}
                                    onClick={() => setSelectedHref(subitem.href)}
                                    className={clsx(
                                      subActive
                                        ? "bg-primary-50 text-primary-600"
                                        : "text-ink-700 hover:bg-ink-50",
                                      "group flex gap-x-2 rounded-md py-2 pr-2 text-sm items-center",
                                      subitem.icon ? "pl-8" : "pl-10",
                                    )}
                                  >
                                    {subitem.icon && (
                                      <subitem.icon
                                        className={clsx(
                                          subActive ? "text-primary-600" : "text-ink-500",
                                          "h-4 w-4 shrink-0",
                                        )}
                                        aria-hidden="true"
                                      />
                                    )}
                                    {subitem.name}
                                  </Link>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    ) : (
                      <Link
                        href={option.href}
                        onClick={() => setSelectedHref(option.href)}
                        className={clsx(
                          active
                            ? "bg-primary-50 text-primary-600 font-medium shadow-sm"
                            : "text-ink-700 hover:bg-ink-50 hover:text-ink-900",
                          "group flex gap-x-3 rounded-xl px-3 py-2.5 text-sm transition-all",
                          collapsed && "justify-center px-2",
                        )}
                      >
                        {option.icon && (
                          <option.icon
                            className={clsx(
                              active ? "text-primary-600" : "text-ink-500",
                              "h-5 w-5 shrink-0",
                            )}
                            aria-hidden="true"
                          />
                        )}
                        {!collapsed && (
                          <>
                            {option.name}
                            {option.count ? (
                              <span className="ml-auto w-9 min-w-max whitespace-nowrap rounded-full bg-white px-2.5 py-0.5 text-center text-xs font-medium leading-5 text-ink-500 ring-1 ring-inset ring-ink-200">
                                {option.count}
                              </span>
                            ) : null}
                          </>
                        )}
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
      </ul>
    );
  }

  const userInitial = (me.data?.username || me.data?.email || "?").charAt(0).toUpperCase();

  return (
    <div>
      {/* Mobile sidebar */}
      <Transition show={sidebarOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50 lg:hidden" onClose={setSidebarOpen}>
          <TransitionChild
            as={Fragment}
            enter="transition-opacity ease-linear duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="transition-opacity ease-linear duration-300"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-ink-900/80" />
          </TransitionChild>
          <div className="fixed inset-0 flex">
            <TransitionChild
              as={Fragment}
              enter="transition ease-in-out duration-300 transform"
              enterFrom="-translate-x-full"
              enterTo="translate-x-0"
              leave="transition ease-in-out duration-300 transform"
              leaveFrom="translate-x-0"
              leaveTo="-translate-x-full"
            >
              <DialogPanel className="relative mr-16 flex w-full max-w-xs flex-1">
                <TransitionChild
                  as={Fragment}
                  enter="ease-in-out duration-300"
                  enterFrom="opacity-0"
                  enterTo="opacity-100"
                  leave="ease-in-out duration-300"
                  leaveFrom="opacity-100"
                  leaveTo="opacity-0"
                >
                  <div className="absolute left-full top-0 flex w-16 justify-center pt-5">
                    <button type="button" className="-m-2.5 p-2.5" onClick={() => setSidebarOpen(false)}>
                      <span className="sr-only">Close sidebar</span>
                      <XMarkIcon className="h-6 w-6 text-white" aria-hidden="true" />
                    </button>
                  </div>
                </TransitionChild>
                <div className="flex grow flex-col gap-y-5 overflow-y-auto bg-white px-6 py-4">
                  <Brand />
                  <nav className="flex flex-1 flex-col">{renderSections(false)}</nav>
                </div>
              </DialogPanel>
            </TransitionChild>
          </div>
        </Dialog>
      </Transition>

      {/* Desktop sidebar */}
      <div
        className={clsx(
          "hidden lg:fixed lg:inset-y-0 lg:z-50 lg:flex lg:flex-col transition-all duration-300",
          sidebarCollapsed ? "lg:w-20" : "lg:w-72",
        )}
      >
        <div
          className={clsx(
            "flex grow flex-col gap-y-5 overflow-y-auto border-r border-ink-100 bg-white pb-4 transition-all",
            sidebarCollapsed ? "px-3" : "px-6",
          )}
        >
          <div
            className={clsx(
              "flex h-16 shrink-0 items-center border-b border-ink-100 mb-2",
              sidebarCollapsed ? "justify-center" : "gap-3",
            )}
          >
            <Brand collapsed={sidebarCollapsed} />
          </div>

          <nav className="flex flex-1 flex-col">
            {renderSections(sidebarCollapsed)}

            <div className="mt-auto pt-4">
              <button
                type="button"
                onClick={() => setSidebarCollapsed((prev) => !prev)}
                className={clsx(
                  "flex items-center gap-2 w-full rounded-xl py-2.5 text-sm text-ink-500 hover:bg-ink-50 hover:text-ink-900 transition-all",
                  sidebarCollapsed ? "justify-center px-2" : "px-3",
                )}
              >
                {sidebarCollapsed ? (
                  <ChevronDoubleRightIcon className="h-5 w-5" />
                ) : (
                  <>
                    <ChevronDoubleLeftIcon className="h-5 w-5" />
                    <span>Collapse</span>
                  </>
                )}
              </button>
            </div>
          </nav>
        </div>
      </div>

      <div className={clsx("transition-all", sidebarCollapsed ? "lg:pl-20" : "lg:pl-72")}>
        {/* Topbar */}
        <div className="sticky top-0 z-40 border-b border-ink-100 bg-white shadow-sm">
          <div className="flex h-16 items-center gap-x-4 px-4 sm:gap-x-6 sm:px-6 lg:px-8">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              className="-m-2.5 p-2.5 text-ink-500 hover:text-ink-900 lg:hidden"
            >
              <span className="sr-only">Open sidebar</span>
              <Bars3Icon className="h-6 w-6" aria-hidden="true" />
            </button>

            <div className="h-6 w-px bg-ink-200 lg:hidden" aria-hidden="true" />

            <div className="flex flex-1 gap-x-4 self-stretch lg:gap-x-6">
              <div className="flex flex-1" />
              <div className="flex items-center gap-x-4 lg:gap-x-6">
                <button
                  type="button"
                  className="-m-2.5 p-2.5 text-ink-500 hover:text-ink-900"
                  aria-label="View notifications"
                >
                  <BellIcon className="h-6 w-6" aria-hidden="true" />
                </button>

                <div className="hidden lg:block lg:h-6 lg:w-px lg:bg-ink-200" aria-hidden="true" />

                <Menu as="div" className="relative">
                  <MenuButton className="relative flex items-center gap-3">
                    <span className="sr-only">Open user menu</span>
                    <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary-50 text-primary-600 font-semibold border border-ink-100">
                      {userInitial}
                    </div>
                    <div className="hidden lg:flex flex-col items-start leading-tight">
                      <span className="text-sm font-semibold text-ink-900">
                        {me.data?.username || me.data?.email?.split("@")[0] || "—"}
                      </span>
                      <span className="text-xs text-ink-500">{me.data?.email}</span>
                    </div>
                    <ChevronDownIcon className="hidden lg:block h-4 w-4 text-ink-400" aria-hidden="true" />
                  </MenuButton>
                  <MenuItems className="absolute right-0 z-10 mt-2.5 w-40 origin-top-right rounded-md bg-white py-2 shadow-lg outline outline-1 outline-ink-200">
                    <MenuItem>
                      <button
                        onClick={logout}
                        className="block w-full px-3 py-1 text-left text-sm text-ink-900 data-[focus]:bg-ink-50"
                      >
                        Sign out
                      </button>
                    </MenuItem>
                  </MenuItems>
                </Menu>
              </div>
            </div>
          </div>
        </div>

        <main className="bg-gradient-to-b from-primary-50/60 to-white min-h-[calc(100vh-4rem)] py-10">
          <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/app/components/layout/SidebarLayout.tsx
git commit -m "feat(web): port Survify SidebarLayout component"
```

---

## Task 14: Create `(inapp)` route group with layout

**Files:**
- Create: `web/app/(inapp)/layout.tsx`

- [ ] **Step 1: Write the layout**

```tsx
"use client";

import {
  CurrencyDollarIcon,
  DocumentTextIcon,
  HomeIcon,
  PlusIcon,
} from "@heroicons/react/24/outline";
import type { ReactNode } from "react";

import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import type { SidebarSection } from "@/app/components/layout/sections";

const SECTIONS: SidebarSection[] = [
  {
    id: "workspace",
    name: "Workspace",
    options: [
      { name: "Dashboard", href: "/", icon: HomeIcon, default: true },
      { name: "New Thesis", href: "/wizard", icon: PlusIcon },
      { name: "Drafts", href: "/papers", icon: DocumentTextIcon },
    ],
  },
  {
    id: "account",
    name: "Account",
    options: [{ name: "Credit", href: "/credit", icon: CurrencyDollarIcon }],
  },
];

export default function InAppLayout({ children }: { children: ReactNode }) {
  return <SidebarLayout sections={SECTIONS}>{children}</SidebarLayout>;
}
```

- [ ] **Step 2: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/app/(inapp)/layout.tsx
git commit -m "feat(web): inapp route-group layout with sidebar shell"
```

---

## Task 15: Move existing pages into `(inapp)` and strip their inline sidebars

**Files:**
- Move: `web/app/page.jsx` → `web/app/(inapp)/page.jsx`
- Move: `web/app/wizard/page.jsx` → `web/app/(inapp)/wizard/page.jsx`
- Move: `web/app/paper/[id]/page.jsx` → `web/app/(inapp)/paper/[id]/page.jsx`
- Edit each moved page to remove its own `<Sidebar />` and the `className="app"` wrapper.

- [ ] **Step 1: Move dashboard page**

```bash
git mv web/app/page.jsx web/app/(inapp)/page.jsx
```

Edit `web/app/(inapp)/page.jsx`. Replace the file body with:

```jsx
"use client";

import useSWR from "swr";
import { Dashboard } from "../components/dashboard";
import { swrFetcher } from "../lib/api";

export default function Page() {
  const { data: papers, error, isLoading, mutate } = useSWR("/papers", swrFetcher);
  return <Dashboard papers={papers || []} loading={isLoading} error={error} refresh={mutate} />;
}
```

(Note: component imports now use `../components/...` because the route group adds a directory level; `app/components/` is the same directory but accessed differently. Verify with `cat` after editing.)

- [ ] **Step 2: Move wizard page**

```bash
git mv web/app/wizard web/app/(inapp)/wizard
```

Edit `web/app/(inapp)/wizard/page.jsx`. Replace with:

```jsx
"use client";

import { Wizard } from "../../components/wizard";

export default function WizardPage() {
  return <Wizard />;
}
```

- [ ] **Step 3: Move paper detail page**

```bash
git mv web/app/paper web/app/(inapp)/paper
```

Edit `web/app/(inapp)/paper/[id]/page.jsx`:
- Remove the `Sidebar` import line.
- Inside `PaperPageInner` (and any other render block), remove `<Sidebar />`.
- Remove the wrapping `<div className="app">…</div>` if present, returning only the page content.

(Find the exact lines to edit by `grep -n "Sidebar" web/app/(inapp)/paper/[id]/page.jsx` and remove each.)

- [ ] **Step 4: Boot dev server and smoke-test all three routes**

Run: `cd web && npm run dev`

In a browser:
- `/` — dashboard renders inside the new shell; no double sidebar.
- `/wizard` — wizard renders inside the new shell.
- `/paper/<some-id>` — paper page renders inside the new shell (use any UUID; SWR may 404 but the layout should appear).

Watch the dev-server stdout for errors.

- [ ] **Step 5: Commit**

```bash
git add web/app/\(inapp\)/
git commit -m "feat(web): move dashboard/wizard/paper into (inapp) route group"
```

---

## Task 16: Create `admin` route group with allowlist gate

**Files:**
- Create: `web/app/admin/layout.tsx`
- Create: `web/app/admin/page.tsx`
- Create: `web/app/admin/users/page.tsx` (stub)

- [ ] **Step 1: Write the admin layout**

`web/app/admin/layout.tsx`:

```tsx
"use client";

import {
  CpuChipIcon,
  CreditCardIcon,
  DocumentTextIcon,
  SpeakerWaveIcon,
  UserIcon,
} from "@heroicons/react/24/outline";
import Link from "next/link";
import type { ReactNode } from "react";

import { SidebarLayout } from "@/app/components/layout/SidebarLayout";
import type { SidebarSection } from "@/app/components/layout/sections";
import { useMe } from "@/app/lib/use-me";

const SECTIONS: SidebarSection[] = [
  {
    id: "admin",
    name: "Admin",
    options: [
      { name: "Users", href: "/admin/users", icon: UserIcon },
      { name: "Papers", href: "/admin/papers", icon: DocumentTextIcon },
      { name: "Jobs", href: "/admin/jobs", icon: CpuChipIcon },
      { name: "Announcements", href: "/admin/announcements", icon: SpeakerWaveIcon },
      { name: "Orders", href: "/admin/orders", icon: CreditCardIcon },
    ],
  },
];

export default function AdminLayout({ children }: { children: ReactNode }) {
  const me = useMe();

  if (me.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-500">
        Loading…
      </div>
    );
  }

  if (!me.data?.is_super_admin) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white">
        <h1 className="text-2xl font-bold text-ink-900">Admin access required</h1>
        <p className="text-sm text-ink-500">Your account is not on the admin allowlist.</p>
        <Link
          href="/"
          className="rounded-xl bg-primary-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-primary-700"
        >
          Back to app
        </Link>
      </div>
    );
  }

  return <SidebarLayout sections={SECTIONS}>{children}</SidebarLayout>;
}
```

- [ ] **Step 2: Write the admin index redirect**

`web/app/admin/page.tsx`:

```tsx
import { redirect } from "next/navigation";

export default function AdminIndex() {
  redirect("/admin/users");
}
```

- [ ] **Step 3: Write the users stub**

`web/app/admin/users/page.tsx`:

```tsx
export default function UsersPage() {
  return (
    <div className="rounded-2xl border border-ink-100 bg-white p-8 shadow-sm">
      <h1 className="text-xl font-bold text-ink-900">Users</h1>
      <p className="mt-2 text-sm text-ink-500">
        Admin user list will land in Plan 3. This stub confirms the admin shell renders for allowlisted accounts.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Type-check**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Smoke-test**

Run: `cd web && npm run dev`

Open `/admin` in a browser:
- Logged out → redirected to `/login` by existing proxy.
- Logged in as a non-allowlisted user → 403 page with "Back to app".
- Logged in as `cao.nv17@gmail.com` (or any allowlisted email) → admin sidebar with Users stub visible.

- [ ] **Step 6: Commit**

```bash
git add web/app/admin/
git commit -m "feat(web): admin route group with allowlist gate"
```

---

## Task 17: Update proxy to allow `/admin` through auth (no proxy change needed — verify)

**Files:**
- Verify: `web/proxy.js`

- [ ] **Step 1: Read the proxy**

Run: `cat web/proxy.js`
Confirm the matcher does NOT explicitly exclude `/admin`; it just enforces `dothesis_session` cookie. The admin layout's React-side gate handles role check.

- [ ] **Step 2: No code change required**

(This task exists as a checkpoint so the engineer doesn't accidentally introduce a parallel admin gate in proxy.js.)

---

## Task 18: End-to-end verification

- [ ] **Step 1: Restart backend**

Run: `cd api && uvicorn app.main:app --reload`

- [ ] **Step 2: Restart frontend**

Run: `cd web && npm run dev`

- [ ] **Step 3: Manual click-through (browser)**

1. Open http://localhost:3000/login. Sign up with `cao.nv17@gmail.com` / `supersecret`.
2. After redirect, you should land on `/` inside the new sidebar shell. Sidebar shows: Dashboard, New Thesis, Drafts; Credit. Topbar shows the bell + user menu with your email.
3. Click "New Thesis" → `/wizard` loads inside the shell.
4. Visit `/admin` → redirected to `/admin/users`. Admin sidebar shows; Users stub renders.
5. Sign out (user menu). Sign up a second account (`alice@example.com`). Visit `/admin` → 403 page with "Back to app" button.
6. Click "Back to app" → back at `/` with user sidebar (no admin section visible).

- [ ] **Step 4: Run full backend test suite**

Run: `cd api && pytest -q`
Expected: all tests pass; no new failures.

- [ ] **Step 5: Type-check the frontend**

Run: `cd web && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 6: Commit (only if anything was tweaked)**

If steps above surfaced bugs and you patched them, commit a final clean-up. Otherwise skip.

---

## Done criteria

- API: `cao.nv17@gmail.com` (and any email in `DOTHESIS_SUPER_ADMIN_EMAILS`) is recognised as super-admin by `/api/v1/auth/me`. New `User` columns `credit` and `username` exist (nullable username, credit default 0). `require_admin` dep raises 403 for non-admins and returns the user for admins. Test suite passes.
- Web: Tailwind classes resolve. `tsc --noEmit` clean. Existing pages (dashboard, wizard, paper detail) render inside the new sidebar shell. `/admin` routes are 403-gated by allowlist email. Sidebar collapse persists in localStorage.
- Visual smoke-tested in a real browser by an admin and a non-admin user.

## Out of scope (deferred to Plans 2 & 3)

- Credit packages page, Polar checkout, per-paper credit deduction, paper-creation tier resolution.
- Admin entity pages beyond the Users stub (Papers, Jobs, Announcements, Orders).
- Announcement dialog and CRUD.
- Migration of `dashboard.jsx`, `wizard.jsx`, etc. to TS+Tailwind internals.
