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
