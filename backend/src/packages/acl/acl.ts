// backend/src/packages/acl/acl.ts
//
// ACL — central place for role checks.
// isSuperAdmin: email is in SUPER_ADMIN_EMAILS.
// isAdmin: user.role === 'Admin', or super admin (super admin implies admin).
//
// `import type { User }` is required: Task 3 imports ACL from inside User.ts,
// so a value-level User import here would create a circular runtime dependency.
// User is only used as a type token (in MaybeUser), so the type-only import is sufficient.

import type { DocumentType } from '@typegoose/typegoose';
import type { User } from '@/models/User';
import { Roles } from '@/Constants';
import { SUPER_ADMIN_EMAILS } from '@/constants/admin';

type MaybeUser = DocumentType<User> | User | null | undefined;

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
