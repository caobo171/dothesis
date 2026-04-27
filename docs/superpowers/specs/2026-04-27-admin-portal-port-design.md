# Admin Portal — Port from Survify

**Date:** 2026-04-27
**Status:** Design approved, pending implementation plan
**Source:** `/Users/caonguyenvan/project/survify`
**Target:** `/Users/caonguyenvan/project/dothesis`

## Goal

Bring an admin portal to dothesis by porting the relevant parts of survify's admin UI and backend, adapted to dothesis's domain (documents, citations, humanize jobs, plagiarism jobs).

## Scope

### In scope
- **Users management** — list, detail, add credit, role/plan changes, deactivate
- **Job management — four separate sections** (one per dothesis job model):
  - Documents
  - Humanize jobs
  - Plagiarism jobs
  - AutoCite jobs
- **Credit transactions** — read-only list with filters
- **System announcements** — CRUD + enable/disable, with public banner endpoint
- **AI provider config** — manage AI provider credentials/defaults (repurposed from survify's `models` admin section)

### Out of scope (explicit)
- Affiliate program + withdrawals (whole subsystem, not just admin UI)
- Survey forms (`forms`) — survify-specific, no domain fit
- Data collection orders (`data.orders`) — survify-specific, no domain fit
- Audit log collection + UI (deferred to follow-up)
- Rich-text announcements (markdown only in v1)
- Bulk actions / multi-select on admin tables
- CSV export
- Rate limiting on admin endpoints

## Decisions

| Topic | Decision |
|---|---|
| Orders concept | Do **not** introduce a unified `Order` model. Keep dothesis's four separate job models, with one admin section per model. |
| Credit transactions | Reuse existing `Credit` model unchanged. |
| Admin role | `User.role === 'Admin'`. Existing field, default `'User'`. |
| Super admin | Hardcoded `SUPER_ADMIN_EMAILS` constant (with env-var override `process.env.SUPER_ADMIN_EMAILS`). |
| Frontend stack | Add survify's deps to dothesis: `react-hook-form`, `zod`, `@hookform/resolvers`, `@headlessui/react`, `@heroicons/react`, `dayjs`, `class-variance-authority`, `lodash`, `@dnd-kit/core`, `@dnd-kit/sortable`. |
| Rollout | Incremental, slice-by-slice. Each slice lands and is verified independently. |

## Architecture

### Backend — `/Users/caonguyenvan/project/dothesis/backend/src`

New files:
- `constants/admin.ts` — exports `SUPER_ADMIN_EMAILS: string[]` (hardcoded, env-overridable).
- `packages/acl/acl.ts` — `ACL` class:
  - `ACL.ROLES = { User: 'User', Admin: 'Admin' }`
  - `ACL.isAdmin(user)` → `user.role === 'Admin' || isSuperAdmin(user)`
  - `ACL.isSuperAdmin(user)` → `SUPER_ADMIN_EMAILS.includes(user.email)`
- `api/middlewares/requireAdmin.ts` — runs after auth; 403 if not admin.
- `api/middlewares/requireSuperAdmin.ts` — same, but for super admin.
- `api/routes/admin/` — one subfolder per section (`user`, `document`, `humanize`, `plagiarism`, `autocite`, `credit`, `announcement`, `ai-provider`).

Mounted in `backend/src/api/index.ts`:

```ts
app.use('/api/admin', requireAdmin, adminRouter);
```

Super-admin-only handlers wrap with `requireSuperAdmin` per route inside the admin router.

### Frontend — `/Users/caonguyenvan/project/dothesis/frontend/app`

New route group `app/admin/` (peer of `(auth)` and `(workspace)`):
- `app/admin/layout.tsx` — fetches `/api/me`; redirects non-admins; renders sidebar shell.
- `app/admin/page.tsx` — dashboard landing (basic stats: user count, jobs in last 24h, credits flow).
- `app/admin/users/page.tsx`, `app/admin/users/[id]/page.tsx`
- `app/admin/documents/page.tsx`, `app/admin/documents/[id]/page.tsx`
- `app/admin/humanize/page.tsx`, `app/admin/humanize/[id]/page.tsx`
- `app/admin/plagiarism/page.tsx`, `app/admin/plagiarism/[id]/page.tsx`
- `app/admin/autocite/page.tsx`, `app/admin/autocite/[id]/page.tsx`
- `app/admin/credits/page.tsx`
- `app/admin/announcements/page.tsx`, `app/admin/announcements/[id]/edit/page.tsx`
- `app/admin/ai-providers/page.tsx`

Reusable components in `app/admin/_components/`: `AdminTable`, `Pagination`, `FiltersBar`, `StatusBadge`, `DateRangePicker`, `OwnerCell`, `ConfirmDialog`, `JsonViewer`, `AdminPageHeader`, `useAdminList` hook.

### Data flow

Frontend admin pages → SWR fetch from `/api/admin/*` → backend reads MongoDB via existing typegoose models. No new infrastructure; only two new models.

## Auth & ACL

- `User.secureRelease()` extended to add `is_admin` and `is_super_admin` boolean flags. Frontend uses these for UI gating.
- Server-side gate is the source of truth. Client-side gate is UX only.
- 401 → existing auth redirect; 403 from `/api/admin/*` → toast "Forbidden" + redirect to `/`.

## Backend routes per section

All under `/api/admin`, gated by `requireAdmin`. Routes flagged **[SA]** require super admin.

### Users (`admin/user/`)
- `GET /users` — filters: q, role, plan, emailVerified, sort, page, limit
- `GET /users/:id` — detail with per-job-type counts and total credit in/out
- `POST /users/:id/credit` — add credit (writes `Credit` doc + bumps `User.credit`)
- `PATCH /users/:id/role` **[SA]**
- `PATCH /users/:id/plan`
- `POST /users/:id/deactivate` **[SA]**

### Documents (`admin/document/`)
- `GET /documents` — filters: q, owner, dateRange, page, limit
- `GET /documents/:id`
- `DELETE /documents/:id` **[SA]**

### Humanize / Plagiarism / AutoCite (parallel: `admin/humanize/`, `admin/plagiarism/`, `admin/autocite/`)
- `GET /:resource` — filters: q, owner, status, dateRange, page, limit
- `GET /:resource/:id` — detail (input, output, iterations, tokenUsage where applicable, status, timestamps)
- `POST /:resource/:id/cancel`
- `POST /:resource/:id/retry` **[SA]**
- `DELETE /:resource/:id` **[SA]**

### Credits (`admin/credit/`)
- `GET /credits` — filters: owner, direction, status, orderType, dateRange, page, limit
- `GET /credits/:id`
- Read-only. Mutations only via `POST /admin/users/:id/credit`.

### System announcements (`admin/announcement/`) **[all SA]**
- `GET /announcements`
- `POST /announcements`
- `PATCH /announcements/:id`
- `DELETE /announcements/:id`
- `POST /announcements/:id/enable`
- `POST /announcements/:id/disable`
- Plus public `GET /api/announcements/active` (no auth) for workspace UI banners.

### AI provider config (`admin/ai-provider/`) **[all SA]**
- `GET /ai-providers` — `apiKey` never returned, only `hasKey: boolean`.
- `POST /ai-providers`
- `PATCH /ai-providers/:id`
- `DELETE /ai-providers/:id`
- `POST /ai-providers/:id/toggle`
- Existing humanize/plagiarism services updated to read provider config from this collection, with env var fallback when no record exists.

### List response contract

Every list endpoint returns `{ items, total, page, limit }`. SWR keys mirror query strings.

### Validation

Request bodies validated with `zod` schemas colocated with each route.

## Models

### New: `backend/src/models/SystemAnnouncement.ts`
```
title: string
content: string                 // markdown
audience: 'all' | 'free' | 'paid'
enabled: boolean
startsAt?: Date
endsAt?: Date
createdBy: string               // admin email
timestamps
```
Index `{ enabled: 1, startsAt: 1, endsAt: 1 }` for the public `active` query.

### New: `backend/src/models/AiProviderConfig.ts`
```
provider: 'openai' | 'anthropic' | 'gemini' | 'custom'
name: string                    // display label
apiKey: string                  // encrypted via existing packages/crypto; never returned
baseUrl?: string
defaultModel: string
enabled: boolean
order: number
purpose: 'humanize' | 'plagiarism' | 'autocite' | 'general'
timestamps
```
`secureRelease()` strips `apiKey` and adds `hasKey: boolean`.

### Modified: `backend/src/models/User.ts`
- Add `disabled?: boolean` (soft-deactivate).
- `secureRelease()` adds `is_admin: boolean` and `is_super_admin: boolean`.

### Unchanged
`Document`, `HumanizeJob`, `PlagiarismJob`, `AutoCiteJob`, `Credit`.

## Frontend shell

- Two-column: collapsible sidebar (240px, left) + content (right).
- Sidebar groups:
  - **Operations:** Users, Credits
  - **Jobs:** Documents, Humanize, Plagiarism, AutoCite
  - **Content:** Announcements
  - **Config:** AI Providers (super admin only)
- Top bar: breadcrumbs · current admin email + super-admin badge · "Back to app" link.
- Mobile: sidebar collapses to drawer using `@headlessui/react` `Dialog`.

### Shared primitives (`app/admin/_components/`)
- `AdminTable<T>` — generic table with column config, sort, loading/empty states.
- `Pagination` — URL-synced via `useSearchParams`.
- `FiltersBar` — slot-based; sections compose their own filters.
- `StatusBadge` — color-coded for job/credit statuses.
- `DateRangePicker` — `dayjs` + plain inputs (no heavy datepicker).
- `OwnerCell` — email + link to `/admin/users/:id`.
- `ConfirmDialog` — `@headlessui/react` Dialog; required for **[SA]** mutations.
- `JsonViewer` — read-only `<pre>` with copy button for job blobs.
- `useAdminList<T>(endpoint, query)` — SWR wrapper returning `{ items, total, isLoading, mutate }`.

### Per-section UI

- **Users list** — cols: email, fullName, role, plan, credit, emailVerified, createdAt. Filters: q, role, plan, verified.
- **User detail** — header (name/email/role/plan), tabs:
  - Overview (counts)
  - Credits (filtered by owner)
  - Jobs (HumanizeJob/PlagiarismJob/AutoCiteJob/Document tables filtered by owner)

  Actions: Add Credit (modal), Set Plan, Set Role **[SA]**, Deactivate **[SA]**.
- **Documents list/detail** — title, owner, createdAt, size; detail shows preview + delete **[SA]**.
- **Humanize / Plagiarism / AutoCite list/detail** — same shape; filters: status, owner, dateRange. Detail: input, output, iterations, tokenUsage, status, timestamps. Actions: Cancel, Retry **[SA]**, Delete **[SA]**.
- **Credits list** — cols: createdAt, owner, direction, amount, status, orderType, description. Read-only.
- **Announcements list/edit [SA]** — list with inline enable toggle. Edit: title, content (textarea, markdown), audience, enabled, start/end. Public banner component added to workspace layout consuming `/api/announcements/active`.
- **AI Providers [SA]** — table: provider, name, defaultModel, enabled, order. Edit modal: provider, name, baseUrl, apiKey (write-only — placeholder shows "set" / "unset"), defaultModel, enabled, order. Drag-to-reorder via `@dnd-kit`.

### Form pattern

All create/edit forms: `react-hook-form` + `@hookform/resolvers/zod`, mutate via `axios`, on success call SWR `mutate()` and toast via `react-toastify`.

## Error handling

- Admin routes throw existing app errors (`packages/error`). 401 from auth middleware, 403 from `requireAdmin`/`requireSuperAdmin`, 404 from `findById` misses, 422 on zod validation fail, 500 fallback.
- Frontend axios interceptor: 403 on `/api/admin/*` → toast "Forbidden" + redirect `/`. 401 → existing auth redirect.
- Destructive mutations always go through `ConfirmDialog`. Non-destructive mutations show inline toast.

## Audit logging

Every admin mutation writes a structured log line:

```json
{ "adminId", "adminEmail", "action", "target", "targetId", "before", "after", "ts" }
```

Uses dothesis's existing logger if present; otherwise `console.info(JSON.stringify(...))` for v1. No separate audit collection in v1.

## Testing

- **Backend:** integration tests under `backend/tests/admin/` per section. Each seeds a non-admin user, an admin user, and a super-admin user, then verifies route gating (403/200) and happy-path behavior. Conforms to whatever harness `backend/tests` already uses.
- **Frontend:** smoke tests for the layout gate (non-admin redirected) and one list/detail flow per section type. Unit-level testing of admin tables not in v1.

## Implementation order (incremental rollout)

Each step lands as its own verified slice.

1. **Foundation** — install frontend deps, port `ACL` + `SUPER_ADMIN_EMAILS`, add admin middlewares, set up `/api/admin/*` mount, create `app/admin/` route group + layout/sidebar, expose `is_admin`/`is_super_admin` on `secureRelease`.
2. **Users** — list, detail, add credit, role/plan/deactivate.
3. **Credit transactions** — read-only list.
4. **HumanizeJob admin** — list + detail + cancel/retry/delete (template for the other three job sections).
5. **Document, PlagiarismJob, AutoCiteJob admin** — applying the HumanizeJob template.
6. **System announcements** — CRUD + public banner endpoint + workspace banner.
7. **AI provider config** — model + CRUD + service integration with env-var fallback.

After each step: backend integration tests pass, frontend smoke flow works, deployed-or-deployable.
