// backend/src/constants/admin.ts
//
// SUPER_ADMIN_EMAILS — hardcoded fallback list of super admin emails.
// Override at runtime via process.env.SUPER_ADMIN_EMAILS (comma-separated)
// so prod/dev can differ without code changes.

// Entries should be lowercase. The runtime .map(toLowerCase) below is defense-in-depth
// in case a future edit introduces a mixed-case entry.
const FALLBACK_SUPER_ADMIN_EMAILS: string[] = [
  'cao.nv17@gmail.com',
  'cao.nguyen1701@gmail.com'
];

const fromEnv = (process.env.SUPER_ADMIN_EMAILS || '')
  .split(',')
  .map((s) => s.trim().toLowerCase())
  .filter(Boolean);

export const SUPER_ADMIN_EMAILS: string[] =
  fromEnv.length ? fromEnv : FALLBACK_SUPER_ADMIN_EMAILS.map((e) => e.toLowerCase());
