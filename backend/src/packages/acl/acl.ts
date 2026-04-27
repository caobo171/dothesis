// backend/src/packages/acl/acl.ts
//
// ACL — central place for role checks. Mirrors the pattern used by a sibling
// admin codebase. isSuperAdmin: email is in SUPER_ADMIN_EMAILS.
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
