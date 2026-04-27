// backend/src/constants/admin.ts
//
// SUPER_ADMIN_EMAILS — hardcoded fallback list of super admin emails.
// Override at runtime via process.env.SUPER_ADMIN_EMAILS (comma-separated)
// so prod/dev can differ without code changes.

// Entries MUST be lowercase — ACL.isSuperAdmin compares user.email.toLowerCase()
// against this list. Lowercase at declaration so the invariant is visible here,
// not hidden inside the export expression.
const FALLBACK_SUPER_ADMIN_EMAILS: string[] = [
  'cao.nv17@gmail.com',
];

const fromEnv = (process.env.SUPER_ADMIN_EMAILS || '')
  .split(',')
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

export const SUPER_ADMIN_EMAILS: string[] =
  fromEnv.length ? fromEnv : FALLBACK_SUPER_ADMIN_EMAILS;
