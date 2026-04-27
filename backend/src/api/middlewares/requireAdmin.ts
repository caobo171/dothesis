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
