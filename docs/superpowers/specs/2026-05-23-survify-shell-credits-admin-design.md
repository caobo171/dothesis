# Port Survify's shell, credits, and admin into Opendraft

**Date:** 2026-05-23
**Status:** Draft — pending user review

## Goal

Adopt Survify's layout chrome (sidebar + sticky header), credit-pack billing flow, and admin section in `opendraft/web` and `opendraft/api`, while keeping the existing FastAPI engine (papers/jobs/exports/SSE) untouched.

## Non-goals

- Rewriting the drafting engine or the SSE/job-runner machinery.
- Migrating every existing page (Dashboard, Wizard, PaperShell, DraftEditor, Citations, ExportTab, AgentRun, Billing) to the new stack in this change. Those keep working under the new shell; per-page Tailwind/TS migration is a follow-up.
- Marketing/landing pages — public surfaces are out of scope.

## Stack changes (`opendraft/web`)

Add the following dev dependencies:

- `typescript`, `@types/react`, `@types/node`
- `tailwindcss`, `postcss`, `autoprefixer`
- `@headlessui/react`
- `@heroicons/react`
- `lucide-react`
- `clsx`
- `next-themes` (only if dark mode is enabled later — defer if not needed day 1)

Files:

- `tsconfig.json` — Next.js defaults, `paths: { "@/*": ["./app/*", "./*"] }`.
- `tailwind.config.ts` — content globs cover `app/**/*.{ts,tsx,js,jsx}`. Extend theme `colors.primary` from the existing `--blue-*` tokens in `globals.css` so Survify's `primary-50/600/...` classes resolve to opendraft's electric blue.
- `postcss.config.js` — tailwind + autoprefixer.
- `app/globals.css` — keep the CSS-variable design system (used by existing pages); add `@tailwind base/components/utilities` at the top.

Existing `.jsx` files keep working — Next compiles both.

## Routing layout

```
app/
  layout.tsx                  # root: AuthProvider + global Tailwind
  (inapp)/
    layout.tsx                # wraps SidebarLayout (user nav)
    page.tsx                  # dashboard (moved from app/page.jsx)
    wizard/page.jsx           # moved
    papers/page.tsx           # NEW — drafts list
    paper/[id]/...            # moved
    credit/page.tsx           # NEW
    credit/_components/Credit.tsx, PricePackages.tsx
  admin/
    layout.tsx                # wraps SidebarLayout (admin nav)
    page.tsx                  # → users (Survify pattern)
    users/page.tsx
    papers/page.tsx
    jobs/page.tsx
    announcements/page.tsx
    orders/page.tsx
  login/                      # untouched
  signup/                     # untouched
  components/
    layout/
      SidebarLayout.tsx       # ported from Survify
      Topbar.tsx              # the sticky header bar inside SidebarLayout
      SidebarSections.tsx     # config-driven nav rendering (already in SidebarLayout)
    ui/                       # shared primitives (Button, Card, Dialog, Table, Pagination)
    common/
      AnnouncementDialog.tsx
      PricingPackages.tsx
```

Wrapping existing JSX pages in the new shell does not require their conversion to TS. The shell injects the layout; pages are rendered as `children`.

## Shell components

### SidebarLayout (`app/components/layout/SidebarLayout.tsx`)

Direct port of `survify-frontend/components/layout/sidebar/sidebar-layout.tsx`:

- Desktop: fixed sidebar, collapsible to icon-only (persist `sidebarCollapsed` in `localStorage`).
- Mobile: Headless UI `Dialog` slide-over.
- Nav rendered from a `sections: { id, name, options }[]` prop — supports sub-items with chevron expand, count badges, `default`/active highlighting.
- Help Center card pinned bottom (text changed for Opendraft: "Find docs" → GitHub README, "Contact Coach" → `mailto:cao.nguyen@wele-learn.com`).
- Sticky top bar: mobile burger, search slot (empty placeholder for now), bell button (notification dropdown stub), user menu with avatar + email + "Sign out".

Brand swap: replace Survify logo PNGs with opendraft's `BrandMark` from `app/components/shared.jsx`, lifted into a `<Brand />` component.

### Section config

User shell (`app/(inapp)/layout.tsx`):

```ts
sections = [
  {
    id: 'workspace', name: 'Workspace',
    options: [
      { name: 'Dashboard', href: '/', icon: HomeIcon },
      { name: 'New Thesis', href: '/wizard', icon: PlusIcon },
      { name: 'Drafts', href: '/papers', icon: DocumentTextIcon },
    ],
  },
  {
    id: 'account', name: 'Account',
    options: [
      { name: 'Credit', href: '/credit', icon: CurrencyDollarIcon },
    ],
  },
];
```

Admin shell (`app/admin/layout.tsx`):

```ts
sections = [
  {
    id: 'admin', name: 'Admin',
    options: [
      { name: 'Users',         href: '/admin/users',         icon: UserIcon },
      { name: 'Papers',        href: '/admin/papers',        icon: DocumentTextIcon },
      { name: 'Jobs',          href: '/admin/jobs',          icon: CpuChipIcon },
      { name: 'Announcements', href: '/admin/announcements', icon: SpeakerWaveIcon },
      { name: 'Orders',        href: '/admin/orders',        icon: CreditCardIcon },
    ],
  },
];
```

Both layouts read `useMe()`; if the route is `/admin/*` and `user.is_super_admin !== true`, render a 403 with a "Back to app" link instead of the children.

## Wizard — Standard / Premium model selector

The wizard exposes one field labeled "Model" with two radio choices:

- **Standard** — fast and inexpensive.
- **Premium** — higher quality, costs more credits.

The backend resolves the tier to a concrete provider/model:

```python
# api/app/pricing.py
TIER_TO_MODEL = {
    "standard": "gemini-flash",
    "premium":  "gpt-5",     # configurable via env: OPENDRAFT_PREMIUM_MODEL
}
```

The `papers` table gains a `model_tier` column (`standard` | `premium`). The resolved provider/model goes on the job row for ops/log purposes only. The frontend never receives or sends the underlying model name.

Allowed-model allowlist in `papers.py` is replaced with the tier mapping.

## Credit system

### Schema (Alembic migration)

```sql
ALTER TABLE users
  ADD COLUMN credit INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN is_super_admin BOOLEAN NOT NULL DEFAULT FALSE,
  ADD COLUMN username TEXT;

CREATE TABLE orders (
  id            UUID PRIMARY KEY,
  user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  package_id    TEXT NOT NULL,           -- starter_package | standard_package | expert_package
  credits       INTEGER NOT NULL,
  amount_cents  INTEGER NOT NULL,
  currency      TEXT NOT NULL DEFAULT 'USD',
  status        TEXT NOT NULL DEFAULT 'pending',  -- pending | paid | refunded | failed
  polar_checkout_id TEXT,
  polar_order_id    TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  paid_at       TIMESTAMPTZ
);

CREATE TABLE credit_transactions (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  delta       INTEGER NOT NULL,         -- positive for credit, negative for debit
  reason      TEXT NOT NULL,            -- purchase | paper_run | refund | admin_grant
  ref_type    TEXT,                     -- order | paper | user
  ref_id      UUID,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE announcements (
  id          UUID PRIMARY KEY,
  kind        TEXT NOT NULL,            -- first_login | login_banner
  title       TEXT NOT NULL,
  body        TEXT NOT NULL,
  image_url   TEXT,
  cta_label   TEXT,
  cta_url     TEXT,
  active      BOOLEAN NOT NULL DEFAULT TRUE,
  starts_at   TIMESTAMPTZ,
  ends_at     TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE papers ADD COLUMN model_tier TEXT NOT NULL DEFAULT 'standard';
```

`credit_transactions` is the source of truth. `users.credit` is a denormalized cache updated in the same transaction as ledger inserts. A cron/admin-tool can rebuild the cache from the ledger if it ever diverges.

### Packages (verbatim from Survify)

```python
# api/app/pricing.py
PACKAGES = [
  {"id": "starter_package",  "name": "Starter package",  "price_cents":  900, "old_price_cents": 1500, "credits": 300},
  {"id": "standard_package", "name": "Standard package", "price_cents": 1900, "old_price_cents": 3500, "credits": 700},
  {"id": "expert_package",   "name": "Expert package",   "price_cents": 4900, "old_price_cents":10000, "credits": 2000},
]
```

### Per-paper cost (placeholder; tune later)

```python
PAPER_COST = {
  ("research", "standard"):  60, ("research", "premium"):  150,
  ("bachelor", "standard"): 120, ("bachelor", "premium"):  300,
  ("master",   "standard"): 240, ("master",   "premium"):  600,
  ("phd",      "standard"): 480, ("phd",      "premium"): 1200,
}
```

### Polar integration

Two endpoints + one webhook:

- `GET  /api/credit/packages` — returns `PACKAGES` config.
- `POST /api/credit/checkout` body `{ package_id, quantity }` — creates an `Order(status=pending)`, calls Polar `checkouts.create` with `metadata={ order_id, user_id, package_id, credits }`, returns `{ checkout_url }`. Frontend redirects.
- `POST /api/polar/webhook` — verifies Polar signature using `POLAR_WEBHOOK_SECRET`; on `order.paid`:
  1. Look up `Order` by `polar_checkout_id`. Idempotent (no-op if already paid).
  2. In one transaction: set `orders.status='paid'`, `orders.paid_at=now()`, `orders.polar_order_id=...`; insert `credit_transactions` with positive delta; `UPDATE users SET credit = credit + N`.

Env vars: `POLAR_ACCESS_TOKEN`, `POLAR_WEBHOOK_SECRET`, `POLAR_SERVER` (sandbox|production), `OPENDRAFT_BASE_URL` (for return URLs).

Success/cancel URLs route back to `/credit?polar=success` and `/credit?polar=cancel`. The Credit page already shows a success banner when `?polar=success` is present (Survify code).

### Paper-creation flow with credit check

`POST /api/papers`:

1. Resolve `cost = PAPER_COST[(level, tier)]`.
2. `SELECT credit FROM users WHERE id = :uid FOR UPDATE`.
3. If `credit < cost`, return `402 {error: {code: "insufficient_credits", required, balance}}`.
4. In the same transaction: insert `credit_transactions(delta=-cost, reason='paper_run', ref_type='paper', ref_id=paper.id)`; `UPDATE users SET credit = credit - cost`.
5. Spawn job (existing logic).

On terminal job failure (status transitions to `failed`/`canceled`) inside `job_runner.py`'s status writer:

- Insert refund `credit_transactions(delta=+cost, reason='refund', ref_type='paper', ref_id=paper.id)` and `UPDATE users SET credit = credit + cost`.
- Idempotent: refund is only inserted if no refund row exists yet for this paper.

### Frontend

Port `(inapp)/credit/page.tsx`, `_components/Credit.tsx`, `_components/PricePackages.tsx` and `components/common/PricingPackages.tsx` from Survify. Strip Paddle code paths; keep Polar only. Replace `useMe()`/`useMyForms()`/`useMyOrders()` calls with opendraft equivalents:

- `useMe()` — wrap `AuthContext` in a SWR-backed hook returning `{ id, email, username, credit, is_super_admin }`.
- `useMyForms()` → drop (no surveys).
- `useMyOrders()` → `useMyOrders()` against `/api/credit/orders` returning `{ order_num, recent: [...] }`.

Stats row on the Credit page becomes: Drafts count + Orders count.

## Admin section

Gated server-side by a `require_admin(user = Depends(current_user))` FastAPI dependency that raises 403 unless `user.is_super_admin`.

Five pages, all under `/admin/*`:

### `/admin/users`

- `GET /api/admin/users?page=&q=&limit=` — paginated list with email, username, credit, is_super_admin, created_at, last_seen.
- `GET /api/admin/users/{id}` — detail.
- `POST /api/admin/users/{id}/credit` body `{ delta, note? }` — admin grant/debit; appends ledger row with `reason='admin_grant'`.
- `POST /api/admin/users/{id}/admin-toggle` — flip `is_super_admin` (cannot unset on yourself).

UI: searchable table → click row → slide-over drawer with grant form and admin toggle.

### `/admin/papers`

- `GET /api/admin/papers?page=&user_id=&status=&q=` — list across all users.
- Columns: title, owner email, level, tier, status, latest job progress, created_at.

### `/admin/jobs`

- `GET /api/admin/jobs?status=running|failed|done|...` — list with paper title, status, phase, progress, started_at, error_text.
- `POST /api/admin/jobs/{id}/cancel` — sends SIGTERM via existing job runner machinery; sets `canceled`; refund triggers if appropriate.

### `/admin/announcements`

- Full CRUD: `GET/POST/PATCH/DELETE /api/admin/announcements`.
- Fields: kind (radio: first-login / login-banner), title, body (textarea), image_url, cta_label/url, active toggle, starts_at/ends_at.
- User-side fetch: `GET /api/announcements/me` returns at most one `first_login` (if user account < 48h old) and one currently-active `login_banner`. Front-end stores `localStorage` keys (`opendraft_first_annoucement_<user>`, `opendraft_login_annoucement_<user>_<id>`) to throttle (once per user for first-login; once per day for login-banner).

### `/admin/orders`

- `GET /api/admin/orders?status=&user_id=&page=` — purchase audit.
- Columns: user email, package, credits, amount, status, polar_checkout_id, created_at, paid_at.
- Click row → drawer with Polar link, raw payload.

## Auth & me-hook

The existing `lib/auth-context.jsx` provides `user`. Add a thin SWR layer:

```ts
// app/lib/use-me.ts
export function useMe() {
  return useSWR('/api/me', swrFetcher);
}
```

`/api/me` returns the User row plus `credit`, `is_super_admin`, `username`. Replace direct `useAuth().user` reads in the new shell with `useMe()` so it stays in sync after credit changes.

## Migration order

1. Tailwind/TS scaffolding + tsconfig + tailwind.config + globals.
2. Alembic migration for new columns + tables.
3. `is_super_admin` + `credit` on user, `/api/me`, `require_admin` dep.
4. New `SidebarLayout` + `(inapp)` route group + admin route group; wrap existing JSX pages.
5. Credit API + Polar checkout + webhook + Credit page UI.
6. Per-paper credit cost wiring + tier-based model resolution in `papers.py`.
7. Admin pages, one at a time: users → papers → jobs → orders → announcements.
8. Announcement dialog on inapp layout.

Each step is independently testable and reversible.

## Risks / open questions

- **Polar account setup** — needs an account, products, webhook secret. Until those exist, checkout returns a fake URL in dev (env-flagged `OPENDRAFT_PAYMENTS=dummy`).
- **Existing pages styling drift** — wrapping `.jsx` pages in the new Tailwind shell may produce visual inconsistencies on hover/focus states. Acceptable until the per-page migration follow-up.
- **Refund race** — if a job fails during cancel, the refund logic must be guarded by `SELECT FOR UPDATE` on the paper row plus a check that no refund ledger row exists yet.
- **Pricing tuning** — placeholders only. Real numbers come from product/finance later.

## Testing strategy

- **Backend:** pytest for `/api/credit/checkout` (happy + signature failure + idempotent webhook), `/api/papers` (insufficient-credit 402, refund on failure), `require_admin` 403, admin endpoints.
- **Frontend:** smoke-test each route renders without console errors; manual click-through of the wizard → credit flow.
- **Manual:** Polar sandbox end-to-end once, then trust unit tests + idempotent webhook.
