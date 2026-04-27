# Admin Portal — Slice 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the foundation that every subsequent admin slice will build on: install frontend deps, port the ACL/super-admin pattern, add admin auth middlewares, mount `/api/admin`, and create a gated `/admin` route group with a working layout. After this slice, an admin can navigate to `/admin` and see a placeholder dashboard; a non-admin is redirected.

**Architecture:** Backend adds an `ACL` helper and two Express middlewares (`requireAdmin`, `requireSuperAdmin`), mounts a new admin sub-router under `/api/admin`. Frontend adds a peer route group `app/admin/` with its own layout that fetches `/api/me`, redirects non-admins, and renders a sidebar shell. Server-side gating is the source of truth; client-side is UX only.

**Tech Stack:**
- Backend: Express, typegoose/mongoose, passport-jwt (existing). No new backend deps.
- Frontend (new deps): `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `@heroicons/react`, `dayjs`, `class-variance-authority`, `lodash`, `@dnd-kit/core`, `@dnd-kit/sortable`.

**Conventions in this codebase you must follow:**
- All API routes use POST (not GET), with `access_token` in the request body. Reads are POSTs too.
- Every route inside `/api` runs `passport.authenticate('jwt', { session: false })`.
- Response envelope is `{ code, data?, message? }` using the `Code` enum from `backend/src/Constants.ts`.
- Frontend SWR fetches use `Fetch.getFetcher` which POSTs under the hood.
- No automated test framework on backend — verify with explicit `curl` commands.

---

## File Structure

**Backend — files created or modified:**

| Path | Responsibility |
|---|---|
| `backend/src/constants/admin.ts` (new) | `SUPER_ADMIN_EMAILS` constant + env override. |
| `backend/src/packages/acl/acl.ts` (new) | `ACL` class with `isAdmin` / `isSuperAdmin` static helpers. |
| `backend/src/models/User.ts` (modify) | Add `disabled?: boolean`. Extend `secureRelease()` with `is_admin`, `is_super_admin`. |
| `backend/src/api/middlewares/requireAdmin.ts` (new) | Express middleware: 403 if not admin. |
| `backend/src/api/middlewares/requireSuperAdmin.ts` (new) | Express middleware: 403 if not super admin. |
| `backend/src/api/routes/admin/index.ts` (new) | Admin sub-router. Mounts section sub-routers (none yet) plus a `/admin/healthcheck` route. |
| `backend/src/api/index.ts` (modify) | Register the admin sub-router. |

**Frontend — files created or modified:**

| Path | Responsibility |
|---|---|
| `frontend/package.json` (modify) | Add new deps. |
| `frontend/lib/admin/api.ts` (new) | Thin helper for POST calls under `/api/admin/*`, returning `{ code, data }`. |
| `frontend/app/admin/_components/AdminSidebar.tsx` (new) | Static sidebar nav (links disabled until later slices). |
| `frontend/app/admin/_components/AdminTopbar.tsx` (new) | Topbar with admin email, super-admin badge, "Back to app" link. |
| `frontend/app/admin/layout.tsx` (new) | Fetches `/api/me`; redirects non-admins; renders the shell. |
| `frontend/app/admin/page.tsx` (new) | Landing dashboard placeholder (3 stat cards). |

---

## Task 1: Add `SUPER_ADMIN_EMAILS` constant

**Files:**
- Create: `backend/src/constants/admin.ts`

- [ ] **Step 1: Create the file**

```ts
// backend/src/constants/admin.ts
//
// SUPER_ADMIN_EMAILS — hardcoded fallback list of super admin emails.
// Override at runtime via process.env.SUPER_ADMIN_EMAILS (comma-separated)
// so prod/dev can differ without code changes. Survify uses the same pattern.

const FALLBACK_SUPER_ADMIN_EMAILS: string[] = [
  // Add the project owner's email(s) here.
  'cao.nv17@gmail.com',
];

const fromEnv = (process.env.SUPER_ADMIN_EMAILS || '')
  .split(',')
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

export const SUPER_ADMIN_EMAILS: string[] = (
  fromEnv.length ? fromEnv : FALLBACK_SUPER_ADMIN_EMAILS.map((e) => e.toLowerCase())
);
```

- [ ] **Step 2: Build to verify no TS errors**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0 with no errors.

- [ ] **Step 3: Commit**

```bash
git add backend/src/constants/admin.ts
git commit -m "feat(admin): add SUPER_ADMIN_EMAILS constant with env override"
```

---

## Task 2: Add `ACL` helper class

**Files:**
- Create: `backend/src/packages/acl/acl.ts`

- [ ] **Step 1: Create the file**

```ts
// backend/src/packages/acl/acl.ts
//
// ACL — central place for role checks. Mirrors survify's pattern.
// isSuperAdmin: email is in SUPER_ADMIN_EMAILS.
// isAdmin: user.role === 'Admin', or super admin (super admin implies admin).

import { DocumentType } from '@typegoose/typegoose';
import { User } from '@/models/User';
import { Roles } from '@/Constants';
import { SUPER_ADMIN_EMAILS } from '@/constants/admin';

type MaybeUser = DocumentType<User> | (User & { _id?: any }) | null | undefined;

export class ACL {
  static ROLES = Roles;

  static isSuperAdmin(user?: MaybeUser): boolean {
    if (!user || !user.email) return false;
    return SUPER_ADMIN_EMAILS.includes(user.email.toLowerCase());
  }

  static isAdmin(user?: MaybeUser): boolean {
    if (!user) return false;
    if (ACL.isSuperAdmin(user)) return true;
    return user.role === Roles.Admin;
  }
}

export default ACL;
```

- [ ] **Step 2: Verify it type-checks**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/src/packages/acl/acl.ts
git commit -m "feat(admin): add ACL helper with isAdmin/isSuperAdmin checks"
```

---

## Task 3: Extend `User.secureRelease()` with admin flags + add `disabled`

**Files:**
- Modify: `backend/src/models/User.ts`

- [ ] **Step 1: Add the `disabled` field and update `secureRelease`**

Replace the entire current contents of `backend/src/models/User.ts` with:

```ts
import { prop, getModelForClass, modelOptions } from '@typegoose/typegoose';
import { ACL } from '@/packages/acl/acl';

@modelOptions({ schemaOptions: { collection: 'users', timestamps: true } })
export class User {
  @prop({ required: true, unique: true })
  public username!: string;

  @prop({ required: true })
  public fullName!: string;

  @prop({ required: true, unique: true })
  public email!: string;

  @prop({ required: true })
  public password!: string;

  @prop()
  public googleId?: string;

  @prop({ default: false })
  public emailVerified!: boolean;

  @prop()
  public verificationToken?: string;

  @prop({ default: 0 })
  public credit!: number;

  @prop({ default: 'free' })
  public plan!: string;

  @prop({ default: 'User' })
  public role!: string;

  // Soft-deactivate flag. Set by admin "deactivate" action in a later slice.
  // Keeping it optional so existing user docs without the field continue to work.
  @prop({ default: false })
  public disabled?: boolean;

  @prop()
  public version?: string;

  @prop()
  public lastLogin?: Date;

  public secureRelease() {
    const obj: any = (this as any).toObject ? (this as any).toObject() : { ...this };
    obj.id = obj._id;
    delete obj.password;
    delete obj.verificationToken;
    delete obj.__v;
    // Expose admin flags so the frontend can gate UI without a separate request.
    // Server-side enforcement still happens via requireAdmin/requireSuperAdmin middlewares.
    obj.is_admin = ACL.isAdmin(this as any);
    obj.is_super_admin = ACL.isSuperAdmin(this as any);
    return obj;
  }
}

export const UserModel = getModelForClass(User);
```

- [ ] **Step 2: Type-check**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Smoke test the existing `/api/me` route**

Start the backend: `cd backend && npm run dev` (runs nodemon).

In another terminal:

```bash
# Replace YOUR_TOKEN with a real access_token from cookies after logging in via the frontend.
curl -s -X POST http://localhost:8001/api/me \
  -H 'Content-Type: application/json' \
  -d '{"access_token":"YOUR_TOKEN"}' | jq .
```

Expected: response includes `data.is_admin` and `data.is_super_admin` boolean fields.

For the project-owner email (`cao.nv17@gmail.com`), expect both to be `true`.
For any other user, expect `is_admin` to depend on `role`, `is_super_admin` to be `false`.

Stop the dev server with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add backend/src/models/User.ts
git commit -m "feat(admin): expose is_admin/is_super_admin on User.secureRelease, add disabled flag"
```

---

## Task 4: Add `requireAdmin` middleware

**Files:**
- Create: `backend/src/api/middlewares/requireAdmin.ts`

- [ ] **Step 1: Create the file**

```ts
// backend/src/api/middlewares/requireAdmin.ts
//
// Run this AFTER passport.authenticate('jwt'). It assumes req.user is populated.
// Returns 403 with the project's standard envelope if the user is not an admin.

import { Request, Response, NextFunction } from 'express';
import { Code } from '@/Constants';
import { ACL } from '@/packages/acl/acl';

export function requireAdmin(req: Request, res: Response, next: NextFunction) {
  const user = req.user as any;
  if (!ACL.isAdmin(user)) {
    return res.status(403).json({ code: Code.InvalidAuth, message: 'forbidden' });
  }
  return next();
}

export default requireAdmin;
```

- [ ] **Step 2: Type-check**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/src/api/middlewares/requireAdmin.ts
git commit -m "feat(admin): add requireAdmin Express middleware"
```

---

## Task 5: Add `requireSuperAdmin` middleware

**Files:**
- Create: `backend/src/api/middlewares/requireSuperAdmin.ts`

- [ ] **Step 1: Create the file**

```ts
// backend/src/api/middlewares/requireSuperAdmin.ts
//
// Stricter than requireAdmin — used per-route on destructive/sensitive ops.
// Same prerequisites: runs after passport.authenticate('jwt').

import { Request, Response, NextFunction } from 'express';
import { Code } from '@/Constants';
import { ACL } from '@/packages/acl/acl';

export function requireSuperAdmin(req: Request, res: Response, next: NextFunction) {
  const user = req.user as any;
  if (!ACL.isSuperAdmin(user)) {
    return res.status(403).json({ code: Code.InvalidAuth, message: 'forbidden' });
  }
  return next();
}

export default requireSuperAdmin;
```

- [ ] **Step 2: Type-check**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/src/api/middlewares/requireSuperAdmin.ts
git commit -m "feat(admin): add requireSuperAdmin Express middleware"
```

---

## Task 6: Create the admin sub-router with a healthcheck route

**Files:**
- Create: `backend/src/api/routes/admin/index.ts`

- [ ] **Step 1: Create the admin router**

```ts
// backend/src/api/routes/admin/index.ts
//
// Mount point for all admin section routers. Every section will be added here
// in subsequent slices (users, jobs, credits, announcements, ai-providers).
//
// The healthcheck route below proves the gating chain works end-to-end:
// passport (auth) -> requireAdmin -> handler.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { requireAdmin } from '@/api/middlewares/requireAdmin';

export default () => {
  const router = Router();

  router.post(
    '/healthcheck',
    passport.authenticate('jwt', { session: false }),
    requireAdmin,
    (req, res) => {
      const user = req.user as any;
      return res.json({
        code: Code.Success,
        data: {
          ok: true,
          email: user.email,
          is_super_admin: user.email && user.secureRelease().is_super_admin,
        },
      });
    }
  );

  return router;
};
```

- [ ] **Step 2: Type-check**

Run: `cd backend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add backend/src/api/routes/admin/index.ts
git commit -m "feat(admin): add admin sub-router with /admin/healthcheck"
```

---

## Task 7: Wire the admin router into `/api`

**Files:**
- Modify: `backend/src/api/index.ts`

- [ ] **Step 1: Add the admin import and mount**

Replace the entire current contents of `backend/src/api/index.ts` with:

```ts
import { Router } from 'express';
import auth from './routes/auth/auth';
import me from './routes/me';
import credit from './routes/credit';
import document from './routes/document';
import humanize from './routes/humanize';
import cite from './routes/cite';
import library from './routes/library';
import plagiarism from './routes/plagiarism';
import webhook from './routes/webhook';
import adminRouter from './routes/admin';

export default () => {
  const router = Router();

  auth(router);
  me(router);
  credit(router);
  document(router);
  humanize(router);
  cite(router);
  library(router);
  plagiarism(router);
  webhook(router);

  // Admin sub-router. Each handler inside applies passport.authenticate + requireAdmin
  // (and requireSuperAdmin where applicable). Mounting here puts everything under /api/admin/*.
  router.use('/admin', adminRouter());

  router.get('/status', (req, res) => {
    res.json({ status: 'ok' });
  });

  return router;
};
```

- [ ] **Step 2: Smoke test the gating chain**

Start the backend: `cd backend && npm run dev`.

In another terminal, with `ADMIN_TOKEN` and `USER_TOKEN` set to real tokens:

```bash
# 1. Unauthenticated — expect 401-ish (passport returns its own response).
curl -s -o /dev/null -w 'status=%{http_code}\n' \
  -X POST http://localhost:8001/api/admin/healthcheck

# 2. Authenticated as a non-admin user — expect 403 with code=InvalidAuth.
curl -s -X POST http://localhost:8001/api/admin/healthcheck \
  -H 'Content-Type: application/json' \
  -d "{\"access_token\":\"$USER_TOKEN\"}"

# 3. Authenticated as an admin (e.g. SUPER_ADMIN_EMAILS member) — expect ok.
curl -s -X POST http://localhost:8001/api/admin/healthcheck \
  -H 'Content-Type: application/json' \
  -d "{\"access_token\":\"$ADMIN_TOKEN\"}" | jq .
```

Expected case 1: `status=401`.
Expected case 2: `{"code":5,"message":"forbidden"}` (Code.InvalidAuth = 5).
Expected case 3: `{"code":1,"data":{"ok":true,"email":"...","is_super_admin":true}}`.

If you don't have a non-admin token, create one by signing up a test user via the frontend and copying its `access_token` cookie.

Stop the dev server.

- [ ] **Step 3: Commit**

```bash
git add backend/src/api/index.ts
git commit -m "feat(admin): mount /api/admin sub-router"
```

---

## Task 8: Install frontend dependencies

**Files:**
- Modify: `frontend/package.json` (via npm)

- [ ] **Step 1: Install runtime deps**

Run:

```bash
cd frontend && npm install --save \
  react-hook-form \
  zod \
  @hookform/resolvers \
  @headlessui/react \
  @heroicons/react \
  dayjs \
  class-variance-authority \
  lodash \
  @dnd-kit/core \
  @dnd-kit/sortable \
  @dnd-kit/utilities
```

Expected: installs without conflicts. Versions chosen by npm based on React 19 peer ranges.

- [ ] **Step 2: Install lodash types**

Run:

```bash
cd frontend && npm install --save-dev @types/lodash
```

- [ ] **Step 3: Verify typescript still compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 4: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "chore(admin): add deps for admin portal (rhf, zod, headlessui, heroicons, dayjs, dnd-kit)"
```

---

## Task 9: Add admin API helper

**Files:**
- Create: `frontend/lib/admin/api.ts`

- [ ] **Step 1: Create the helper**

```ts
// frontend/lib/admin/api.ts
//
// Thin wrapper around the existing Fetch helper for admin endpoints.
// Centralizing this gives one place to add interceptors (e.g., 403 redirects)
// in a follow-up without touching every page.

import Fetch from '@/lib/core/fetch/Fetch';
import Cookie from '@/lib/core/fetch/Cookie';

export type AdminResponse<T = any> = {
  code: number;
  data?: T;
  message?: string;
};

const withToken = (params: Record<string, any> = {}) => ({
  ...params,
  access_token: Cookie.fromDocument('access_token'),
});

export const AdminApi = {
  // SWR-friendly fetcher: receives a [url, params] tuple or a string.
  fetcher: async (key: string | [string, Record<string, any> | undefined]) => {
    const [url, params] = typeof key === 'string' ? [key, undefined] : key;
    const res = await Fetch.post<AdminResponse>(url, withToken(params));
    return res.data as AdminResponse;
  },

  // For mutations from event handlers.
  post: async <T = any>(url: string, params: Record<string, any> = {}) => {
    const res = await Fetch.post<AdminResponse<T>>(url, withToken(params));
    return res.data as AdminResponse<T>;
  },
};

export default AdminApi;
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/admin/api.ts
git commit -m "feat(admin): add AdminApi helper for /api/admin/* fetches"
```

---

## Task 10: Build the admin sidebar component

**Files:**
- Create: `frontend/app/admin/_components/AdminSidebar.tsx`

- [ ] **Step 1: Create the sidebar**

```tsx
// frontend/app/admin/_components/AdminSidebar.tsx
//
// Static sidebar nav for the admin shell. Section links are listed for the
// full portal scope but only the dashboard link routes anywhere in this slice.
// Other links render but are visually disabled until later slices implement them.

'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  HomeIcon,
  UsersIcon,
  CurrencyDollarIcon,
  DocumentTextIcon,
  SparklesIcon,
  ShieldCheckIcon,
  MegaphoneIcon,
  CpuChipIcon,
  CommandLineIcon,
} from '@heroicons/react/24/outline';

type NavItem = {
  label: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  group: 'Operations' | 'Jobs' | 'Content' | 'Config';
  superAdminOnly?: boolean;
  enabled?: boolean;
};

const NAV: NavItem[] = [
  { label: 'Dashboard', href: '/admin', icon: HomeIcon, group: 'Operations', enabled: true },
  { label: 'Users', href: '/admin/users', icon: UsersIcon, group: 'Operations' },
  { label: 'Credits', href: '/admin/credits', icon: CurrencyDollarIcon, group: 'Operations' },
  { label: 'Documents', href: '/admin/documents', icon: DocumentTextIcon, group: 'Jobs' },
  { label: 'Humanize', href: '/admin/humanize', icon: SparklesIcon, group: 'Jobs' },
  { label: 'Plagiarism', href: '/admin/plagiarism', icon: ShieldCheckIcon, group: 'Jobs' },
  { label: 'AutoCite', href: '/admin/autocite', icon: CommandLineIcon, group: 'Jobs' },
  { label: 'Announcements', href: '/admin/announcements', icon: MegaphoneIcon, group: 'Content', superAdminOnly: true },
  { label: 'AI Providers', href: '/admin/ai-providers', icon: CpuChipIcon, group: 'Config', superAdminOnly: true },
];

export function AdminSidebar({ isSuperAdmin }: { isSuperAdmin: boolean }) {
  const pathname = usePathname();
  const groups: Array<NavItem['group']> = ['Operations', 'Jobs', 'Content', 'Config'];

  return (
    <aside className="fixed left-0 top-0 h-screen w-60 border-r border-gray-200 bg-white">
      <div className="px-4 py-5 text-lg font-semibold">DoThesis Admin</div>
      <nav className="px-2">
        {groups.map((group) => {
          const items = NAV.filter((n) => n.group === group && (!n.superAdminOnly || isSuperAdmin));
          if (items.length === 0) return null;
          return (
            <div key={group} className="mb-6">
              <div className="px-3 text-xs font-medium uppercase tracking-wider text-gray-500">{group}</div>
              <ul className="mt-1">
                {items.map((item) => {
                  const active = pathname === item.href;
                  const Icon = item.icon;
                  const baseClass = 'flex items-center gap-2 rounded px-3 py-2 text-sm';
                  const stateClass = item.enabled
                    ? active
                      ? 'bg-gray-900 text-white'
                      : 'text-gray-700 hover:bg-gray-100'
                    : 'cursor-not-allowed text-gray-400';
                  return (
                    <li key={item.href}>
                      {item.enabled ? (
                        <Link href={item.href} className={`${baseClass} ${stateClass}`}>
                          <Icon className="h-5 w-5" />
                          {item.label}
                        </Link>
                      ) : (
                        <span className={`${baseClass} ${stateClass}`} title="Coming in a later slice">
                          <Icon className="h-5 w-5" />
                          {item.label}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}

export default AdminSidebar;
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/_components/AdminSidebar.tsx
git commit -m "feat(admin): add AdminSidebar with grouped nav and super-admin gating"
```

---

## Task 11: Build the admin topbar component

**Files:**
- Create: `frontend/app/admin/_components/AdminTopbar.tsx`

- [ ] **Step 1: Create the topbar**

```tsx
// frontend/app/admin/_components/AdminTopbar.tsx

'use client';

import Link from 'next/link';

type Props = {
  email: string;
  isSuperAdmin: boolean;
};

export function AdminTopbar({ email, isSuperAdmin }: Props) {
  return (
    <header className="sticky top-0 z-10 flex h-14 items-center justify-between border-b border-gray-200 bg-white px-6">
      <div className="text-sm text-gray-500">Admin</div>
      <div className="flex items-center gap-4">
        <span className="text-sm text-gray-700">{email}</span>
        {isSuperAdmin && (
          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800">
            Super admin
          </span>
        )}
        <Link
          href="/"
          className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-700 hover:bg-gray-50"
        >
          Back to app
        </Link>
      </div>
    </header>
  );
}

export default AdminTopbar;
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/_components/AdminTopbar.tsx
git commit -m "feat(admin): add AdminTopbar with super-admin badge"
```

---

## Task 12: Build the admin layout (auth gate)

**Files:**
- Create: `frontend/app/admin/layout.tsx`

- [ ] **Step 1: Create the layout**

```tsx
// frontend/app/admin/layout.tsx
//
// Root of the /admin route group. Single source of truth for the client-side gate.
// Real enforcement is server-side per route — this is UX only.

'use client';

import React, { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useMe } from '@/hooks/user';
import Cookie from '@/lib/core/fetch/Cookie';
import { ClientOnly } from '@/components/common/ClientOnly';
import AdminSidebar from './_components/AdminSidebar';
import AdminTopbar from './_components/AdminTopbar';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { data: user, isLoading } = useMe();

  useEffect(() => {
    if (isLoading) return;

    // Not signed in → push to login.
    if (!user && !Cookie.fromDocument('access_token')) {
      router.replace('/login');
      return;
    }

    // Signed in but not admin → bounce to home. Server-side gate would also reject,
    // but we don't even render the shell in this case.
    if (user && !user.is_admin) {
      router.replace('/');
    }
  }, [user, isLoading, router]);

  // Render nothing until we know the user is admin. Avoids flicker of the shell
  // before the redirect lands.
  if (isLoading || !user || !user.is_admin) {
    return null;
  }

  return (
    <ClientOnly>
      <div className="min-h-screen bg-gray-50">
        <AdminSidebar isSuperAdmin={!!user.is_super_admin} />
        <div className="ml-60">
          <AdminTopbar email={user.email} isSuperAdmin={!!user.is_super_admin} />
          <main className="p-6">{children}</main>
        </div>
      </div>
    </ClientOnly>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/layout.tsx
git commit -m "feat(admin): add /admin layout with non-admin redirect"
```

---

## Task 13: Build the admin dashboard placeholder page

**Files:**
- Create: `frontend/app/admin/page.tsx`

- [ ] **Step 1: Create the page**

```tsx
// frontend/app/admin/page.tsx
//
// Placeholder dashboard for the foundation slice. Real stats wire up in a later
// slice (after user/job admin endpoints exist). Three cards keep the visual
// alive while we land subsequent slices.

'use client';

export default function AdminDashboardPage() {
  const cards = [
    { label: 'Total users', value: '—' },
    { label: 'Jobs (24h)', value: '—' },
    { label: 'Credits (24h, net)', value: '—' },
  ];

  return (
    <div>
      <h1 className="mb-6 text-2xl font-semibold">Dashboard</h1>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-lg border border-gray-200 bg-white p-4">
            <div className="text-xs uppercase tracking-wider text-gray-500">{c.label}</div>
            <div className="mt-2 text-2xl font-semibold text-gray-900">{c.value}</div>
          </div>
        ))}
      </div>
      <p className="mt-6 text-sm text-gray-600">
        Foundation slice landed. User management, job sections, credits, announcements, and AI provider
        config will be added in subsequent slices.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/admin/page.tsx
git commit -m "feat(admin): add placeholder dashboard at /admin"
```

---

## Task 14: End-to-end smoke test

This task has no code — it's the verification step that proves the whole foundation slice works together. No commit at the end.

- [ ] **Step 1: Start backend**

Run in one terminal: `cd backend && npm run dev`
Expected: server logs `DoThesis backend running on port 8001`.

- [ ] **Step 2: Start frontend**

Run in another terminal: `cd frontend && npm run dev`
Expected: server logs `Local: http://localhost:8002`.

- [ ] **Step 3: Sign in as a non-admin user, then visit /admin**

In a browser:
1. Go to `http://localhost:8002/login` and sign in (or sign up + verify) as a normal user.
2. Navigate to `http://localhost:8002/admin`.

Expected: the page redirects you back to `/` (home). The admin shell never renders.

- [ ] **Step 4: Sign in as an admin, then visit /admin**

In an incognito window:
1. Sign in as a user whose email is in `SUPER_ADMIN_EMAILS` (e.g. `cao.nv17@gmail.com`).
2. Navigate to `http://localhost:8002/admin`.

Expected:
- Sidebar shows on the left with "Operations / Jobs / Content / Config" groups.
- Sidebar includes "Announcements" and "AI Providers" entries (super-admin-only — present because you're a super admin).
- Topbar shows your email with a yellow "Super admin" badge.
- Main area shows "Dashboard" header and three placeholder cards with `—` values.
- Section links other than "Dashboard" appear grayed out (cursor: not-allowed) — they're disabled placeholders for the next slices.

- [ ] **Step 5: Verify the backend gate works directly**

In a third terminal:

```bash
curl -s -X POST http://localhost:8001/api/admin/healthcheck \
  -H 'Content-Type: application/json' \
  -d "{\"access_token\":\"<NON_ADMIN_TOKEN>\"}"
```

Expected: `{"code":5,"message":"forbidden"}`.

```bash
curl -s -X POST http://localhost:8001/api/admin/healthcheck \
  -H 'Content-Type: application/json' \
  -d "{\"access_token\":\"<ADMIN_TOKEN>\"}" | jq .
```

Expected: `{"code":1,"data":{"ok":true,"email":"...","is_super_admin":true}}`.

- [ ] **Step 6: Stop both dev servers**

Ctrl+C in both terminals.

If everything above passes, the foundation slice is complete and the next slice (Users management) can be planned.

---

## Out of scope for this slice (called out from the design spec)

These ship in subsequent slices and have **no tasks in this plan** by design:

- User list / detail / add credit / role change / deactivate (Slice 2)
- Credit transactions list (Slice 3)
- HumanizeJob admin section (Slice 4 — establishes the pattern)
- Document, PlagiarismJob, AutoCiteJob admin sections (Slice 5)
- System announcements + public banner (Slice 6)
- AI provider config + service integration (Slice 7)
- `react-quill` install (markdown-only announcements decided)
- `chart.js` install (no charts in v1 dashboard)
- Backend test framework setup (deferred — verify via curl for now)
