// backend/src/api/routes/admin/user.ts
//
// Admin user management routes. All routes follow the project convention:
// POST under /api/admin/users/*, body contains access_token (consumed by
// passport-jwt) and the admin's filter/payload fields.
//
// Gating:
//   - Every route here is wrapped at mount time with passport.authenticate('jwt')
//     and requireAdmin (see admin/index.ts). Super-admin-only mutations are
//     individually wrapped with requireSuperAdmin per-route below.
//
// List response shape: { code, data: { items, total, page, limit } }.
// Detail response shape: { code, data: <user with counts/totals> }.

import { Router } from 'express';
import passport from 'passport';
import { Code, CreditDirection, Roles } from '@/Constants';
import { UserModel } from '@/models/User';
import { CreditModel } from '@/models/Credit';
import { DocumentModel } from '@/models/Document';
import { HumanizeJobModel } from '@/models/HumanizeJob';
import { PlagiarismJobModel } from '@/models/PlagiarismJob';
import { AutoCiteJobModel } from '@/models/AutoCiteJob';
import { CreditService } from '@/services/credit.service';
import { requireAdmin } from '@/api/middlewares/requireAdmin';
import { requireSuperAdmin } from '@/api/middlewares/requireSuperAdmin';

const auth = passport.authenticate('jwt', { session: false });

export default () => {
  const router = Router();

  // ── List users ───────────────────────────────────────────────────────────
  // Body: { q?, role?, plan?, emailVerified?, disabled?, page?, limit? }
  // q matches username, fullName, or email (case-insensitive substring).
  router.post('/users', auth, requireAdmin, async (req, res) => {
    const { q, role, plan, emailVerified, disabled, page = 1, limit = 25 } = req.body || {};
    const pageNum = Math.max(1, parseInt(String(page), 10) || 1);
    const limitNum = Math.min(100, Math.max(1, parseInt(String(limit), 10) || 25));

    const filter: any = {};
    if (role) filter.role = role;
    if (plan) filter.plan = plan;
    if (typeof emailVerified === 'boolean' || emailVerified === 'true' || emailVerified === 'false') {
      filter.emailVerified = emailVerified === true || emailVerified === 'true';
    }
    if (typeof disabled === 'boolean' || disabled === 'true' || disabled === 'false') {
      filter.disabled = disabled === true || disabled === 'true';
    }
    if (q && typeof q === 'string' && q.trim()) {
      // Escape regex special chars so an admin searching for "."  or "@"
      // doesn't end up running an unintended pattern.
      const safe = q.trim().replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const rx = new RegExp(safe, 'i');
      filter.$or = [{ username: rx }, { fullName: rx }, { email: rx }];
    }

    const [total, docs] = await Promise.all([
      UserModel.countDocuments(filter),
      UserModel.find(filter).sort({ createdAt: -1 }).skip((pageNum - 1) * limitNum).limit(limitNum),
    ]);

    return res.json({
      code: Code.Success,
      data: {
        items: docs.map((d) => d.secureRelease()),
        total,
        page: pageNum,
        limit: limitNum,
      },
    });
  });

  // ── User detail ──────────────────────────────────────────────────────────
  // Body: { id }
  // Adds aggregate counts so the detail page can render a snapshot without
  // fetching each section independently.
  router.post('/users/get', auth, requireAdmin, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });

    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    const ownerId = user._id.toString();
    const [
      documentCount,
      humanizeCount,
      plagiarismCount,
      autoCiteCount,
      creditInbound,
      creditOutbound,
    ] = await Promise.all([
      DocumentModel.countDocuments({ owner: ownerId }),
      HumanizeJobModel.countDocuments({ owner: ownerId }),
      PlagiarismJobModel.countDocuments({ owner: ownerId }),
      AutoCiteJobModel.countDocuments({ owner: ownerId }),
      CreditModel.aggregate([
        { $match: { owner: ownerId, direction: CreditDirection.Inbound } },
        { $group: { _id: null, total: { $sum: '$amount' } } },
      ]),
      CreditModel.aggregate([
        { $match: { owner: ownerId, direction: CreditDirection.Outbound } },
        { $group: { _id: null, total: { $sum: '$amount' } } },
      ]),
    ]);

    return res.json({
      code: Code.Success,
      data: {
        ...user.secureRelease(),
        counts: {
          documents: documentCount,
          humanize: humanizeCount,
          plagiarism: plagiarismCount,
          autocite: autoCiteCount,
        },
        creditTotals: {
          inbound: creditInbound[0]?.total || 0,
          outbound: creditOutbound[0]?.total || 0,
        },
      },
    });
  });

  // ── Add credit (admin grant) ─────────────────────────────────────────────
  // Body: { id, amount, description }
  // Writes via CreditService so the inbound transaction is recorded in the
  // credits collection (same path as Stripe purchase).
  router.post('/users/credit', auth, requireAdmin, async (req, res) => {
    const { id, amount, description } = req.body || {};
    const numericAmount = Number(amount);
    if (!id || !numericAmount || numericAmount <= 0) {
      return res.json({ code: Code.InvalidInput, message: 'id and positive amount required' });
    }
    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    const adminEmail = (req.user as any)?.email || 'unknown';
    await CreditService.addCredits(
      id,
      numericAmount,
      description || `admin grant by ${adminEmail}`,
      'admin_grant',
      adminEmail
    );

    const updated = await UserModel.findById(id);
    return res.json({ code: Code.Success, data: updated?.secureRelease() });
  });

  // ── Update plan ──────────────────────────────────────────────────────────
  // Body: { id, plan }
  router.post('/users/plan', auth, requireAdmin, async (req, res) => {
    const { id, plan } = req.body || {};
    if (!id || !plan) return res.json({ code: Code.InvalidInput, message: 'id and plan required' });

    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    user.plan = String(plan);
    await user.save();
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });

  // ── Update role [SA] ─────────────────────────────────────────────────────
  // Body: { id, role }
  // Only super admin can promote/demote — prevents an admin-level account
  // from elevating itself further.
  router.post('/users/role', auth, requireAdmin, requireSuperAdmin, async (req, res) => {
    const { id, role } = req.body || {};
    if (!id || !role) return res.json({ code: Code.InvalidInput, message: 'id and role required' });
    if (role !== Roles.User && role !== Roles.Admin) {
      return res.json({ code: Code.InvalidInput, message: 'invalid role' });
    }

    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    user.role = role;
    await user.save();
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });

  // ── Deactivate (soft) [SA] ───────────────────────────────────────────────
  // Body: { id }
  // Sets disabled=true. Existing JWTs continue to be valid until revoked at
  // the auth layer — that revocation is out of scope for this slice.
  router.post('/users/deactivate', auth, requireAdmin, requireSuperAdmin, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });

    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    user.disabled = true;
    await user.save();
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });

  // ── Re-activate [SA] ─────────────────────────────────────────────────────
  router.post('/users/activate', auth, requireAdmin, requireSuperAdmin, async (req, res) => {
    const { id } = req.body || {};
    if (!id) return res.json({ code: Code.InvalidInput, message: 'id required' });

    const user = await UserModel.findById(id);
    if (!user) return res.json({ code: Code.NotFound, message: 'user not found' });

    user.disabled = false;
    await user.save();
    return res.json({ code: Code.Success, data: user.secureRelease() });
  });

  return router;
};
