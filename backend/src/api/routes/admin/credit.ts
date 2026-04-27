// backend/src/api/routes/admin/credit.ts
//
// Admin credit transactions — read-only. The only mutation path for credits
// remains the user-grant action under /admin/users/credit (slice 2). This
// section just exposes the transactions table for auditing.
//
// Filters: owner (user id), direction (inbound|outbound), status, orderType,
// dateFrom / dateTo (ISO date strings). All optional.

import { Router } from 'express';
import passport from 'passport';
import { Code } from '@/Constants';
import { CreditModel } from '@/models/Credit';
import { UserModel } from '@/models/User';
import { requireAdmin } from '@/api/middlewares/requireAdmin';

const auth = passport.authenticate('jwt', { session: false });

export default () => {
  const router = Router();

  router.post('/credits', auth, requireAdmin, async (req, res) => {
    const {
      owner,
      direction,
      status,
      orderType,
      dateFrom,
      dateTo,
      page = 1,
      limit = 25,
    } = req.body || {};

    const pageNum = Math.max(1, parseInt(String(page), 10) || 1);
    const limitNum = Math.min(100, Math.max(1, parseInt(String(limit), 10) || 25));

    const filter: any = {};
    if (owner) filter.owner = String(owner);
    if (direction) filter.direction = String(direction);
    if (status) filter.status = String(status);
    if (orderType) filter.orderType = String(orderType);
    if (dateFrom || dateTo) {
      filter.createdAt = {};
      if (dateFrom) filter.createdAt.$gte = new Date(String(dateFrom));
      if (dateTo) filter.createdAt.$lte = new Date(String(dateTo));
    }

    const [total, docs] = await Promise.all([
      CreditModel.countDocuments(filter),
      CreditModel.find(filter).sort({ createdAt: -1 }).skip((pageNum - 1) * limitNum).limit(limitNum),
    ]);

    // Resolve owner emails in one batch so the table can show a label without
    // forcing the frontend to fetch each user separately.
    const ownerIds = Array.from(new Set(docs.map((d) => d.owner).filter(Boolean)));
    const ownersMap: Record<string, { email: string; username: string }> = {};
    if (ownerIds.length) {
      const owners = await UserModel.find({ _id: { $in: ownerIds } });
      for (const u of owners) {
        ownersMap[u._id.toString()] = { email: u.email, username: u.username };
      }
    }

    return res.json({
      code: Code.Success,
      data: {
        items: docs.map((d) => ({
          ...d.secureRelease(),
          ownerInfo: ownersMap[d.owner] || null,
        })),
        total,
        page: pageNum,
        limit: limitNum,
      },
    });
  });

  return router;
};
