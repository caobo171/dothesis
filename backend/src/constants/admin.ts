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
